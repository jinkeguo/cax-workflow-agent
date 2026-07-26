---
name: cae-workflow
description: Automate and recover end-to-end SolidWorks-to-HyperMesh-to-Abaqus engineering workflows through MCP adapters. Use for CAD parameterization, geometry handoff, meshing, solver setup, analysis, postprocessing, case resumption, application errors, convergence failures, mesh failures, log diagnosis, web research for unknown failures, evidence-backed recovery planning, and verified inter-application handoffs.
---

# CAE Workflow

Drive the user's engineering objective through explicit stages:

`CAD -> geometry handoff -> mesh -> solver deck -> solve -> postprocess`

Prioritize completing the cross-application workflow. Use verification as the
gate that permits automation to continue, not as the final user value.

## Decision Router

Load only the reference required by the current stage:

| Task | Read or run |
|---|---|
| Plan or execute the full three-application chain | Read `references/end-to-end-automation.md` |
| Plan or resume a full case | Read `references/workflow-contract.md` |
| Work with HyperMesh and Abaqus | Read `references/hypermesh-abaqus.md` |
| Work with SolidWorks CAD | Read `references/solidworks.md` |
| Design or extend MCP tools | Read `references/mcp-contracts.md` |
| Review architecture and prior art | Read `references/design-notes.md` |
| Diagnose an error or failed stage | Call `diagnose_cae_failure`, then read `references/error-recovery.md` |
| Research an unknown error on the web | Read `references/web-failure-research.md` |
| Diagnose a previously observed pitfall | Read `references/pitfalls.md` |
| Start a new case manifest | Adapt `references/case-manifest.example.json` |
| Independently validate an Abaqus hex mesh | Run `scripts/validate_abaqus_mesh.py` |
| Repair missing component ELSETs | Run `scripts/ensure_abaqus_elsets.py` |
| Validate a case manifest | Run `scripts/validate_case_manifest.py` |

1. Translate the user's engineering objective into CAD, mesh, solver, and result deliverables.
2. Call `get_cae_capabilities`; distinguish implemented, unavailable, and planned adapters.
3. Create or read the case manifest and call `plan_next_action`.
4. Execute the next bounded MCP operation.
5. If it fails, preserve logs and call `diagnose_cae_failure`.
6. If no known rule matches, call `prepare_failure_research`, search the web, and
   pass extracted evidence to `evaluate_failure_research`.
7. Apply deterministic recovery automatically only when it preserves engineering intent.
8. Ask before changing geometry, mesh policy, material, contact, loads, constraints, or solve cost.
9. Validate the recovered artifact and continue the workflow.
10. Promote a web-derived candidate with `record_verified_failure_rule` only after
    local recovery evidence exists; then record the stage result.

Keep native geometry, native mesh, solver deck, job artifacts, and postprocessed
results as separate versioned artifacts. A process exit code alone is never a stage gate.

## Recovery Loop

Use this sequence for every failed application operation:

`detect -> classify -> explain -> recover/ask -> retry bounded operation -> verify -> learn`

- Identify the first causal error, not only downstream cascade messages.
- Return practical user advice even when no automatic adapter exists.
- Prefer a recommended MCP tool when the repair is implemented.
- Stop and request a decision when recovery changes physical or modeling intent.
- Add recurring validated failures to the knowledge references and deterministic rules.
- Never treat search rank, repeated forum advice, or an AI summary as verification.

For HyperMesh 2025 and Abaqus work:

- Use `inspect_hm_model` to establish component, solid, surface, node, and element counts.
- Use `mesh_hm_solids` only with reviewed solid IDs and a derived output path. It
  intentionally refuses solids whose owning components already contain elements
  to prevent overlapping meshes, and assigns generated Hex8 elements to C3D8R.
- Use `check_hm_mesh_quality` after meshing. Treat aspect-ratio limits for thin
  laminate solids as a project policy, not a universal default.
- Use `smooth_hm_solid_mesh` only on explicit element IDs after previewing the
  node-coordinate change; rerun quality and geometry-deviation checks afterward.
- Use `export_abaqus_deck` only when an output path is explicit. Do not overwrite unless the user approved it.
- Use `ensure_component_elsets` after HyperMesh export when element blocks lack named ELSETs.
- Use `validate_abaqus_mesh` before adding materials, interactions, loads, or submitting a solve.
- Use `get_case_status` to verify case-manifest artifacts and determine the next incomplete stage.
- Use `plan_next_action` to select one deterministic next tool call and its arguments.
- Use `record_case_stage` first with `confirm_write=false` to show the pending manifest
  update. Only repeat with `confirm_write=true` after approval and include the inspected
  manifest SHA-256 plus a stable idempotency key.
- Use `get_abaqus_environment` before the first solver operation in a new installation.
- Run `run_abaqus_datacheck` before any full solve. It accepts flattened decks only.
- Use `inspect_abaqus_job` to classify existing job artifacts without launching software.
- Use `submit_abaqus_job` only after datacheck and explicit solve-cost approval.
  Monitor with `monitor_abaqus_job`; use `cancel_abaqus_job` only for a running
  job and only after termination confirmation.
- Use `retry_abaqus_job` only for runtime-transient, restored-license, or
  user-cancelled cases. Convergence or model failures require a reviewed new deck.
- Use `summarize_abaqus_odb` for read-only step, frame, instance, field-output,
  and set discovery.
- Use `extract_abaqus_field`, `extract_abaqus_path`, and
  `render_abaqus_contour` for traceable JSON/CSV/PNG results.
- Use `extract_abaqus_failure_indices` only for fields Abaqus actually wrote.
  If no supported field is present, recommend the required output request; do
  not invent a failure index from unrelated fields.
- Treat a stage reported as `planned` by `get_cae_capabilities` as unsupported; do not
  improvise a vendor automation call or report that stage as complete.

For SolidWorks work:

- Call `get_solidworks_environment` before the first CAD operation.
- Call `test_solidworks_connection` when COM availability must be verified on a
  workstation. A successful registry check alone is not proof of a live COM connection.
- Use `inspect_solidworks_document` for read-only feature, body, configuration, bounding-box,
  and named-dimension evidence.
- Use `instantiate_solidworks_template` to create a new `.SLDPRT` from a reviewed template.
  Pass fully qualified dimension names such as `D1@ParentPlateSketch`.
- Use `export_solidworks_document` for STEP, Parasolid, or IGES handoff.
- Preview every write before setting `confirm_write=true`; never modify the source template.

## Safety Boundaries

Read-only inspection and derived validation may run automatically.

Require user approval before overwriting authoritative files, changing design or solver intent,
deleting artifacts, or launching an expensive solve. Never report success from process exit alone;
return entity counts, mesh checks, artifact paths, logs, warnings, and elapsed time.

## HyperMesh Runtime

Use the core `hmopengl` executable with `-batch -tcl`. Configure it with
`CAE_HM_EXECUTABLE` when automatic discovery does not find the installation. Some
`hmbatch` wrappers can remain idle without starting HyperMesh, so every call must
have a timeout and retain logs in an isolated run directory.
