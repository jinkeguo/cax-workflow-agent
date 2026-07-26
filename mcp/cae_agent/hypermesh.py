from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .result import ToolResult

HM_EXECUTABLE_ENV = "CAE_HM_EXECUTABLE"
ABAQUS_TEMPLATE_ENV = "CAE_ABAQUS_TEMPLATE"


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        key = str(resolved).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def _hypermesh_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get(HM_EXECUTABLE_ENV)
    if explicit:
        candidates.append(Path(explicit))
    for command in ("hmopengl.exe", "hmopengl"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))

    roots: list[Path] = []
    for variable in ("ALTAIR_HOME", "HW_ROOT"):
        value = os.environ.get(variable)
        if value:
            roots.append(Path(value))
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable)
        if value:
            roots.append(Path(value) / "Altair")
    roots.append(Path("/opt/altair"))

    patterns = (
        "hwdesktop/hw/bin/win64/hmopengl.exe",
        "hwdesktop/hw/bin/linux64/hmopengl",
        "*/hwdesktop/hw/bin/win64/hmopengl.exe",
        "*/hwdesktop/hw/bin/linux64/hmopengl",
    )
    for root in roots:
        for pattern in patterns:
            candidates.extend(root.glob(pattern))
    return _unique_paths(candidates)


def discover_hypermesh_executable() -> Path | None:
    return next((path for path in _hypermesh_candidates() if path.is_file()), None)


def _derived_template(executable: Path | None) -> Path | None:
    if executable is None:
        return None
    hwdesktop = next(
        (parent for parent in executable.parents if parent.name.casefold() == "hwdesktop"),
        None,
    )
    if hwdesktop is None:
        return None
    return hwdesktop / "templates" / "feoutput" / "abaqus" / "standard.3d"


def _template_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get(ABAQUS_TEMPLATE_ENV)
    if explicit:
        candidates.append(Path(explicit))
    derived = _derived_template(discover_hypermesh_executable())
    if derived:
        candidates.append(derived)
    for executable in _hypermesh_candidates():
        candidate = _derived_template(executable)
        if candidate:
            candidates.append(candidate)
    return _unique_paths(candidates)


def discover_abaqus_template() -> Path | None:
    return next((path for path in _template_candidates() if path.is_file()), None)


def hypermesh_installation_status() -> dict[str, Any]:
    executable = discover_hypermesh_executable()
    template = discover_abaqus_template()
    return {
        "executable": str(executable) if executable else None,
        "executable_exists": executable is not None,
        "executable_candidates": [str(path) for path in _hypermesh_candidates()],
        "abaqus_template": str(template) if template else None,
        "abaqus_template_exists": template is not None,
        "abaqus_template_candidates": [str(path) for path in _template_candidates()],
        "configuration": {
            "executable_env": HM_EXECUTABLE_ENV,
            "template_env": ABAQUS_TEMPLATE_ENV,
        },
    }


def _tcl_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if "}" in value:
        raise ValueError("Paths containing '}' are not supported by the Tcl adapter")
    return "{" + value + "}"


def _executable() -> Path:
    executable = discover_hypermesh_executable()
    if executable is None:
        candidates = ", ".join(str(path) for path in _hypermesh_candidates()) or "<none>"
        raise FileNotFoundError(
            f"HyperMesh executable was not found. Set {HM_EXECUTABLE_ENV}. "
            f"Candidates checked: {candidates}"
        )
    return executable


def _template() -> Path:
    template = discover_abaqus_template()
    if template is None:
        candidates = ", ".join(str(path) for path in _template_candidates()) or "<none>"
        raise FileNotFoundError(
            f"HyperMesh Abaqus export template was not found. Set {ABAQUS_TEMPLATE_ENV}. "
            f"Candidates checked: {candidates}"
        )
    return template


def _run_hypermesh(script: str, timeout_seconds: int) -> tuple[subprocess.CompletedProcess[str], Path]:
    executable = _executable()
    run_root = Path(
        tempfile.mkdtemp(prefix="cae-hm-", dir=os.environ.get("CAE_RUN_ROOT"))
    ).resolve()
    script_path = run_root / "operation.tcl"
    script_path.write_text(script, encoding="utf-8")
    try:
        completed = subprocess.run(
            [str(executable), "-batch", "-tcl", str(script_path)],
            cwd=run_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        (run_root / "stdout.log").write_text(exc.stdout or "", encoding="utf-8")
        (run_root / "stderr.log").write_text(exc.stderr or "", encoding="utf-8")
        raise TimeoutError(
            f"HyperMesh exceeded {timeout_seconds}s; logs retained at {run_root}"
        ) from exc
    (run_root / "stdout.log").write_text(completed.stdout or "", encoding="utf-8")
    (run_root / "stderr.log").write_text(completed.stderr or "", encoding="utf-8")
    return completed, run_root


def _parse_inspection_report(path: Path) -> dict:
    components: list[dict] = []
    types: dict[str, int] = {}
    configurations: dict[str, int] = {}
    solver_types: dict[str, int] = {}
    summary: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = raw.split("\t")
        if fields[0] == "COMPONENT" and len(fields) >= 6:
            components.append(
                {
                    "id": int(fields[1]),
                    "name": fields[2],
                    "elements": int(fields[3]),
                    "solids": int(fields[4]),
                    "surfaces": int(fields[5]),
                }
            )
        elif fields[0] == "TYPE" and len(fields) >= 3:
            types[fields[1] or "<empty>"] = int(fields[2])
        elif fields[0] == "CONFIG" and len(fields) >= 3:
            configurations[fields[1]] = int(fields[2])
        elif fields[0] == "SOLVER_TYPE" and len(fields) >= 3:
            solver_types[fields[1]] = int(fields[2])
        elif fields[0] == "SUMMARY" and len(fields) >= 3:
            summary[fields[1].lower()] = int(fields[2])
    return {
        "summary": summary,
        "components": components,
        "element_type_names": types,
        "element_configurations": configurations,
        "solver_types": solver_types,
    }


def inspect_hm_model(input_path: str, timeout_seconds: int = 60) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"HyperMesh model does not exist: {source}")
    report_name = "inspection.tsv"
    script = f"""*readfile {_tcl_path(source)} 0
set report [open {{{report_name}}} w]
*createmark components 1 all
set comps [hm_getmark components 1]
foreach cid $comps {{
    set cname [hm_getvalue components id=$cid dataname=name]
    *createmark elements 1 "by collector id" $cid
    set nelems [llength [hm_getmark elements 1]]
    *createmark solids 1 "by collector id" $cid
    set nsolids [llength [hm_getmark solids 1]]
    *createmark surfaces 1 "by collector id" $cid
    set nsurfs [llength [hm_getmark surfaces 1]]
    puts $report "COMPONENT\\t$cid\\t$cname\\t$nelems\\t$nsolids\\t$nsurfs"
}}
*createmark elements 1 all
set elems [hm_getmark elements 1]
array set types {{}}
array set configs {{}}
array set solverTypes {{}}
foreach eid $elems {{
    set etype [hm_getvalue elements id=$eid dataname=typename]
    set config [hm_getvalue elements id=$eid dataname=config]
    set solverType [hm_getvalue elements id=$eid dataname=type]
    if {{![info exists types($etype)]}} {{set types($etype) 0}}
    if {{![info exists configs($config)]}} {{set configs($config) 0}}
    if {{![info exists solverTypes($solverType)]}} {{set solverTypes($solverType) 0}}
    incr types($etype)
    incr configs($config)
    incr solverTypes($solverType)
}}
foreach etype [lsort [array names types]] {{
    puts $report "TYPE\\t$etype\\t$types($etype)"
}}
foreach config [lsort [array names configs]] {{
    puts $report "CONFIG\\t$config\\t$configs($config)"
}}
foreach solverType [lsort [array names solverTypes]] {{
    puts $report "SOLVER_TYPE\\t$solverType\\t$solverTypes($solverType)"
}}
puts $report "SUMMARY\\tcomponents\\t[llength $comps]"
puts $report "SUMMARY\\telements\\t[llength $elems]"
*createmark nodes 1 all
puts $report "SUMMARY\\tnodes\\t[llength [hm_getmark nodes 1]]"
*createmark solids 1 all
puts $report "SUMMARY\\tsolids\\t[llength [hm_getmark solids 1]]"
*createmark surfaces 1 all
puts $report "SUMMARY\\tsurfaces\\t[llength [hm_getmark surfaces 1]]"
close $report
*quit 1
"""
    try:
        completed, run_root = _run_hypermesh(script, timeout_seconds)
        report = run_root / report_name
        logs = [str(run_root / "stdout.log"), str(run_root / "stderr.log")]
        if completed.returncode != 0 or not report.is_file():
            return ToolResult(
                status="failed",
                logs=logs,
                error=f"HyperMesh inspection failed with exit code {completed.returncode}",
                application={"name": "Altair HyperMesh", "version": "2025"},
                elapsed_seconds=time.monotonic() - started,
            )
        return ToolResult(
            status="succeeded",
            artifacts=[
                {"path": str(source), "role": "inspected-hypermesh-model"},
                {"path": str(report), "role": "inspection-report"},
            ],
            checks=_parse_inspection_report(report),
            logs=logs,
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )


def export_abaqus_deck(
    input_path: str,
    output_path: str,
    overwrite: bool = False,
    timeout_seconds: int = 120,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"HyperMesh model does not exist: {source}")
    if target.exists() and not overwrite:
        return ToolResult(status="needs_input", error=f"Output already exists: {target}")
    temporary_name = "export.inp"
    try:
        template = _template()
        script = f"""*readfile {_tcl_path(source)} 0
*templatefileset {_tcl_path(template)}
*feoutputmergeincludefiles 0
hm_answernext yes
*feoutputwithdata {_tcl_path(template)} {{{temporary_name}}} 0 0 2 1 6
*quit 1
"""
        completed, run_root = _run_hypermesh(script, timeout_seconds)
        temporary = run_root / temporary_name
        logs = [str(run_root / "stdout.log"), str(run_root / "stderr.log")]
        if completed.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            return ToolResult(
                status="failed",
                logs=logs,
                error=f"HyperMesh export failed with exit code {completed.returncode}",
                application={"name": "Altair HyperMesh", "version": "2025"},
                elapsed_seconds=time.monotonic() - started,
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(target.name + ".tmp")
        shutil.copy2(temporary, staging)
        if target.exists():
            target.unlink()
        shutil.move(str(staging), str(target))
        return ToolResult(
            status="succeeded",
            artifacts=[{"path": str(target), "role": "abaqus-solver-deck"}],
            checks={"bytes": target.stat().st_size},
            logs=logs,
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )


def _validate_positive_ids(values: list[int], label: str) -> list[int]:
    if not values:
        raise ValueError(f"{label} must contain at least one ID")
    normalized = sorted(set(int(value) for value in values))
    if any(value <= 0 for value in normalized):
        raise ValueError(f"{label} must contain positive integer IDs")
    return normalized


def _atomic_copy(source: Path, target: Path, overwrite: bool) -> None:
    if target.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".tmp")
    shutil.copy2(source, staging)
    if target.exists():
        target.unlink()
    shutil.move(str(staging), str(target))


def mesh_hm_solids(
    input_path: str,
    output_path: str,
    solid_ids: list[int],
    element_size: float,
    source_element_type: str = "quad",
    overwrite: bool = False,
    confirm_mesh: bool = False,
    timeout_seconds: int = 600,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"HyperMesh model does not exist: {source}")
    try:
        ids = _validate_positive_ids(solid_ids, "solid_ids")
        if element_size <= 0:
            raise ValueError("element_size must be greater than zero")
        element_types = {"tria": 0, "quad": 512, "mixed": 1024}
        if source_element_type not in element_types:
            raise ValueError("source_element_type must be tria, quad, or mixed")
        if target.exists() and not overwrite:
            return ToolResult(status="needs_input", error=f"Output already exists: {target}")
        if not confirm_mesh:
            return ToolResult(
                status="needs_confirmation",
                artifacts=[{"path": str(source), "role": "proposed-hypermesh-input"}],
                checks={
                    "operation": "solidmap-selected-solids",
                    "solid_ids": ids,
                    "element_size": element_size,
                    "source_element_type": source_element_type,
                    "output_path": str(target),
                    "overwrite": overwrite,
                    "method": "HyperMesh multi-solid mapping with automatic source/target selection",
                },
                warnings=[
                    "Solid mapping replaces existing solid elements on selected solids. "
                    "Set confirm_mesh=true only after reviewing the selection and mesh policy."
                ],
                application={"name": "Altair HyperMesh", "version": "2025"},
                elapsed_seconds=time.monotonic() - started,
            )
        id_text = " ".join(str(value) for value in ids)
        report_name = "solidmap-report.tsv"
        output_name = "meshed.hm"
        element_type = element_types[source_element_type]
        script = f"""*readfile {_tcl_path(source)} 0
set report [open {{{report_name}}} w]
*createmark solids 1 {id_text}
set selected [hm_getmark solids 1]
puts $report "REQUESTED\\t{len(ids)}"
puts $report "SELECTED\\t[llength $selected]"
if {{[llength $selected] != {len(ids)}}} {{
    puts $report "STATUS\\tfailed"
    puts $report "ERROR\\tOne or more solid IDs were not found"
    close $report
    exit 2
}}
*createmark elements 1 all
set before [llength [hm_getmark elements 1]]
set occupied {{}}
set selectedComponents {{}}
foreach solidId $selected {{
    set componentId [hm_getvalue solids id=$solidId dataname=collector.id]
    lappend selectedComponents $componentId
    *createmark elements 2 "by collector id" $componentId
    set componentElementCount [llength [hm_getmark elements 2]]
    if {{$componentElementCount > 0}} {{
        lappend occupied "$solidId:$componentId:$componentElementCount"
    }}
}}
if {{[llength $occupied] > 0}} {{
    puts $report "STATUS\\tblocked-existing-elements"
    puts $report "OCCUPIED_SOLIDS\\t[join $occupied ,]"
    puts $report "ERROR\\tSelected solid components already contain elements"
    close $report
    exit 3
}}
set meshError ""
set meshStage "begin-solid-map"
if {{[catch {{
    *createmark solids 1 {id_text}
    *solidmap_solids_begin 1 {element_type} {element_size:.12g}
    set meshStage "generate-solid-map"
    *solidmap_solids_end
    set meshStage "assign-C3D8R"
    *elementtype 208 7
    foreach componentId $selectedComponents {{
        *createmark elements 1 "by collector id" $componentId
        *elementsettypes 1
    }}
}} meshError]}} {{
    puts $report "STATUS\\tfailed"
    puts $report "STAGE\\t$meshStage"
    puts $report "ERROR\\t$meshError"
    close $report
    exit 2
}}
*createmark elements 1 all
set after [llength [hm_getmark elements 1]]
puts $report "STATUS\\tsucceeded"
puts $report "ELEMENTS_BEFORE\\t$before"
puts $report "ELEMENTS_AFTER\\t$after"
puts $report "ELEMENTS_DELTA\\t[expr {{$after - $before}}]"
puts $report "HEX8_SOLVER_TYPE\\tC3D8R"
close $report
hm_answernext yes
*writefile {{{output_name}}} 1
*quit 1
"""
        completed, run_root = _run_hypermesh(script, timeout_seconds)
        report = run_root / report_name
        generated = run_root / output_name
        logs = [str(run_root / "stdout.log"), str(run_root / "stderr.log")]
        report_text = (
            report.read_text(encoding="utf-8", errors="replace")
            if report.is_file()
            else ""
        )
        values: dict[str, Any] = {}
        for line in report_text.splitlines():
            fields = line.split("\t", 1)
            if len(fields) == 2:
                key, value = fields
                values[key.lower()] = (
                    int(value) if value.lstrip("-").isdigit() else value
                )
        succeeded = (
            completed.returncode == 0
            and generated.is_file()
            and generated.stat().st_size > 0
            and values.get("status") == "succeeded"
        )
        if not succeeded:
            blocked = values.get("status") == "blocked-existing-elements"
            return ToolResult(
                status="needs_input" if blocked else "failed",
                artifacts=[
                    {"path": str(run_root), "role": "failed-solidmap-run-directory"}
                ],
                checks=values,
                logs=logs,
                error=(
                    (
                        "Selected solids already have elements in their owning "
                        "components. Delete or move the existing mesh in a reviewed "
                        "derived model before remeshing; automatic duplication is "
                        "intentionally blocked."
                    )
                    if blocked
                    else values.get("error")
                    or f"HyperMesh solid mapping failed with exit code {completed.returncode}"
                ),
                application={"name": "Altair HyperMesh", "version": "2025"},
                elapsed_seconds=time.monotonic() - started,
            )
        _atomic_copy(generated, target, overwrite)
        return ToolResult(
            status="succeeded",
            artifacts=[
                {"path": str(target), "role": "meshed-hypermesh-model"},
                {"path": str(report), "role": "solidmap-report"},
            ],
            checks=values,
            logs=logs,
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )


def check_hm_mesh_quality(
    input_path: str,
    jacobian_min: float = 0.6,
    aspect_max: float = 5.0,
    min_length: float = 0.0,
    timeout_seconds: int = 120,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"HyperMesh model does not exist: {source}")
    if not 0 < jacobian_min <= 1:
        return ToolResult(status="failed", error="jacobian_min must be in (0, 1]")
    if aspect_max <= 1:
        return ToolResult(status="failed", error="aspect_max must be greater than 1")
    if min_length < 0:
        return ToolResult(status="failed", error="min_length cannot be negative")
    report_name = "mesh-quality.tsv"
    length_command = ""
    if min_length > 0:
        length_command = f"""
*createmark elements 1 all
*createmark elements 2
*elementtestlength elements 1 {min_length:.12g} 2 1 4 0 ""
set failedLength [hm_getmark elements 2]
"""
    else:
        length_command = "set failedLength {}\n"
    script = f"""*readfile {_tcl_path(source)} 0
*setelementcheckmethod "solver" 1
*createmark elements 1 all
set total [llength [hm_getmark elements 1]]
*createmark elements 2
*elementtestjacobian elements 1 {jacobian_min:.12g} 2 4 0 ""
set failedJacobian [hm_getmark elements 2]
*createmark elements 1 all
*createmark elements 2
*elementtestaspect elements 1 {aspect_max:.12g} 2 4 0 ""
set failedAspect [hm_getmark elements 2]
{length_command}
set report [open {{{report_name}}} w]
puts $report "TOTAL\\t$total"
puts $report "FAILED_JACOBIAN\\t[llength $failedJacobian]"
puts $report "FAILED_ASPECT\\t[llength $failedAspect]"
puts $report "FAILED_MIN_LENGTH\\t[llength $failedLength]"
puts $report "JACOBIAN_IDS\\t[join [lrange $failedJacobian 0 199] ,]"
puts $report "ASPECT_IDS\\t[join [lrange $failedAspect 0 199] ,]"
puts $report "MIN_LENGTH_IDS\\t[join [lrange $failedLength 0 199] ,]"
close $report
*quit 1
"""
    try:
        completed, run_root = _run_hypermesh(script, timeout_seconds)
        report = run_root / report_name
        logs = [str(run_root / "stdout.log"), str(run_root / "stderr.log")]
        if completed.returncode != 0 or not report.is_file():
            return ToolResult(
                status="failed",
                artifacts=[{"path": str(run_root), "role": "failed-quality-run-directory"}],
                logs=logs,
                error=f"HyperMesh quality check failed with exit code {completed.returncode}",
                application={"name": "Altair HyperMesh", "version": "2025"},
                elapsed_seconds=time.monotonic() - started,
            )
        values: dict[str, Any] = {}
        for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
            key, value = line.split("\t", 1)
            values[key.lower()] = int(value) if value.isdigit() else value
        failed_total = (
            int(values.get("failed_jacobian", 0))
            + int(values.get("failed_aspect", 0))
            + int(values.get("failed_min_length", 0))
        )
        values.update(
            {
                "jacobian_min": jacobian_min,
                "aspect_max": aspect_max,
                "min_length": min_length,
                "failed_total_nonunique": failed_total,
            }
        )
        return ToolResult(
            status="succeeded",
            artifacts=[
                {"path": str(source), "role": "checked-hypermesh-model"},
                {"path": str(report), "role": "mesh-quality-report"},
            ],
            checks=values,
            warnings=(
                ["One or more 3D quality criteria failed; inspect the reported IDs."]
                if failed_total
                else []
            ),
            logs=logs,
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )


def smooth_hm_solid_mesh(
    input_path: str,
    output_path: str,
    element_ids: list[int],
    iterations: int = 5,
    overwrite: bool = False,
    confirm_repair: bool = False,
    timeout_seconds: int = 180,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"HyperMesh model does not exist: {source}")
    try:
        ids = _validate_positive_ids(element_ids, "element_ids")
        if not 1 <= iterations <= 50:
            raise ValueError("iterations must be between 1 and 50")
        if target.exists() and not overwrite:
            return ToolResult(status="needs_input", error=f"Output already exists: {target}")
        if not confirm_repair:
            return ToolResult(
                status="needs_confirmation",
                artifacts=[{"path": str(source), "role": "proposed-repair-input"}],
                checks={
                    "operation": "smooth-solid-interior-nodes",
                    "element_ids": ids,
                    "iterations": iterations,
                    "output_path": str(target),
                },
                warnings=[
                    "Smoothing changes node coordinates. Review selected elements and "
                    "rerun quality and geometry-deviation checks after repair."
                ],
                elapsed_seconds=time.monotonic() - started,
            )
        id_text = " ".join(str(value) for value in ids)
        output_name = "smoothed.hm"
        script = f"""*readfile {_tcl_path(source)} 0
*createmark elements 1 {id_text}
set selected [hm_getmark elements 1]
if {{[llength $selected] != {len(ids)}}} {{
    error "One or more element IDs were not found"
}}
*marksmoothsolids 1 {iterations}
hm_answernext yes
*writefile {{{output_name}}} 1
*quit 1
"""
        completed, run_root = _run_hypermesh(script, timeout_seconds)
        generated = run_root / output_name
        logs = [str(run_root / "stdout.log"), str(run_root / "stderr.log")]
        if completed.returncode != 0 or not generated.is_file():
            return ToolResult(
                status="failed",
                artifacts=[{"path": str(run_root), "role": "failed-smoothing-run-directory"}],
                logs=logs,
                error=f"HyperMesh solid smoothing failed with exit code {completed.returncode}",
                elapsed_seconds=time.monotonic() - started,
            )
        _atomic_copy(generated, target, overwrite)
        return ToolResult(
            status="succeeded",
            artifacts=[{"path": str(target), "role": "smoothed-hypermesh-model"}],
            checks={
                "selected_elements": len(ids),
                "iterations": iterations,
                "required_next_tool": "check_hm_mesh_quality",
            },
            logs=logs,
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            application={"name": "Altair HyperMesh", "version": "2025"},
            elapsed_seconds=time.monotonic() - started,
        )
