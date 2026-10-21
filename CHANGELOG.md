# Changelog

## 0.3.0 (candidate)

- Include the public capture-only Recorder in the installed distribution, with truquence-recorder and legacy aliases.
- Add an optional MCP SDK extra and truquence-mcp workflow-verification entry point.
- Merge package keywords, project links and the workflow description from 0.2.1 metadata.
- Mark hook assertions as self_reported; keep authenticity and completeness UNKNOWN.

## 0.2.0

- Accept full n8n execution JSON and exported Make scenario logs with explicit local expectations.
- Generate draft contracts from n8n workflow JSON with `truquence init`.
- Add a real local n8n execution walkthrough and fail-closed error, incomplete-evidence and duplicate-run checks.
- Preserve three-checker acceptance, CSV comparison and loopback HTTP behavior.

## 0.1.0

- Local Action Contract validation and unsigned JSON/Markdown acceptance reports.
- Cross-check authorization, recovery and completion evidence; block contradictory effect counts.
- Supplied atomic-event CSV reconciliation through a CLI and loopback HTTP interface.
- Synthetic examples, schemas and regression tests; no runtime dependencies.
