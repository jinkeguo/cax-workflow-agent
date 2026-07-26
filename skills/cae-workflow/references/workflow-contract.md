# CAE Workflow Contract

## Stage Model

| Stage | Required input | Primary output | Minimum gate |
|---|---|---|---|
| `cad` | dimensions, topology intent, units | native CAD plus neutral CAD | reopen succeeds; body/part counts and bounding box match intent |
| `mesh` | verified geometry, mesh plan | native preprocessor model plus mesh export | element/node counts, type, grouping, connectivity, Jacobian/volume, and interface policy pass |
| `deck` | verified mesh, physics definition | solver input deck | materials, sections, sets, orientations, steps, contacts, BCs, loads, and outputs resolve |
| `solve` | verified deck | solver database and logs | solver completes; errors are zero; warnings are classified; balance/convergence checks pass |
| `post` | verified results | tables, plots, report, derived metrics | requested quantities are reproducible and traceable to result database and frame |

Never use a later-stage result to claim an earlier stage is correct unless the later check actually covers the earlier requirement.

## Case Manifest

Use `case-manifest.example.json` as the starting schema. The manifest is the future Agent's durable state, not a substitute for raw artifacts.

Required top-level fields:

- `schema_version`
- `case_id`
- `objective`
- `units`
- `solver`
- `stages`
- `artifacts`

Each stage uses one status: `pending`, `in_progress`, `passed`, `failed`, or `skipped`. `skipped` requires a reason.

Each artifact records:

- `path`
- `role`
- `produced_by`
- optional `sha256`
- optional `evidence`

Run:

```text
python scripts/validate_case_manifest.py <manifest.json>
```

## Evidence Bundle

Store compact machine-readable evidence beside human-readable summaries:

- geometry: dimensions, bounding box, part/body/solid counts
- mesh: component/set counts, node/element counts, type distribution, connectivity checks, quality extrema
- deck: keyword inventory, unresolved references, unit declaration, load/BC summary
- solve: exit status, analysis status, increments, cutbacks, warnings/errors, reactions and energy checks
- post: result database path, step/frame identifiers, extraction script version, plotted quantities

## Handoff Rule

A stage handoff contains:

1. immutable input reference
2. produced artifact
3. gate evidence
4. unresolved warnings
5. next-stage assumptions

If any item is missing, keep the current stage active.
