# End-to-End Automation

## Objective Contract

Translate a user request into these deliverables:

1. CAD geometry and parameter contract.
2. Neutral geometry handoff.
3. Native HyperMesh model and mesh policy.
4. Solver deck with sets, materials, sections, interactions, steps, loads, and outputs.
5. Datacheck and analysis evidence.
6. ODB-derived results and report artifacts.

Record which deliverables are automatic, guided, manual, or unsupported.

## SolidWorks Stage

1. Detect the desktop COM runtime.
2. Inspect the template/document, configurations, features, bodies, and named dimensions.
3. Preview dimension changes.
4. Rebuild a staged copy and inspect rebuild evidence.
5. Save a new native document.
6. Export STEP or Parasolid.
7. Verify file existence, size, and geometry/body evidence before handoff.

Use templates for repeatable families such as intact laminates, scarf/step repair
parent plates, and repair patches. Do not invent a fragile feature tree without
an explicit design contract.

## HyperMesh Stage

1. Import or open geometry.
2. Confirm solver profile, units, scale, parts, components, solids, and surfaces.
3. Clean topology and partition geometry for the intended mesh flow.
4. Create ply/component organization and interface policy.
5. Apply mesh controls and generate 2D/3D mesh.
6. Repair failures locally.
7. Check quality and exported solver element type.
8. Save the native `.hm` model and export an Abaqus deck.

Current MCP coverage includes native-model inspection, explicit-ID solid-map
meshing for unmeshed solids, C3D8R type assignment, 3D quality checks, bounded
solid smoothing, and Abaqus export. The map adapter rejects selected solid
components that already contain elements so it cannot silently create an
overlapping mesh. Generic geometry cleanup, partitioning, ply/component
creation, explicit source/target face hints, and Thin Solids remain guided:
perform those choices in the HyperMesh UI, inspect the saved artifact, and
resume automation.

## Abaqus Stage

1. Normalize ELSET/NSET contracts.
2. Add or verify materials, sections, orientations, interactions, steps,
   boundary conditions, loads, and output requests.
3. Validate mesh/deck structure.
4. Run datacheck and diagnose every error/warning.
5. Obtain approval for an expensive full analysis.
6. Submit, monitor, stop, or recover the job through bounded adapters.
7. Inspect ODB structure and extract requested results.
8. Generate plots, tables, comparisons, and provenance.

Current MCP coverage includes deck normalization/validation, datacheck,
approval-gated job submission, monitoring, cancellation, bounded retry, ODB
structural summaries, field extrema/tables, node-list paths, contour PNGs, and
extraction of Abaqus-computed composite failure fields. Full setup authoring,
cross-case comparison, and formatted engineering report generation require
additional adapters.

## Resume Contract

After any manual operation or application restart:

1. Inspect the exact artifact on disk.
2. Compare its hash, timestamp, counts, and expected role with the case manifest.
3. Mark the previous stage passed only with evidence.
4. Continue from the first incomplete stage.

Never restart the full chain when a verified intermediate artifact can be reused.
