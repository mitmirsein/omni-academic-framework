---
title: Omni-Academic Framework v0.5.1 무자비 재검층
date: 2026-05-19
reviewer: Codex
scope: HEAD after v0.5.x improvement commits; src/, tests/, README, skills/, handoff/ 대조
requested_version: 0.5.1
observed_version: pyproject/README report 0.5.0
verification:
  pytest: "52 passed"
  mock_path_check: "failed audit with UNGROUNDED_NODE"
  scholar_self_test_default_env: "failed: ModuleNotFoundError: bs4"
  git_status_before_review: clean
---

# 0. 평결

0.4.x에 비하면 프로젝트는 확실히 살아났다. 이전 리뷰의 핵심 지적 중 상당수는 실제로 흡수되었다.

- `tests/`가 생겼고 52개 테스트가 통과한다.
- `general.yaml`, `__init__.py`, console script, optional dependency groups가 추가되었다.
- Crossref dummy DOI는 실제 REST client로 교체되었다.
- Recon routing은 `lenses/*.yaml`의 `recon_clients`로 이동했다.
- `OntologyExtractor`는 provider를 명시 주입하도록 바뀌었다.
- `AuditGate`는 paragraph manifest를 요구한다.
- `RunStore`, `ReconCache`, PDF scraper, Snowball mode가 추가되었다.

하지만 “0.5.1 완료”라고 보기엔 아직 핵심 계약 몇 개가 깨져 있다. 특히 **README가 말하는 clone 후 `--mock` 오프라인 경로가 audit에서 실패**한다. 그리고 Gate 2 Forensic은 아직 실제 gate가 아니라 sidecar report에 가깝다. “무자비한 학술 엔진”의 이름을 달려면 다음 라운드는 source-span grounding과 gate composition이 핵심이다.

# 1. 점수

| Area | Score | 판단 |
| --- | ---: | --- |
| Vision / Philosophy | 8/10 | 여전히 선명하다. |
| Implementation Progress | 6/10 | v0.4 대비 큰 진전. |
| Audit / Fidelity | 4/10 | paragraph-id grounding은 생겼지만 source-span 검증은 없다. |
| Reproducibility | 5/10 | core tests는 통과. optional skills는 여전히 전제조건 약함. |
| Truth-in-Docs | 5/10 | README가 많이 정직해졌지만 버전/범위 과장이 남아 있다. |
| Production Research Readiness | 4/10 | typed artifacts는 생겼으나 Gate 2/Analyze가 약하다. |

종합: **5.5/10**. 이전 1.5/10에서 크게 개선되었지만, 아직 “프레임워크”보다는 “검증 가능한 core PoC + 느슨한 skill layer”다.

# 2. 확인된 개선

## 2.1 AuditGate가 ground truth를 받기 시작했다

`src/audit/gate.py`의 `verify_ontology()`가 `paragraph_manifest`를 받고, manifest가 없으면 `NO_SOURCE_MANIFEST` error로 실패한다. 노드의 `paragraph_id`가 manifest에 없으면 `UNGROUNDED_NODE`로 실패한다.

이건 이전 리뷰의 가장 큰 결함이었던 “원문을 보지 않는 audit”을 부분적으로 해결한다.

## 2.2 MockProvider 기본값 제거

`src/ontology/extractor.py`는 provider를 명시 주입하지 않으면 `ValueError`를 던진다. router는 `--mock`일 때만 `MockProvider`를 만든다. 이전의 “어떤 논문을 넣어도 mock graph가 나오는 기본 경로”는 제거되었다.

## 2.3 Recon은 config-driven에 가까워졌다

`lenses/*.yaml`에 `recon_clients`가 들어갔다. `ReconEngine._resolve_clients()`는 lens config를 읽고 client factory에서 조립한다. medical/economics/theology/humanities blind spot도 PubMed/EconBiz/OpenAlex로 일부 보강되었다.

## 2.4 테스트가 생겼다

실행 결과:

```text
52 passed in 0.80s
```

테스트 범위:

- AuditGate
- ForensicAuditor
- Paragraph ID assignment
- Lens loading
- Recon client routing
- Scraper factory
- ReconCache
- Snowball mode
- RunStore / export gate
- External tool resolver

# 3. 치명 Findings

## F1. README가 약속한 `--mock` 오프라인 경로가 audit에서 실패한다

README는 “clone 후 즉시 실행은 `--mock` 경로에 한함”이라고 말한다. 그러나 실제 mock ontology는 audit를 통과하지 못한다.

확인 명령의 핵심 결과:

```text
manifest: ['P_0001', 'P_0002']
node_pids: ['P_01', 'P_02']
passed: False
codes: ['UNGROUNDED_NODE', 'UNGROUNDED_NODE']
```

원인:

- `assign_paragraph_ids()`는 `P_0001`, `P_0002` 형식을 만든다.
- `MockProvider`는 여전히 `P_01`, `P_02`를 반환한다.
- 따라서 mock run은 새 AuditGate의 핵심 규칙을 위반한다.

왜 심각한가:

- README가 보장하는 유일한 clone-immediate path가 깨져 있다.
- 테스트는 “P_01류는 실패해야 한다”만 확인하고, “router `--mock` E2E가 기대한 방식으로 끝나는지”는 확인하지 않는다.

개선:

- `MockProvider`를 manifest-aware로 만들 것.
- 프롬프트에서 `[P_0001]` 패턴을 파싱해 실제 존재하는 paragraph_id만 사용하게 할 것.
- `tests/test_router_cli.py` 또는 equivalent로 `omni <fixture> --module ontology --mock`이 manifest/audit 의미상 기대대로 동작하는지 통합 테스트할 것.

## F2. Gate 2 Forensic은 아직 gate가 아니다

`--forensic`을 켜면 `ForensicAuditor().verify_papers()` 결과가 `forensic.json`으로 저장된다. 그러나 error finding이 있어도 pipeline은 계속 HITL 선택으로 진행한다.

현재 동작:

- Forensic findings 저장: 있음
- Error findings가 있으면 paper 차단: 없음
- `RunStore.audit_passed`에 forensic 결과 반영: 없음
- Vault export gate가 forensic error를 보는지: 아님

왜 심각한가:

README는 Gate 2를 “유령 인용/가짜 DOI/죽은 URL 차단”이라고 설명한다. 하지만 지금은 “보고”만 하고 “차단”하지 않는다. 이름은 gate인데 행동은 sidecar report다.

개선:

- `ForensicReport` 모델을 만들 것.
- `RunStore` manifest에 `forensic_passed`와 finding summary를 기록할 것.
- `--forensic-strict` 기본값을 고려하거나, 최소한 error finding이 있는 paper는 HITL 후보에서 제거할 것.
- `export_to_vault()`는 `audit_passed`뿐 아니라 `forensic_passed`도 확인해야 한다.

## F3. AuditGate grounding은 아직 paragraph-id 수준이라 hallucination을 막기 어렵다

현재 `AuditGate`는 node paragraph_id가 manifest에 존재하는지만 본다. LLM이 존재하는 paragraph ID만 붙이면 내용은 얼마든지 만들어낼 수 있다.

현재 스키마 문제:

- `Node`에는 `source_quote`나 `source_span`이 없다.
- `Edge.reasoning`은 문자열 길이만 검사한다.
- 해당 reasoning이 실제 paragraph에 포함되는지 확인할 수 없다.

개선:

- `Node`에 `source_quote: str` 또는 `source_span: {paragraph_id, start, end, text}`를 추가할 것.
- `Edge`에도 `source_quote` 또는 `source_paragraph_ids`를 추가할 것.
- `AuditGate`는 quote가 해당 paragraph text에 실제 포함되는지 검사해야 한다.
- LLM provider system prompt도 source quote 필수로 강화할 것.

## F4. Analyze 모듈은 여전히 mock인데 성공처럼 말한다

`src/analyze/lens_analyzer.py`는 실제 LLM 분석을 하지 않는다. 렌즈 스펙을 출력하고 고정 성공 메시지를 찍는다.

문제:

- `router._run_analyze()`도 무조건 “최종 분석 리포트 도출 완료”를 출력한다.
- README의 “Lens Analyzer” 설명과 실제 동작이 아직 맞지 않는다.

개선:

- Analyze는 `[BLUEPRINT]`로 명시 강등하거나, 실제 provider 기반 `AnalysisReport`를 반환하게 할 것.
- 현 상태에서는 “렌즈 스펙 프리뷰” 정도로 이름을 바꿔야 정직하다.

## F5. 버전 드리프트

사용자는 0.5.1 완료라고 했지만, 실제 파일은 다음과 같다.

- `pyproject.toml`: `version = "0.5.0"`
- `README.md`: `Status: Prototype (v0.5.0)`
- HEAD에 version tag 없음

개선:

- 실제 릴리스가 0.5.1이면 pyproject, README, tag, changelog/handoff를 맞출 것.
- 아니면 사용자-facing 명칭을 0.5.0 post-improvement HEAD로 정정할 것.

## F6. `skills/` 계층은 아직 머신 로컬 경로를 품고 있다

`src/config/tools.py`와 core scraper는 `OMNI_*` 규약을 도입했지만, `skills/semantic-scholar/scripts/s2_runner.py`는 여전히 다음 경로를 하드코딩한다.

```python
load_dotenv("/Users/msn/Desktop/MS_Dev.nosync/.env")
```

스킬 문서도 output 예시에 `/Users/msn/Desktop/MS_Brain.nosync/...`를 직접 박고 있다.

개선:

- `.env` 로드는 `OMNI_ENV_FILE` 또는 repo root `.env` fallback으로 바꿀 것.
- 사용자별 output path 예시는 `--output ./Evidence/...` 등 repo-relative로 바꿀 것.
- legacy scripts는 `[LEGACY / machine-local]`로 명시하거나 별도 archive로 격리할 것.

## F7. Optional skill dependencies는 lock에는 있으나 기본 실행 경로에 없다

`uv.lock`에는 `beautifulsoup4`, `requests`, `python-dotenv`가 optional extra로 기록되어 있다. 하지만 기본 `uv run python skills/google-scholar-semantic/scripts/scholar_runner.py --self-test`는 `bs4` import 실패로 실행되지 않았다.

확인 결과:

```text
ModuleNotFoundError: No module named 'bs4'
```

개선:

- README/SKILL에 `uv run --extra scholar-browser ...` 또는 `uv sync --extra scholar-browser` 같은 정확한 명령을 명시할 것.
- `scholar_runner.py --self-test`는 import error를 친절하게 잡아 설치 안내를 출력해야 한다.
- optional runner smoke test를 CI/pytest에 넣을 경우 extra 환경에서만 돌리도록 marker를 둘 것.

## F8. KCI는 README에서 과장되어 있다

README는 KCI를 “실 API” 구현 목록에 넣는다. 그러나 코드 주석은 KCI XML 경로를 “공개 스키마 기준 추정값이며 미검증”이라고 인정한다.

개선:

- README에서는 KCI를 “adapter scaffold / schema unverified”로 낮춰 적을 것.
- 실 KCI 응답 fixture를 확보해 `_parse()` 단위 테스트를 추가할 것.

# 4. 우선순위 개선안

## P0 — Mock E2E를 살려라

- `MockProvider` paragraph ID 포맷 수정 또는 manifest-aware mock 구현
- `omni fixture.md --module ontology --mock` 통합 테스트 추가
- README의 clone-immediate promise와 테스트를 일치시킬 것

## P1 — Forensic을 진짜 Gate로 승격

- `ForensicReport` 도입
- paper 후보 filtering 또는 hard fail 옵션
- manifest/export gate에 forensic 결과 반영

## P2 — Source-span grounding 도입

- `Node.source_quote`
- `Edge.source_quote` 또는 `source_paragraph_ids`
- quote-in-paragraph mechanical audit
- LLM tool schema와 prompt 동시 변경

## P3 — Analyze의 정직성 회복

- `[BLUEPRINT]`로 강등하거나 실제 `AnalysisReport` 구현
- 고정 성공 메시지 제거

## P4 — Skill layer 이식성 정리

- `/Users/msn/...` 하드코딩 제거
- optional extra 실행 명령 보정
- `skills/semantic-scholar`와 `google-scholar-semantic` self-test 경로 정비

## P5 — Version hygiene

- 0.5.1이면 pyproject/README/tag 맞춤
- 아니면 문서에 “HEAD after v0.5.0 improvements”라고 명시

# 5. 검증 로그

## 통과

```text
uv run python -m pytest
52 passed in 0.80s
```

## 실패 / 위험 확인

```text
MockProvider + assign_paragraph_ids + AuditGate
passed: False
codes: ['UNGROUNDED_NODE', 'UNGROUNDED_NODE']
```

```text
uv run python skills/google-scholar-semantic/scripts/scholar_runner.py --self-test
ModuleNotFoundError: No module named 'bs4'
```

```text
uv run python -c "import requests, dotenv, bs4"
ModuleNotFoundError: No module named 'dotenv'
```

## 작업트리

검층 전후 `git status --short`는 clean이었다. 이 문서 생성 후에는 `handoff/peer-review-v0.5.1-2026-05-19.md`만 새 파일로 추가된다.

# 6. 최종 판단

v0.5.x 개선은 방향이 맞다. 특히 AuditGate, lens registry, RunStore, tests는 이전 상태와 비교하면 실질적 전진이다.

그러나 다음 라운드의 기준은 더 엄격해야 한다. 이제 “목업을 걷어냈다”가 아니라 “검증 경로가 실제로 실패와 통과를 올바르게 나눈다”를 증명해야 한다. 그 첫 관문은 `--mock` E2E 통과, Forensic hard gate, source-span audit이다.
