# Release checklist

- [x] Add the MIT open-source license.
- [x] Set the public repository metadata to
  `jinkeguo/cax-workflow-agent`.
- Run all portable tests on Python 3.9 and 3.12.
- Validate `.codex-plugin/plugin.json` and the CAE workflow skill.
- Scan for absolute workstation paths and proprietary artifacts.
- Verify that the SolidWorks PowerShell bridge is present in the wheel.
- Reinstall the plugin and confirm all 32 MCP tools in a new Codex task.
- Run an optional live SolidWorks template test on a disposable part copy.
- Record tested HyperMesh, Abaqus, and SolidWorks versions.
- Tag `v0.1.0` only after CI passes.
