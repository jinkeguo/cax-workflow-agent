# Design Notes and Prior Art

The Agent separates four concerns:

1. The Skill holds domain workflow, acceptance gates, and failure knowledge.
2. MCP tools perform bounded application operations and return structured evidence.
3. The case manifest stores cross-stage state and artifact provenance.
4. Codex performs orchestration, approvals, retries, and user-facing teaching.

## Referenced projects

- `lyj24240-sketch/hypermesh-new-interface-skill`
  - https://github.com/lyj24240-sketch/hypermesh-new-interface-skill
  - Used as the HyperMesh 2023+ interface knowledge baseline.
- `dbwls99706/ros2-engineering-skills`
  - https://github.com/dbwls99706/ros2-engineering-skills
  - Inspired the decision-router layout, progressive disclosure, failure registry,
    and factual regression-test approach.

No vendor automation code was copied from these repositories. The HyperMesh and Abaqus
adapters in this plugin were implemented and tested against the local installations.

## MCP protocol

The zero-dependency stdio server follows JSON-RPC 2.0 and MCP protocol version
`2025-06-18`. The transport layer can later be replaced by the official Python SDK
without changing the CAE tool contracts.
