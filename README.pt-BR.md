[English](README.md) · [Traditional Chinese](README.zh-Hant.md) · [Japanese](README.ja.md) · [Korean](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

> **Modo de manutenção.** Este projeto não está em desenvolvimento ativo. Issues e pull requests podem não receber resposta.

Sua execução do n8n aparece em verde. A saída estava correta?

*Texto provisório, aguardando confirmação.*

```sh
pip install truquence
```

Compare execuções exportadas com os resultados esperados definidos explicitamente, sem conexão.

## Exemplos

- [n8n: Saída do fluxo](docs/workflows.md#n8n)
- [Make: Logs do cenário](docs/workflows.md#make-scenario-log-adapter)
- [Action Contract: Evidência sintética](docs/quickstart.md)

## Para agentes de IA

Instale o pacote e siga um exemplo. Os comandos e as limitações abaixo são idênticos em todas as versões.

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

Tradução assistida por máquina; correções são bem-vindas. [Relatar um problema de tradução](https://github.com/cplj/truquence-public/issues/new?template=translation.yml).
