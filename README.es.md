[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

Tu ejecución de n8n aparece en verde. ¿El resultado fue correcto?

*Texto provisional, pendiente de confirmación.*

```sh
pip install truquence
```

Compara ejecuciones exportadas con expectativas explícitas, sin conexión.

## Ejemplos

- [n8n: Salida del flujo](docs/workflows.md#n8n)
- [Make: Registros del escenario](docs/workflows.md#make-scenario-log-adapter)
- [Action Contract: Evidencia sintética](docs/quickstart.md)

## Para agentes de IA

Instala el paquete y sigue un ejemplo. Los comandos y las limitaciones siguientes son idénticos en todas las versiones.

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

Traducción asistida por máquina; se agradecen las correcciones. [Informar de un problema de traducción](https://github.com/cplj/truquence-public/issues/new?template=translation.yml).
