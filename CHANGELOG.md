# Changelog

All notable changes to CAX Workflow Agent are documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

- Fix Abaqus submission previews so the confirmation boundary does not require
  a locally installed Abaqus runtime.
- Continue expanding guided HyperMesh partition, ply, and source-target
  workflows.
- Add tested application-version evidence for additional workstation
  configurations.

## [0.1.0] - 2026-07-26

### Added

- Codex plugin manifest, CAE workflow skill, and MCP server with 32 tools.
- SolidWorks COM discovery, live handshake, template parameterization,
  rebuild, staged save, and STEP/Parasolid/IGES export.
- HyperMesh native-model inspection, Abaqus deck export, solid-map meshing,
  C3D8R assignment, mesh-quality checks, and bounded smoothing.
- Abaqus deck validation and repair, datacheck, job control, retry policy, ODB
  queries, field/path extraction, contour rendering, and failure-index
  collection.
- Resumable case manifests, deterministic next-action planning, diagnostic
  rules, official-documentation research preparation, and locally verified
  recovery-rule promotion.
- Windows CI for Python 3.9 and 3.12, MIT licensing, security guidance, and
  contributor documentation.

[Unreleased]: https://github.com/jinkeguo/cax-workflow-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jinkeguo/cax-workflow-agent/releases/tag/v0.1.0
