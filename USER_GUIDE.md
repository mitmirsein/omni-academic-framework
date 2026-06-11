# Omni-Academic Framework 사용자 가이드

이 문서는 `omni-academic-framework`를 독립 프로젝트로 실행하는 실무 가이드입니다. 목표는 명령, 산출물, gate 상태, 문제 해결을 빠르게 확인할 수 있게 하는 것입니다.

## 1. 첫 실행

프로젝트 루트에서 환경을 확인합니다.

```bash
uv run omni --status
uv run omni --list-lenses
```

API key 없이 기본 파이프라인을 확인합니다.

```bash
uv run omni ./examples/sample.md --module ontology --lens general --mock
```

생성 위치:

```text
runs/examples-sample-md/<timestamp>/
```

주요 파일:

- `paragraphs.json`
- `ontology.json`
- `audit.json`
- `manifest.json`
- `report.md`

## 2. 설치와 설정

개발 checkout:

```bash
git clone https://github.com/mitmirsein/omni-academic-framework.git
cd omni-academic-framework
uv run omni --status
```

전역 도구 설치:

```bash
uv tool install git+https://github.com/mitmirsein/omni-academic-framework.git
omni --status
```

실 LLM 모드는 Anthropic provider를 기본으로 사용합니다.

```bash
uv run --extra llm omni --setup
```

필수 변수:

| 변수 | 용도 |
|---|---|
| `ANTHROPIC_API_KEY` | live ontology/analyze/draft/review 실행 |

선택 변수:

| 변수 | 용도 |
|---|---|
| `SERPAPI_API_KEY` | SerpAPI 기반 Google Scholar 검색 |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar rate limit 완화 |
| `OMNI_LIGHTPANDA_BIN` | 브라우저 렌더링이 필요한 페이지 fallback |
| `OMNI_PDF_EXTRACTOR` | 외부 PDF 텍스트 추출기 |
| `OMNI_LENS_DIR` | 사용자 lens 디렉터리 |

`OPENAI_API_KEY`와 `GEMINI_API_KEY`는 기본 live path에는 필요하지 않습니다.

## 3. 모듈별 실행

| 모듈 | 사용할 때 | 주요 산출물 |
|---|---|---|
| `recon` | 검색어로 후보 논문을 찾을 때 | `digest.json` |
| `ontology` | 텍스트에서 grounded knowledge map을 만들 때 | `ontology.json`, `audit.json` |
| `analyze` | lens 기반 briefing 또는 LLM analysis가 필요할 때 | `lens_brief.md`, optional `lens_analysis.*` |
| `draft` | source-grounded draft를 만들 때 | `draft.json`, `draft.md`, `draft_audit.json` |
| `review` | draft run을 패널 리뷰할 때 | grounding 통과 시 `review.json`, `review.md` |

### Recon

```bash
uv run omni "Pauline mission universal gospel" --lens theology
```

기본 모듈은 `recon`입니다. 후보 논문을 출력하고 HITL 선택을 요청합니다. `q`를 입력하면 정찰 결과만 저장하고 종료합니다.

자주 쓰는 옵션:

```bash
uv run omni "inflation dynamics" --lens economics --no-cache
uv run omni "justification ethics" --lens theology --forensic
uv run omni "ignored label" --snowball "10.1234/example.doi"
uv run omni "kci harvest" --module recon --kci-harvest ARTI
```

### Ontology

```bash
uv run omni ./paper.md --module ontology --lens general --mock
uv run --extra llm omni ./paper.md --module ontology --lens general
```

입력이 실제 파일 경로이면 파일 내용을 읽습니다. 경로가 아니면 입력 문자열 자체를 분석 대상으로 사용합니다.

Ontology run은 `paragraphs.json`을 먼저 만들고, 모든 node/edge의 `paragraph_id`와 `source_quote`를 원문 문단에 대조합니다.

### Analyze

```bash
uv run omni ./paper.md --module analyze --lens theology
uv run --extra llm omni ./paper.md --module analyze --lens theology --llm-analysis
uv run --extra llm omni ./paper.md --module analyze --lens theology --llm-critic
```

기본 `analyze`는 source-bound briefing scaffold를 저장합니다. 실제 LLM 분석은 `--llm-analysis`를 붙여야 합니다.

`--llm-critic`은 `--llm-analysis`를 포함하며 critic 결과와 critic grounding audit을 함께 저장합니다.

### Draft

```bash
uv run omni ./paper.md --module draft --lens general --mock
uv run --extra llm omni ./paper.md --module draft --lens general
```

Draft는 먼저 ontology를 만들고 audit합니다. ontology audit이 실패하면 draft를 만들지 않고 status를 `blocked_by_audit`으로 남깁니다.

Draft claim은 다음 조건을 만족해야 합니다.

- `claims[]`에 등록됨
- 본문에서 `[C#]`로 참조됨
- 실제 `paragraph_id`에 묶임
- 해당 문단에 존재하는 verbatim `source_quote`를 가짐

### Review

```bash
uv run omni runs/examples-sample-md/latest --module review --lens general --mock
uv run --extra llm omni <draft-run> --module review --lens general
```

Review 대상은 `draft.json`을 포함한 run 디렉터리 또는 `draft.json` 파일 경로입니다.

패널 설정은 `lenses/review_panel.yaml`에 있습니다.

- Ella
- Miranda
- Methodologist
- Devil's Advocate
- Chief Editor synthesis

각 review의 `source_quotes`는 draft에 verbatim으로 존재해야 합니다. 마지막 재시도까지 grounding이 실패하면 `failure.json`을 쓰고 status를 `blocked_by_review_grounding`으로 남기며 `review.json`/`review.md`는 만들지 않습니다.

리뷰 입력이 저장된 run을 가리키면 그 run의 manifest에서 `draft_passed=true`를 확인합니다(출처 체인). draft 감사에 반려된 run을 넘기면 `blocked_by_source_audit`로 차단되고, manifest 없는 단독 `draft.json` 입력은 `source_provenance=unverified`로 기록됩니다.

## 4. Run 다루기

Run은 아래 형식으로 저장됩니다.

```text
runs/<query-slug>/<timestamp>/
```

Mock run은 timestamp 앞에 `MOCK-`가 붙습니다.

조회:

```bash
uv run omni --show-run examples-sample-md/latest
uv run omni --show-run runs/examples-sample-md/latest
```

`--show-run`은 blocked/failed 상태일 때 다음에 확인할 파일과 재시도 방향을 함께 출력합니다.

무결성 검증:

```bash
uv run omni --verify-run examples-sample-md/latest
uv run omni --verify-run runs/examples-sample-md/latest
```

`--verify-run`은 `manifest.json`의 `artifact_manifest`를 기준으로 파일 존재 여부, byte size, sha256을 확인합니다.

중요 파일:

| 파일 | 의미 |
|---|---|
| `manifest.json` | run metadata, status, provenance, artifact hash |
| `report.md` | 사람이 읽는 요약 |
| `paragraphs.json` | 문단 ID와 원문 문단 mapping |
| `ontology.json` | 추출된 node/edge |
| `audit.json` | ontology gate 결과 |
| `draft_audit.json` | draft gate 결과 |
| `failure.json` | blocked/failed path 진단 |

## 5. 주요 Status

| Status | 의미 |
|---|---|
| `completed` | 필수 gate 통과 |
| `blocked_by_audit` | ontology audit 실패 |
| `blocked_by_draft_audit` | draft compliance 실패 |
| `blocked_by_review_grounding` | review quote grounding 실패 |
| `blocked_by_source_audit` | 리뷰 대상 draft run이 draft 감사를 통과하지 못함 |
| `review_rejected` | review는 완료됐지만 Chief Editor가 reject |
| `analysis_failed` | lens/provider/input 문제로 분석 실패 |
| `scraping_failed` | 원문 수집이 markdown을 만들지 못함 |
| `no_papers_found` | recon 후보 없음 |
| `cancelled_by_user` | HITL 단계에서 사용자가 중단 |

## 6. Lens

기본 lens는 `lenses/`에 있습니다.

- `general`
- `theology`
- `economics`
- `medical`
- `humanities`
- `cs`

목록 확인:

```bash
uv run omni --list-lenses
```

사용자 lens 디렉터리:

```bash
OMNI_LENS_DIR=/path/to/lenses uv run omni ./paper.md --module ontology --lens custom
```

Lens는 focus area, prompt, ontology directive, recon client 조합을 정의할 수 있습니다.

## 7. 로컬 DB 조회

Run metadata는 `runs/index.db`에 저장됩니다.

```bash
uv run python -m omni_academic.store.query_db
uv run python -m omni_academic.store.query_db --latest --json
uv run python -m omni_academic.store.query_db theology --passed
uv run python -m omni_academic.store.query_db --status blocked_by_audit
```

주요 필터:

| 옵션 | 의미 |
|---|---|
| `--passed` / `--failed` | `audit_passed` 기준 |
| `--mock` / `--live` | mock mode 기준 |
| `--status VALUE` | run status 기준 |
| `--latest` | 최신 run 1건 |
| `--limit N` | 출력 개수 제한 |
| `--json` | JSON 출력 |

## 8. 문제 해결

### 후보 논문이 없음

```bash
uv run omni "broader query" --lens general --no-cache
uv run omni --status
```

가능한 원인: API key 없음, rate limit, query가 너무 좁음, 빈 결과 cache, client 장애.

### 원문 스크래핑 실패

```bash
uv run omni --status
```

대응:

- 브라우저 렌더링이 필요하면 `OMNI_LIGHTPANDA_BIN` 설정
- PDF 추출이 어렵다면 `OMNI_PDF_EXTRACTOR` 설정
- 다른 source URL 시도

### Ontology 추출 실패

파이프라인 점검:

```bash
uv run omni ./paper.md --module ontology --mock
```

Live mode:

```bash
uv run --extra llm omni ./paper.md --module ontology
```

`ANTHROPIC_API_KEY`와 `llm` extra를 확인합니다.

### Review가 `review.json`을 만들지 않음

`manifest.json`과 `failure.json`을 확인합니다. status가 `blocked_by_review_grounding`이면 review가 draft에 없는 문구를 인용하려 한 것입니다. 이는 fail-closed 동작입니다.

## 9. 유지관리

Git에서 제외되는 로컬 경로:

- `.env`
- `.venv/`
- `.cache/`
- `runs/`
- `handoff/`
- `scratch/`
- `.pytest_cache/`
- `__pycache__/`
- `.DS_Store`

정리해도 되는 파일:

```bash
find . -path './.venv' -prune -o -name '__pycache__' -type d -prune -exec rm -rf {} +
rm -rf .pytest_cache
```

주의:

- `.env`는 로컬 설정입니다.
- `runs/`는 실행 산출물입니다.
- `.cache/`는 recon cache입니다.

## 10. 개발 검증

```bash
uv run ruff check
uv run python -m pytest -q
```

push 전에는 두 명령을 실행하고 `git status --short`를 확인합니다.
