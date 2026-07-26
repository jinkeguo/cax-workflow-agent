from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .result import ToolResult

ALLOWED_STAGES = {"cad", "mesh", "deck", "solve", "post"}
ALLOWED_STATUSES = {"pending", "in_progress", "passed", "failed"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def get_case_status(manifest_path: str) -> ToolResult:
    started = time.monotonic()
    path = Path(manifest_path).expanduser().resolve()
    if not path.is_file():
        return ToolResult(status="failed", error=f"Manifest does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        artifact_checks = []
        warnings: list[str] = []
        for artifact in data.get("artifacts", []):
            artifact_path = Path(artifact["path"])
            if not artifact_path.is_absolute():
                artifact_path = path.parent / artifact_path
            exists = artifact_path.is_file()
            actual_sha256 = None
            matches = None
            if exists:
                actual_sha256 = _sha256(artifact_path)
                expected = artifact.get("sha256")
                matches = actual_sha256 == expected.upper() if expected else None
                if matches is False:
                    warnings.append(f"SHA-256 mismatch: {artifact_path}")
            else:
                warnings.append(f"Missing artifact: {artifact_path}")
            artifact_checks.append(
                {
                    "path": str(artifact_path.resolve()),
                    "role": artifact.get("role"),
                    "exists": exists,
                    "sha256": actual_sha256,
                    "hash_matches_manifest": matches,
                }
            )
        stages = {
            name: value.get("status", "unknown")
            for name, value in data.get("stages", {}).items()
        }
        failed_artifacts = [
            item for item in artifact_checks
            if not item["exists"] or item["hash_matches_manifest"] is False
        ]
        return ToolResult(
            status="failed" if failed_artifacts else "succeeded",
            artifacts=artifact_checks,
            checks={
                "case_id": data.get("case_id"),
                "objective": data.get("objective"),
                "stages": stages,
                "artifact_count": len(artifact_checks),
                "verified_artifacts": len(artifact_checks) - len(failed_artifacts),
            },
            warnings=warnings,
            application={"name": "CAE case manifest validator", "version": "0.1.0"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def record_case_stage(
    manifest_path: str,
    stage: str,
    stage_status: str,
    evidence: list[str],
    idempotency_key: str,
    expected_manifest_sha256: str | None = None,
    confirm_write: bool = False,
) -> ToolResult:
    started = time.monotonic()
    path = Path(manifest_path).expanduser().resolve()
    if not path.is_file():
        return ToolResult(status="failed", error=f"Manifest does not exist: {path}")
    if stage not in ALLOWED_STAGES:
        return ToolResult(status="failed", error=f"Unsupported stage: {stage}")
    if stage_status not in ALLOWED_STATUSES:
        return ToolResult(status="failed", error=f"Unsupported stage status: {stage_status}")
    if not idempotency_key.strip():
        return ToolResult(status="failed", error="idempotency_key must not be empty")
    try:
        current_hash = _sha256(path)
        if expected_manifest_sha256 and current_hash != expected_manifest_sha256.upper():
            return ToolResult(
                status="needs_input",
                checks={"actual_manifest_sha256": current_hash},
                error="Manifest changed since it was inspected; refresh before writing.",
                elapsed_seconds=time.monotonic() - started,
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        history = data.setdefault("agent_history", [])
        existing = next(
            (item for item in history if item.get("idempotency_key") == idempotency_key),
            None,
        )
        if existing:
            return ToolResult(
                status="succeeded",
                artifacts=[{"path": str(path), "role": "case-manifest"}],
                checks={
                    "idempotent_replay": True,
                    "record": existing,
                    "manifest_sha256": current_hash,
                },
                elapsed_seconds=time.monotonic() - started,
            )

        previous = data.setdefault("stages", {}).setdefault(
            stage, {"status": "pending", "evidence": []}
        )
        preview = {
            "stage": stage,
            "previous_status": previous.get("status", "pending"),
            "new_status": stage_status,
            "new_evidence": evidence,
            "manifest_sha256": current_hash,
            "idempotency_key": idempotency_key,
        }
        if not confirm_write:
            return ToolResult(
                status="needs_input",
                artifacts=[{"path": str(path), "role": "case-manifest"}],
                checks={"write_preview": preview},
                warnings=["No file was changed. Set confirm_write=true after approval."],
                elapsed_seconds=time.monotonic() - started,
            )

        previous["status"] = stage_status
        current_evidence = previous.setdefault("evidence", [])
        for item in evidence:
            if item not in current_evidence:
                current_evidence.append(item)
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "idempotency_key": idempotency_key,
            "stage": stage,
            "status": stage_status,
            "evidence": evidence,
        }
        history.append(record)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
        new_hash = _sha256(path)
        return ToolResult(
            status="succeeded",
            artifacts=[{"path": str(path), "role": "updated-case-manifest"}],
            checks={
                "idempotent_replay": False,
                "record": record,
                "previous_manifest_sha256": current_hash,
                "manifest_sha256": new_hash,
            },
            application={"name": "CAE case manifest writer", "version": "0.1.0"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )
