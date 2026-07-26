from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .abaqus_runtime import _run, _run_root
from .result import ToolResult

INVARIANTS = {
    "magnitude",
    "mises",
    "tresca",
    "press",
    "max_principal",
    "mid_principal",
    "min_principal",
    "max_inplane_principal",
    "min_inplane_principal",
    "outofplane_principal",
}

POSITIONS = {
    "nodal": "NODAL",
    "integration_point": "INTEGRATION_POINT",
    "element_nodal": "ELEMENT_NODAL",
    "centroid": "CENTROID",
}

FAILURE_FIELDS = (
    "CFAILURE",
    "MSTRS",
    "TSAIH",
    "TSAIW",
    "AZZIT",
    "MSTRN",
    "DMICRT",
    "MSTRAINCRT",
    "MSTRESSCRT",
    "TSAIWUCRT",
    "TSAIWUECRT",
    "DMIFI",
    "MSTRAINFI",
    "MSTRESSFI",
    "TSAIWUFI",
    "TSAIWUEFI",
    "HSNFTCRT",
    "HSNFCCRT",
    "HSNMTCRT",
    "HSNMCCRT",
    "DAMAGEFT",
    "DAMAGEFC",
    "DAMAGEMT",
    "DAMAGEMC",
)


def _target_path(output_path: str, expected_suffix: str) -> Path:
    target = Path(output_path).expanduser().resolve()
    if target.suffix.lower() != expected_suffix:
        raise ValueError(f"output_path must end with {expected_suffix}")
    return target


def _copy_derived(source: Path, target: Path, overwrite: bool) -> None:
    if target.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".tmp")
    shutil.copy2(source, staging)
    if target.exists():
        target.unlink()
    shutil.move(str(staging), str(target))


def _write_config(run_root: Path, config: dict[str, Any]) -> Path:
    path = run_root / "config.json"
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _execute_script(
    run_root: Path,
    script_text: str,
    mode: str,
    timeout_seconds: int,
) -> tuple[subprocess.CompletedProcess[str], list[str], Path]:
    script = run_root / "operation.py"
    script.write_text(script_text, encoding="utf-8")
    arguments = (
        ["python", str(script)]
        if mode == "python"
        else ["viewer", f"noGUI={script}"]
    )
    completed, logs = _run(arguments, run_root, timeout_seconds)
    return completed, logs, script


def _script_failure_detail(
    run_root: Path,
    completed: subprocess.CompletedProcess[str],
) -> str:
    diagnostics: list[str] = []
    for name in ("abaqus-stderr.log", "abaqus-stdout.log"):
        path = run_root / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                diagnostics.append(text[-1200:])
    evidence = "\n".join(diagnostics).strip()
    if evidence:
        return evidence
    return (
        f"Abaqus returned exit code {completed.returncode} but did not produce "
        "the required output evidence."
    )


FIELD_SCRIPT = r"""
from __future__ import print_function
import csv
import json
from odbAccess import openOdb

with open(r"__CONFIG_PATH__", "r") as stream:
    cfg = json.load(stream)

try:
    text_type = unicode
except NameError:
    text_type = str

def native_strings(value):
    if isinstance(value, text_type) and not isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, list):
        return [native_strings(item) for item in value]
    if isinstance(value, dict):
        return dict(
            (native_strings(key), native_strings(item))
            for key, item in value.items()
        )
    return value

cfg = native_strings(cfg)
odb = openOdb(path=str(cfg["odb_path"]), readOnly=True)
step_name = cfg.get("step_name") or list(odb.steps.keys())[-1]
step = odb.steps[step_name]
frame = step.frames[int(cfg.get("frame_index", -1))]
field = frame.fieldOutputs[cfg["field_name"]]

set_name = cfg.get("set_name")
if set_name:
    region = None
    for repository in (odb.rootAssembly.nodeSets, odb.rootAssembly.elementSets):
        if set_name in repository:
            region = repository[set_name]
            break
        upper = set_name.upper()
        if upper in repository:
            region = repository[upper]
            break
    if region is None:
        raise KeyError("Set not found: " + set_name)
    field = field.getSubset(region=region)

component = cfg.get("component")
invariant = cfg.get("invariant")
component_labels = list(field.componentLabels)

def selected_value(item):
    if component:
        if component not in component_labels:
            raise KeyError("Component %s not in %s" % (component, component_labels))
        return float(item.data[component_labels.index(component)])
    if invariant:
        attribute = {
            "magnitude": "magnitude",
            "mises": "mises",
            "tresca": "tresca",
            "press": "press",
            "max_principal": "maxPrincipal",
            "mid_principal": "midPrincipal",
            "min_principal": "minPrincipal",
            "max_inplane_principal": "maxInPlanePrincipal",
            "min_inplane_principal": "minInPlanePrincipal",
            "outofplane_principal": "outOfPlanePrincipal",
        }[invariant]
        return float(getattr(item, attribute))
    data = item.data
    try:
        size = len(data)
    except TypeError:
        return float(data)
    if size == 1:
        return float(data[0])
    raise ValueError("Vector/tensor field requires component or invariant")

rows = []
minimum = None
maximum = None
total = 0
limit = int(cfg.get("max_rows", 100000))
for item in field.values:
    value = selected_value(item)
    record = {
        "value": value,
        "instance": getattr(getattr(item, "instance", None), "name", None),
        "node_label": getattr(item, "nodeLabel", None),
        "element_label": getattr(item, "elementLabel", None),
        "integration_point": getattr(item, "integrationPoint", None),
        "position": str(getattr(item, "position", "")),
        "section_point": (
            getattr(getattr(item, "sectionPoint", None), "description", None)
        ),
    }
    if minimum is None or value < minimum["value"]:
        minimum = dict(record)
    if maximum is None or value > maximum["value"]:
        maximum = dict(record)
    if len(rows) < limit:
        rows.append(record)
    total += 1

report = {
    "odb_path": cfg["odb_path"],
    "step_name": step_name,
    "frame_index": int(cfg.get("frame_index", -1)),
    "frame_value": frame.frameValue,
    "field_name": cfg["field_name"],
    "component_labels": component_labels,
    "component": component,
    "invariant": invariant,
    "set_name": set_name,
    "value_count": total,
    "exported_rows": len(rows),
    "truncated": total > len(rows),
    "minimum": minimum,
    "maximum": maximum,
}
with open(r"__REPORT_PATH__", "w") as stream:
    json.dump(report, stream, indent=2)
with open(r"__CSV_PATH__", "w") as stream:
    writer = csv.writer(stream)
    writer.writerow([
        "value", "instance", "node_label", "element_label",
        "integration_point", "position", "section_point"
    ])
    for row in rows:
        writer.writerow([
            row["value"], row["instance"], row["node_label"],
            row["element_label"], row["integration_point"],
            row["position"], row["section_point"]
        ])
odb.close()
"""


def extract_abaqus_field(
    input_path: str,
    output_path: str,
    field_name: str,
    step_name: str | None = None,
    frame_index: int = -1,
    set_name: str | None = None,
    component: str | None = None,
    invariant: str | None = None,
    max_rows: int = 100_000,
    overwrite: bool = False,
    timeout_seconds: int = 300,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"ODB does not exist: {source}")
    try:
        target = _target_path(output_path, ".json")
        if target.exists() and not overwrite:
            return ToolResult(status="needs_input", error=f"Output already exists: {target}")
        if not field_name.strip():
            raise ValueError("field_name is required")
        if component and invariant:
            raise ValueError("Specify component or invariant, not both")
        normalized_invariant = invariant.lower() if invariant else None
        if normalized_invariant and normalized_invariant not in INVARIANTS:
            raise ValueError(f"Unsupported invariant: {invariant}")
        if not 1 <= max_rows <= 1_000_000:
            raise ValueError("max_rows must be between 1 and 1000000")
        run_root = _run_root("cae-abq-field-")
        report = run_root / "field-report.json"
        csv_path = run_root / "field-values.csv"
        config = _write_config(
            run_root,
            {
                "odb_path": str(source),
                "step_name": step_name,
                "frame_index": frame_index,
                "field_name": field_name,
                "set_name": set_name,
                "component": component,
                "invariant": normalized_invariant,
                "max_rows": max_rows,
            },
        )
        script_text = (
            FIELD_SCRIPT
            .replace("__CONFIG_PATH__", str(config))
            .replace("__REPORT_PATH__", str(report))
            .replace("__CSV_PATH__", str(csv_path))
        )
        completed, logs, _ = _execute_script(
            run_root, script_text, "python", timeout_seconds
        )
        if completed.returncode != 0 or not report.is_file():
            return ToolResult(
                status="failed",
                artifacts=[{"path": str(run_root), "role": "failed-field-extraction"}],
                logs=logs,
                error=(
                    "Abaqus field extraction failed: "
                    + _script_failure_detail(run_root, completed)
                ),
                elapsed_seconds=time.monotonic() - started,
            )
        _copy_derived(report, target, overwrite)
        csv_target = target.with_suffix(".csv")
        _copy_derived(csv_path, csv_target, overwrite)
        summary = json.loads(target.read_text(encoding="utf-8"))
        return ToolResult(
            status="succeeded",
            artifacts=[
                {"path": str(target), "role": "abaqus-field-summary"},
                {"path": str(csv_target), "role": "abaqus-field-table"},
            ],
            checks=summary,
            warnings=(
                ["The exported value table was truncated; extrema still use all values."]
                if summary.get("truncated")
                else []
            ),
            logs=logs,
            application={"name": "Abaqus ODB API", "version": "unknown"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


FAILURE_SCRIPT = r"""
from __future__ import print_function
import json
from odbAccess import openOdb

with open(r"{config_path}", "r") as stream:
    cfg = json.load(stream)
try:
    text_type = unicode
except NameError:
    text_type = str

def native_strings(value):
    if isinstance(value, text_type) and not isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, list):
        return [native_strings(item) for item in value]
    if isinstance(value, dict):
        return dict(
            (native_strings(key), native_strings(item))
            for key, item in value.items()
        )
    return value

cfg = native_strings(cfg)
odb = openOdb(path=str(cfg["odb_path"]), readOnly=True)
step_name = cfg.get("step_name") or list(odb.steps.keys())[-1]
frame = odb.steps[step_name].frames[int(cfg.get("frame_index", -1))]
requested = cfg["failure_fields"]
results = {{}}
for name in requested:
    if name not in frame.fieldOutputs:
        continue
    field = frame.fieldOutputs[name]
    labels = list(field.componentLabels)
    maxima = {{}}
    for item in field.values:
        data = item.data
        try:
            values = list(data)
        except TypeError:
            values = [float(data)]
        if not labels:
            item_labels = [name] if len(values) == 1 else [
                "%s_%d" % (name, index + 1) for index in range(len(values))
            ]
        else:
            item_labels = labels
        for index, value in enumerate(values):
            label = item_labels[index]
            value = float(value)
            current = maxima.get(label)
            if current is None or value > current["value"]:
                maxima[label] = {{
                    "value": value,
                    "instance": getattr(getattr(item, "instance", None), "name", None),
                    "node_label": getattr(item, "nodeLabel", None),
                    "element_label": getattr(item, "elementLabel", None),
                    "integration_point": getattr(item, "integrationPoint", None),
                    "section_point": (
                        getattr(getattr(item, "sectionPoint", None), "description", None)
                    ),
                }}
    results[name] = {{
        "component_labels": labels,
        "maxima": maxima,
        "value_count": len(field.values),
    }}
report = {{
    "odb_path": cfg["odb_path"],
    "step_name": step_name,
    "frame_index": int(cfg.get("frame_index", -1)),
    "frame_value": frame.frameValue,
    "available_failure_fields": sorted(results.keys()),
    "results": results,
}}
with open(r"{report_path}", "w") as stream:
    json.dump(report, stream, indent=2)
odb.close()
"""


def extract_abaqus_failure_indices(
    input_path: str,
    output_path: str,
    step_name: str | None = None,
    frame_index: int = -1,
    overwrite: bool = False,
    timeout_seconds: int = 300,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"ODB does not exist: {source}")
    try:
        target = _target_path(output_path, ".json")
        if target.exists() and not overwrite:
            return ToolResult(status="needs_input", error=f"Output already exists: {target}")
        run_root = _run_root("cae-abq-failure-")
        report = run_root / "failure-indices.json"
        config = _write_config(
            run_root,
            {
                "odb_path": str(source),
                "step_name": step_name,
                "frame_index": frame_index,
                "failure_fields": list(FAILURE_FIELDS),
            },
        )
        script_text = FAILURE_SCRIPT.format(
            config_path=str(config),
            report_path=str(report),
        )
        completed, logs, _ = _execute_script(
            run_root, script_text, "python", timeout_seconds
        )
        if completed.returncode != 0 or not report.is_file():
            return ToolResult(
                status="failed",
                artifacts=[{"path": str(run_root), "role": "failed-failure-index-extraction"}],
                logs=logs,
                error=(
                    "Abaqus composite failure-index extraction failed: "
                    + _script_failure_detail(run_root, completed)
                ),
                elapsed_seconds=time.monotonic() - started,
            )
        _copy_derived(report, target, overwrite)
        summary = json.loads(target.read_text(encoding="utf-8"))
        available = summary.get("available_failure_fields", [])
        return ToolResult(
            status="succeeded",
            artifacts=[{"path": str(target), "role": "composite-failure-index-summary"}],
            checks=summary,
            warnings=(
                []
                if available
                else [
                    "No supported Abaqus failure-index field exists in this frame. "
                    "Request CFAILURE/DMICRT/DMIFI or the required criterion during analysis."
                ]
            ),
            logs=logs,
            application={"name": "Abaqus ODB API", "version": "unknown"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


CONTOUR_SCRIPT = r"""
from abaqus import session
from abaqusConstants import *
import visualization

odb_path = r"{odb_path}"
output_base = r"{output_base}"
odb = visualization.openOdb(path=odb_path)
viewport = session.Viewport(name="CAX Contour", origin=(0, 0), width=180, height=120)
viewport.setValues(displayedObject=odb)
step_names = list(odb.steps.keys())
step_name = {step_name}
if step_name is None:
    step_index = len(step_names) - 1
else:
    step_index = step_names.index(step_name)
frame_index = {frame_index}
if frame_index < 0:
    frame_index = len(odb.steps[step_names[step_index]].frames) + frame_index
viewport.odbDisplay.setFrame(step=step_index, frame=frame_index)
position = {position}
refinement = {refinement}
if refinement is None:
    viewport.odbDisplay.setPrimaryVariable(
        variableLabel={field_name}, outputPosition=position
    )
else:
    viewport.odbDisplay.setPrimaryVariable(
        variableLabel={field_name}, outputPosition=position,
        refinement=refinement
    )
viewport.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
session.printOptions.setValues(rendition=COLOR, vpDecorations=OFF, vpBackground=OFF)
session.printToFile(fileName=output_base, format=PNG, canvasObjects=(viewport,))
odb.close()
"""


def _refinement_expression(
    component: str | None,
    invariant: str | None,
) -> str:
    if component and invariant:
        raise ValueError("Specify component or invariant, not both")
    if component:
        return f"(COMPONENT, {component!r})"
    if invariant:
        labels = {
            "magnitude": "Magnitude",
            "mises": "Mises",
            "tresca": "Tresca",
            "press": "Pressure",
            "max_principal": "Max. Principal",
            "mid_principal": "Mid. Principal",
            "min_principal": "Min. Principal",
        }
        normalized = invariant.lower()
        if normalized not in labels:
            raise ValueError(f"Unsupported contour invariant: {invariant}")
        return f"(INVARIANT, {labels[normalized]!r})"
    return "None"


def render_abaqus_contour(
    input_path: str,
    output_path: str,
    field_name: str,
    position: str,
    step_name: str | None = None,
    frame_index: int = -1,
    component: str | None = None,
    invariant: str | None = None,
    overwrite: bool = False,
    timeout_seconds: int = 300,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"ODB does not exist: {source}")
    try:
        target = _target_path(output_path, ".png")
        if target.exists() and not overwrite:
            return ToolResult(status="needs_input", error=f"Output already exists: {target}")
        if position not in POSITIONS:
            raise ValueError(f"position must be one of {sorted(POSITIONS)}")
        refinement = _refinement_expression(component, invariant)
        run_root = _run_root("cae-abq-contour-")
        output_base = run_root / "contour"
        script_text = CONTOUR_SCRIPT.format(
            odb_path=str(source),
            output_base=str(output_base),
            step_name=repr(step_name),
            frame_index=frame_index,
            position=POSITIONS[position],
            refinement=refinement,
            field_name=repr(field_name),
        )
        completed, logs, _ = _execute_script(
            run_root, script_text, "viewer", timeout_seconds
        )
        generated = output_base.with_suffix(".png")
        if completed.returncode != 0 or not generated.is_file():
            return ToolResult(
                status="failed",
                artifacts=[{"path": str(run_root), "role": "failed-contour-render"}],
                logs=logs,
                error=(
                    "Abaqus contour rendering failed: "
                    + _script_failure_detail(run_root, completed)
                ),
                elapsed_seconds=time.monotonic() - started,
            )
        _copy_derived(generated, target, overwrite)
        return ToolResult(
            status="succeeded",
            artifacts=[{"path": str(target), "role": "abaqus-contour-png"}],
            checks={
                "field_name": field_name,
                "position": position,
                "component": component,
                "invariant": invariant,
                "step_name": step_name,
                "frame_index": frame_index,
                "bytes": target.stat().st_size,
            },
            logs=logs,
            application={"name": "Abaqus Viewer", "version": "unknown"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


PATH_SCRIPT = r"""
from abaqus import session
from abaqusConstants import *
import json
import visualization

odb = visualization.openOdb(path=r"{odb_path}")
viewport = session.Viewport(name="CAX Path", origin=(0, 0), width=160, height=100)
viewport.setValues(displayedObject=odb)
step_names = list(odb.steps.keys())
step_name = {step_name}
step_index = len(step_names) - 1 if step_name is None else step_names.index(step_name)
frame_index = {frame_index}
if frame_index < 0:
    frame_index = len(odb.steps[step_names[step_index]].frames) + frame_index
viewport.odbDisplay.setFrame(step=step_index, frame=frame_index)
path = session.Path(
    name="CAX_NODE_PATH",
    type=NODE_LIST,
    expression=(({instance_name}, tuple({node_labels})),)
)
refinement = {refinement}
if refinement is None:
    variable = (({field_name}, {position}),)
else:
    variable = (({field_name}, {position}, (refinement,)),)
xy = session.XYDataFromPath(
    name="CAX_PATH_DATA",
    path=path,
    includeIntersections=False,
    shape=UNDEFORMED,
    pathStyle=PATH_POINTS,
    labelType=TRUE_DISTANCE,
    viewport=viewport.name,
    variable=variable
)
series = xy if isinstance(xy, (list, tuple)) else [xy]
result = {{
    "odb_path": r"{odb_path}",
    "step_name": step_names[step_index],
    "frame_index": frame_index,
    "instance_name": {instance_name},
    "node_labels": list({node_labels}),
    "field_name": {field_name},
    "position": {position_name},
    "series": [
        {{"name": item.name, "data": [[float(x), float(y)] for x, y in item.data]}}
        for item in series
    ],
}}
with open(r"{report_path}", "w") as stream:
    json.dump(result, stream, indent=2)
odb.close()
"""


def extract_abaqus_path(
    input_path: str,
    output_path: str,
    instance_name: str,
    node_labels: list[int],
    field_name: str,
    position: str = "nodal",
    step_name: str | None = None,
    frame_index: int = -1,
    component: str | None = None,
    invariant: str | None = None,
    overwrite: bool = False,
    timeout_seconds: int = 300,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"ODB does not exist: {source}")
    try:
        target = _target_path(output_path, ".json")
        if target.exists() and not overwrite:
            return ToolResult(status="needs_input", error=f"Output already exists: {target}")
        labels = [int(label) for label in node_labels]
        if len(labels) < 2 or any(label <= 0 for label in labels):
            raise ValueError("node_labels must contain at least two positive IDs")
        if position not in POSITIONS:
            raise ValueError(f"position must be one of {sorted(POSITIONS)}")
        refinement = _refinement_expression(component, invariant)
        run_root = _run_root("cae-abq-path-")
        report = run_root / "path-data.json"
        script_text = PATH_SCRIPT.format(
            odb_path=str(source),
            report_path=str(report),
            step_name=repr(step_name),
            frame_index=frame_index,
            instance_name=repr(instance_name),
            node_labels=repr(tuple(labels)),
            field_name=repr(field_name),
            position=POSITIONS[position],
            position_name=repr(position),
            refinement=refinement,
        )
        completed, logs, _ = _execute_script(
            run_root, script_text, "viewer", timeout_seconds
        )
        if completed.returncode != 0 or not report.is_file():
            return ToolResult(
                status="failed",
                artifacts=[{"path": str(run_root), "role": "failed-path-extraction"}],
                logs=logs,
                error=(
                    "Abaqus path extraction failed: "
                    + _script_failure_detail(run_root, completed)
                ),
                elapsed_seconds=time.monotonic() - started,
            )
        _copy_derived(report, target, overwrite)
        summary = json.loads(target.read_text(encoding="utf-8"))
        return ToolResult(
            status="succeeded",
            artifacts=[{"path": str(target), "role": "abaqus-path-data"}],
            checks=summary,
            logs=logs,
            application={"name": "Abaqus Viewer", "version": "unknown"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )
