[English](README.md) · [Traditional Chinese](README.zh-Hant.md) · [Japanese](README.ja.md) · [Korean](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

> **Maintenance mode.** This project is not actively developed. Issues and pull requests may not receive a response.

Check supplied workflow runs against explicit expectations, capture local hook events, and verify a receipt ledger offline.

## Install

Python 3.10+. Recorder commands require POSIX; native hook setup also needs `/usr/bin/cc`.

```sh
python -m pip install truquence
truquence --help
truquence-recorder --help
```

Core and Recorder use the standard library. Add MCP:

```sh
python -m pip install 'truquence[mcp]'
truquence-mcp --help
```

For the unreleased 0.3.0 candidate, install its local wheel. PyPI 0.2.0 has no MCP or Recorder entry point.

## Record a synthetic event

```sh
printf '%s\n' '{"hook_event_name":"PreToolUse","session_id":"example-session","cwd":"/example","tool_name":"Bash","tool_use_id":"example-call","tool_input":{"command":"echo hello"}}' | truquence-recorder hook
truquence-recorder verify
```

The hook prints `{}`. Verification reports `integrity: SELF_CONSISTENT`; `authenticity` and `completeness` remain `UNKNOWN`. This writes to your local ledger. [Recorder setup and limits](recorder/README.md).

## For AI agents

Start `truquence-mcp` over stdio. Call `truquence_accept` with `contract_json`, `execution_json` and `source` (`n8n` or `make`). Each JSON text is limited to 1 MiB. [Runnable MCP example and schemas](docs/integrations.md).

Read `status` and `gateBlocked`. FAIL and UNKNOWN block acceptance; PASS concerns supplied records only. No command authorizes a retry or proves an external action happened.

Evidence levels: passive capture describes hook collection, hook assertions are `self_reported`, and supplied workflow exports are `imported`. None is independent observation.

[Acceptance](docs/quickstart.md) · [Schemas](docs/contracts.md)
