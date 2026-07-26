# SolidWorks Adapter

## Scope

The SolidWorks adapter uses the desktop COM API and a reviewed parameterized-template
workflow. It detects the runtime, inspects native documents, clones `.SLDPRT` templates,
sets fully qualified dimensions, rebuilds, saves a new native part, and exports STEP,
Parasolid, or IGES.

It does not invent an unconstrained feature tree. A template preserves engineering intent,
stable feature names, and repeatable downstream topology.

## Template contract

Pass millimetre values using fully qualified SolidWorks names:

```json
{
  "D1@ParentPlateSketch": 100.0,
  "D2@ParentPlateSketch": 20.0,
  "D1@ParentPlateExtrude": 2.0
}
```

SolidWorks stores length dimensions in metres. The bridge converts millimetres at the MCP
boundary.

## Workflow

1. Call `get_solidworks_environment`.
2. Call `test_solidworks_connection`; require `connection=ok` and a returned revision.
3. Inspect the template with `inspect_solidworks_document`.
4. Review requested dimension names and current values.
5. Preview `instantiate_solidworks_template` with `confirm_write=false`.
6. After approval, repeat with `confirm_write=true`.
7. Reinspect the generated `.SLDPRT`.
8. Verify the STEP or Parasolid output before passing it to HyperMesh.

The default Windows bridge uses pywin32 dynamic `IDispatch`. This avoids relying on
PowerShell type-library binding, which can fail on otherwise usable custom SolidWorks
installations. Set `CAE_SOLIDWORKS_BRIDGE=powershell` only when the legacy bridge is required.

Inspection is read-only. Instantiation works on a staging copy, never the original template.
Existing outputs require both approval and `overwrite=true`.

Official API basis:

- `ISldWorks::OpenDoc6`
- `IModelDoc2::Parameter`
- `IDimension::SystemValue`
- `IModelDoc2::ForceRebuild3`
- `IModelDoc2::Save3` / `SaveAs3`
- `IPartDoc::GetBodies2`
- `IBody2::GetBodyBox`

https://help.solidworks.com/2025/english/api/sldworksapi/
