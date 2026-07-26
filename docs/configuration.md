# Configuration and runtime discovery

All application paths are optional. CAX Workflow Agent resolves them in this order:

1. explicit `CAE_*` environment variable;
2. executable on the system `PATH`;
3. common vendor installation directories.

Use `get_cae_capabilities`, `get_solidworks_environment`, and
`get_abaqus_environment` to inspect the resolved runtime.

## Windows example

```powershell
$env:CAE_SOLIDWORKS_EXECUTABLE = 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe'
$env:CAE_HM_EXECUTABLE = 'C:\Program Files\Altair\2025\hwdesktop\hw\bin\win64\hmopengl.exe'
$env:CAE_ABAQUS_TEMPLATE = 'C:\Program Files\Altair\2025\hwdesktop\templates\feoutput\abaqus\standard.3d'
$env:CAE_ABAQUS_COMMAND = 'C:\SIMULIA\Commands\abaqus.bat'
```

These are examples only. Do not copy them into `.mcp.json`; set values for the
local Codex process or maintain an uncommitted local configuration.

`CAE_RUN_ROOT` may point to a writable directory used as the parent for isolated
operation folders. If omitted, the operating-system temporary directory is used.

## SolidWorks template contract

Use fully qualified dimension names such as `D1@Sketch1`. Public values are
millimetres. The adapter copies the template into a temporary staging file,
changes dimensions, rebuilds, saves, optionally exports, and only then moves
the verified outputs into place.

## Diagnostics

If discovery fails, the capability result includes the candidate paths that
were checked and the environment variable that can override discovery. Logs
remain in the isolated run directory reported by the tool result.
