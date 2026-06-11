# Omni-Academic Framework 품질 고도화 개선 및 구현 방안

**작성일**: 2026-06-11
**기준 버전**: `0.6.0` (커밋 `f3939e1`)
**대상**: 후속 구현 에이전트 / 유지보수자
**선행 문서**: `handoff/project-peer-review-improvement-plan-2026-05-24.md` (구현 완료됨 — Gate/status semantics, draft 차단, review grounding hard fail)

---

## 1. 진단 요약

현재 코드베이스는 린트·테스트 기준으로 깨끗하다 (2026-06-11 실측):

- `uv run ruff check`: `All checks passed!`
- `uv run python -m pytest -q`: `135 passed, 2 skipped`
- CI(`.github/workflows/ci.yml`): lint + offline test + CLI smoke + byte-compile 게이트 동작 중

2026-05-24 개선 계획에서 지적된 gate/status 결함은 모두 해소되었다. 이번 계획의 초점은 **"게이트가 존재하는가"가 아니라 "게이트 체계가 헌법(CLAUDE.md)의 약속을 빠짐없이, 일관된 기준으로 집행하는가"**이다.

핵심 결론 5가지:

1. **출처 체인 단절**: `review` 모듈이 draft 감사에 실패한(`blocked_by_draft_audit`) run의 `draft.json`도 그대로 리뷰하고 `Accept`까지 부여할 수 있다.
2. **인용 대조 정책 비일관**: 동일한 "verbatim quote grounding" 개념을 게이트마다 다른 기준(정규화 vs 원문 그대로)으로 검사한다.
3. **헌법 §3 미이행 항목**: "토큰 비율 방어선"이 코드 어디에도 구현되어 있지 않다. 원문 손실률/커버리지를 측정하는 정량 지표가 전무하다.
4. **truncation 침묵 위험**: live LLM 응답이 `max_tokens`로 잘려도 `stop_reason`을 기록만 하고 방어하지 않는다.
5. **헌법 §4 미이행 항목**: "동적 용어집/문체 가이드 자가 생성" 메커니즘이 미구현 상태다.

---

## 2. 주요 Findings

### P1 — Fidelity 체인 결함 (즉시 수정 권장)

#### F1. Review 모듈의 출처 체인(Chain of Custody) 단절

**Severity**: High
**파일**: `omni_academic/supervisor/router.py:628-649`

`_run_review()`는 run 디렉터리에서 `draft.json`을 직접 읽는다. 이때 해당 run의 `manifest.json`을 전혀 확인하지 않는다.

문제:

- `_run_draft()`는 진단 목적으로 draft 감사 **실패 시에도** `draft.json`/`draft.md`를 기록한다(`run_store.py` 진단 정책상 의도된 동작).
- 따라서 `status=blocked_by_draft_audit`인 run을 `--module review`에 넘기면, **감사에 반려된 초안이 아무 경고 없이 피어 리뷰를 통과해 `Accept` 평결을 받을 수 있다.**
- `--mock` draft를 live review에 넘기는 경로도 동일하게 무검증이다.
- "grounding이 깨지면 통과한 산출물로 취급하지 않는다"는 README 원칙이 모듈 경계에서 끊긴다.

개선 방향:

- `_run_review()`에서 source run의 `manifest.json`을 로드해 다음을 확인한다.
  - `draft_passed`가 `true`가 아니면 기본 차단(신규 status `blocked_by_source_audit` 또는 기존 `analysis_failed` + 명시 사유).
  - source가 `mock=true`인데 현재 리뷰가 live면 manifest에 `source_mock=true`를 기록하고 콘솔 경고.
- review run manifest에 출처 추적 필드를 기록한다: `source_run_id`, `source_draft_passed`, `source_mock`.
- 단독 `draft.json` 파일 경로 입력(레거시 fallback)은 manifest가 없으므로 `source_provenance="unverified"`로 명시 기록한다.

#### F2. 인용 대조(quote grounding) 정규화 정책이 게이트마다 다름

**Severity**: High
**파일**: `omni_academic/audit/gate.py:15-17,151-166` / `audit/draft_gate.py:85` / `audit/lens_gate.py:108` / `draft/scribe.py:169` / `analyze/peer_review.py:174-189`

현재 같은 개념의 검증이 세 가지 다른 기준으로 수행된다:

| 검증 지점 | 매칭 기준 |
|---|---|
| `AuditGate` (ontology) | `_canon`: 소문자화 + 공백 단일화 (관대) |
| `DraftComplianceAuditor`, `LensComplianceAuditor`, `ScribeAgent._verify_grounding` | raw 부분문자열 (엄격) |
| `PeerReviewPanel._verify_review_grounding` | strip 후 raw 부분문자열 (엄격) |

문제:

- 동일 provider 출력이 ontology 게이트는 통과하고 draft 게이트는 반려되는 비대칭이 생긴다. 사용자는 게이트 실패가 "환각" 때문인지 "공백/대소문자/유니코드 차이" 때문인지 구분할 수 없다.
- PDF·웹 추출 원문은 NBSP(U+00A0), curly quotes(" "), soft hyphen, 줄바꿈 하이픈 등이 흔하다. raw 매칭은 이런 차이로 **참 인용을 환각으로 오판(false positive 차단)** 하고, `_canon`의 소문자화는 반대로 지나치게 관대하다.
- 정책이 각 파일에 복붙된 `_norm`/`_canon`/raw 비교로 흩어져 있어 한 곳을 고치면 나머지와 어긋난다.

개선 방향:

- 공유 모듈 `omni_academic/text/grounding.py`를 신설하고 **단일 정책**을 정의한다:

```python
import unicodedata

def canon_quote(text: str) -> str:
    """grounding 대조용 표준 정규화 — 모든 게이트가 이 함수만 사용한다.

    NFKC 정규화(전각/NBSP/리거처) + curly→straight quote + 공백 단일화.
    대소문자는 보존한다(소문자화는 검증력을 깎는 과잉 관대함).
    """
    t = unicodedata.normalize("NFKC", text or "")
    for src, dst in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"), ("­", "")):
        t = t.replace(src, dst)
    return " ".join(t.split())

def quote_in(quote: str, corpus: str) -> bool:
    return bool(canon_quote(quote)) and canon_quote(quote) in canon_quote(corpus)
```

- `AuditGate`, `DraftComplianceAuditor`, `LensComplianceAuditor`, `ScribeAgent`, `PeerReviewPanel`의 모든 quote 비교를 `quote_in()`으로 교체한다.
- 정규화로 **구제된** 매칭(raw로는 불일치, canon으로는 일치)은 `info` finding(`QUOTE_NORMALIZED_MATCH`)으로 기록해 추적 가능성을 남긴다.
- 골든 테스트: NBSP/curly quote/줄바꿈 변형 케이스가 게이트 5곳 모두에서 동일 판정을 받는지 단일 파라미터라이즈 테스트로 고정한다.

#### F3. 헌법 §3 "토큰 비율 방어선" 미구현 — 무손실 정량 지표 부재

**Severity**: High (헌법 명시 항목)
**파일**: 해당 구현 없음 (신설 대상: `omni_academic/audit/coverage.py`)

CLAUDE.md §3은 "문단 ¶ ID Binding, **토큰 비율 방어선**, Forensic Audit"을 타협 불가능한 통제 계층으로 명시하지만, 현재 구현된 것은 ID Binding과 Forensic Audit뿐이다. 산출물이 원문을 **얼마나 덮는지/잃었는지** 측정하는 지표가 없어서, 예컨대 50문단 논문에서 앞 5문단만 다룬 ontology도 "통과"로 기록된다(MockProvider는 실제로 앞 3개 블록만 사용한다 — `provider.py:184`).

개선 방향:

- `CoverageAuditor`(결정론적, LLM 불사용)를 신설해 다음을 산출한다.
  - `paragraph_coverage`: 전체 문단 수 대비, 최소 1개 노드/claim/finding이 앵커한 문단 비율.
  - `token_ratio`: 원문 공백 분리 토큰 수 대비 산출물(노드 라벨+인용 / draft 본문) 토큰 수 비율.
  - `tail_coverage`: 문서 후반 1/3 구간의 문단 커버리지(앞부분 편식 검출 — §4 자가-동기화의 전제 진단).
- 결과를 `coverage.json` artifact + manifest 필드(`paragraph_coverage` 등)로 기록하고 `report.md` Executive Summary에 표기한다.
- 기본은 **warning 게이트**(차단하지 않음)로 시작한다. 차단 임계값은 렌즈 YAML의 선택 필드(`coverage_thresholds`)로 주입 — 코어에 도메인별 임계값을 하드코딩하지 않는다(헌법 §2).
- ontology/draft/analyze 세 모듈 경로에 공통 장착한다.

#### F4. LLM 응답 truncation 침묵 위험

**Severity**: Medium-High
**파일**: `omni_academic/llm/provider.py:349-371`

`AnthropicProvider`는 `stop_reason`을 `last_usage`에 기록만 한다. `max_tokens`로 잘린 tool 입력은 (a) pydantic 검증에서 우연히 깨지거나, (b) **검증을 통과할 만큼만 잘린 채** 그대로 하류로 흘러간다. (b)의 경우 nodes/claims 일부가 조용히 유실되어도 게이트는 "존재하는 것"만 검사하므로 잡지 못한다 — F3과 결합된 무손실 위반이다.

개선 방향:

- `generate_structured_output()`에서 `stop_reason == "max_tokens"`이면 즉시 `RuntimeError`를 raise하고, 메시지에 `OMNI_LLM_MAX_TOKENS` 상향 안내를 포함한다.
- 단위 테스트: stub response로 truncation 케이스를 고정한다.

#### F5. OntologyExtractor만 self-correcting 재시도가 없음

**Severity**: Medium
**파일**: `omni_academic/ontology/extractor.py:74-90`

`ScribeAgent`(draft)와 `PeerReviewPanel`(review)은 grounding 실패를 구체 오류 메시지와 함께 피드백해 재시도하는 루프를 갖고 있지만, ontology 추출은 1회 시도 후 `AuditGate` 실패 → 즉시 `blocked_by_audit`이다. live 경로에서 인용 한 글자 차이로 전체 run(특히 `--module draft`의 1단계)이 차단된다.

개선 방향:

- `_run_ontology()`/`_run_draft()`의 추출 단계에 동일 패턴의 재시도 루프(기본 `max_attempts=2`)를 도입한다: 1차 추출 → `AuditGate` error finding을 CORRECTION 블록으로 프롬프트에 부착 → 재추출.
- `manifest.llm_usage.ontology_attempts`를 기록한다.
- F2(정규화 통일)가 선행되면 재시도 필요 빈도 자체가 줄어든다 — 구현 순서상 F2 다음에 둔다.

### P2 — 견고성/운영성

#### F6. 문단 분할기의 한계 — 검증력의 토대가 약함

**Severity**: Medium
**파일**: `omni_academic/text/paragraphs.py:12`

빈 줄(`\n\s*\n`) 기준 분할 하나뿐이다. 문제:

- pypdf 추출 텍스트는 페이지 단위 거대 블록이 되기 쉽다 → 한 문단이 수천 단어면 "quote가 해당 문단에 있는가" 검사가 사실상 "문서 전체에 있는가"로 퇴화해 검증력이 붕괴한다.
- 위치 기반 ID(`P_0001`…)는 원문이 한 문단만 바뀌어도 전부 시프트되어 run 간 비교가 불가능하다.

개선 방향:

- 분할 강화: 최대 길이(예: 공백 분리 350 토큰) 초과 블록은 문장 경계에서 하위 분할(`P_0007a` 식 파생 ID 또는 연번 유지).
- `paragraphs.json`에 문단별 `char_len`, `sha1` 기록 → run 간 diff와 안정 참조 기반 마련.
- 거대 문단(>N 토큰)이 존재하면 `COARSE_PARAGRAPH` warning finding을 AuditGate에 추가해 검증력 약화를 가시화한다.

#### F7. ForensicAuditor의 오판 가능성

**Severity**: Medium
**파일**: `omni_academic/audit/forensic.py:48-55`

`_resolves()`는 405에만 GET 폴백하고, 그 외 4xx는 모두 "resolve 실패"로 본다. User-Agent도 없다. 출판사 사이트는 봇 HEAD 요청에 403/429를 흔히 반환하므로 **실존 DOI가 `GHOST_DOI`(error)로 차단**될 수 있다 — 유령 인용 차단 장치가 거짓 양성을 만드는 역설.

개선 방향:

- 표준 User-Agent 헤더 추가.
- 403/429/503 응답은 "실존 부정"이 아니라 "검증 불확정"으로 분류 → `UNVERIFIABLE_DOI` **warning**(차단하지 않음)으로 다운그레이드. 404/410만 `GHOST_DOI` error 유지.
- 테스트: status code별 판정 매트릭스를 단위 테스트로 고정.

#### F8. LLM usage가 마지막 시도만 기록됨

**Severity**: Low-Medium
**파일**: `omni_academic/llm/provider.py:21,349-360`, `supervisor/router.py:605-608`

`last_usage`는 호출마다 덮어써진다. 재시도가 발생하면 1차 호출의 토큰 비용이 manifest에서 유실되어 비용 감사가 부정확하다.

개선 방향:

- provider에 `usage_log: list[dict]` 누적 버퍼를 추가하고(`last_usage`는 호환 유지), router는 `usage_log` 전체와 합산(`total_input_tokens`/`total_output_tokens`)을 manifest에 기록한다.

#### F9. 렌즈 YAML 스키마 검증 부재

**Severity**: Low-Medium
**파일**: `omni_academic/config/lens.py:38-48`

`load_lens()`는 `yaml.safe_load` 후 dict를 그대로 반환한다. 오타 필드(`focus_area:` 단수형 등)는 조용히 무시되어 렌즈가 빈 지시로 동작한다 — 어댑터 주입이 핵심 메커니즘(헌법 §2)인 만큼 주입 실패는 시끄럽게 알려야 한다.

개선 방향:

- `LensConfig` pydantic 모델(`extra="allow"`) 도입: 알려진 필드 타입 검증 + 알 수 없는 top-level 키는 warning 출력.
- `--list-lenses`에 검증 결과(OK/warning) 컬럼 추가.
- 기존 dict 반환 인터페이스는 유지(점진 전환)하거나 `model_dump()`로 호환.

#### F10. 모델 선택이 코드 상수에 고정됨

**Severity**: Low
**파일**: `omni_academic/llm/provider.py:221`, `supervisor/router.py:71-76`

`DEFAULT_MODEL = "claude-opus-4-7"`이 유일한 경로다. 생성자는 `model` 인자를 받지만 `_make_provider()`가 전달하지 않는다.

개선 방향:

- `OMNI_LLM_MODEL` 환경변수 지원(`_make_provider`에서 주입), `--status` 진단 화면과 `.env.example`에 항목 추가. 모델명은 이미 `llm_usage.model`로 manifest에 기록되므로 추적성은 확보되어 있다.

### P3 — 아키텍처 고도화 (중기)

#### F11. Peer Review가 단일 LLM 호출의 페르소나 시뮬레이션

**Severity**: Medium (설계 의도와의 간극)
**파일**: `omni_academic/analyze/peer_review.py:121-158`

"4인 패널 + Chief Editor"가 실제로는 **한 번의 `generate_structured_output` 호출**로 생성된다. 한 모델이 한 컨텍스트에서 모든 페르소나를 쓰므로 관점 간 상관이 높고, 점수도 동일 분포에서 나온다. 진정한 다각 비평(독립성)이라 보기 어렵다.

개선 방향:

- 패널리스트별 **독립 호출**(panelist 단일 스키마 `PanelistReview`) 4회 + Chief Editor 종합 호출 1회로 분리하는 `--independent-panel` 모드를 추가한다.
  - 각 호출은 해당 패널리스트의 지침만 받는다(타 패널 피드백 비공개 → 앵커링 차단).
  - grounding 검증·재시도는 패널리스트 단위로 수행(실패 격리).
  - 비용은 약 5배 — 기본값은 현행 single-shot 유지, 플래그 opt-in. manifest에 `review_mode` 기록.
- MockProvider에 `PanelistReview` 단일 스키마 분기 추가로 오프라인 테스트 유지.

#### F12. 헌법 §4 "동적 용어집/문체 가이드" 미구현

**Severity**: Medium (헌법 명시 항목)
**파일**: 해당 구현 없음 (신설 대상: `omni_academic/analyze/glossary.py`)

입력 텍스트를 스캔해 동적 용어집(Dynamic Glossary)·문체 가이드를 생성하고 하네스에 장착하는 메커니즘이 없다. 현재 draft/analyze 프롬프트는 렌즈 정적 설정만 주입받는다.

개선 방향 (MVP):

1. **추출**: 문서 앞부분(예: 첫 30문단)에서 LLM이 `GlossaryReport`(용어, 정의 인용 `paragraph_id`+`source_quote`, 문체 관찰)를 생성 — 기존 source-bound 패턴 그대로.
2. **감사**: 용어 정의 인용을 `LensComplianceAuditor`와 동일한 결정론 게이트로 검증(환각 용어 차단) → `glossary.json` artifact.
3. **장착**: draft/analyze 프롬프트에 "검증된 용어집" 블록으로 주입. 미생성 시 현행 동작과 동일(opt-in `--glossary`).
- TRE 등 외부 용어 참조 필터는 **이 프레임워크에 넣지 않는다** — 공유용 독립 도구 제약(vault 비결합) 유지. 필요 시 사용자가 렌즈 YAML로 주입한다.

#### F13. recon/engine.py 모놀리스 (1,190줄)

**Severity**: Low (동작 문제 없음, 유지보수성)
**파일**: `omni_academic/recon/engine.py`

8개 API 클라이언트(arXiv/KCI/OpenAlex/PubMed/DBLP/EconBiz/SemanticScholar/Scholar)와 엔진·digest 로직이 한 파일에 있다. 헌법 §5의 plug-and-play 의도라면 클라이언트당 한 파일이 자연스럽다.

개선 방향:

- `recon/clients/` 패키지로 클라이언트 분리, `engine.py`는 레지스트리/오케스트레이션만 유지. `from omni_academic.recon.engine import XxxClient` 재수출로 기존 import·테스트 경로 보존.
- 순수 기계적 이동(동작 변경 0) — 별도 커밋으로 분리해 리뷰 가능성 확보.

#### F14. 테스트 커버리지 측정 부재

**Severity**: Low
**파일**: `pyproject.toml`, `.github/workflows/ci.yml`

137개 테스트가 있으나 커버리지 사각지대(예: live provider 오류 분기, `status.py` 진단 화면)가 측정되지 않는다.

개선 방향:

- `pytest-cov`를 dev extra에 추가, CI에 `--cov=omni_academic --cov-report=term` 리포트 출력(처음에는 fail 임계값 없이 가시화만). 측정 후 사각지대 기준으로 후속 테스트를 정한다.

---

## 3. 구현 로드맵

### Phase 1 — Fidelity 체인 완결 (F2 → F4 → F1 → F3)

목표: "게이트를 통과한 산출물만 다음 단계에 들어가고, 통과 기준은 어디서나 같다."

| 순서 | 작업 | 대상 파일 | 신규 테스트 |
|---|---|---|---|
| 1 | `text/grounding.py` 신설 + 5개 게이트 정책 통일 (F2) | `audit/gate.py`, `audit/draft_gate.py`, `audit/lens_gate.py`, `draft/scribe.py`, `analyze/peer_review.py` | NBSP/curly quote/개행 변형의 게이트 간 동일 판정 파라미터라이즈 테스트 |
| 2 | `stop_reason=max_tokens` hard fail (F4) | `llm/provider.py` | truncation stub 테스트 |
| 3 | review 출처 체인 검증 (F1) | `supervisor/router.py`, `supervisor/run_status.py`, `store/run_store.py` | blocked draft → review 차단 / mock draft → live review 경고 기록 / 단독 파일 입력 `unverified` 기록 |
| 4 | `CoverageAuditor` + `coverage.json` (F3) | `audit/coverage.py`(신설), `supervisor/router.py`, `store/run_store.py`, `SCHEMAS.md` | 커버리지 계산 골든 테스트, manifest 필드 계약 테스트 |

완료 기준:

- 게이트 전부가 `grounding.canon_quote` 단일 정책 사용 (`grep -rn "_canon\|quote not in\|q in corpus"`로 잔존 자체 구현 0건).
- `blocked_by_draft_audit` run을 리뷰하면 `review.json`이 생성되지 않고 차단 status가 기록된다.
- 모든 ontology/draft/analyze run의 manifest에 `paragraph_coverage`가 기록된다.
- 기존 137개 테스트 무손상 통과.

### Phase 2 — 견고성/운영성 (F5, F6, F7, F8, F9, F10)

| 작업 | 대상 파일 |
|---|---|
| ontology 추출 audit-feedback 재시도 (F5) | `supervisor/router.py` 또는 `ontology/extractor.py` |
| 문단 분할 강화 + `COARSE_PARAGRAPH` 경고 (F6) | `text/paragraphs.py`, `audit/gate.py` |
| ForensicAuditor 판정 매트릭스 정밀화 (F7) | `audit/forensic.py` |
| usage 누적 로그 (F8) | `llm/provider.py`, `supervisor/router.py` |
| `LensConfig` 스키마 검증 (F9) | `config/lens.py` |
| `OMNI_LLM_MODEL` (F10) | `supervisor/router.py`, `supervisor/status.py`, `.env.example` |

완료 기준: 각 항목 단위 테스트 + `SCHEMAS.md`/`USER_GUIDE.md` 갱신. F6은 기존 golden fixture(`tests/test_schema_contracts.py`)가 깨지지 않는 ID 정책을 선택했는지 확인.

### Phase 3 — 아키텍처 고도화 (F11, F12, F13, F14)

- 독립 패널 리뷰 모드(F11)와 동적 용어집(F12)은 **비용이 드는 opt-in 기능**으로 추가하고 기본 경로는 바꾸지 않는다.
- recon 클라이언트 분리(F13)는 기능 작업과 절대 섞지 않는 순수 리팩터 커밋.
- 커버리지 가시화(F14)는 Phase 3 시작 전에 깔아 사각지대 데이터를 먼저 얻는 것도 무방.

---

## 4. 권장 작업 순번 (요약)

1. **F2 grounding 정책 통일** — 다른 모든 게이트 작업의 토대. 가장 먼저.
2. **F4 truncation hard fail** — 작고 위험 제거 효과 큼.
3. **F1 review 출처 체인** — fidelity 체인의 마지막 구멍.
4. **F3 CoverageAuditor** — 헌법 §3 완성. warning부터.
5. **Phase 2 일괄** — 견고성. 각 항목 독립 커밋 가능.
6. **Phase 3** — opt-in 고도화 + 리팩터.

---

## 5. 검증 명령 (각 Phase 공통)

```bash
uv run ruff check
uv run python -m pytest -q
uv run omni ./examples/sample.md --module draft --lens general --mock
uv run omni runs/examples-sample-md/latest --module review --lens general --mock
uv run omni --verify-run examples-sample-md/latest
```

추가로 Phase 1 이후에는 의도적 실패 경로를 수동 확인한다:

```bash
# blocked draft run을 리뷰에 넘겨 차단되는지 확인 (scripted provider 테스트로도 고정)
uv run python -m pytest tests/test_peer_review.py tests/test_draft.py -q
```

---

## 6. 비범위 (Non-Goals)

- **OpenAI/Gemini provider 실구현**: 예약 경계 유지(`provider.py`의 placeholder 정책 그대로).
- **vault/번역 파이프라인 연동**: 본 프로젝트는 공유용 독립 도구다. TRE 용어 필터 등 개인 워크플로 자산을 코어에 넣지 않는다.
- **게이트 완화**: 어떤 개선도 error를 warning으로 낮추는 방향이어서는 안 된다(단, F7처럼 **애초에 오판이던 것**의 정정은 완화가 아니라 정확화다).
- **풀 스타일 린트 전수 정리**: `ruff` select 확대는 별도 작업.

---

## 7. 구현 완료 기록

### Phase 1 — 완료 (2026-06-11)

| Finding | 커밋 | 비고 |
|---|---|---|
| F2 grounding 정책 통일 | `6bdff4a` | `text/grounding.py` 신설, 게이트 5곳 + 재시도 검증기 3곳(`ScribeAgent`/`LensAnalyzer`/`PeerReviewPanel`) 교체, `QUOTE_NORMALIZED_MATCH` info finding, 파라미터라이즈 테스트 19건 |
| F4 truncation hard fail | `59ef025` | `stop_reason=max_tokens` 시 RuntimeError + `OMNI_LLM_MAX_TOKENS` 안내, fake client 테스트 3건 |
| F1 review 출처 체인 | `12769a3` | `blocked_by_source_audit` status 신설, `source_run_id`/`source_draft_passed`/`source_mock`/`source_provenance` manifest 기록, 차단·unverified 경로 테스트 |
| F3 CoverageAuditor | `b1a6866` | `audit/coverage.py` 신설, ontology/draft/analyze 경로 장착, `coverage.json` + manifest 미러링 + report.md 표기, 렌즈 `coverage_thresholds` 옵션, 테스트 6건 |

완료 기준 검증 (2026-06-11 실측):

- `uv run ruff check`: 통과
- `uv run python -m pytest -q`: `165 passed, 2 skipped` (기존 135 + 신규 30)
- 게이트 자체 quote 매칭 잔존 0건: `grep -rn "_canon|quote not in" omni_academic/` (grounding.py 제외) 매치 없음
- mock CLI 스모크: draft → review → `--verify-run` 전 구간 통과, review run manifest에 `source_provenance=manifest`/`source_draft_passed=true` 기록 확인, draft run에 `coverage.json` + coverage manifest 필드 기록 확인
- `blocked_by_draft_audit` run 리뷰 차단은 `test_router_review_blocked_when_source_draft_failed`로 고정

### Phase 2 — 완료 (2026-06-11)

| Finding | 커밋 | 비고 |
|---|---|---|
| F5 ontology 재시도 | `ca2fd39` | `OntologyExtractor`에 grounding 검증 + CORRECTION 재시도(기본 2회), `llm_usage.ontology_attempts` 기록, draft 경로에서 usage 병합(덮어쓰기 버그 함께 수정) |
| F6 문단 분할 강화 | `fffe61f` | 350토큰 초과 블록을 문장 경계에서 하위 분할(연번 `P_\d+` 유지, 토큰 시퀀스 무손실), AuditGate `COARSE_PARAGRAPH` 경고. 콘텐츠 해시 사이드카는 paragraphs.json 계약 보존을 위해 보류 |
| F7 Forensic 정밀화 | `c2afe41` | User-Agent 추가, 판정 매트릭스: 404/410만 `GHOST_DOI`(error), 403/429/5xx/네트워크 오류는 `UNVERIFIABLE_DOI`/`UNVERIFIABLE_URL`(warning, 비차단) |
| F8 usage 누적 | `2a004b9` | provider 인스턴스별 `usage_log`, manifest에 `<step>_calls` + `<step>_total_input/output_tokens` (기존 키 호환 유지) |
| F9 렌즈 스키마 검증 | `a6db7be` | pydantic `LensConfig`(extra 허용), 타입 위반 시 `LensConfigError`, 미지 키 `lens_warnings()`, `--list-lenses` Validation 컬럼 |
| F10 모델 env | `66e1488` | `OMNI_LLM_MODEL` 주입, `--status`에 `OMNI_LLM_MODEL`/`OMNI_LLM_MAX_TOKENS` 진단 행, `.env.example`/문서 갱신 |

완료 기준 검증 (2026-06-11 실측):

- `uv run ruff check`: 통과
- `uv run python -m pytest -q`: `198 passed, 2 skipped` (Phase 1 종료 시점 165 + 신규 33)
- 번들 렌즈 7종 전부 `LensConfig` 계약 통과(`test_all_bundled_lenses_satisfy_contract`)
- mock CLI 스모크: draft → review → `--verify-run` 전 구간 통과
- `--status`/`--list-lenses` 신규 진단 표기 실측 확인

## 8. 후속 에이전트 주의사항

- 각 Finding은 독립 커밋으로 구현하고, 커밋마다 위 검증 명령을 통과시킨다.
- MockProvider 성공 경로만으로 판단하지 말 것 — 실패 경로는 scripted provider로 반드시 고정한다(기존 `tests/test_peer_review.py`의 패턴 참조).
- `SCHEMAS.md`는 manifest/artifact 필드를 추가할 때마다 같은 커밋에서 갱신한다(golden 계약 테스트가 어긋남을 잡아준다).
- `handoff/`는 gitignore 대상이다. 이 문서(`QUALITY_IMPROVEMENT_PLAN.md`)는 추적 대상이며, 구현 완료 시 각 Finding에 완료 커밋 해시를 추기한다.
