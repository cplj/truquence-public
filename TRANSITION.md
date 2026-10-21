# Repository transition

Truquence is the main project entry point. The existing module repositories remain available with their current package and command names.

The 0.3.0 candidate includes the public Recorder under `src/signwarden_recorder/` and installs `truquence-recorder`, `swr` and `signwarden-recorder`. Its guide remains under `recorder/`. Install the optional `truquence[mcp]` extra for the stdio MCP server. Existing module packages keep their current interfaces.

The Recorder stores supplied local hook events and checks a hash chain. It does not include policy matching, replay, consensus rules, or an inference engine. A consistent chain does not establish event completeness, authorship, source authenticity, or real tool effects.

Existing websites, package releases, server registrations, and email identities retain their current configuration. This repository update does not migrate user settings or activate a combined runtime. Review a component's input requirements and limitations before using its records for a decision.
