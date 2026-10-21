[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

这次 n8n 运行显示成功。输出对了吗？

*此句为草稿，待确认。*

```sh
pip install truquence
```

离线比对导出的工作流运行记录与明确的预期结果。

## 示例

- [n8n: 工作流输出](docs/workflows.md#n8n)
- [Make: 场景日志](docs/workflows.md#make-scenario-log-adapter)
- [Action Contract: 合成证据](docs/quickstart.md)

## 供 AI 代理使用

安装后按示例操作。以下命令和限制声明在各语言版中保持一致。

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

机器辅助翻译，欢迎修正。 [报告翻译问题](https://github.com/cplj/truquence-public/issues/new?template=translation.yml).
