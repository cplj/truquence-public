[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

Your n8n run shows green. Was the output right?

*Draft wording; awaiting confirmation.*

```sh
pip install truquence
```

Check exported workflow runs against explicit expectations, offline.

## Examples

- [n8n: Workflow output](docs/workflows.md#n8n)
- [Make: Scenario logs](docs/workflows.md#make-scenario-log-adapter)
- [Action Contract: Synthetic evidence](docs/quickstart.md)

## For AI agents

Install, then follow a walkthrough. Commands and limits below are identical across editions.

`truquence --help` · `truquence accept --help`

[Input/output schemas](docs/contracts.md) · [Workflow reference](docs/workflows.md) · [Agent reference](llms.txt) · [Recorder](recorder/README.md)

<!-- limits:start -->
Python 3.10+. FAIL and UNKNOWN block acceptance. Define expectations independently.
Supplied exports only; no workflow execution or live-state verification.
Make checks identity, status and operation count, not outputs or side effects.
Synthetic evidence does not prove external execution. Unsigned reports establish
neither authenticity, completeness, authorization nor business acceptance.
No report grants retry permission. Retain partial files; use a fresh output prefix.
<!-- limits:end -->

Machine-assisted translations; corrections welcome. [Report a translation issue](https://github.com/cplj/truquence-public/issues/new?template=translation.yml).
