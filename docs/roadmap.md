# Development roadmap

The roadmap is organized by user-visible workflow completion, not by internal
module count.

## Phase 1 — Resumable adapter foundation

- SolidWorks template inspection, parameterization, rebuild, and neutral export.
- HyperMesh native-model inspection and Abaqus export.
- Abaqus deck validation, datacheck, job inspection, and ODB structure summary.
- Case manifests, stage planning, previews, logs, and evidence gates.
- First cross-application failure diagnostic rules.
- Official-documentation-first web research and verified local rule promotion.

## Phase 2 — Automated modeling and meshing

- SolidWorks assembly and multi-body workflow adapters.
- Reviewed template libraries for laminate and repair geometries.
- HyperMesh import, topology cleanup, partitioning, component/ply organization.
- Mesh Controls, Map, Thin Solids, quality repair, and interface-node policies.
- Recovery loops for non-sweepable solids, source/target errors, and poor quality.

Implemented MVP: explicit-ID mapping for unmeshed solids, C3D8R assignment,
quality checks, overlap prevention, and bounded smoothing. Geometry cleanup,
partition/ply authoring, explicit source/target hints, and Thin Solids remain.

## Phase 3 — Solver-ready Abaqus workflow

- Materials, orientations, sections, cohesive/contact definitions.
- Steps, loads, constraints, output requests, and deck composition.
- Approval-gated submission, monitoring, cancellation, and bounded retries.
- Recovery knowledge for singularity, contact, convergence, distortion, and damage.

Implemented MVP: approval-gated submission, evidence-based monitoring,
cancellation, and policy-limited retry. Solver setup authoring remains.

## Phase 4 — Postprocessing and reporting

- Contours, probes, paths, XY data, failure indices, and interface results.
- Comparison across intact, cohesive, and repair configurations.
- Tables, images, reports, and full provenance.

Implemented MVP: field extrema and CSV tables, node-list paths, contour PNGs,
and extraction of Abaqus-computed composite failure fields. Cross-case
comparison and formatted reports remain.

## Phase 5 — Evaluation and extensibility

- Versioned error knowledge with reproducible cases.
- Workflow benchmarks and recovery success metrics.
- Additional CAD, meshing, solver, and postprocessing MCP adapters.
- Specialist agents only after stage contracts and evaluations are stable.
