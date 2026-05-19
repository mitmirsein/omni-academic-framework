# Omni-Academic Framework Peer Review

Reviewed: 2026-05-19
Scope: `/Users/msn/Desktop/MS_Dev.nosync/projects/omni-academic-framework`
Mode: 코드 수정 없는 피어 리뷰 및 개선 제안

## Executive Verdict

현재 프로젝트는 "강한 비전 문서 + 부분 PoC + 다수의 실행 불능 계약" 상태다. 철학은 선명하지만, 핵심 주장인 Ontology-First, Audit-first, 범용 학술 엔진, clone 후 즉시 실행 가능성은 아직 코드 레벨에서 성립하지 않는다.

가장 심각한 문제는 README/스킬 문서가 약속하는 안전장치가 실제 구현에 거의 내려오지 않았다는 점이다. 지금 상태로 연구 실무에 투입하면, mock output과 더미 citation이 진짜 검증 결과처럼 보이는 위험이 있다.

## Scores

| Area | Score | Rationale |
| --- | ---: | --- |
| Vision / Philosophy | 8/10 | 문제의식과 방향은 강하다. |
| Architecture Contract | 4/10 | 문서상 계약은 많지만 서로 충돌하거나 경로가 틀린다. |
| Implementation Completeness | 1.5/10 | 핵심 경로가 mock/stub 중심이다. |
| Audit / Fidelity Guarantee | 1/10 | 실제 audit gate는 구조 일부만 본다. |
| Reproducibility | 2/10 | 의존성 누락과 missing module 때문에 clone 후 실행이 어렵다. |
| Production Research Readiness | 0.5/10 | 검증된 E2E slice가 없다. |

## Critical Findings

### 1. Audit 시스템은 이름만 있다

README는 3중 Audit Gate를 약속한다.

- `README.md:41-45`: I/O Envelope, Forensic Search, Schema Compliance 감사 선언
- `src/audit/gate.py:28-50`: 실제 구현은 orphan node, self-loop, reasoning 길이만 검사

누락된 핵심 검증:

- `paragraph_id`가 원문에 실제 존재하는지 확인하지 않음
- DOI/URL 실존 여부를 확인하지 않음
- 렌즈 스키마 준수 여부를 확인하지 않음
- hallucination을 원문 span과 대조하지 않음
- 토큰 비율, 수식 보존, paragraph parity 검사가 없음

결론: 프로젝트가 가장 자랑하는 "무자비한 감사"가 아직 프레임워크의 심장이 아니라 콘솔 메시지다.

### 2. Recon deep dive가 Crossref 결과에서 깨질 수 있다

- `src/recon/engine.py:101-112`: `CrossrefClient`는 dummy DOI만 반환하고 `url`을 채우지 않는다.
- `src/supervisor/router.py:63-68`: 라우터는 선택된 논문의 `target_paper.url`을 그대로 scraper에 넘긴다.
- `src/recon/scraper.py:50`: `ScraperFactory.get_scraper()`는 `"sciencedirect" in url`을 수행한다.

`url is None`이면 TypeError가 발생한다. 더 큰 문제는 dummy Crossref 결과가 digest에 정상 논문처럼 보인다는 점이다.

### 3. Ontology Extractor는 실제 추출기가 아니다

- `src/ontology/extractor.py:52-55`: 기본 provider가 `MockProvider`
- `src/llm/provider.py:23-31`: 입력 문서와 무관하게 `Mock Artifact`, `Mock Concept`를 반환

Ontology-First가 hallucination을 줄이는 구조가 되려면, 노드와 엣지가 원문 paragraph/span에 묶여야 한다. 지금은 입력과 무관한 mock graph가 정상 audit을 통과할 수 있다.

### 4. `--module analyze` 기본 경로가 실패한다

- `src/supervisor/router.py:106`: CLI 기본 lens는 `general`
- `src/analyze/lens_analyzer.py:21-24`: `lenses/general.yaml`을 찾는다.
- 실제 `lenses/`에는 `cs`, `theology`, `medical`, `humanities`, `economics`만 있다.

기본 명령이 실패하는 것은 CLI 계약의 기본 신뢰도를 깎는다.

### 5. "문서 경로 입력" 계약이 구현되지 않았다

- `src/supervisor/router.py:105`: help는 `검색 쿼리 또는 타겟 문서 경로`라고 설명한다.
- 실제 ontology/analyze 경로는 파일을 읽지 않고 문자열 자체를 문서 본문처럼 전달한다.

즉 `/path/to/paper.md`를 넘기면 파일 내용이 아니라 경로 문자열을 분석한다.

### 6. 의존성 선언이 실제 스킬 스크립트와 맞지 않는다

- `pyproject.toml:7-12`: `pydantic`, `rich`, `pyyaml`, `httpx`만 선언
- `skills/semantic-scholar/scripts/s2_runner.py:1-7`: `requests`, `dotenv` 사용
- `skills/google-scholar-semantic/scripts/scholar_runner.py:14`: `bs4` 사용

`uv.lock`에도 `requests`, `python-dotenv`, `beautifulsoup4`가 확인되지 않았다. 스킬 스크립트가 프레임워크 일부라면 dependency group 또는 optional extra로 선언되어야 한다.

### 7. Google Scholar Semantic은 repo 단독 실행이 불가능하다

- `skills/google-scholar-semantic/SKILL.md:17`: 핵심 도구를 `scripts/scholar_runner.py -> agents/stealth_browser.py`로 선언
- `skills/google-scholar-semantic/scripts/scholar_runner.py:378`: `from agents.stealth_browser import MoltbotBrowser`
- 프로젝트 내부에 `agents/stealth_browser.py`가 없다.

문서상 "clone만 해도 즉시 독립적으로 사용"이라는 README 주장과 직접 충돌한다.

### 8. 범용/플러그인 원칙을 코드가 배신한다

- `AGENTS.md:10-12`: domain hard-coding 금지, adapter/plugin 주입 원칙
- `src/recon/engine.py:117-122`: lens별 API registry가 코드에 하드코딩
- `lenses/medical.yaml`, `lenses/economics.yaml`는 있으나 recon registry에는 연결되어 있지 않음

렌즈가 data-driven configuration이어야 하는데, 현재는 코드 수정 없이는 도메인 확장이 불완전하다.

### 9. `.skills/...`와 `skills/...` 경로 계약이 불일치한다

여러 문서가 `.skills/...` 경로를 가정하지만 실제 repo 경로는 `skills/...`다.

- `skills/semantic-scholar/SKILL.md:31-36`
- `skills/google-scholar-semantic/SKILL.md:60-79`
- `workflows/omni-research.md:11-12`

사용자가 문서대로 명령을 실행하면 경로부터 실패한다.

### 10. 테스트가 없다

`tests/` 디렉터리는 비어 있고 tracked test file도 없다. 특히 아래는 최소 테스트가 필요하다.

- `AuditGate.verify_ontology()`
- `ScraperFactory.get_scraper(None)`
- `RouterRequest` CLI 기본 경로
- `LensAnalyzer` missing/default lens behavior
- `scholar_runner.py --self-test`
- dependency import smoke test

## Improvement Plan

### Phase 0: Truth-in-README

목표: 문서가 현재 구현 상태를 과장하지 않게 만든다.

작업:

- README에 `Status: Prototype / Mock-heavy`를 명시한다.
- "clone만 해도 즉시 독립 사용" 문구를 제거하거나 선행 조건을 명시한다.
- mock provider, dummy Crossref, missing stealth browser를 known limitation으로 적는다.
- `.skills/...` 경로를 `skills/...`로 통일한다.

Acceptance:

- README만 읽어도 현재 실행 가능한 범위와 미구현 범위가 구분된다.

### Phase 1: One Honest E2E Slice

목표: 작지만 진짜로 동작하는 한 줄기 pipeline을 만든다.

추천 slice:

1. Semantic Scholar 또는 arXiv 검색
2. Digest 생성
3. HITL 선택
4. URL 또는 OA PDF/HTML 획득
5. Markdown full text 저장
6. Paragraph ID 부여
7. OntologyMap 생성
8. AuditReport JSON 생성

핵심 설계:

- 모든 모듈은 콘솔 출력이 아니라 typed result를 반환한다.
- `MockProvider`는 기본값이 아니라 `--mock`에서만 사용한다.
- 실패는 콘솔 메시지로 삼키지 말고 error envelope에 보존한다.

Acceptance:

- `uv run omni ...` 또는 `uv run python -m src.supervisor.router ...`가 한 개 fixture 문서에서 offline E2E 통과
- 결과물: `DigestReport`, `FullTextDocument`, `OntologyMap`, `AuditReport`

### Phase 2: AuditGate를 진짜 Gate로 재작성

목표: "감사"를 생성형 self-critique가 아니라 기계적 대조 계층으로 만든다.

필수 audit checks:

- Node paragraph_id exists in manifest
- Edge source/target node exists
- Every node has source quote or source span
- Every source span appears in original text
- DOI syntax and DOI resolution status
- URL HTTP status / final URL / retrieved_at
- Lens schema compliance
- Output schema validation
- Paragraph parity for translation paths
- Token ratio guard for translation paths

추천 모델:

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

Acceptance:

- mock ontology가 원문 span 없이 통과하지 못한다.
- orphan/self-loop만 보는 현재 검사를 대체한다.

### Phase 3: Config-driven Lens Registry

목표: 도메인 확장을 코드 수정 없이 가능하게 만든다.

작업:

- `lenses/*.yaml`에 recon clients, required audit gates, analysis prompts를 포함한다.
- `ReconEngine`이 `api_registry`를 코드에 들고 있지 않게 한다.
- `general.yaml`을 추가하거나 CLI 기본값을 존재하는 렌즈로 바꾼다.

Acceptance:

- `medical`, `economics` 렌즈가 별도 코드 수정 없이 recon client 선택에 영향을 준다.

### Phase 4: Dependency and Packaging Repair

작업:

- core dependencies와 skill dependencies를 분리한다.
- 예:
  - core: `pydantic`, `rich`, `pyyaml`, `httpx`
  - semantic-scholar extra: `requests`, `python-dotenv`
  - scholar-browser extra: `beautifulsoup4`, `playwright` 또는 실제 stealth browser package
- console script entrypoint 추가
- Python version 현실화: 현재 lock은 CPython 3.14 환경에서 시도되었지만 project는 `>=3.11`만 명시한다. 지원 범위를 테스트로 고정해야 한다.

Acceptance:

- `uv sync --extra semantic-scholar`
- `uv run python skills/google-scholar-semantic/scripts/scholar_runner.py --self-test`
- `uv run python -c "import ..."` smoke test 통과

### Phase 5: Test Harness

최소 테스트 파일:

- `tests/test_audit_gate.py`
- `tests/test_scraper_factory.py`
- `tests/test_lens_registry.py`
- `tests/test_router_cli.py`
- `tests/test_scholar_runner_offline.py`

최소 fixtures:

- short article markdown with paragraph IDs
- ontology map with valid spans
- ontology map with hallucinated node
- Scholar Labs sample HTML
- malformed URL/no URL paper metadata

Acceptance:

- network 없이 핵심 계약 테스트 가능
- CI 또는 local smoke command 하나로 regression 확인 가능

## Recommended First Patch Set

가장 먼저 고칠 순서:

1. `ScraperFactory.get_scraper()`가 `None`/empty URL을 명시적으로 거부하게 수정
2. `CrossrefClient` 더미 결과 제거 또는 mock 모드로 격리
3. `general.yaml` 추가 또는 CLI default lens 변경
4. 파일 경로 입력 시 실제 파일 내용을 읽는 resolver 추가
5. `AuditGate`에 paragraph_id 존재성 검사 추가
6. `MockProvider` 기본 사용 금지, `--mock` 플래그 추가
7. pyproject에 누락 dependency group 추가
8. `.skills` 문서 경로를 `skills`로 정정

## Verification Performed

확인한 것:

- `rg --files`로 프로젝트 파일 구조 확인
- `README.md`, `AGENTS.md`, `pyproject.toml`, `workflows/omni-research.md` 검토
- `src/` 핵심 구현 검토
- `skills/` 핵심 스킬 문서 및 runner 검토
- Python AST 문법 파싱 확인: `syntax_ok`
- `tests/`가 비어 있음을 확인
- tracked `.DS_Store` 파일 3개 확인

실행 제한:

- 기본 `python3` 환경에서 `rich` import 실패
- `uv run --no-sync`는 의존성 sync 없이 `.venv`를 만들었고 `pydantic` import 실패
- 생성된 `.venv` 부산물은 제거함
- 네트워크/API 기반 실제 recon은 수행하지 않음

## Final Assessment

이 프로젝트는 버릴 물건이 아니라, 과장된 껍질을 벗겨야 살아난다. 다음 단계의 핵심은 더 큰 비전을 쓰는 것이 아니라, 작고 정직한 E2E slice 하나를 통과시키는 것이다. 그 뒤에만 "Omni"라는 이름을 다시 붙일 자격이 생긴다.
