# Architecture

CAX Workflow Agent separates workflow reasoning, recovery knowledge, application
execution, and evidence:

```text
Engineering objective
  -> Codex Agent
       -> CAE workflow and recovery Skill
       -> case planner and state
       -> MCP orchestration layer
            -> SolidWorks COM adapter
            -> HyperMesh Tcl/batch adapter
            -> Abaqus deck/runtime/ODB adapter
       -> artifacts, logs, checks, and recovery history
```

## Skill

`skills/cae-workflow/SKILL.md` tells Codex how to sequence the full CAx chain,
diagnose failed stages, select recovery actions, and decide where approval is
required.

## MCP server

`mcp/cae_agent/mcp_server.py` is the cross-application execution layer. It
exposes typed JSON-RPC/MCP tools over standard input and output. This boundary
makes vendor adapters composable, independently testable, and replaceable.
Tools return a common `ToolResult` containing status, artifacts, checks,
warnings, logs, application metadata, elapsed time, and an optional error.

## Adapters

- `solidworks.py` uses a pywin32 COM bridge by default for document inspection,
  template parameterization, rebuild, save, and neutral export. A legacy
  PowerShell STA bridge remains available as an explicit fallback.
- `hypermesh.py` launches a fresh HyperMesh batch process with a generated Tcl
  operation and retains its run directory.
- `abaqus.py` performs solver-independent input-deck repair and validation.
- `abaqus_runtime.py` runs isolated Abaqus queries/datachecks and reads existing
  job evidence; it also provides approval-gated submit, monitor, cancel, and
  bounded retry operations.
- `abaqus_post.py` runs Abaqus Python/Viewer scripts for field tables and
  extrema, node-list paths, contour PNGs, and solver-computed composite failure
  fields.
- `diagnostics.py` classifies known failure signatures and returns causes,
  bounded recovery actions, approval boundaries, and recommended MCP tools.
- `research.py` prepares official-documentation searches, evaluates extracted
  web evidence, and records locally verified failure rules with provenance.
- `manifest.py` records case-stage evidence with previews, hashes, and
  idempotency keys.
- `planner.py` chooses one deterministic next action from case state.

## Trust boundary

Vendor applications are outside the MCP process. An adapter must verify output
artifacts and diagnostic files before returning success. A zero process exit
code by itself is not sufficient evidence. Verification supports continued
automation; it is not the product's only purpose.
