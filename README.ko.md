[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Deutsch](README.de.md) · [Français](README.fr.md)

# Truquence

n8n 실행이 성공으로 표시됩니다. 출력도 맞았나요?

*이 문구는 초안이며 확인을 기다리고 있습니다.*

```sh
pip install truquence
```

내보낸 워크플로 실행 기록을 명시한 예상 결과와 오프라인으로 대조합니다.

## 예제

- [n8n: 워크플로 출력](docs/workflows.md#n8n)
- [Make: 시나리오 로그](docs/workflows.md#make-scenario-log-adapter)
- [Action Contract: 합성 증거](docs/quickstart.md)

## AI 에이전트 안내

설치 후 예제를 따라 하세요. 아래 명령과 제한 사항은 모든 언어판에서 동일합니다.

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

기계 보조 번역입니다. 수정을 환영합니다. [번역 문제 신고](https://github.com/cplj/truquence-public/issues/new?template=translation.yml).
