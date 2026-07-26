from __future__ import annotations

import json
import importlib.util
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .result import ToolResult

try:
    import winreg
except ImportError:  # pragma: no cover - SolidWorks COM is Windows-only.
    winreg = None

SUPPORTED_NATIVE = {".sldprt", ".sldasm", ".slddrw"}
SUPPORTED_EXPORT = {".step", ".stp", ".x_t", ".x_b", ".iges", ".igs"}


def _powershell_bridge_path() -> Path:
    return Path(__file__).with_name("solidworks_bridge.ps1").resolve()


def _python_bridge_path() -> Path:
    return Path(__file__).with_name("solidworks_bridge.py").resolve()


def _powershell_command() -> str:
    return os.environ.get("CAE_POWERSHELL_COMMAND", "powershell.exe")


def _run_root(prefix: str) -> Path:
    return Path(
        tempfile.mkdtemp(prefix=prefix, dir=os.environ.get("CAE_RUN_ROOT"))
    ).resolve()


def _registered_clsid() -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application\CLSID"
        ) as key:
            return str(winreg.QueryValueEx(key, None)[0])
    except OSError:
        return None


def _registered_executable() -> Path | None:
    """Return the COM LocalServer32 executable, including custom install paths."""
    clsid = _registered_clsid()
    if winreg is None or not clsid:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\LocalServer32"
        ) as key:
            command = str(winreg.QueryValueEx(key, None)[0]).strip()
    except OSError:
        return None
    if not command:
        return None
    if Path(command).is_file():
        executable = command
    elif command.startswith('"'):
        executable = command.split('"', 2)[1]
    else:
        match = re.match(r"(?i)^(.+?\.exe)(?:\s|$)", command)
        executable = match.group(1) if match else command
    return Path(executable).expanduser().resolve()


def _pywin32_available() -> bool:
    try:
        return (
            importlib.util.find_spec("pythoncom") is not None
            and importlib.util.find_spec("win32com.client.dynamic") is not None
        )
    except (ImportError, ModuleNotFoundError):
        return False


def _bridge_backend() -> str:
    configured = os.environ.get("CAE_SOLIDWORKS_BRIDGE", "").strip().lower()
    if configured:
        if configured not in {"python", "powershell"}:
            raise ValueError(
                "CAE_SOLIDWORKS_BRIDGE must be either 'python' or 'powershell'"
            )
        return configured
    return "python" if _pywin32_available() else "powershell"


def _candidate_executables() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("CAE_SOLIDWORKS_EXECUTABLE")
    if explicit:
        candidates.append(Path(explicit))
    registered = _registered_executable()
    if registered:
        candidates.append(registered)
    found = shutil.which("SLDWORKS.exe")
    if found:
        candidates.append(Path(found))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates.extend(
        [
            program_files / "SOLIDWORKS Corp" / "SOLIDWORKS" / "SLDWORKS.exe",
            program_files / "Dassault Systemes" / "SOLIDWORKS" / "SLDWORKS.exe",
        ]
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def solidworks_installation_status() -> dict[str, Any]:
    clsid = _registered_clsid()
    candidates = _candidate_executables()
    executable = next((item for item in candidates if item.is_file()), None)
    try:
        backend = _bridge_backend()
        backend_error = None
    except ValueError as exc:
        backend = None
        backend_error = str(exc)
    return {
        "com_progid": "SldWorks.Application",
        "com_registered": clsid is not None,
        "com_clsid": clsid,
        "registered_executable": (
            str(_registered_executable()) if _registered_executable() else None
        ),
        "executable": str(executable) if executable else None,
        "executable_exists": executable is not None,
        "candidate_executables": [str(item) for item in candidates],
        "bridge_backend": backend,
        "pywin32_available": _pywin32_available(),
        "runtime_available": clsid is not None and backend_error is None,
        "configuration_error": backend_error,
    }


def get_solidworks_environment() -> ToolResult:
    started = time.monotonic()
    checks = solidworks_installation_status()
    warnings: list[str] = []
    if not checks["runtime_available"]:
        warnings.append(
            "SolidWorks COM is not registered. Install desktop SolidWorks and start a new "
            "Codex task before using document operations."
        )
    return ToolResult(
        status="succeeded",
        checks=checks,
        warnings=warnings,
        application={"name": "SolidWorks adapter", "version": "0.1.0"},
        elapsed_seconds=time.monotonic() - started,
    )


def _invoke_bridge(
    request: dict[str, Any], timeout_seconds: int
) -> tuple[dict[str, Any], Path, list[str]]:
    run_root = _run_root("cae-sw-")
    request_path = run_root / "request.json"
    response_path = run_root / "response.json"
    request_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    backend = _bridge_backend()
    if backend == "python":
        command = [
            sys.executable,
            str(_python_bridge_path()),
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ]
    else:
        command = [
            _powershell_command(),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-STA",
            "-File",
            str(_powershell_bridge_path()),
            "-RequestPath",
            str(request_path),
            "-ResponsePath",
            str(response_path),
        ]
    completed = subprocess.run(
        command,
        cwd=run_root,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    stdout_log = run_root / f"solidworks-{backend}-stdout.log"
    stderr_log = run_root / f"solidworks-{backend}-stderr.log"
    stdout_log.write_text(completed.stdout or "", encoding="utf-8")
    stderr_log.write_text(completed.stderr or "", encoding="utf-8")
    if not response_path.is_file():
        raise RuntimeError(
            f"SolidWorks bridge exited {completed.returncode} without a response; "
            f"logs: {run_root}"
        )
    response = json.loads(response_path.read_text(encoding="utf-8-sig"))
    response["bridge_exit_code"] = completed.returncode
    response["bridge_backend"] = backend
    return response, run_root, [str(stdout_log), str(stderr_log)]


def test_solidworks_connection(
    visible: bool = False,
    timeout_seconds: int = 90,
) -> ToolResult:
    """Launch or attach to SolidWorks and query its revision without opening a file."""
    started = time.monotonic()
    gate = _runtime_gate(started)
    if gate:
        return gate
    try:
        response, run_root, logs = _invoke_bridge(
            {"operation": "ping", "visible": visible},
            timeout_seconds,
        )
        succeeded = response.get("status") == "succeeded"
        return ToolResult(
            status="succeeded" if succeeded else "failed",
            artifacts=[
                {
                    "path": str(run_root / "response.json"),
                    "role": "solidworks-connection-report",
                }
            ],
            checks=response.get("checks", {}),
            warnings=response.get("warnings", []),
            logs=logs,
            error=response.get("error"),
            application={
                "name": "SolidWorks",
                "version": str(response.get("solidworks_revision", "unknown")),
            },
            elapsed_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            status="failed",
            error=f"SolidWorks connection test exceeded {timeout_seconds}s.",
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def _runtime_gate(started: float) -> ToolResult | None:
    status = solidworks_installation_status()
    if status["runtime_available"]:
        return None
    return ToolResult(
        status="needs_input",
        checks=status,
        warnings=[
            "The adapter is installed, but the SolidWorks desktop COM server is unavailable."
        ],
        error="SolidWorks is not installed or its COM API is not registered.",
        application={"name": "SolidWorks adapter", "version": "0.1.0"},
        elapsed_seconds=time.monotonic() - started,
    )


def inspect_solidworks_document(
    input_path: str,
    dimension_names: list[str] | None = None,
    visible: bool = False,
    timeout_seconds: int = 120,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"SolidWorks document does not exist: {source}")
    if source.suffix.lower() not in SUPPORTED_NATIVE:
        return ToolResult(status="failed", error=f"Unsupported SolidWorks document: {source.suffix}")
    gate = _runtime_gate(started)
    if gate:
        return gate
    try:
        response, run_root, logs = _invoke_bridge(
            {
                "operation": "inspect",
                "input_path": str(source),
                "dimension_names": dimension_names or [],
                "visible": visible,
            },
            timeout_seconds,
        )
        succeeded = response.get("status") == "succeeded"
        return ToolResult(
            status="succeeded" if succeeded else "failed",
            artifacts=[
                {"path": str(source), "role": "inspected-solidworks-document"},
                {"path": str(run_root / "response.json"), "role": "solidworks-inspection-report"},
            ],
            checks=response.get("checks", {}),
            warnings=response.get("warnings", []),
            logs=logs,
            error=response.get("error"),
            application={
                "name": "SolidWorks",
                "version": str(response.get("solidworks_revision", "unknown")),
            },
            elapsed_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            status="failed",
            error=f"SolidWorks inspection exceeded {timeout_seconds}s.",
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def _validate_dimensions(dimensions_mm: dict[str, float]) -> str | None:
    if not dimensions_mm:
        return "dimensions_mm must contain at least one fully qualified dimension name"
    for name, value in dimensions_mm.items():
        if not name.strip() or "@" not in name:
            return f"Dimension name must be fully qualified, for example D1@Base-Extrude: {name!r}"
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            return f"Dimension value must be a positive finite millimetre value: {name}={value}"
    return None


def instantiate_solidworks_template(
    template_path: str,
    output_native_path: str,
    dimensions_mm: dict[str, float],
    export_path: str | None = None,
    overwrite: bool = False,
    confirm_write: bool = False,
    visible: bool = False,
    timeout_seconds: int = 180,
) -> ToolResult:
    started = time.monotonic()
    template = Path(template_path).expanduser().resolve()
    target = Path(output_native_path).expanduser().resolve()
    export_target = Path(export_path).expanduser().resolve() if export_path else None
    if not template.is_file():
        return ToolResult(status="failed", error=f"SolidWorks template does not exist: {template}")
    if template.suffix.lower() != ".sldprt":
        return ToolResult(
            status="failed",
            error="Version 0.1 template instantiation supports .SLDPRT parts only.",
        )
    if target.suffix.lower() != ".sldprt":
        return ToolResult(status="failed", error="output_native_path must end in .SLDPRT")
    if template == target:
        return ToolResult(status="failed", error="Template and output paths must differ")
    dimension_error = _validate_dimensions(dimensions_mm)
    if dimension_error:
        return ToolResult(status="failed", error=dimension_error)
    if export_target and export_target.suffix.lower() not in SUPPORTED_EXPORT:
        return ToolResult(
            status="failed",
            error=f"Unsupported neutral export extension: {export_target.suffix}",
        )
    conflicts = [str(path) for path in (target, export_target) if path and path.exists()]
    if conflicts and not overwrite:
        return ToolResult(
            status="needs_input",
            checks={"existing_outputs": conflicts},
            error="One or more outputs already exist. Approval and overwrite=true are required.",
        )
    preview = {
        "operation": "instantiate-solidworks-template",
        "template_path": str(template),
        "output_native_path": str(target),
        "export_path": str(export_target) if export_target else None,
        "dimensions_mm": dimensions_mm,
        "overwrite": overwrite,
    }
    if not confirm_write:
        return ToolResult(
            status="needs_input",
            checks={"write_preview": preview},
            warnings=["No file was changed. Set confirm_write=true after approval."],
            elapsed_seconds=time.monotonic() - started,
        )
    gate = _runtime_gate(started)
    if gate:
        gate.checks["write_preview"] = preview
        return gate

    run_root = _run_root("cae-sw-template-")
    working_native = run_root / ("working" + template.suffix)
    working_export = (
        run_root / ("export" + export_target.suffix) if export_target else None
    )
    shutil.copy2(template, working_native)
    try:
        response, bridge_root, logs = _invoke_bridge(
            {
                "operation": "parameterize",
                "input_path": str(working_native),
                "dimensions_mm": dimensions_mm,
                "export_path": str(working_export) if working_export else None,
                "visible": visible,
            },
            timeout_seconds,
        )
        if response.get("status") != "succeeded":
            return ToolResult(
                status="failed",
                artifacts=[{"path": str(run_root), "role": "failed-solidworks-staging-directory"}],
                checks=response.get("checks", {}),
                warnings=response.get("warnings", []),
                logs=logs,
                error=response.get("error", "SolidWorks template instantiation failed."),
                application={"name": "SolidWorks", "version": str(response.get("solidworks_revision", "unknown"))},
                elapsed_seconds=time.monotonic() - started,
            )
        if not working_native.is_file() or working_native.stat().st_size == 0:
            raise RuntimeError("SolidWorks did not produce a non-empty native part")
        if working_export and (
            not working_export.is_file() or working_export.stat().st_size == 0
        ):
            raise RuntimeError("SolidWorks did not produce the requested neutral export")

        target.parent.mkdir(parents=True, exist_ok=True)
        native_staging = target.with_name(target.name + ".tmp")
        shutil.copy2(working_native, native_staging)
        if target.exists():
            target.unlink()
        os.replace(native_staging, target)
        artifacts = [{"path": str(target), "role": "parameterized-solidworks-part"}]
        if export_target and working_export:
            export_target.parent.mkdir(parents=True, exist_ok=True)
            export_staging = export_target.with_name(export_target.name + ".tmp")
            shutil.copy2(working_export, export_staging)
            if export_target.exists():
                export_target.unlink()
            os.replace(export_staging, export_target)
            artifacts.append({"path": str(export_target), "role": "neutral-cad-export"})
        return ToolResult(
            status="succeeded",
            artifacts=artifacts,
            checks=response.get("checks", {}),
            warnings=response.get("warnings", []),
            logs=logs,
            application={"name": "SolidWorks", "version": str(response.get("solidworks_revision", "unknown"))},
            elapsed_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            status="failed",
            artifacts=[{"path": str(run_root), "role": "timed-out-solidworks-staging-directory"}],
            error=f"SolidWorks template instantiation exceeded {timeout_seconds}s.",
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            artifacts=[
                {"path": str(run_root), "role": "failed-solidworks-staging-directory"},
                {"path": str(bridge_root), "role": "solidworks-bridge-directory"}
                if "bridge_root" in locals()
                else {"path": str(run_root), "role": "solidworks-run-directory"},
            ],
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def export_solidworks_document(
    input_path: str,
    output_path: str,
    overwrite: bool = False,
    confirm_write: bool = False,
    visible: bool = False,
    timeout_seconds: int = 180,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"SolidWorks document does not exist: {source}")
    if source.suffix.lower() not in {".sldprt", ".sldasm"}:
        return ToolResult(status="failed", error="Only .SLDPRT and .SLDASM can be exported")
    if target.suffix.lower() not in SUPPORTED_EXPORT:
        return ToolResult(status="failed", error=f"Unsupported export extension: {target.suffix}")
    if target.exists() and not overwrite:
        return ToolResult(status="needs_input", error=f"Output already exists: {target}")
    preview = {
        "operation": "export-solidworks-document",
        "input_path": str(source),
        "output_path": str(target),
        "overwrite": overwrite,
    }
    if not confirm_write:
        return ToolResult(
            status="needs_input",
            checks={"write_preview": preview},
            warnings=["No file was changed. Set confirm_write=true after approval."],
            elapsed_seconds=time.monotonic() - started,
        )
    gate = _runtime_gate(started)
    if gate:
        gate.checks["write_preview"] = preview
        return gate
    run_root = _run_root("cae-sw-export-")
    working_export = run_root / ("export" + target.suffix)
    try:
        response, bridge_root, logs = _invoke_bridge(
            {
                "operation": "export",
                "input_path": str(source),
                "export_path": str(working_export),
                "visible": visible,
            },
            timeout_seconds,
        )
        if response.get("status") != "succeeded" or not working_export.is_file():
            return ToolResult(
                status="failed",
                artifacts=[{"path": str(bridge_root), "role": "failed-solidworks-export-directory"}],
                checks=response.get("checks", {}),
                warnings=response.get("warnings", []),
                logs=logs,
                error=response.get("error", "SolidWorks export failed."),
                elapsed_seconds=time.monotonic() - started,
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(target.name + ".tmp")
        shutil.copy2(working_export, staging)
        if target.exists():
            target.unlink()
        os.replace(staging, target)
        return ToolResult(
            status="succeeded",
            artifacts=[{"path": str(target), "role": "neutral-cad-export"}],
            checks=response.get("checks", {}),
            warnings=response.get("warnings", []),
            logs=logs,
            application={"name": "SolidWorks", "version": str(response.get("solidworks_revision", "unknown"))},
            elapsed_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            status="failed",
            artifacts=[{"path": str(run_root), "role": "timed-out-solidworks-export-directory"}],
            error=f"SolidWorks export exceeded {timeout_seconds}s.",
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            artifacts=[{"path": str(run_root), "role": "failed-solidworks-export-directory"}],
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )
