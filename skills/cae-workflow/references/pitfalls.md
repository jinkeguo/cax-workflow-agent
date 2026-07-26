# CAE Workflow Pitfalls

Record failures discovered in real work. Add a regression check when practical.

| # | Pitfall | Failure | Required response |
|---|---|---|---|
| 1 | Treating a successful command exit as a saved model | Script exits zero but output was not overwritten | Reopen the exact output and query counts/geometry |
| 2 | Launching this HyperMesh installation through `hmbatch.exe` | Stub waits indefinitely before creating `hmopengl.exe` | Invoke `hmopengl.exe -batch -tcl` directly |
| 3 | Using `*newmodel` in HyperMesh 2025 Tcl | `invalid command name "*newmodel"` | Omit it in a fresh batch session |
| 4 | Omitting overwrite confirmation before `*writefile` | Build log changes while `.hm` remains old | Call `hm_answernext yes`, then verify timestamp and contents |
| 5 | Trusting Component comments as Abaqus sets | INP contains `**HW_COMPONENT` but no `ELSET` | Add and validate explicit `ELSET` definitions |
| 6 | Checking HyperMesh config only | Config is Hex8 but solver keyword may differ | Export and confirm `*ELEMENT, TYPE=C3D8R` |
| 7 | Equivalencing all coincident nodes before cohesive insertion | Interface node pairs are destroyed | Define interface policy before equivalence |
| 8 | Using geometry `Surfaces` and FE `Facets` interchangeably | Wrong entity is selected or nothing highlights | Choose selector by entity ownership |
| 9 | Applying mesh size larger than a retained repair step | Step collapses or creates poor flow | Align repair dimensions to mesh pitch or refine locally |
| 10 | Trusting Abaqus process exit code during datacheck | WMI/CPU failure prints `exited with error(s)` but the wrapper exits zero | Require DAT evidence, a completion marker, and no Abaqus error markers |
