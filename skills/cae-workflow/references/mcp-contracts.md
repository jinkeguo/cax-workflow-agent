# MCP and Agent Contracts

## Architecture

```text
CAE Agent
  -> CAE workflow skill
  -> stage adapters
       -> CAD MCP
       -> meshing MCP
       -> solver MCP
       -> postprocessing MCP
  -> artifact store and case manifest
```

The Agent chooses stages and handles state. Each MCP tool performs one bounded operation and returns structured evidence.

## Common Tool Envelope

Every mutating tool should accept:

- `case_id`
- explicit input artifact path or opaque artifact ID
- output path or output role
- operation-specific parameters
- `dry_run` when feasible
- `idempotency_key`

Every result should return:

- `status`: `succeeded`, `failed`, or `needs_input`
- produced artifacts
- raw log paths
- structured checks
- warnings
- application/version information
- elapsed time

Do not return only natural-language success.

## Initial MCP Surface

### CAD adapter

- open/create document
- set parameters and dimensions
- rebuild
- enumerate bodies/features
- export STEP/Parasolid
- capture preview

### HyperMesh adapter

- open/save native model
- set solver profile
- enumerate Parts/Components/Solids
- run Tcl or Python automation
- generate mesh
- run checks
- export solver deck

### Solver adapter

- datacheck
- submit job
- poll status
- stop job
- collect logs and result database

### Post adapter

- list steps/frames/fields
- extract scalar or path data
- render contours
- export tables and provenance

## Approval Boundaries

Require explicit user approval before:

- overwriting authoritative CAD or native CAE files
- deleting geometry, mesh, jobs, or results
- launching an expensive or long-running solve
- changing dimensions, materials, BCs, contacts, or solver intent
- publishing or sharing artifacts externally

Read-only inspection and derived validation artifacts may run automatically.

## Agent Evolution

Start with one orchestrator. Add specialist agents only when:

- stage contracts are stable;
- tools return structured evidence;
- representative evaluations exist;
- handoff failures are measurable;
- specialization improves success rather than hiding state.
