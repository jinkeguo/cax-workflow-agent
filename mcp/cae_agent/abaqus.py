from __future__ import annotations

import math
import re
import shutil
import time
from collections import Counter
from pathlib import Path

from .result import ToolResult

COMPONENT_RE = re.compile(r"^\*\*HW_COMPONENT\b.*?\bNAME=([^\s]+)", re.IGNORECASE)
ELEMENT_RE = re.compile(r"^\*ELEMENT\b", re.IGNORECASE)
ELSET_RE = re.compile(r"(?:^|,)\s*ELSET\s*=", re.IGNORECASE)


def _determinant3(matrix: list[list[float]]) -> float:
    a, b, c = matrix
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def _center_jacobian(coords: list[tuple[float, float, float]]) -> float:
    signs = (
        (-1, -1, -1),
        (1, -1, -1),
        (1, 1, -1),
        (-1, 1, -1),
        (-1, -1, 1),
        (1, -1, 1),
        (1, 1, 1),
        (-1, 1, 1),
    )
    jac = [[0.0] * 3 for _ in range(3)]
    for (x, y, z), (sx, sy, sz) in zip(coords, signs):
        for local_axis, derivative in enumerate((sx / 8.0, sy / 8.0, sz / 8.0)):
            jac[local_axis][0] += derivative * x
            jac[local_axis][1] += derivative * y
            jac[local_axis][2] += derivative * z
    return _determinant3(jac)


def _parse_deck(path: Path):
    nodes: dict[int, tuple[float, float, float]] = {}
    elements: dict[int, tuple[str, tuple[int, ...], str | None]] = {}
    mode: str | None = None
    element_type = ""
    element_set: str | None = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            upper = line.upper()
            mode = None
            if upper.startswith("*NODE"):
                mode = "node"
            elif upper.startswith("*ELEMENT"):
                mode = "element"
                type_match = re.search(r"\bTYPE\s*=\s*([^,\s]+)", line, re.I)
                set_match = re.search(r"\bELSET\s*=\s*([^,\s]+)", line, re.I)
                element_type = type_match.group(1).upper() if type_match else ""
                element_set = set_match.group(1) if set_match else None
            continue
        fields = [field.strip() for field in line.split(",") if field.strip()]
        if mode == "node":
            nodes[int(fields[0])] = tuple(map(float, fields[1:4]))
        elif mode == "element":
            elements[int(fields[0])] = (
                element_type,
                tuple(map(int, fields[1:])),
                element_set,
            )
    return nodes, elements


def validate_abaqus_mesh(
    input_path: str,
    expected_type: str | None = None,
    expected_elements: int | None = None,
) -> ToolResult:
    started = time.monotonic()
    path = Path(input_path).expanduser().resolve()
    if not path.is_file():
        return ToolResult(
            status="failed",
            error=f"Input deck does not exist: {path}",
            elapsed_seconds=time.monotonic() - started,
        )
    try:
        nodes, elements = _parse_deck(path)
        types = Counter(record[0] for record in elements.values())
        sets = Counter(record[2] or "<none>" for record in elements.values())
        errors: list[str] = []
        if expected_elements is not None and len(elements) != expected_elements:
            errors.append(f"element count {len(elements)} != {expected_elements}")
        if expected_type and set(types) != {expected_type.upper()}:
            errors.append(f"element types {dict(types)} != {expected_type.upper()}")

        missing_refs = 0
        duplicate_connectivity = 0
        seen: set[tuple[int, ...]] = set()
        determinants: list[float] = []
        for _, connectivity, _ in elements.values():
            if any(node_id not in nodes for node_id in connectivity):
                missing_refs += 1
                continue
            key = tuple(sorted(connectivity))
            if key in seen:
                duplicate_connectivity += 1
            seen.add(key)
            if len(connectivity) == 8:
                determinants.append(
                    _center_jacobian([nodes[node_id] for node_id in connectivity])
                )

        nonpositive = sum(value <= 0.0 for value in determinants)
        if missing_refs:
            errors.append(f"{missing_refs} elements reference missing nodes")
        if duplicate_connectivity:
            errors.append(f"{duplicate_connectivity} duplicate connectivities")
        if nonpositive:
            errors.append(f"{nonpositive} hex elements have nonpositive center Jacobian")
        if not all(math.isfinite(value) for value in determinants):
            errors.append("non-finite Jacobian determinant")

        bbox = None
        if nodes:
            axes = list(zip(*nodes.values()))
            bbox = {
                "min": [min(axis) for axis in axes],
                "max": [max(axis) for axis in axes],
            }
        checks = {
            "nodes": len(nodes),
            "elements": len(elements),
            "element_types": dict(types),
            "element_sets": dict(sets),
            "bbox": bbox,
            "missing_node_references": missing_refs,
            "duplicate_connectivity": duplicate_connectivity,
            "hex_center_determinant_min": min(determinants) if determinants else None,
            "hex_center_determinant_max": max(determinants) if determinants else None,
            "hex_nonpositive": nonpositive,
        }
        return ToolResult(
            status="failed" if errors else "succeeded",
            artifacts=[{"path": str(path), "role": "validated-abaqus-deck"}],
            checks=checks,
            error="; ".join(errors) if errors else None,
            application={"name": "Abaqus deck validator", "version": "0.1.0"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def ensure_component_elsets(
    input_path: str,
    output_path: str,
    overwrite: bool = False,
) -> ToolResult:
    started = time.monotonic()
    source = Path(input_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if not source.is_file():
        return ToolResult(status="failed", error=f"Input deck does not exist: {source}")
    if source == target:
        return ToolResult(status="failed", error="Input and output paths must differ")
    if target.exists() and not overwrite:
        return ToolResult(status="needs_input", error=f"Output already exists: {target}")
    try:
        current_component: str | None = None
        names: list[str] = []
        converted: list[str] = []
        text = source.read_text(encoding="utf-8", errors="strict")
        for line in text.splitlines(keepends=True):
            match = COMPONENT_RE.match(line.strip())
            if match:
                current_component = match.group(1)
            if ELEMENT_RE.match(line.strip()) and not ELSET_RE.search(line):
                if not current_component:
                    raise ValueError("*ELEMENT block has no preceding **HW_COMPONENT name")
                newline = "\n" if line.endswith("\n") else ""
                line = f"{line.rstrip(chr(13) + chr(10))},ELSET={current_component}{newline}"
                names.append(current_component)
            converted.append(line)
        if not names:
            return ToolResult(
                status="succeeded",
                artifacts=[{"path": str(source), "role": "abaqus-deck-already-has-elsets"}],
                checks={"converted_element_blocks": 0},
                warnings=["No element blocks required conversion."],
                elapsed_seconds=time.monotonic() - started,
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            stream.write("".join(converted))
        if target.exists():
            target.unlink()
        shutil.move(str(temporary), str(target))
        return ToolResult(
            status="succeeded",
            artifacts=[{"path": str(target), "role": "abaqus-deck-with-component-elsets"}],
            checks={"converted_element_blocks": len(names), "elsets": names},
            application={"name": "Abaqus deck normalizer", "version": "0.1.0"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )
