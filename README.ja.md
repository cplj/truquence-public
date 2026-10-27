[English](README.md) · [Traditional Chinese](README.zh-Hant.md) · [Japanese](README.ja.md) · [Korean](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

> **メンテナンスモード。** このプロジェクトは現在積極的には開発されていません。Issue や Pull Request に返信できない場合があります。

n8n の実行は成功と表示されています。出力は正しかったでしょうか？

*この文言は草案です。確認待ちです。*

```sh
pip install truquence
```

エクスポートしたワークフローの実行記録を、明示した期待結果とオフラインで照合します。

## 使用例

- [n8n: ワークフローの出力](docs/workflows.md#n8n)
- [Make: シナリオのログ](docs/workflows.md#make-scenario-log-adapter)
- [Action Contract: 合成データによる証拠](docs/quickstart.md)

## AI エージェント向け

インストール後、使用例に従ってください。以下のコマンドと制限事項は全言語で同一です。

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

機械翻訳を補助に使用しています。修正を歓迎します。 [翻訳の問題を報告](https://github.com/cplj/truquence-public/issues/new?template=translation.yml).
