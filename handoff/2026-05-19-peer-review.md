---
title: Omni-Academic Framework 무자비 피어리뷰
date: 2026-05-19
reviewer: Claude Opus 4.7 (claude-opus-4-7) — Claude Code
scope: src/ 전체(~250줄) + README/CLAUDE.md/SKILL.md/lenses/workflows 대조
commit: d8993f3 (v0.4.0)
---

# 평결 (Verdict)

문서는 v4.0 팔란티어 정보전 엔진을 약속하지만, 코드는 v0.1 목업이다. README·CLAUDE.md·SKILL.md가 묘사하는 시스템과 `src/`에 실재하는 시스템 사이에 두 자릿수의 격차가 있다. 이 프로젝트의 가장 큰 결함은 버그가 아니라 **문서가 아키텍처가 아니라 희망사항(aspirational fiction)을 사실처럼 서술하고 있다**는 점이다.

---

# 1. 치명적 결함 — 핵심 가치가 미구현 베이퍼웨어

## (1) "심장"이라던 3중 Audit Gate가 존재하지 않는다
CLAUDE.md §3은 무손실 하네스를 "타협 불가능한 최우선 통제 계층"이라 선언하고, README §3은 Gate 1/2/3을 명시한다. 실제 `src/audit/gate.py`는:

- **Gate 1 (¶ ID 바인딩 / 토큰 비율)** — 코드에 없음. `paragraph_id`는 그냥 문자열 필드이며 원문 대조 로직 0줄.
- **Gate 2 (유령 인용 / 가짜 DOI 교차검증)** — 없음. DOI ping 코드 없음.
- **Gate 3 (스키마/렌즈 컴플라이언스, self-redteaming)** — 없음.

실재하는 것은 고립 노드·셀프루프·짧은 reasoning 문자열을 보는 ~30줄짜리 그래프 위생 검사뿐. 프레임워크의 "가장 빛나는 지점"이라 광고한 것이 통째로 비어 있다.

## (2) Audit는 환각을 구조적으로 잡을 수 없다
`verify_ontology(ontology)` 는 원문을 인자로 받지 않는다. 그래프 내부 형태만 본다. 잘 연결되고 reasoning이 10자만 넘으면 완전히 날조된 온톨로지도 100점으로 통과한다. `paragraph_id`가 원문에 실존하는지 검증하지 않으므로 "할루시네이션의 여지를 원천 차단"(README §1)은 거짓 — 감사기에 ground truth 접근 자체가 없어 환각 탐지가 원리적으로 불가능하다.

## (3) 파이프라인 전체가 MockProvider 위에서 돈다
`OntologyExtractor`는 `MockProvider`를 기본값으로 쓰고, 이건 입력과 무관하게 하드코딩된 노드 2개를 반환한다. `OpenAIProvider`/`AnthropicProvider`는 둘 다 `raise NotImplementedError`. 어떤 논문을 넣어도 결과는 동일한 가짜 노드 2개. v0.4.0 "E2E HITL 파이프라인 연결" 커밋은 아무것도 흐르지 않는 빈 파이프를 연결한 것.

---

# 2. 자기 헌법 위반 (Local Constitution §2 정면 위반)

`src/recon/engine.py:120`:
```python
"theology": [KCIClient(), CrossrefClient()],  # 신학 렌즈에서도 KCI 강력 추천
```
CLAUDE.md §2는 코어 모듈에 특정 학문(신학) 하드코딩을 명시적으로 금지한다. 주석까지 달아놓은 정면 위반. v0.3.2 "theology → omni/academic 중립화" 커밋은 스킬 이름만 바꾼 화장(cosmetic)이고 실제 하드코딩 결합은 그대로. `lens-template.md`의 `enforce_terms: [API, Transformer, LLM]`도 같은 위반. "Adapter-based Assembly / 런타임 주입" 원칙은 미구현 — 라우팅은 `api_registry` 딕셔너리 하드코딩이고 렌즈 파일은 검색 라우팅을 전혀 구동하지 않는다.

---

# 3. 정확성 버그

| # | 위치 | 문제 |
|---|------|------|
| B1 | `engine.py:42,43` | `.replace('\\n', ' ')` — 리터럴 백슬래시-n 치환. 실제 개행(`\n`)은 그대로 통과. 의도한 정규화가 전혀 동작 안 함. |
| B2 | `engine.py:42` | `entry.find('arxiv:title', ns).text` — 요소 누락 시 `None.text` → AttributeError로 gather 전체 크래시. |
| B3 | `engine.py` arXiv/KCI | `query`를 f-string에 raw 삽입. 공백·특수문자 미인코딩으로 요청 깨짐. `urllib.parse.quote` 필요. |
| B4 | `engine.py:96` | KCI: bare `except Exception` → 빈 리스트 반환. 실패와 "결과 없음" 구분 불가. Open API는 보통 `key=` 필수, XML 경로는 "규격 기준" 주석뿐 미검증 — 사실상 동작 안 할 가능성 큼. |
| B5 | `engine.py:101` | `CrossrefClient`가 기본 `general` 레지스트리에 들어 있으면서 가짜 DOI `10.1234/crossref.dummy`를 실제 결과처럼 사용자에게 노출. 반환각 프레임워크 디폴트 경로에 DOI 위조기가 박힌 최악의 아이러니. |
| B6 | `router.py:97` | `_run_analyze`가 온톨로지 맵을 받지 않음. 헌법은 "온톨로지 맵과 원문을 동시에" 요구하지만 raw 쿼리 문자열만 전달, 그나마 `LensAnalyzer.analyze`는 그 인자조차 안 읽음 — 죽은 경로. |
| B7 | `engine.py:146` | noise 필터가 substring 매칭. `"index"`는 *"Index Theory in Topology"* 같은 정상 논문을 오탐 드롭. |
| B8 | packaging | `__init__.py` 전무인데 `from src....` 절대임포트 + `packages=["src"]`. 휠 설치 시 임포트 실패. `console_scripts` 엔트리포인트 없음. `pyproject` 버전 0.1.0인데 커밋 태그 v0.4.0 — 버전 드리프트. |
| B9 | `tests/` | 빈 디렉터리. 기계적 검증 엄밀성이 유일한 셀링포인트인 프레임워크에 테스트 0개. |

부수: README는 "Fail-Fast"를 강조하지만 클라이언트 bare-except + `gather(return_exceptions=True)` 이중 삼킴으로 시스템이 거의 절대 큰 소리로 죽지 않음 — 주장과 정반대. `skills/scholar_runner.py`(1111줄)는 `src/` 어디서도 호출되지 않는 고아 스크립트 — "Built-in Elite Tools 완전 내장"은 산문으로만 존재.

---

# 4. 개선 제안 (우선순위순)

**P0 — 정직성 회복.** 코드에 없는 기능을 README/SKILL/CLAUDE.md에서 전부 `[BLUEPRINT]` / `[NOT IMPLEMENTED]`로 명시 태깅. 현 상태로 외부 공개 시 신뢰를 잃는다. 버전을 0.1.0으로 통일.

**P1 — Audit Gate를 진짜로 만들기 (핵심 가치).** `verify_ontology(ontology, source_document)` 시그니처로 변경, 최소한 Gate 1 구현: ① 원문을 `¶` 단위로 분할해 paragraph_id 집합 생성 ② 모든 `Node.paragraph_id`가 그 집합에 실존하는지 검증 ③ 미실존 시 환각으로 reject. 이게 없으면 프로젝트 존재 이유가 없다. 골든 테스트 5개부터.

**P2 — 헌법 위반 제거.** `api_registry` 하드코딩 폐기, 렌즈 YAML의 `search_priority`를 읽어 클라이언트 동적 조립. 렌즈 포맷을 `.yaml` 하나로 통일(`lens-template.md`와 `cs.yaml` 스키마 통합). 도메인명(theology 등)을 코어에서 완전 제거.

**P3 — 정직한 디폴트.** `CrossrefClient` 더미를 디폴트 레지스트리에서 제거하거나 실제 Crossref REST(`api.crossref.org/works`, 키 불필요) 구현. 가짜 DOI 노출 경로 즉시 차단. bare `except`를 구체 예외 + 명시적 실패 신호로 교체.

**P4 — 버그 처리.** B1(`'\n'`), B2(None 가드), B3(`quote`), B8(`__init__.py` + entry point). KCI는 실 API 스펙 확인 후 재작성하거나 솔직하게 `NotImplemented`로 강등.

**P5 — 실 LLM 연결.** `AnthropicProvider`를 tool-use 구조화 출력으로 실제 구현(프롬프트 캐싱 포함). MockProvider는 테스트 전용으로 격리, 기본값에서 제외.

---

요약: 아키텍처 비전은 일관되고 야심차지만, 현재 코드는 비전의 1할 미만이고 핵심 차별점(무자비한 감사)이 통째로 비어 있으며 자기 헌법을 코드 레벨에서 위반한다. 가장 시급한 건 P0(문서 정직성)와 P1(Audit Gate 실구현).
