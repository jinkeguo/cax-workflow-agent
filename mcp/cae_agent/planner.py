from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .abaqus_runtime import abaqus_installation_status
from .hypermesh import hypermesh_installation_status
from .result import ToolResult
from .solidworks import solidworks_installation_status

STAGE_ORDER = ("cad", "mesh", "deck", "solve", "post")
PASSED = {"passed", "succeeded", "complete", "completed"}


def get_cae_capabilities() -> ToolResult:
    """Report implemented adapters without pretending unsupported stages are available."""
    hypermesh = hypermesh_installation_status()
    abaqus = abaqus_installation_status()
    hm_exists = hypermesh["executable_exists"]
    template_exists = hypermesh["abaqus_template_exists"]
    solidworks = solidworks_installation_status()
    return ToolResult(
        status="succeeded",
        checks={
            "stages": {
                "cad": {
                    "status": (
                        "available" if solidworks["runtime_available"] else "unavailable"
                    ),
                    "adapters": [
                        "get_solidworks_environment",
                        "inspect_solidworks_document",
                        "instantiate_solidworks_template",
                        "export_solidworks_document",
                    ],
                    "note": (
                        "The template-driven SolidWorks COM adapter is implemented. "
                        "This machine does not currently expose the SolidWorks COM runtime."
                        if not solidworks["runtime_available"]
                        else "Template-driven SolidWorks inspection, parameterization, and neutral export are available."
                    ),
                },
                "mesh": {
                    "status": "available" if hm_exists else "unavailable",
                    "adapters": [
                        "inspect_hm_model",
                        "mesh_hm_solids",
                        "check_hm_mesh_quality",
                        "smooth_hm_solid_mesh",
                    ],
                    "note": (
                        "Explicit-ID multi-solid mapped meshing, 3D quality checks, "
                        "and bounded solid smoothing are available. Geometry-specific "
                        "partitioning and source/target hints remain guided."
                    ),
                },
                "deck": {
                    "status": "available" if hm_exists and template_exists else "unavailable",
                    "adapters": [
                        "export_abaqus_deck",
                        "ensure_component_elsets",
                        "validate_abaqus_mesh",
                    ],
                },
                "solve": {
                    "status": "available" if abaqus["command_exists"] else "unavailable",
                    "adapters": [
                        "get_abaqus_environment",
                        "run_abaqus_datacheck",
                        "inspect_abaqus_job",
                        "submit_abaqus_job",
                        "monitor_abaqus_job",
                        "cancel_abaqus_job",
                        "retry_abaqus_job",
                    ],
                    "note": (
                        "Datacheck, approval-gated background submission, monitoring, "
                        "termination, and unchanged-input transient retry are available."
                    ),
                },
                "post": {
                    "status": "available" if abaqus["command_exists"] else "unavailable",
                    "adapters": [
                        "summarize_abaqus_odb",
                        "extract_abaqus_field",
                        "extract_abaqus_path",
                        "render_abaqus_contour",
                        "extract_abaqus_failure_indices",
                    ],
                    "note": (
                        "ODB summaries, field tables, node-list path XY data, PNG "
                        "contours, and Abaqus-computed composite failure indices are available."
                    ),
                },
            },
            "runtime": {
                "hypermesh": hypermesh,
                "abaqus": abaqus,
                "solidworks": solidworks,
            },
            "cross_cutting": {
                "failure_diagnosis": {
                    "status": "available",
                    "adapters": ["diagnose_cae_failure"],
                    "note": "Rule-backed diagnosis covers initial SolidWorks, HyperMesh, and Abaqus failure signatures and returns recovery boundaries.",
                },
                "failure_web_research": {
                    "status": "available",
                    "adapters": [
                        "prepare_failure_research",
                        "evaluate_failure_research",
                        "record_verified_failure_rule",
                    ],
                    "note": "Unknown signatures can be researched on the web, evidence-ranked, verified locally, and promoted into a traceable local rule registry.",
                }
            },
        },
        application={"name": "CAX Workflow Agent", "version": "0.1.0"},
    )


def _resolve_artifacts(manifest: dict[str, Any], manifest_path: Path) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for item in manifest.get("artifacts", []):
        path = Path(item.get("path", ""))
        if not path.is_absolute():
            path = manifest_path.parent / path
        resolved.append({**item, "resolved_path": str(path.resolve()), "exists": path.is_file()})
    return resolved


def _first_artifact(artifacts: list[dict[str, Any]], terms: tuple[str, ...]):
    for artifact in reversed(artifacts):
        role = str(artifact.get("role", "")).lower()
        if all(term in role for term in terms) and artifact["exists"]:
            return artifact
    return None


def plan_next_action(manifest_path: str) -> ToolResult:
    """Return one deterministic next action from case state and available artifacts."""
    started = time.monotonic()
    path = Path(manifest_path).expanduser().resolve()
    if not path.is_file():
        return ToolResult(status="failed", error=f"Manifest does not exist: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        stages = manifest.get("stages", {})
        artifacts = _resolve_artifacts(manifest, path)
        current_stage = next(
            (
                stage
                for stage in STAGE_ORDER
                if str(stages.get(stage, {}).get("status", "pending")).lower() not in PASSED
            ),
            None,
        )
        if current_stage is None:
            return ToolResult(
                status="succeeded",
                checks={
                    "case_id": manifest.get("case_id"),
                    "workflow_status": "complete",
                    "current_stage": None,
                    "next_action": None,
                },
                elapsed_seconds=time.monotonic() - started,
            )

        decision: dict[str, Any] = {
            "case_id": manifest.get("case_id"),
            "workflow_status": "active",
            "current_stage": current_stage,
            "next_action": None,
            "tool": None,
            "arguments": {},
            "approval_required": False,
            "reason": "",
        }
        hm_mesh = _first_artifact(artifacts, ("native", "mesh"))
        hm_geometry = _first_artifact(artifacts, ("native", "model")) or _first_artifact(
            artifacts, ("geometry",)
        )
        normalized_deck = _first_artifact(artifacts, ("deck", "elset"))
        any_deck = _first_artifact(artifacts, ("deck",))
        datacheck = _first_artifact(artifacts, ("datacheck",))
        odb = _first_artifact(artifacts, ("odb",))
        solidworks_native = _first_artifact(artifacts, ("solidworks",))

        if current_stage == "cad":
            if solidworks_native and solidworks_installation_status()["runtime_available"]:
                decision.update(
                    next_action="inspect-solidworks-document",
                    tool="inspect_solidworks_document",
                    arguments={"input_path": solidworks_native["resolved_path"]},
                    reason="A native SolidWorks artifact exists and should be inspected before export.",
                )
                status = "succeeded"
            elif not solidworks_installation_status()["runtime_available"]:
                decision.update(
                    next_action="install-or-register-solidworks",
                    tool="get_solidworks_environment",
                    arguments={},
                    reason="The SolidWorks adapter is installed but the desktop COM runtime is unavailable.",
                )
                status = "needs_input"
            else:
                decision.update(
                    next_action="provide-parameterized-solidworks-template",
                    reason="CAD creation requires a .SLDPRT template and fully qualified dimension names.",
                )
                status = "needs_input"
        elif current_stage == "mesh":
            candidate = hm_mesh or hm_geometry
            if candidate:
                decision.update(
                    next_action="inspect-hypermesh-model",
                    tool="inspect_hm_model",
                    arguments={"input_path": candidate["resolved_path"]},
                    reason="Inspect the current HyperMesh artifact before deciding whether meshing is complete.",
                )
                status = "succeeded"
            else:
                decision.update(
                    next_action="provide-hypermesh-artifact",
                    reason="No existing HyperMesh geometry or mesh artifact was found.",
                )
                status = "needs_input"
        elif current_stage == "deck":
            if normalized_deck:
                decision.update(
                    next_action="validate-abaqus-mesh",
                    tool="validate_abaqus_mesh",
                    arguments={"input_path": normalized_deck["resolved_path"]},
                    reason="A normalized Abaqus deck exists; validate it before solver setup.",
                )
                status = "succeeded"
            elif any_deck:
                output = str(Path(any_deck["resolved_path"]).with_name(
                    Path(any_deck["resolved_path"]).stem + "-elsets.inp"
                ))
                decision.update(
                    next_action="ensure-component-elsets",
                    tool="ensure_component_elsets",
                    arguments={
                        "input_path": any_deck["resolved_path"],
                        "output_path": output,
                        "overwrite": False,
                    },
                    reason="An Abaqus deck exists but no normalized ELSET deck is recorded.",
                )
                status = "succeeded"
            elif hm_mesh:
                output = str(path.parent / f"{manifest.get('case_id', 'case')}.inp")
                decision.update(
                    next_action="export-abaqus-deck",
                    tool="export_abaqus_deck",
                    arguments={
                        "input_path": hm_mesh["resolved_path"],
                        "output_path": output,
                        "overwrite": False,
                    },
                    reason="A native mesh exists but no solver deck is recorded.",
                )
                status = "succeeded"
            else:
                decision.update(
                    next_action="provide-meshed-hypermesh-model",
                    reason="Deck creation requires a verified native mesh artifact.",
                )
                status = "needs_input"
        elif current_stage == "solve":
            deck = normalized_deck or any_deck
            if deck and not datacheck:
                decision.update(
                    next_action="run-abaqus-datacheck",
                    tool="run_abaqus_datacheck",
                    arguments={"input_path": deck["resolved_path"]},
                    reason="A solver deck exists but no successful datacheck artifact is recorded.",
                )
                status = "succeeded"
            else:
                decision.update(
                    next_action="approve-and-configure-abaqus-submit",
                    approval_required=True,
                    reason="Datacheck is complete or unavailable; launching a solve requires approval and a submission adapter.",
                )
                status = "needs_input"
        else:
            if odb:
                decision.update(
                    next_action="summarize-abaqus-odb",
                    tool="summarize_abaqus_odb",
                    arguments={"input_path": odb["resolved_path"]},
                    reason="An Abaqus ODB exists and can be inspected without modifying it.",
                )
                status = "succeeded"
            else:
                decision.update(
                    next_action="provide-solver-result",
                    reason="Postprocessing requires a recorded solver result such as an Abaqus ODB.",
                )
                status = "needs_input"

        return ToolResult(
            status=status,
            artifacts=artifacts,
            checks=decision,
            application={"name": "CAX Workflow Agent", "version": "0.1.0"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )
