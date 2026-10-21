# Truquence components

Truquence checks supplied records against explicit expectations. Each component has a separate scope; combining their records does not establish that an external action happened.

| Component | Current entry point | Scope |
|---|---|---|
| Acceptance | Existing `truquence` command | Compare supplied execution records with a contract. |
| MCP | Installed `truquence-mcp` with `truquence[mcp]` | Verify supplied workflow JSON over stdio. |
| Recorder | [Capture and chain verification](recorder/README.md) | Installed `truquence-recorder` captures local hook events and verifies the stored hash chain. |
| Authorization | [SignWarden](https://github.com/cplj/signwarden-public) | Existing tool-policy and authorization interfaces. |
| Reconciliation | [Axiocairn](https://github.com/cplj/axiocairn-public) | Existing receipt lookup and reconciliation interfaces. |
| Observation | [Kinesift](https://github.com/cplj/kinesift-public) | Bounded execution observations and coverage reports. |
| Physical | [RoboCairn](https://github.com/cplj/robocairn-public) | Compare supplied recorded observations; no physical system runs. |

The legacy repositories retain their existing commands, imports, schemas, licenses, and versions. Their links identify components; they do not imply a combined runtime or complete observation coverage.

See [transition notes](TRANSITION.md) for the repository layout and compatibility limits.
