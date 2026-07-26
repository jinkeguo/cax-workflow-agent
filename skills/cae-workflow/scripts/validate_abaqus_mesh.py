#!/usr/bin/env python3
"""Validate nodes and linear hex elements in an Abaqus input deck."""

from __future__ import annotations

import argparse
import math
import re
from collections import Counter
from pathlib import Path


def determinant3(matrix: list[list[float]]) -> float:
    a, b, c = matrix
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def center_jacobian(coords: list[tuple[float, float, float]]) -> float:
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
        derivatives = (sx / 8.0, sy / 8.0, sz / 8.0)
        for local_axis, derivative in enumerate(derivatives):
            jac[local_axis][0] += derivative * x
            jac[local_axis][1] += derivative * y
            jac[local_axis][2] += derivative * z
    return determinant3(jac)


def parse(path: Path):
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--expect-elements", type=int)
    parser.add_argument("--expect-type")
    args = parser.parse_args()

    nodes, elements = parse(args.input)
    errors: list[str] = []
    types = Counter(record[0] for record in elements.values())
    sets = Counter(record[2] or "<none>" for record in elements.values())

    if args.expect_elements is not None and len(elements) != args.expect_elements:
        errors.append(f"element count {len(elements)} != {args.expect_elements}")
    if args.expect_type and set(types) != {args.expect_type.upper()}:
        errors.append(f"element types {dict(types)} != {args.expect_type.upper()}")

    missing_refs = 0
    duplicate_connectivity = 0
    seen: set[tuple[int, ...]] = set()
    determinants: list[float] = []
    for _, (_, connectivity, _) in elements.items():
        if any(node_id not in nodes for node_id in connectivity):
            missing_refs += 1
            continue
        key = tuple(sorted(connectivity))
        if key in seen:
            duplicate_connectivity += 1
        seen.add(key)
        if len(connectivity) == 8:
            determinants.append(center_jacobian([nodes[node_id] for node_id in connectivity]))

    if missing_refs:
        errors.append(f"{missing_refs} elements reference missing nodes")
    if duplicate_connectivity:
        errors.append(f"{duplicate_connectivity} duplicate connectivities")
    nonpositive = sum(value <= 0.0 for value in determinants)
    if nonpositive:
        errors.append(f"{nonpositive} hex elements have nonpositive center Jacobian")

    xs = [coord[0] for coord in nodes.values()]
    ys = [coord[1] for coord in nodes.values()]
    zs = [coord[2] for coord in nodes.values()]
    print(f"NODES={len(nodes)}")
    print(f"ELEMENTS={len(elements)}")
    print(f"TYPES={dict(types)}")
    print(f"ELSETS={dict(sets)}")
    if nodes:
        print(f"BBOX={min(xs)},{min(ys)},{min(zs)}:{max(xs)},{max(ys)},{max(zs)}")
    print(f"MISSING_NODE_REFS={missing_refs}")
    print(f"DUPLICATE_CONNECTIVITY={duplicate_connectivity}")
    if determinants:
        print(f"HEX_CENTER_DET_MIN={min(determinants):.12g}")
        print(f"HEX_CENTER_DET_MAX={max(determinants):.12g}")
        print(f"HEX_NONPOSITIVE={nonpositive}")
        if not all(math.isfinite(value) for value in determinants):
            errors.append("non-finite Jacobian determinant")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
