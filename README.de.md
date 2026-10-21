[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

Dein n8n-Lauf wird grün angezeigt. War die Ausgabe richtig?

*Vorläufige Formulierung; Bestätigung steht aus.*

```sh
pip install truquence
```

Vergleiche exportierte Workflow-Läufe offline mit ausdrücklich festgelegten Erwartungen.

## Beispiele

- [n8n: Workflow-Ausgabe](docs/workflows.md#n8n)
- [Make: Szenario-Protokolle](docs/workflows.md#make-scenario-log-adapter)
- [Action Contract: Synthetische Nachweise](docs/quickstart.md)

## Für KI-Agenten

Installiere das Paket und folge einem Beispiel. Die folgenden Befehle und Einschränkungen sind in allen Sprachfassungen identisch.

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

Maschinengestützte Übersetzung; Korrekturen sind willkommen. [Übersetzungsfehler melden](https://github.com/cplj/truquence-public/issues/new?template=translation.yml).
