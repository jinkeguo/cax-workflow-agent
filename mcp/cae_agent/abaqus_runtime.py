from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .result import ToolResult

ABAQUS_COMMAND_ENV = "CAE_ABAQUS_COMMAND"
JOB_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
INCLUDE_RE = re.compile(r"^\s*\*INCLUDE\b", re.IGNORECASE | re.MULTILINE)
ABAQUS_ERROR_RE = re.compile(
    r"^\s*\*\*\*\s*ERROR\b"
    r"|^\s*Abaqus\s+Error:"
    r"|Abaqus/(?:Analysis|Datacheck)\s+exited\s+with\s+error",
    re.IGNORECASE | re.MULTILINE,
)
DATACHECK_COMPLETE_RE = re.compile(
    r"ANALYSIS\s+DATACHECK\s+COMPLETE", re.IGNORECASE
)
WARNING_SUMMARY_RE = re.compile(
    r"ANALYSIS\s+DATACHECK\s+COMPLETE\s+WITH\s+(\d+)\s+WARNING",
    re.IGNORECASE,
)
ANALYSIS_COMPLETE_RE = re.compile(
    r"THE ANALYSIS HAS COMPLETED SUCCESSFULLY|Abaqus\s+JOB\s+\S+\s+COMPLETED",
    re.IGNORECASE,
)
ANALYSIS_FAILED_RE = re.compile(
    r"Abaqus/Analysis exited with error|THE ANALYSIS HAS NOT BEEN COMPLETED|"
    r"Abaqus\s+Error:",
    re.IGNORECASE,
)


def _command_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get(ABAQUS_COMMAND_ENV)
    if explicit:
        candidates.append(Path(explicit))
    for name in ("abaqus.bat", "abaqus", "abq2025.bat", "abq2024.bat", "abq2023.bat"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable)
        if not value:
            continue
        commands = Path(value) / "SIMULIA" / "Commands"
        candidates.extend(commands.glob("*/abaqus.bat"))
        candidates.extend(commands.glob("*/abq*.bat"))
        candidates.extend(commands.glob("abaqus.bat"))
        candidates.extend(commands.glob("abq*.bat"))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        key = str(resolved).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def discover_abaqus_command() -> Path | None:
    return next((path for path in _command_candidates() if path.is_file()), None)


def abaqus_installation_status() -> dict:
    command = discover_abaqus_command()
    return {
        "command": str(command) if command else None,
        "command_exists": command is not None,
        "candidate_commands": [str(path) for path in _command_candidates()],
        "configuration": {"command_env": ABAQUS_COMMAND_ENV},
    }


def _command() -> Path:
    command = discover_abaqus_command()
    if command is None:
        candidates = ", ".join(str(path) for path in _command_candidates()) or "<none>"
        raise FileNotFoundError(
            f"Abaqus command was not found. Set {ABAQUS_COMMAND_ENV}. "
            f"Candidates checked: {candidates}"
        )
    return command


def _run_root(prefix: str) -> Path:
    return Path(
        tempfile.mkdtemp(prefix=prefix, dir=os.environ.get("CAE_RUN_ROOT"))
    ).resolve()


def _run(
    arguments: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    command = _command()
    if not command.is_file():
        raise FileNotFoundError(f"Abaqus command not found: {command}")
    completed = subprocess.run(
        [str(command), *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    stdout_log = cwd / "abaqus-stdout.log"
    stderr_log = cwd / "abaqus-stderr.log"
    stdout_log.write_text(completed.stdout or "", encoding="utf-8")
    stderr_log.write_text(completed.stderr or "", encoding="utf-8")
    return completed, [str(stdout_log), str(stderr_log)]


def get_abaqus_environment(timeout_seconds: int = 30) -> ToolResult:
    started = time.monotonic()
    run_root = _run_root("cae-abq-info-")
    try:
        completed, logs = _run(["information=release"], run_root, timeout_seconds)
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        version_match = re.search(r"\bAbaqus\s+(\d{4})\b", output)
        return ToolResult(
            status="succeeded" if completed.returncode == 0 else "failed",
            checks={
                "command": str(_command()),
                "command_exists": _command().is_file(),
                "release": version_match.group(1) if version_match else None,
                "exit_code": completed.returncode,
            },
            logs=logs,
            application={
                "name": "Abaqus",
                "version": version_match.group(1) if version_match else "unknown",
            },
            elapsed_seconds=time.monotonic() - started,
            error=None if completed.returncode == 0 else "Abaqus release query failed.",
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            logs=[str(run_root)],
            elapsed_seconds=time.monotonic() - started,
        )


def run_abaqus_datacheck(
    input_path: str,
    job_name: str = "cae_datacheck",
    cpus: int = 1,
    timeout_seconds: int = 300,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"Abaqus deck does not exist: {source}")
    if not JOB_RE.fullmatch(job_name):
        return ToolResult(status="failed", error=f"Invalid Abaqus job name: {job_name}")
    if not 1 <= cpus <= 64:
        return ToolResult(status="failed", error="cpus must be between 1 and 64")
    text = source.read_text(encoding="utf-8", errors="replace")
    if INCLUDE_RE.search(text):
        return ToolResult(
            status="needs_input",
            error=(
                "The input deck contains *INCLUDE. This isolated datacheck adapter "
                "requires a flattened deck to avoid losing relative include files."
            ),
        )
    run_root = _run_root("cae-abq-datacheck-")
    local_input = run_root / "model.inp"
    shutil.copy2(source, local_input)
    try:
        completed, logs = _run(
            [
                f"job={job_name}",
                "input=model.inp",
                "datacheck",
                "interactive",
                "ask_delete=OFF",
                f"cpus={cpus}",
            ],
            run_root,
            timeout_seconds,
        )
        produced = []
        for candidate in sorted(run_root.glob(f"{job_name}.*")):
            if candidate.is_file():
                produced.append({"path": str(candidate), "role": f"abaqus-{candidate.suffix[1:]}"})
        diagnostic_text = ""
        dat_text = ""
        for suffix in (".dat", ".msg", ".sta", ".log"):
            candidate = run_root / f"{job_name}{suffix}"
            if candidate.is_file():
                content = candidate.read_text(encoding="utf-8", errors="replace")
                diagnostic_text += "\n" + content
                if suffix == ".dat":
                    dat_text = content
        process_text = (completed.stdout or "") + "\n" + (completed.stderr or "")
        all_diagnostics = process_text + "\n" + diagnostic_text
        error_markers = len(ABAQUS_ERROR_RE.findall(all_diagnostics))
        dat_path = run_root / f"{job_name}.dat"
        msg_path = run_root / f"{job_name}.msg"
        dat_exists = dat_path.is_file() and dat_path.stat().st_size > 0
        msg_exists = msg_path.is_file() and msg_path.stat().st_size > 0
        completion_marker = bool(
            DATACHECK_COMPLETE_RE.search(dat_text)
            or re.search(
                rf"Abaqus\s+JOB\s+{re.escape(job_name)}\s+COMPLETED",
                process_text,
                re.IGNORECASE,
            )
        )
        warning_match = WARNING_SUMMARY_RE.search(dat_text)
        warning_messages = int(warning_match.group(1)) if warning_match else 0
        warning_markers = len(
            re.findall(r"^\s*\*\*\*\s*WARNING\b", dat_text, re.IGNORECASE | re.MULTILINE)
        )
        failure_reasons: list[str] = []
        if completed.returncode != 0:
            failure_reasons.append(f"process exit code was {completed.returncode}")
        if error_markers:
            failure_reasons.append(f"found {error_markers} Abaqus error marker(s)")
        if not dat_exists:
            failure_reasons.append("required DAT evidence was not produced")
        if not completion_marker:
            failure_reasons.append("no Abaqus datacheck completion marker was found")
        succeeded = not failure_reasons
        warnings: list[str] = []
        if warning_messages:
            warnings.append(
                f"Abaqus datacheck completed with {warning_messages} warning message(s); "
                f"inspect {dat_path}."
            )
        if "getWMI:" in all_diagnostics:
            warnings.append(
                "Abaqus could not query Windows WMI. Run the adapter with normal desktop "
                "permissions and inspect the retained stderr log."
            )
        return ToolResult(
            status="succeeded" if succeeded else "failed",
            artifacts=[
                {"path": str(source), "role": "datacheck-input-deck"},
                {"path": str(run_root), "role": "abaqus-datacheck-run-directory"},
                *produced,
            ],
            checks={
                "exit_code": completed.returncode,
                "error_markers": error_markers,
                "completion_marker": completion_marker,
                "dat_exists": dat_exists,
                "msg_exists": msg_exists,
                "warning_messages": warning_messages,
                "warning_markers": warning_markers,
                "produced_files": len(produced),
                "job_name": job_name,
                "cpus": cpus,
            },
            warnings=warnings,
            logs=logs,
            application={"name": "Abaqus", "version": "2022"},
            elapsed_seconds=time.monotonic() - started,
            error=None if succeeded else "Abaqus datacheck failed: " + "; ".join(failure_reasons),
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            status="failed",
            artifacts=[{"path": str(run_root), "role": "timed-out-datacheck-directory"}],
            error=f"Abaqus datacheck exceeded {timeout_seconds}s.",
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            artifacts=[{"path": str(run_root), "role": "failed-datacheck-directory"}],
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def inspect_abaqus_job(job_directory: str, job_name: str) -> ToolResult:
    started = time.monotonic()
    directory = Path(job_directory).expanduser().resolve()
    if not directory.is_dir():
        return ToolResult(status="failed", error=f"Job directory does not exist: {directory}")
    if not JOB_RE.fullmatch(job_name):
        return ToolResult(status="failed", error=f"Invalid Abaqus job name: {job_name}")
    extensions = (".lck", ".sta", ".msg", ".dat", ".odb", ".sim", ".log", ".prt")
    files = {suffix: directory / f"{job_name}{suffix}" for suffix in extensions}
    text = ""
    for suffix in (".sta", ".msg", ".dat", ".log"):
        if files[suffix].is_file():
            text += files[suffix].read_text(encoding="utf-8", errors="replace")
    completed = bool(ANALYSIS_COMPLETE_RE.search(text))
    failed = bool(ANALYSIS_FAILED_RE.search(text))
    running = files[".lck"].exists() and not completed and not failed
    progress_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and re.search(
            r"\b(?:increment|step time|total time|stable time increment|completed)\b",
            line,
            re.IGNORECASE,
        )
    ]
    increment_matches = re.findall(
        r"\bINCREMENT\s+(\d+)\b", text, re.IGNORECASE
    )
    warning_markers = len(
        re.findall(r"^\s*\*\*\*\s*WARNING\b", text, re.IGNORECASE | re.MULTILINE)
    )
    error_markers = len(ABAQUS_ERROR_RE.findall(text))
    status = "failed" if failed else "succeeded"
    return ToolResult(
        status=status,
        artifacts=[
            {"path": str(path), "role": f"abaqus-job-{suffix[1:]}"}
            for suffix, path in files.items()
            if path.is_file()
        ],
        checks={
            "job_state": (
                "failed" if failed else "completed" if completed else "running" if running else "unknown"
            ),
            "completed": completed,
            "failed": failed,
            "running": running,
            "odb_exists": files[".odb"].is_file(),
            "odb_bytes": files[".odb"].stat().st_size if files[".odb"].is_file() else 0,
            "last_increment": (
                int(increment_matches[-1]) if increment_matches else None
            ),
            "progress_tail": progress_lines[-20:],
            "warning_markers": warning_markers,
            "error_markers": error_markers,
        },
        application={"name": "Abaqus job inspector", "version": "0.1.0"},
        elapsed_seconds=time.monotonic() - started,
        error="Abaqus job log reports failure." if failed else None,
    )


def submit_abaqus_job(
    input_path: str,
    job_directory: str,
    job_name: str,
    cpus: int = 1,
    confirm_submit: bool = False,
    timeout_seconds: int = 60,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    directory = Path(job_directory).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"Abaqus deck does not exist: {source}")
    if not JOB_RE.fullmatch(job_name):
        return ToolResult(status="failed", error=f"Invalid Abaqus job name: {job_name}")
    if not 1 <= cpus <= 64:
        return ToolResult(status="failed", error="cpus must be between 1 and 64")
    text = source.read_text(encoding="utf-8", errors="replace")
    if INCLUDE_RE.search(text):
        return ToolResult(
            status="needs_input",
            error=(
                "The submission adapter requires a flattened input deck. Resolve "
                "*INCLUDE dependencies before submission."
            ),
        )
    command_preview = [
        str(_command()),
        f"job={job_name}",
        f"input={job_name}.inp",
        "background",
        "ask_delete=OFF",
        f"cpus={cpus}",
    ]
    if not confirm_submit:
        return ToolResult(
            status="needs_confirmation",
            artifacts=[{"path": str(source), "role": "proposed-analysis-input"}],
            checks={
                "operation": "submit_abaqus_analysis",
                "job_directory": str(directory),
                "job_name": job_name,
                "cpus": cpus,
                "command": command_preview,
                "input_bytes": source.stat().st_size,
            },
            warnings=[
                "Set confirm_submit=true only after datacheck and solve cost review."
            ],
            application={"name": "Abaqus", "version": "unknown"},
            elapsed_seconds=time.monotonic() - started,
        )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        existing = sorted(
            path for path in directory.glob(f"{job_name}.*") if path.is_file()
        )
        if existing:
            return ToolResult(
                status="needs_input",
                artifacts=[
                    {"path": str(path), "role": "existing-job-file"}
                    for path in existing
                ],
                error=(
                    f"Job files already exist for {job_name}; choose a new job name "
                    "instead of overwriting evidence."
                ),
                elapsed_seconds=time.monotonic() - started,
            )
        local_input = directory / f"{job_name}.inp"
        shutil.copy2(source, local_input)
        completed, logs = _run(
            [
                f"job={job_name}",
                f"input={local_input.name}",
                "background",
                "ask_delete=OFF",
                f"cpus={cpus}",
            ],
            directory,
            timeout_seconds,
        )
        process_text = (completed.stdout or "") + "\n" + (completed.stderr or "")
        immediate_errors = len(ABAQUS_ERROR_RE.findall(process_text))
        inspected = inspect_abaqus_job(str(directory), job_name)
        submitted = completed.returncode == 0 and immediate_errors == 0
        return ToolResult(
            status="succeeded" if submitted else "failed",
            artifacts=[
                {"path": str(local_input), "role": "submitted-analysis-input"},
                {"path": str(directory), "role": "abaqus-analysis-directory"},
                *inspected.artifacts,
            ],
            checks={
                "submission_exit_code": completed.returncode,
                "immediate_error_markers": immediate_errors,
                "job_name": job_name,
                "cpus": cpus,
                "job_state": inspected.checks.get("job_state"),
                "monitor_tool": "monitor_abaqus_job",
            },
            warnings=inspected.warnings,
            logs=logs,
            application={"name": "Abaqus", "version": "unknown"},
            elapsed_seconds=time.monotonic() - started,
            error=(
                None
                if submitted
                else "Abaqus submission failed before a valid background job was accepted."
            ),
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            status="failed",
            artifacts=[{"path": str(directory), "role": "submission-directory"}],
            error=f"Abaqus submission did not return within {timeout_seconds}s.",
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            artifacts=[{"path": str(directory), "role": "submission-directory"}],
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def monitor_abaqus_job(job_directory: str, job_name: str) -> ToolResult:
    return inspect_abaqus_job(job_directory, job_name)


def cancel_abaqus_job(
    job_directory: str,
    job_name: str,
    confirm_cancel: bool = False,
    timeout_seconds: int = 60,
) -> ToolResult:
    started = time.monotonic()
    inspected = inspect_abaqus_job(job_directory, job_name)
    if inspected.status == "failed" and not inspected.checks:
        return inspected
    state = inspected.checks.get("job_state")
    if state != "running":
        return ToolResult(
            status="needs_input",
            artifacts=inspected.artifacts,
            checks={"job_state": state},
            error=f"Only a running Abaqus job can be cancelled; current state is {state}.",
            elapsed_seconds=time.monotonic() - started,
        )
    if not confirm_cancel:
        return ToolResult(
            status="needs_confirmation",
            artifacts=inspected.artifacts,
            checks={
                "operation": "terminate_abaqus_job",
                "job_directory": str(Path(job_directory).expanduser().resolve()),
                "job_name": job_name,
                "job_state": state,
            },
            warnings=[
                "Termination may leave an incomplete ODB; set confirm_cancel=true to proceed."
            ],
            elapsed_seconds=time.monotonic() - started,
        )
    directory = Path(job_directory).expanduser().resolve()
    try:
        completed, logs = _run(
            ["terminate", f"job={job_name}"],
            directory,
            timeout_seconds,
        )
        accepted = completed.returncode == 0
        return ToolResult(
            status="succeeded" if accepted else "failed",
            artifacts=inspected.artifacts,
            checks={
                "job_name": job_name,
                "previous_state": state,
                "termination_exit_code": completed.returncode,
            },
            logs=logs,
            application={"name": "Abaqus", "version": "unknown"},
            elapsed_seconds=time.monotonic() - started,
            error=None if accepted else "Abaqus did not accept the terminate command.",
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            artifacts=inspected.artifacts,
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def retry_abaqus_job(
    job_directory: str,
    previous_job_name: str,
    new_job_name: str,
    retry_reason: str,
    cpus: int = 1,
    confirm_submit: bool = False,
    timeout_seconds: int = 60,
) -> ToolResult:
    allowed_reasons = {
        "runtime-transient",
        "license-restored",
        "user-cancelled",
    }
    if retry_reason not in allowed_reasons:
        return ToolResult(
            status="needs_input",
            error=(
                "retry_reason must be runtime-transient, license-restored, or "
                "user-cancelled. Model/convergence failures require a reviewed new deck."
            ),
        )
    previous = inspect_abaqus_job(job_directory, previous_job_name)
    if previous.checks.get("job_state") == "running":
        return ToolResult(
            status="needs_input",
            artifacts=previous.artifacts,
            error="The previous job is still running; monitor or cancel it before retrying.",
        )
    source = Path(job_directory).expanduser().resolve() / f"{previous_job_name}.inp"
    if not source.is_file():
        return ToolResult(
            status="failed",
            error=f"Previous submitted input is missing: {source}",
        )
    result = submit_abaqus_job(
        input_path=str(source),
        job_directory=job_directory,
        job_name=new_job_name,
        cpus=cpus,
        confirm_submit=confirm_submit,
        timeout_seconds=timeout_seconds,
    )
    result.checks["retry_of"] = previous_job_name
    result.checks["retry_reason"] = retry_reason
    result.checks["input_unchanged"] = True
    return result


def summarize_abaqus_odb(input_path: str, timeout_seconds: int = 120) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"ODB does not exist: {source}")
    run_root = _run_root("cae-abq-odb-")
    report = run_root / "odb-summary.json"
    script = run_root / "summarize_odb.py"
    script.write_text(
        """from __future__ import print_function
import json
from odbAccess import openOdb

odb_path = %r
report_path = %r
odb = openOdb(path=odb_path, readOnly=True)
result = {"path": odb_path, "steps": {}, "root_sets": {
    "node_sets": sorted(list(odb.rootAssembly.nodeSets.keys())),
    "element_sets": sorted(list(odb.rootAssembly.elementSets.keys()))
}, "instances": {}}
for instance_name, instance in odb.rootAssembly.instances.items():
    result["instances"][instance_name] = {
        "node_count": len(instance.nodes),
        "element_count": len(instance.elements),
        "node_label_sample": [node.label for node in instance.nodes[:20]],
        "element_label_sample": [
            element.label for element in instance.elements[:20]
        ],
        "node_sets": sorted(list(instance.nodeSets.keys())),
        "element_sets": sorted(list(instance.elementSets.keys()))
    }
for step_name, step in odb.steps.items():
    frames = []
    for index, frame in enumerate(step.frames):
        frames.append({
            "index": index,
            "frame_value": frame.frameValue,
            "description": frame.description,
            "field_outputs": sorted(list(frame.fieldOutputs.keys()))
        })
    result["steps"][step_name] = {
        "procedure": step.procedure,
        "frame_count": len(step.frames),
        "frames": frames
    }
odb.close()
with open(report_path, "w") as stream:
    json.dump(result, stream, indent=2)
""" % (str(source), str(report)),
        encoding="utf-8",
    )
    try:
        completed, logs = _run(["python", str(script)], run_root, timeout_seconds)
        if completed.returncode != 0 or not report.is_file():
            return ToolResult(
                status="failed",
                artifacts=[{"path": str(run_root), "role": "failed-odb-summary-directory"}],
                logs=logs,
                error=f"Abaqus Python ODB extraction failed with exit code {completed.returncode}.",
                application={"name": "Abaqus", "version": "2022"},
                elapsed_seconds=time.monotonic() - started,
            )
        summary = json.loads(report.read_text(encoding="utf-8"))
        return ToolResult(
            status="succeeded",
            artifacts=[
                {"path": str(source), "role": "inspected-abaqus-odb"},
                {"path": str(report), "role": "odb-summary-json"},
            ],
            checks=summary,
            logs=logs,
            application={"name": "Abaqus", "version": "2022"},
            elapsed_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            status="failed",
            artifacts=[{"path": str(run_root), "role": "timed-out-odb-summary-directory"}],
            error=f"Abaqus ODB extraction exceeded {timeout_seconds}s.",
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            artifacts=[{"path": str(run_root), "role": "failed-odb-summary-directory"}],
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )
