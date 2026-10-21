[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

Votre exécution de n8n est au vert. Le résultat était-il correct ?

*Formulation provisoire, en attente de confirmation.*

```sh
pip install truquence
```

Comparez hors ligne les exécutions exportées aux résultats attendus définis explicitement.

## Exemples

- [n8n: Sortie du workflow](docs/workflows.md#n8n)
- [Make: Journaux du scénario](docs/workflows.md#make-scenario-log-adapter)
- [Action Contract: Preuves synthétiques](docs/quickstart.md)

## Pour les agents IA

Installez le paquet, puis suivez un exemple. Les commandes et les limites ci-dessous sont identiques dans toutes les versions.

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

Traduction assistée par machine ; les corrections sont bienvenues. [Signaler un problème de traduction](https://github.com/cplj/truquence-public/issues/new?template=translation.yml).
