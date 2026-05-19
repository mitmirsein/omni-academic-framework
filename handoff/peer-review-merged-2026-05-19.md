---
title: Omni-Academic Framework 통합 피어리뷰 (Merged)
date: 2026-05-19
synthesized_by: Claude Opus 4.7 (claude-opus-4-7) — Claude Code
sources:
  - handoff/peer-review-2026-05-19.md (점수표 + Phase 0~5 로드맵 골격)
  - handoff/2026-05-19-peer-review.md (Claude Opus 4.7 — 라인 단위 버그 B1~B9)
scope: src/ 전체 + README/CLAUDE.md/AGENTS.md/SKILL.md/lenses/workflows
commit: d8993f3 (v0.4.0)
status: 두 독립 리뷰의 합치 결론 + 상호보완 사항 통합
---

# 0. 종합 평결 (Verdict)

두 리뷰가 독립적으로 같은 치명 결함을 지목했다 — 신뢰도 높음. 현 상태는 **"강한 비전 문서 + 부분 PoC + 다수 실행 불능 계약"**. 철학은 선명하나 핵심 주장(Ontology-First, Audit-first, 범용 엔진, clone 후 즉시 실행)이 코드 레벨에서 성립하지 않는다. 가장 큰 위험: **mock output과 더미 citation이 진짜 검증 결과처럼 보인다.** 버릴 물건이 아니라 과장된 껍질을 벗겨야 산다.

# 1. 점수 (Scores)

| Area | Score | 근거 |
| --- | ---: | --- |
| Vision / Philosophy | 8/10 | 문제의식·방향 강함 |
| Architecture Contract | 4/10 | 문서 계약 다수가 서로 충돌하거나 경로 오류 |
| Implementation Completeness | 1.5/10 | 핵심 경로가 mock/stub 중심 |
| Audit / Fidelity Guarantee | 1/10 | 실제 gate는 그래프 구조 일부만 검사 |
| Reproducibility | 2/10 | 의존성 누락·missing module로 clone 후 실행 난망 |
| Production Research Readiness | 0.5/10 | 검증된 E2E slice 없음 |

# 2. 치명 결함 — 통합 목록

## C1. Audit 시스템은 이름만 있다 (두 리뷰 합치)
- 선언: `README.md:41-45` 3중 Gate(I/O Envelope, Forensic, Schema)
- 실제: `src/audit/gate.py:28-50` — orphan node, self-loop, reasoning 길이만 검사
- 누락: paragraph_id 원문 실존 검증, DOI/URL 실존, 렌즈 스키마 준수, 원문 span 대조, 토큰 비율, 수식 보존, paragraph parity
- `verify_ontology()`는 원문을 인자로 받지도 않음 → 환각 탐지가 원리적으로 불가능. 잘 연결되고 reasoning 10자 넘으면 날조 그래프도 100점 통과.

## C2. 파이프라인 전체가 MockProvider 위에서 돈다 (합치)
- `src/ontology/extractor.py:52-55` 기본 provider가 `MockProvider`
- `src/llm/provider.py:23-31` 입력 무관 `Mock Artifact`/`Mock Concept` 반환
- `OpenAIProvider`/`AnthropicProvider` 둘 다 `raise NotImplementedError`
- v0.4.0 "E2E HITL 파이프라인 연결" 커밋은 빈 파이프 연결

## C3. CrossrefClient 더미가 디폴트 경로에 노출 + 런타임 크래시 (상호보완)
- `src/recon/engine.py:101-112` dummy DOI `10.1234/crossref.dummy` 반환, `url` 미설정
- `src/supervisor/router.py:63-68` 선택 논문의 `target_paper.url`을 그대로 scraper에 전달
- `src/recon/scraper.py:50` `"sciencedirect" in url` → **`url is None`이면 TypeError로 폭발**
- 동시에 가짜 DOI가 digest에 정상 논문처럼 표시 — 반환각 프레임워크 디폴트 경로에 DOI 위조기

## C4. 자기 헌법 §2 정면 위반 (합치)
- `AGENTS.md/CLAUDE.md §2`: 도메인 하드코딩 금지, adapter/plugin 주입 원칙
- `src/recon/engine.py:117-122`: lens별 API registry가 코드 하드코딩, `"theology": [...]  # 신학 렌즈에서도 KCI 강력 추천` 주석까지 존재
- `lenses/medical.yaml`, `economics.yaml`는 registry에 미연결 — 렌즈는 검색 라우팅을 구동하지 못함
- v0.3.2 "theology→omni 중립화" 커밋은 스킬 이름만 바꾼 화장, 코드 결합은 그대로

## C5. CLI 계약 붕괴 (상호보완)
- `router.py:106` 기본 lens `general` → `lenses/general.yaml` 부재 → 기본 명령 실패
- `router.py:105` help는 "타겟 문서 경로"라지만 ontology/analyze는 파일을 읽지 않고 경로 문자열 자체를 본문으로 취급
- `router.py:97` `_run_analyze`가 온톨로지 맵을 안 받음(헌법은 "온톨로지+원문 동시" 요구), `LensAnalyzer.analyze`는 그 인자조차 안 읽음 — 죽은 경로

## C6. 재현성·패키징 붕괴 (상호보완)
- `pyproject.toml:7-12` core 4종만 선언. 스킬은 `requests`/`python-dotenv`(s2_runner), `bs4`(scholar_runner) 사용 — `uv.lock` 미반영
- `scholar_runner.py:378` `from agents.stealth_browser import MoltbotBrowser` — repo에 `agents/stealth_browser.py` 부재 → "clone만 해도 즉시 독립 사용" 주장과 직접 충돌
- `__init__.py` 전무인데 `from src....` 절대임포트 + `packages=["src"]` → 휠 설치 시 임포트 실패, console script entrypoint 없음
- 문서의 `.skills/...` 경로 vs 실제 `skills/...` 불일치 → 문서대로 실행 시 경로부터 실패
- tracked `.DS_Store` 3개

## C7. 라인 단위 버그 (Claude Opus 4.7 리뷰 기여)

| # | 위치 | 문제 |
|---|------|------|
| B1 | `engine.py:42,43` | `.replace('\\n', ' ')` — 리터럴 백슬래시-n 치환. 실제 개행 미처리. 정규화 무효 |
| B2 | `engine.py:42` | `entry.find('arxiv:title', ns).text` — 요소 누락 시 `None.text` AttributeError로 gather 전체 크래시 |
| B3 | `engine.py` arXiv/KCI | `query`를 f-string raw 삽입. 공백·특수문자 미인코딩. `urllib.parse.quote` 필요 |
| B4 | `engine.py:96` | KCI bare `except` → 빈 리스트. 실패와 "결과 없음" 구분 불가. API key 누락 가능성, XML 경로 미검증 |
| B7 | `engine.py:146` | noise 필터 substring 매칭 — `"index"`가 *"Index Theory"* 정상 논문 오탐 드롭 |

부수: README "Fail-Fast" 주장 vs 클라이언트 bare-except + `gather(return_exceptions=True)` 이중 삼킴으로 거의 안 죽음 — 정반대.

## C8. 테스트 0개 (합치)
`tests/` 빈 디렉터리. 기계적 검증이 유일 셀링포인트인 프레임워크에 테스트 전무.

# 3. 통합 로드맵 (Phase 0~5)

## Phase 0 — Truth-in-README
- README에 `Status: Prototype / Mock-heavy` 명시
- "clone만 해도 즉시 독립 사용" 제거 또는 선행조건 명시
- mock provider, dummy Crossref, missing stealth browser를 known limitation으로 기재
- 코드 미존재 기능을 문서에서 `[BLUEPRINT]`/`[NOT IMPLEMENTED]` 태깅
- `.skills/...` → `skills/...` 통일, pyproject 버전을 0.1.0으로 통일
- **Acceptance**: README만 읽어도 실행 가능 범위와 미구현 범위가 구분됨

## Phase 1 — One Honest E2E Slice
검색(S2/arXiv) → Digest → HITL 선택 → URL/OA 획득 → Markdown 저장 → Paragraph ID 부여 → OntologyMap → AuditReport JSON
- 모든 모듈은 콘솔 출력이 아니라 typed result 반환
- `MockProvider`는 기본값이 아니라 `--mock`에서만
- 실패는 콘솔로 삼키지 말고 error envelope에 보존
- **Acceptance**: `uv run python -m src.supervisor.router ...`가 fixture 1개로 offline E2E 통과, 산출물 `DigestReport`/`FullTextDocument`/`OntologyMap`/`AuditReport`

## Phase 2 — AuditGate를 진짜 Gate로 재작성
필수 checks: node paragraph_id manifest 실존 / edge 노드 실존 / 노드별 source quote·span / span이 원문에 실존 / DOI 문법·resolution / URL HTTP status·final URL·retrieved_at / 렌즈 스키마 준수 / 출력 스키마 검증 / 번역 경로 paragraph parity / 번역 경로 토큰 비율 가드

```python
class AuditFinding(BaseModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    source_ref: str | None = None

class AuditReport(BaseModel):
    passed: bool
    score: int
    findings: list[AuditFinding]
    checked_at: datetime
```
- **Acceptance**: mock ontology가 원문 span 없이 통과 불가, orphan/self-loop만 보는 현재 검사 대체

## Phase 3 — Config-driven Lens Registry
- `lenses/*.yaml`에 recon clients, required audit gates, analysis prompts 포함
- `ReconEngine`이 `api_registry`를 코드에 들고 있지 않게
- `general.yaml` 추가 또는 CLI 기본값을 존재하는 렌즈로
- **Acceptance**: `medical`/`economics` 렌즈가 코드 수정 없이 recon client 선택에 영향

## Phase 4 — Dependency·Packaging Repair + 라인 버그 흡수
- core / skill extra 의존성 분리: core(`pydantic,rich,pyyaml,httpx`), semantic-scholar extra(`requests,python-dotenv`), scholar-browser extra(`beautifulsoup4`,실 stealth browser)
- console script entrypoint 추가, `__init__.py` 보강, Python 지원 범위 테스트로 고정
- **라인 버그 동시 처리**: B1(`'\n'`로 수정), B2(None 가드), B3(`urllib.parse.quote`), B4(구체 예외+명시 실패), B7(substring→정밀 매칭). KCI는 실 API 스펙 확인 후 재작성하거나 `NotImplemented` 강등
- **Acceptance**: `uv sync --extra semantic-scholar`, `scholar_runner.py --self-test`, import smoke test 통과

## Phase 5 — Test Harness
- `tests/test_audit_gate.py`, `test_scraper_factory.py`, `test_lens_registry.py`, `test_router_cli.py`, `test_scholar_runner_offline.py`
- fixtures: paragraph ID 포함 짧은 article md / valid span ontology / hallucinated node ontology / Scholar Labs sample HTML / malformed·no URL paper metadata
- **Acceptance**: network 없이 핵심 계약 테스트, 단일 smoke command로 regression 확인

# 4. Recommended First Patch Set (착수 순서)

1. `ScraperFactory.get_scraper()`가 `None`/empty URL 명시적 거부 (C3 크래시 차단)
2. `CrossrefClient` 더미 제거 또는 `--mock` 격리 (C3)
3. `general.yaml` 추가 또는 CLI default lens 변경 (C5)
4. 파일 경로 입력 시 실제 파일 내용을 읽는 resolver 추가 (C5)
5. `AuditGate`에 paragraph_id 존재성 검사 추가 (C1 최소 착수)
6. `MockProvider` 기본 사용 금지 + `--mock` 플래그 (C2)
7. pyproject 누락 dependency group 추가 (C6)
8. `.skills`→`skills` 문서 경로 정정 (C6)
9. B1/B2/B3 즉시 핫픽스 (저비용·고효과)

# 5. 검증 수행 / 한계

확인: `rg --files` 구조 확인, README/AGENTS/pyproject/workflows 검토, `src/` 전체 검토, `skills/` runner 검토, AST 문법 파싱 OK, `tests/` 빈 것 확인, `.DS_Store` 3개 확인.
한계: 기본 `python3`에서 `rich` import 실패, `uv run --no-sync`는 `pydantic` import 실패(부산물 .venv 제거함), 네트워크/실 API recon 미수행.

# 6. 최종 판단

핵심은 더 큰 비전을 쓰는 게 아니라, **작고 정직한 E2E slice 하나를 통과시키는 것**. P0(문서 정직성) + P1(E2E) + P2(Audit 실구현)가 생사 분기점이다. 그 뒤에만 "Omni"라는 이름을 다시 붙일 자격이 생긴다.
