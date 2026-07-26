#!/usr/bin/env python3
"""Add ELSET parameters to Abaqus element blocks using HW_COMPONENT comments."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

COMPONENT_RE = re.compile(r"^\*\*HW_COMPONENT\b.*?\bNAME=([^\s]+)", re.IGNORECASE)
ELEMENT_RE = re.compile(r"^\*ELEMENT\b", re.IGNORECASE)
ELSET_RE = re.compile(r"(?:^|,)\s*ELSET\s*=", re.IGNORECASE)


def convert(text: str) -> tuple[str, list[str]]:
    current_component: str | None = None
    converted: list[str] = []
    names: list[str] = []
    for line in text.splitlines(keepends=True):
        match = COMPONENT_RE.match(line.strip())
        if match:
            current_component = match.group(1)
        if ELEMENT_RE.match(line.strip()) and not ELSET_RE.search(line):
            if not current_component:
                raise ValueError("*ELEMENT block has no preceding **HW_COMPONENT name")
            newline = "\n" if line.endswith("\n") else ""
            body = line.rstrip("\r\n")
            line = f"{body},ELSET={current_component}{newline}"
            names.append(current_component)
        converted.append(line)
    return "".join(converted), names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output must differ")
    text = args.input.read_text(encoding="utf-8", errors="strict")
    output, names = convert(text)
    if not names:
        raise SystemExit("FAIL: no element blocks required conversion")
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        stream.write(output)
    print(f"PASS: added ELSET to {len(names)} element blocks")
    print("ELSETS=" + ",".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
