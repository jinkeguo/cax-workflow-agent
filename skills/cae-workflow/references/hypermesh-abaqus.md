# HyperMesh to Abaqus

## Current Baseline

- HyperMesh: 2025 new interface
- Solver profile: Abaqus `Standard3D`
- Native model: `.hm`
- Solver deck: `.inp`
- Preferred structured laminate solid: `C3D8R`

## Mesh Gate

Verify:

1. Every intended ply or part is represented by a named Component.
2. Every solid element belongs to exactly one intended Component.
3. Element type exported to Abaqus is the intended keyword, not only the HyperMesh config.
4. No element references a missing node.
5. No duplicate connectivity exists.
6. Hex center Jacobian determinants are positive.
7. Bounding box and total element volume match geometric intent.
8. Interface-node policy is explicit:
   - shared nodes for a continuous bonded interface;
   - coincident independent nodes for later cohesive insertion or contact;
   - mixed policies must be documented by interface.
9. Abaqus `ELSET` and `NSET` definitions exist when later stages depend on grouping.

Use `scripts/validate_abaqus_mesh.py` on the exported deck. Use `scripts/ensure_abaqus_elsets.py` when HyperMesh emitted `**HW_COMPONENT` comments but omitted actual `ELSET` parameters.

## HyperMesh Batch

Some `hmbatch` launchers can remain idle before creating their `hmopengl` child.
Use the core executable directly:

```text
hmopengl.exe -batch -tcl <script.tcl>
```

Set `CAE_HM_EXECUTABLE` if it is not available on `PATH` or under a common Altair
installation directory.

Do not use `*newmodel`; it is not a valid HyperMesh Tcl Modify Command in the observed 2025 environment. A new batch session already starts with an empty model. When overwriting an `.hm` file, call `hm_answernext yes` before `*writefile`.

## Teaching Path

For a sweepable ply:

1. Open `3D ribbon > Map`.
2. Set the main selector to `Solids`.
3. Disable automatic source/target detection when it chooses side faces.
4. Select the bottom face as `Source` and the upper face as `Target`.
5. Set in-plane density or source mesh size.
6. Use one element through a physical ply unless the analysis requires more.
7. Confirm the exported Abaqus type after meshing.

Use `Surfaces` only for geometric face selection, `Facets` for calculated FE faces, and `Elements` for existing mesh.
