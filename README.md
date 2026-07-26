# CAX Workflow Agent

[![Tests](https://github.com/jinkeguo/cax-workflow-agent/actions/workflows/test.yml/badge.svg)](https://github.com/jinkeguo/cax-workflow-agent/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)

**Agentic CAD-to-simulation automation with MCP adapters and engineering
recovery knowledge.**

CAX Workflow Agent is an open-source Codex plugin whose primary goal is to
connect the complete engineering chain:

```text
SolidWorks modeling
  -> STEP / Parasolid handoff
  -> HyperMesh geometry preparation and meshing
  -> Abaqus model setup and analysis
  -> ODB postprocessing and engineering reports
```

The intended user experience is not “call one checker at a time.” A user
describes the engineering objective, and the Agent plans the workflow, calls
the required applications through MCP, diagnoses failures, proposes or applies
bounded recovery actions, and continues until it reaches a result or a decision
that requires engineering approval.

## Product priorities

### 1. End-to-end CAx workflow automation

Coordinate SolidWorks, HyperMesh, and Abaqus as one resumable workflow rather
than three isolated applications:

- create or parameterize geometry;
- export and verify neutral CAD;
- organize geometry, parts, plies, components, and interfaces;
- generate and repair meshes;
- create solver-ready sets and input decks;
- run datacheck, analysis, and job monitoring;
- extract ODB results and generate engineering summaries.

Each stage consumes explicit artifacts and hands verified outputs to the next
stage. Case state allows the Agent to resume after a manual edit, application
restart, or failed operation.

### 2. Engineering-aware diagnosis and recovery

When an application fails, the Agent should:

1. preserve the input, first causal error, and application logs;
2. classify the failure using application and workflow knowledge;
3. explain the likely cause in engineering language;
4. recommend the next bounded action;
5. automatically recover when the repair is deterministic and safe;
6. ask for approval when geometry, mesh policy, material, contact, loads, or
   boundary conditions would change;
7. rerun the smallest relevant check and record what worked.

The first diagnostic engine covers common SolidWorks COM/dimension/rebuild
failures, HyperMesh batch/map/property/topology failures, and Abaqus runtime,
set, section, convergence, contact, distortion, license, and datacheck errors.
When no rule matches, it can prepare version-aware web searches, rank extracted
evidence by authority and relevance, and create a candidate rule. A candidate
becomes reusable knowledge only after a local repair and validation pass.

### 3. MCP-native application integration

MCP is a central feature, not an implementation detail. It gives the Agent
small, typed, composable tools for each engineering application:

```text
Codex Agent
  -> CAE workflow and recovery Skill
  -> MCP orchestration layer
       -> SolidWorks COM adapter
       -> HyperMesh Tcl/batch adapter
       -> Abaqus deck/runtime/ODB adapter
  -> artifacts, logs, checks, and case history
```

The MCP boundary makes adapters independently testable, allows new CAx
applications to be added without rewriting the Agent, and prevents unrestricted
GUI or shell automation from becoming the workflow contract.

### 4. Verification as the workflow foundation

Correctness checks support the automation instead of replacing it. A process
exit code, visible mesh, or generated file is never sufficient by itself.
Every completed stage should return artifacts, structured checks, warnings,
logs, application version, and elapsed time.

## Current capabilities

CAX Workflow Agent currently exposes **32 MCP tools**.

| Area | Current implementation | Maturity |
|---|---|---|
| Workflow | Case manifests, artifact checks, deterministic next-action planning, stage recording | Implemented |
| Diagnosis | Embedded and locally learned rules through `diagnose_cae_failure` | Implemented, expanding |
| Web research | Official-doc-first queries, evidence ranking, candidate rules, verified local promotion | Implemented |
| SolidWorks | Detect COM, perform a no-document live handshake, inspect documents, instantiate parameterized part templates, rebuild, save, export STEP/Parasolid/IGES | Implemented |
| HyperMesh | Detect runtime, inspect native `.hm` models, enumerate entities, export Abaqus decks | Implemented |
| HyperMesh automation | Explicit-ID solid-map meshing for unmeshed solids, C3D8R assignment, 3D Jacobian/aspect/min-length checks, and bounded solid smoothing | Implemented MVP; generic partition/ply/source-target adapters remain guided |
| Abaqus deck | Restore component ELSETs; validate types, connectivity, bounding box, volume, and C3D8R center Jacobians | Implemented |
| Abaqus solve | Query environment, run evidence-gated datacheck, inspect existing job files | Implemented |
| Abaqus submission | Approval-gated background submission, evidence-based monitoring, cancellation, and policy-limited retry | Implemented |
| Abaqus post | Read ODB structure and instances; extract extrema/tables and node-list paths; render contours; collect Abaqus-computed composite failure indices | Implemented |
| Reporting | Traceable JSON/CSV/PNG artifacts | Implemented MVP; cross-case comparison and document reports remain planned |

This table is intentionally explicit: the project is a working adapter and
orchestration foundation, not yet a universal one-prompt CAE automation system.

## Example recovery interaction

```text
User: Abaqus datacheck failed. Here is the DAT file.

Agent:
  1. calls diagnose_cae_failure;
  2. identifies a missing ELSET and recommends ensure_component_elsets;
  3. previews a derived repaired deck;
  4. requests approval if solver intent would change;
  5. reruns run_abaqus_datacheck;
  6. records the repaired artifact, completion marker, warnings, and logs.
```

The same recovery loop applies to missing SolidWorks dimensions, failed
rebuilds, HyperMesh batch timeouts, non-sweepable solids, free nodes, missing
properties, Abaqus singularities, increment failures, contact overclosure, and
element distortion.

## SolidWorks template workflow

The current CAD adapter is template-driven. Supply a reviewed `.SLDPRT`
template and fully qualified SolidWorks dimension names:

```json
{
  "D1@ParentPlateSketch": 100.0,
  "D2@ParentPlateSketch": 20.0,
  "D1@ParentPlateExtrude": 2.0
}
```

Values cross the public interface in millimetres and are converted to
SolidWorks system units at the COM boundary. The adapter rebuilds a staged copy,
never the source template, and can export STEP, Parasolid, or IGES.

See [the parameter example](examples/step-repair-cad-parameters.example.json)
and [the SolidWorks contract](skills/cae-workflow/references/solidworks.md).
For a licensed-workstation smoke test, follow the
[SolidWorks live test guide](docs/solidworks-test-guide.md).
Proprietary SolidWorks templates are not distributed.

## Requirements

- Codex with local plugin and MCP support
- Python 3.9 or newer
- Windows and pywin32 for the default SolidWorks COM bridge
- One or more supported commercial applications

Portable tests do not require commercial applications.

## Configuration

Application discovery checks an explicit environment variable, then `PATH`,
then common vendor installation locations.

| Variable | Purpose |
|---|---|
| `CAE_SOLIDWORKS_EXECUTABLE` | Optional `SLDWORKS.exe` override |
| `CAE_SOLIDWORKS_BRIDGE` | `python` (default when pywin32 is available) or legacy `powershell` |
| `CAE_HM_EXECUTABLE` | HyperMesh `hmopengl.exe`/`hmopengl` |
| `CAE_ABAQUS_TEMPLATE` | HyperMesh `standard.3d` Abaqus export template |
| `CAE_ABAQUS_COMMAND` | Abaqus launcher such as `abaqus.bat` |
| `CAE_POWERSHELL_COMMAND` | PowerShell executable for the SolidWorks bridge |
| `CAE_RUN_ROOT` | Optional parent directory for isolated operation logs |

No workstation-specific paths are committed. See
[configuration.md](docs/configuration.md).

## Install as a Codex plugin

Clone the repository:

```powershell
git clone https://github.com/jinkeguo/cax-workflow-agent.git
cd cax-workflow-agent
python -m pip install -e .
```

Add or copy the repository directory into your Codex plugin marketplace, then
install `cax-workflow-agent` from that marketplace. The plugin manifest is
`.codex-plugin/plugin.json`; the MCP server is declared in `.mcp.json`.

For local development:

```powershell
$env:PYTHONPATH = "$PWD\mcp"
python -m unittest discover -s tests -v
```

Reinstall the plugin and start a new Codex task after every local plugin update.
Release archives are source snapshots; generated `*.egg-info`, caches,
commercial CAx files, solver outputs, and workstation configuration must not be
included.

## Safety boundary

- Read-only inspection and diagnosis may run automatically.
- Deterministic repairs write derived artifacts and preserve originals.
- Existing outputs are not overwritten by default.
- Geometry, mesh policy, material, contact, loads, and boundary-condition
  changes require approval.
- Expensive full analyses require an explicit submission boundary.
- Missing applications or adapters are reported honestly.

## Project status

This is an early public-release candidate. The MCP transport, previews, staging,
diagnosis rules, mesh validation, HyperMesh inspection/solid mapping/quality
checks/smoothing, Abaqus datacheck/job control, and ODB extraction have portable
tests. HyperMesh 2025 and Abaqus 2022 have been exercised on real local
artifacts, including C3D8R remeshing, field/path extraction, and contour
rendering. The SolidWorks COM adapter has also been live-verified on a licensed
Windows workstation, including its no-document handshake through
`test_solidworks_connection`.

See the [architecture](docs/architecture.md) and
[development roadmap](docs/roadmap.md). Release history is recorded in
[CHANGELOG.md](CHANGELOG.md).

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Do not
commit proprietary CAD, mesh, solver, result, or license-server data.

## License

MIT. See [LICENSE](LICENSE).

## Vendor notice

CAX Workflow Agent is independent and is not affiliated with or endorsed by
Dassault Systèmes, SolidWorks, Altair, HyperMesh, or Abaqus. Product names
describe interoperability only.
