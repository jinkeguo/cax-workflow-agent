#!/usr/bin/env python3
"""Validate the minimal durable state used by the CAE workflow skill."""

from __future__ import annotations

import json
import sys
from pathlib import Path

STAGES = ("cad", "mesh", "deck", "solve", "post")
STATUSES = {"pending", "in_progress", "passed", "failed", "skipped"}


def validate(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest root must be an object"]

    for key in ("schema_version", "case_id", "objective", "units", "solver", "stages", "artifacts"):
        if key not in data:
            errors.append(f"missing top-level field: {key}")

    units = data.get("units")
    if not isinstance(units, dict) or not units:
        errors.append("units must be a non-empty object")

    stages = data.get("stages")
    if not isinstance(stages, dict):
        errors.append("stages must be an object")
    else:
        active = 0
        for stage in STAGES:
            entry = stages.get(stage)
            if not isinstance(entry, dict):
                errors.append(f"missing or invalid stage: {stage}")
                continue
            status = entry.get("status")
            if status not in STATUSES:
                errors.append(f"stage {stage} has invalid status: {status!r}")
            if status == "in_progress":
                active += 1
            if status == "skipped" and not entry.get("reason"):
                errors.append(f"stage {stage} is skipped without a reason")
            evidence = entry.get("evidence")
            if evidence is not None and not isinstance(evidence, list):
                errors.append(f"stage {stage} evidence must be a list")
        if active > 1:
            errors.append("at most one stage may be in_progress")

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list")
    else:
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                errors.append(f"artifact {index} must be an object")
                continue
            for key in ("path", "role", "produced_by"):
                if not artifact.get(key):
                    errors.append(f"artifact {index} missing {key}")

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_case_manifest.py <manifest.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    errors = validate(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
