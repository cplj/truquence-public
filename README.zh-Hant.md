[English](README.md) · [Traditional Chinese](README.zh-Hant.md) · [Japanese](README.ja.md) · [Korean](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

這次 n8n 執行顯示成功。輸出對了嗎？

*此句為草稿，待確認。*

```sh
pip install truquence
```

離線比對匯出的工作流程執行紀錄與明確的預期結果。

## 範例

- [n8n: 工作流程輸出](docs/workflows.md#n8n)
- [Make: 情境日誌](docs/workflows.md#make-scenario-log-adapter)
- [Action Contract: 合成證據](docs/quickstart.md)

## 供 AI 代理使用

安裝後依範例操作。以下指令和限制聲明在各語言版中保持一致。

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

機器輔助翻譯，歡迎修正。 [回報翻譯問題](https://github.com/cplj/truquence-public/issues/new?template=translation.yml).
