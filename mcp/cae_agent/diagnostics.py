from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .result import ToolResult

MAX_LOG_BYTES = 2_000_000
MAX_KNOWLEDGE_BYTES = 1_000_000
MAX_KNOWLEDGE_FILES = 10
APPLICATIONS = {"auto", "solidworks", "hypermesh", "abaqus"}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _rule(
    code: str,
    application: str,
    pattern: str,
    title: str,
    cause: str,
    actions: list[str],
    severity: str = "high",
    recovery: str = "guided",
    recommended_tool: str | None = None,
    approval_required: bool = False,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "application": application,
        "pattern": re.compile(pattern, re.IGNORECASE | re.MULTILINE),
        "title": title,
        "cause": cause,
        "actions": actions,
        "severity": severity,
        "recovery": recovery,
        "recommended_tool": recommended_tool,
        "approval_required": approval_required,
        "sources": sources or [],
    }


RULES = [
    _rule(
        "sw-com-not-registered",
        "solidworks",
        r"0x80040154|class not registered|solidworks com.*not registered|"
        r"sldworks\.application.*(?:unavailable|not found)",
        "SolidWorks COM runtime is unavailable",
        "SolidWorks is not installed, its COM registration is broken, or the process "
        "is running in a session that cannot access the desktop COM server.",
        [
            "Run get_solidworks_environment and confirm SldWorks.Application is registered.",
            "Start SolidWorks interactively once under the same Windows user.",
            "Repair the SolidWorks installation if COM registration remains absent.",
        ],
        recommended_tool="get_solidworks_environment",
        recovery="guided",
    ),
    _rule(
        "sw-dimension-not-found",
        "solidworks",
        r"(?:dimension|parameter).*(?:not found|null|unknown)|"
        r"unknown.*(?:dimension|parameter)",
        "SolidWorks dimension name was not resolved",
        "The template contract used an incomplete or stale dimension name, or the target "
        "feature/configuration is suppressed.",
        [
            "Inspect the document and enumerate the exact dimension contract.",
            "Use a fully qualified name such as D1@Sketch1.",
            "Confirm the owning feature is unsuppressed in the active configuration.",
        ],
        recommended_tool="inspect_solidworks_document",
    ),
    _rule(
        "sw-rebuild-failed",
        "solidworks",
        r"(?:force)?rebuild.*(?:fail|false)|feature.*rebuild error",
        "SolidWorks rebuild failed",
        "A changed dimension produced invalid geometry, dangling references, or an "
        "unsatisfied feature dependency.",
        [
            "Inspect failed features and their parents before changing more dimensions.",
            "Restore the last known-good parameter set and change one dimension at a time.",
            "Require user approval if the recovery changes feature or design intent.",
        ],
        recovery="guided",
        approval_required=True,
        sources=[
            "https://help.solidworks.com/2025/english/api/swconst/SO_Messages.htm"
        ],
    ),
    _rule(
        "sw-save-failed",
        "solidworks",
        r"saveas3?.*(?:fail|error)|save.*(?:access denied|permission denied)",
        "SolidWorks save or export failed",
        "The destination is locked, unwritable, already exists, or the requested export "
        "format is incompatible with the document.",
        [
            "Write to a new staging path and verify the destination is not open elsewhere.",
            "Keep overwrite disabled unless the user explicitly approves replacement.",
            "Inspect SolidWorks save error and warning codes from the bridge response.",
        ],
        recommended_tool="export_solidworks_document",
        sources=[
            "https://help.solidworks.com/2023/English/api/swconst/"
            "SOLIDWORKS.Interop.swconst~SOLIDWORKS.Interop.swconst.swFileSaveError_e.html"
        ],
    ),
    _rule(
        "hm-batch-timeout",
        "hypermesh",
        r"hypermesh exceeded|hmbatch.*(?:hang|timeout)|hmopengl.*(?:hang|timeout)",
        "HyperMesh batch process did not complete",
        "The wrapper may not have launched the core process, a dialog may be blocking, or "
        "the operation exceeded its bounded timeout.",
        [
            "Use hmopengl directly with -batch -tcl instead of a hanging hmbatch wrapper.",
            "Inspect retained stdout/stderr and the generated Tcl operation.",
            "Retry once in a fresh isolated run directory; do not reuse a locked model.",
        ],
        recommended_tool="inspect_hm_model",
        recovery="automatic",
        sources=[
            "https://help.altair.com/hwdesktop/hwx/topics/pre_processing/meshing/"
            "batchmesh_unity_t.htm"
        ],
    ),
    _rule(
        "hm-invalid-newmodel",
        "hypermesh",
        r"invalid command name\s+[\"']?\*newmodel",
        "Unsupported HyperMesh Tcl command",
        "*newmodel is not a valid Modify command in the observed HyperMesh 2025 batch "
        "environment.",
        [
            "Remove *newmodel; a fresh batch session already starts with an empty model.",
            "Rerun the bounded Tcl operation and verify the expected artifact.",
        ],
        recovery="automatic",
    ),
    _rule(
        "hm-export-template-missing",
        "hypermesh",
        r"(?:abaqus )?export template.*(?:not found|does not exist)|standard\.3d.*(?:missing|not found)",
        "HyperMesh Abaqus export template was not found",
        "The Altair installation is non-standard or CAE_ABAQUS_TEMPLATE is not configured.",
        [
            "Run get_cae_capabilities and inspect the template candidates.",
            "Set CAE_ABAQUS_TEMPLATE to the installed standard.3d file.",
            "Retry export to a new output path and validate the resulting deck.",
        ],
        recommended_tool="get_cae_capabilities",
        recovery="guided",
    ),
    _rule(
        "hm-map-mesh-failed",
        "hypermesh",
        r"(?:map|thin solid|sweep).*(?:mesh )?(?:fail|unable|not sweepable)|"
        r"(?:source|target).*(?:face|surface).*(?:invalid|fail)",
        "HyperMesh mapped solid meshing failed",
        "The solid is not sweepable with the selected source/target faces, topology is "
        "disconnected, or display/selector state selected an edge instead of a surface.",
        [
            "Isolate one Solid and set the selector to Surfaces for source/target geometry.",
            "Disable automatic source/target detection and select opposite cap faces manually.",
            "Check topology, face correspondence, and edge densities before retrying.",
            "Use Thin Solids only when the geometry satisfies its thickness assumptions.",
        ],
        recovery="guided",
        approval_required=True,
        sources=[
            "https://2025.help.altair.com/2025/hwdesktop/hwx/topics/"
            "pre_processing/meshing/thin_solid_mesh_create_t.htm"
        ],
    ),
    _rule(
        "hm-elements-missing-properties",
        "hypermesh",
        r"elements missing properties|missing propert(?:y|ies)",
        "HyperMesh elements have no assigned property",
        "The mesh exists but solver property/section assignment is incomplete.",
        [
            "If HyperMesh is mesh-only, record this as an intentional downstream Abaqus task.",
            "Otherwise assign the intended property to every affected component.",
            "Export and confirm Abaqus *SOLID SECTION or equivalent section definitions.",
        ],
        recovery="guided",
        approval_required=True,
        sources=[
            "https://docs.software.vt.edu/abaqusv2024/English/"
            "SIMACAEGSARefMap/simagsa-c-cnttroubleshooting.htm"
        ],
    ),
    _rule(
        "hm-free-node",
        "hypermesh",
        r"free node(?: in the model)?",
        "HyperMesh contains an unreferenced node",
        "A construction or anchor node is no longer attached to an element.",
        [
            "Locate the node through model checks and confirm it is not intentional.",
            "Delete only the verified free node; restart HyperMesh if the UI deletion state is stale.",
            "Rerun model checks and confirm the warning is gone.",
        ],
        recovery="guided",
        approval_required=True,
    ),
    _rule(
        "abq-wmi-cpu-query",
        "abaqus",
        r"getwmi[^\r\n]*(?:failed|available\s*\(-1\))|"
        r"number of cpus.*available\s*\(-1\)",
        "Abaqus could not determine available CPUs through Windows WMI",
        "The process lacks normal desktop/WMI permission, so Abaqus reports the available "
        "CPU count as -1 and aborts before datacheck.",
        [
            "Run the Abaqus adapter with normal desktop user permissions.",
            "Confirm WMI access and retry with cpus=1.",
            "Require DAT evidence and a completion marker; never trust exit code 0 alone.",
        ],
        recommended_tool="run_abaqus_datacheck",
        recovery="automatic",
    ),
    _rule(
        "abq-missing-section",
        "abaqus",
        r"elements?.*(?:missing|have no).*(?:property|section)|"
        r"section.*(?:not defined|missing)|material.*(?:not defined|missing)",
        "Abaqus material or section assignment is incomplete",
        "One or more element sets do not have a valid material/section definition.",
        [
            "Identify the affected ELSET from the DAT/MSG file.",
            "Create or correct the material and *SOLID SECTION assignment.",
            "Rerun datacheck before adding more loads or interactions.",
        ],
        recommended_tool="run_abaqus_datacheck",
        approval_required=True,
    ),
    _rule(
        "abq-zero-pivot",
        "abaqus",
        r"zero pivot|numerical singularity|system matrix.*singular",
        "Abaqus system is singular or underconstrained",
        "Boundary conditions, connectors, contact, or material stiffness leave one or more "
        "unrestrained or zero-stiffness degrees of freedom.",
        [
            "Read the reported node and degree of freedom from MSG/DAT.",
            "Check rigid-body motion, disconnected regions, contact activation, and material stiffness.",
            "Do not add arbitrary constraints; obtain approval before changing physical boundary conditions.",
        ],
        recovery="guided",
        approval_required=True,
    ),
    _rule(
        "abq-increment-failure",
        "abaqus",
        r"too many attempts made for this increment|time increment required is less than|"
        r"minimum time increment",
        "Abaqus could not converge within the increment controls",
        "Nonlinearity, contact changes, damage evolution, or an overly large increment "
        "prevented equilibrium.",
        [
            "Inspect the first failing increment and the dominant residual/contact diagnostics.",
            "Check loads, contact, material data, units, and damage stabilization before reducing increments.",
            "Retry with a justified smaller initial increment or stabilization only after preserving solver intent.",
        ],
        recovery="guided",
        approval_required=True,
    ),
    _rule(
        "abq-distortion-volume",
        "abaqus",
        r"excessive distortion|negative volume|zero or negative volume|"
        r"determinant.*(?:zero|negative)",
        "Abaqus detected invalid or severely distorted elements",
        "Mesh quality, contact penetration, material softening, or load increments caused "
        "an element Jacobian/volume failure.",
        [
            "Locate the reported elements and inspect their initial and deformed quality.",
            "Check mesh transitions, contact, units, material damage, and increment size.",
            "Remesh locally or change solver controls only after identifying the physical cause.",
        ],
        recommended_tool="validate_abaqus_mesh",
        approval_required=True,
    ),
    _rule(
        "abq-set-not-found",
        "abaqus",
        r"(?:node|element) set.*(?:not defined|not found|has not been defined)|"
        r"(?:nset|elset).*(?:unknown|missing)",
        "Abaqus references a missing NSET or ELSET",
        "A load, boundary condition, section, interaction, or output request points to a "
        "set that was renamed, omitted during export, or defined in a missing include.",
        [
            "Find every reference to the missing set and compare it with exported set names.",
            "Restore component ELSETs when HyperMesh emitted only HW_COMPONENT comments.",
            "Rerun mesh validation and datacheck after repairing the set contract.",
        ],
        recommended_tool="ensure_component_elsets",
        recovery="automatic",
    ),
    _rule(
        "abq-contact-overclosure",
        "abaqus",
        r"overclosure|initial penetration|contact.*penetration",
        "Abaqus contact starts with overclosure or penetration",
        "The initial geometry, surface orientation, clearance, or contact adjustment policy "
        "is inconsistent.",
        [
            "Inspect the named contact pair/surface and quantify initial penetration.",
            "Check normals, offsets, thickness, tie/contact duplication, and intended clearance.",
            "Require approval before enabling automatic adjustment that changes initial geometry.",
        ],
        recovery="guided",
        approval_required=True,
    ),
    _rule(
        "abq-license",
        "abaqus",
        r"license.*(?:checkout|server).*(?:fail|denied|unavailable)|"
        r"unable to connect to license server",
        "Abaqus license checkout failed",
        "The license server is unreachable, the token pool is exhausted, or the local "
        "license configuration is invalid.",
        [
            "Check the license server address and network reachability.",
            "Inspect token availability and wait rather than repeatedly launching jobs.",
            "Do not treat a license failure as a model failure.",
        ],
        recovery="manual",
    ),
    _rule(
        "abq-static-increment-order",
        "abaqus",
        r"initial time increment is larger than.*maximum time increment",
        "Abaqus initial increment exceeds the configured maximum",
        "The *STATIC parameters are internally inconsistent; Abaqus will clamp the initial "
        "increment to the maximum.",
        [
            "Set the initial increment less than or equal to the maximum increment.",
            "Confirm the complete *STATIC parameter order and intended step time.",
            "Rerun datacheck and keep the warning visible until corrected.",
        ],
        severity="medium",
        recovery="guided",
        approval_required=True,
    ),
    _rule(
        "abq-altair-comment-metadata",
        "abaqus",
        r"Altair_XML_Export|parameter.*appears in a comment line.*not defined|"
        r"substitution of parameters failed",
        "Abaqus interpreted Altair metadata inside comment lines",
        "HyperMesh exported XML-like metadata that triggers Abaqus parameter-substitution "
        "warnings even though it is not solver input.",
        [
            "Confirm all warnings originate only from comment metadata.",
            "Strip the optional metadata block in a derived deck if clean logs are required.",
            "Do not suppress unrelated Abaqus warnings.",
        ],
        severity="low",
        recovery="automatic",
    ),
    _rule(
        "abq-datacheck-error",
        "abaqus",
        r"abaqus/datacheck exited with error|analysis datacheck.*(?:failed|not complete)",
        "Abaqus datacheck did not complete",
        "The input processor, license/runtime environment, or model definition failed before "
        "a valid datacheck completion gate.",
        [
            "Inspect stdout, stderr, DAT, and MSG together; the process exit code is insufficient.",
            "Run diagnose_cae_failure again with the full diagnostic log to find a specific cause.",
            "Do not submit a full analysis until datacheck produces completion evidence.",
        ],
        recommended_tool="run_abaqus_datacheck",
        recovery="guided",
        sources=[
            "https://docs.software.vt.edu/abaqusv2025/English/"
            "SIMACAECAERefMap/simacae-c-anaconcmonitor.htm"
        ],
    ),
]


def _load_log(log_path: str | None) -> tuple[str, list[dict[str, str]]]:
    if not log_path:
        return "", []
    path = Path(log_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Diagnostic log does not exist: {path}")
    if path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError(
            f"Diagnostic log exceeds {MAX_LOG_BYTES} bytes; provide a focused excerpt."
        )
    return (
        path.read_text(encoding="utf-8", errors="replace"),
        [{"path": str(path), "role": "diagnosed-log"}],
    )


def _detect_application(text: str) -> str | None:
    scores = {"solidworks": 0, "hypermesh": 0, "abaqus": 0}
    for rule in RULES:
        if rule["pattern"].search(text):
            scores[rule["application"]] += 1
    markers = {
        "solidworks": (r"\bsolidworks\b", r"\bsldworks\b", r"\.sldprt\b"),
        "hypermesh": (r"\bhypermesh\b", r"\bhmopengl\b", r"\*createmark\b"),
        "abaqus": (r"\babaqus\b", r"\*step\b", r"\bdatacheck\b"),
    }
    for application, patterns in markers.items():
        scores[application] += sum(
            1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE)
        )
    best = max(scores, key=scores.get)
    return best if scores[best] else None


def _load_learned_rules(
    knowledge_paths: list[str] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not knowledge_paths:
        return [], []
    if len(knowledge_paths) > MAX_KNOWLEDGE_FILES:
        raise ValueError(
            f"no more than {MAX_KNOWLEDGE_FILES} knowledge files are allowed"
        )
    learned: list[dict[str, Any]] = []
    artifacts: list[dict[str, str]] = []
    for raw_path in knowledge_paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Knowledge registry does not exist: {path}")
        if path.stat().st_size > MAX_KNOWLEDGE_BYTES:
            raise ValueError(f"Knowledge registry exceeds the supported size: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        for rule in payload.get("rules", []):
            if rule.get("knowledge_status") != "verified":
                continue
            application = str(rule.get("application", "")).lower()
            signature_terms = rule.get("signature_terms") or []
            if application not in APPLICATIONS - {"auto"} or not signature_terms:
                continue
            learned.append(rule)
        artifacts.append({"path": str(path), "role": "failure-rule-registry"})
    return learned, artifacts


def _match_learned_rule(rule: dict[str, Any], text: str) -> str | None:
    terms = [
        str(term).strip()
        for term in rule.get("signature_terms", [])
        if str(term).strip()
    ]
    lowered = text.lower()
    hits = [term for term in terms if term.lower() in lowered]
    mode = str(rule.get("match_mode", "all")).lower()
    matched = bool(hits) if mode == "any" else len(hits) == len(terms)
    return hits[0][:300] if matched else None


def diagnose_cae_failure(
    application: str = "auto",
    stage: str | None = None,
    log_text: str | None = None,
    log_path: str | None = None,
    knowledge_paths: list[str] | None = None,
) -> ToolResult:
    started = time.monotonic()
    normalized_application = application.strip().lower()
    if normalized_application not in APPLICATIONS:
        return ToolResult(
            status="failed",
            error=f"application must be one of {sorted(APPLICATIONS)}",
        )
    try:
        file_text, artifacts = _load_log(log_path)
        learned_rules, knowledge_artifacts = _load_learned_rules(knowledge_paths)
        artifacts.extend(knowledge_artifacts)
        combined = "\n".join(part for part in (log_text or "", file_text) if part)
        if not combined.strip():
            return ToolResult(
                status="needs_input",
                checks={
                    "required_evidence": [
                        "log_text excerpt or log_path",
                        "application when automatic detection is ambiguous",
                        "workflow stage if known",
                    ]
                },
                error="Provide an error message or diagnostic log.",
                elapsed_seconds=time.monotonic() - started,
            )

        detected = _detect_application(combined)
        selected = detected if normalized_application == "auto" else normalized_application
        matches: list[dict[str, Any]] = []
        for rule in RULES:
            if selected and rule["application"] != selected:
                continue
            evidence = rule["pattern"].search(combined)
            if not evidence:
                continue
            matches.append(
                {
                    "code": rule["code"],
                    "application": rule["application"],
                    "title": rule["title"],
                    "severity": rule["severity"],
                    "cause": rule["cause"],
                    "matched_evidence": evidence.group(0)[:300],
                    "recommended_actions": rule["actions"],
                    "recovery": rule["recovery"],
                    "recommended_tool": rule["recommended_tool"],
                    "approval_required": rule["approval_required"],
                    "knowledge_origin": "embedded",
                    "sources": rule["sources"],
                }
            )
        for rule in learned_rules:
            if selected and rule["application"] != selected:
                continue
            evidence = _match_learned_rule(rule, combined)
            if not evidence:
                continue
            matches.append(
                {
                    "code": rule["code"],
                    "application": rule["application"],
                    "title": rule["title"],
                    "severity": rule.get("severity", "high"),
                    "cause": rule["cause"],
                    "matched_evidence": evidence,
                    "recommended_actions": rule["recommended_actions"],
                    "recovery": rule.get("recovery", "guided"),
                    "recommended_tool": rule.get("recommended_tool"),
                    "approval_required": bool(rule.get("approval_required", True)),
                    "knowledge_origin": "verified-web-research",
                    "sources": rule.get("sources", []),
                    "verification_evidence": rule.get("verification_evidence", []),
                }
            )
        matches.sort(
            key=lambda item: (SEVERITY_ORDER[item["severity"]], item["code"])
        )
        generic_actions = [
            "Preserve the exact input artifact and all application logs.",
            "Identify the first causal error rather than later cascade messages.",
            "Apply one bounded repair, then rerun the smallest relevant check.",
            "Escalate to the user before changing geometry, material, contact, loads, or boundary conditions.",
            "Record the failure signature, repair, and verification result in the case history.",
        ]
        warnings = []
        status = "succeeded"
        if not matches:
            status = "needs_input"
            warnings.append(
                "No known failure signature matched. Provide a larger focused excerpt, "
                "the application version, workflow stage, and the first generated error file."
            )
        return ToolResult(
            status=status,
            artifacts=artifacts,
            checks={
                "requested_application": normalized_application,
                "detected_application": detected,
                "selected_application": selected,
                "stage": stage,
                "matched_issues": matches,
                "match_count": len(matches),
                "recovery_ladder": generic_actions,
                "embedded_knowledge_rules": len(RULES),
                "learned_knowledge_rules": len(learned_rules),
                "knowledge_rules": len(RULES) + len(learned_rules),
            },
            warnings=warnings,
            application={"name": "CAX Workflow diagnostic engine", "version": "0.1.0"},
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )
