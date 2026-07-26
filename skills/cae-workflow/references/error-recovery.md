# Error Diagnosis and Recovery

## Recovery Ladder

1. **Preserve**: keep the original input, command, application version, stdout,
   stderr, and native diagnostic files.
2. **Localize**: find the first causal message and the workflow stage that
   produced it.
3. **Classify**: call `diagnose_cae_failure` with the focused log and application.
4. **Explain**: state the likely engineering cause and its confidence.
5. **Recover**:
   - automatic for deterministic environment, metadata, or derived-file repairs;
   - guided for topology, meshing, convergence, and feature-tree repairs;
   - manual/approval-gated for physical modeling intent.
6. **Retry**: rerun only the smallest failed operation.
7. **Verify**: inspect native output and downstream contract.
8. **Learn**: record the signature, attempted repair, outcome, and application version.

## Common SolidWorks Classes

| Failure | First checks | Typical recovery |
|---|---|---|
| COM not registered | `SldWorks.Application`, user session, install state | Start once, repair registration/install |
| Dimension missing | Full `D1@Feature` name, configuration, suppression | Inspect document and correct template contract |
| Rebuild failed | First failed feature, parent references, parameter bounds | Restore known-good parameters; change one input |
| Save/export failed | Lock, path, overwrite, format, error code | Use staging path; preserve source; retry derived output |

## Common HyperMesh Classes

| Failure | First checks | Typical recovery |
|---|---|---|
| Batch timeout | Core process, dialogs, Tcl log | Use `hmopengl -batch -tcl`; fresh run directory |
| Invalid Tcl command | Version and command family | Replace unsupported command; rerun bounded script |
| Map/Thin Solid failure | Solid sweepability, source/target, selector, topology | Isolate Solid; choose cap surfaces; fix topology/density |
| Missing properties | Mesh-only intent versus solver-ready intent | Assign property or defer explicitly to Abaqus |
| Free node | Intentional anchor versus stale construction node | Locate, approve deletion, rerun checks |
| Wrong solver type | Exported `*ELEMENT` keyword | Correct element type mapping and re-export |

## Common Abaqus Classes

| Failure | First checks | Typical recovery |
|---|---|---|
| WMI/CPU `-1` | Desktop permissions and stderr | Run with normal user/WMI access; require DAT evidence |
| Missing section/set | Reported ELSET/NSET and keyword references | Restore set contract; assign section/material |
| Zero pivot/singularity | Node/DOF, disconnected regions, constraints | Fix physical constraint/connectivity; never add arbitrary BCs |
| Increment failure | First failed increment, residual/contact/material messages | Fix cause, then justify increment/stabilization change |
| Distortion/negative volume | Reported elements, initial/deformed quality | Local remesh or correct contact/material/load |
| Contact overclosure | Surface normals, offsets, initial penetration | Correct geometry/contact policy with approval |
| License failure | Server reachability and token availability | Wait/fix license environment; do not edit model |
| Metadata warnings | Altair XML comment block only | Strip derived metadata if desired; retain other warnings |

## Unknown Failures

When no rule matches, do not guess. Request:

- the first error plus 20–50 surrounding lines;
- application and version;
- current workflow stage;
- input artifact type;
- relevant DAT/MSG/STA, HyperMesh stdout/stderr, or SolidWorks bridge response;
- the last operation that succeeded.

Add a rule only after the cause and repair are verified on a real or reproducible case.
