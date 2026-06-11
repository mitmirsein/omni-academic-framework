# Omni-Academic Framework

검증 가능한 학술 텍스트 처리 파이프라인입니다. 논문 검색, 원문 수집, 문단 ID 부여, 온톨로지 추출, 감사, 초안 작성, 피어 리뷰를 독립 모듈로 실행하고 결과를 `runs/` 아래 JSON/Markdown artifact로 저장합니다.

현재 버전은 `0.6.0` 프로토타입입니다. 핵심 설계 원칙은 단순합니다: 생성된 주장과 리뷰는 원문 문단과 verbatim quote에 묶여야 하며, grounding이 깨지면 통과한 산출물로 취급하지 않습니다.

## 주요 기능

- 학술 검색 후보를 렌즈별 client로 수집합니다.
- 원문을 문단 단위로 나누고 `P_0001` 형식 ID를 부여합니다.
- LLM 또는 mock provider로 ontology/draft/review artifact를 생성합니다.
- `AuditGate`, `DraftComplianceAuditor`, peer-review grounding validator로 산출물을 검증합니다.
- 실행 결과를 `manifest.json`, `report.md`, typed JSON artifact, `runs/index.db`로 보존합니다.

## 설치

전역 도구로 설치:

```bash
uv tool install git+https://github.com/mitmirsein/omni-academic-framework.git
omni --status
omni --list-lenses
```

개발용 실행:

```bash
git clone https://github.com/mitmirsein/omni-academic-framework.git
cd omni-academic-framework
uv run omni --status
```

실 LLM 실행에는 Anthropic extra와 API key가 필요합니다.

```bash
uv run --extra llm omni --setup
```

## 빠른 시작

API key 없이 로컬 fixture로 ontology pipeline을 확인:

```bash
uv run omni ./examples/sample.md --module ontology --lens general --mock
```

초안 생성:

```bash
uv run omni ./examples/sample.md --module draft --lens general --mock
```

생성된 draft run을 리뷰:

```bash
uv run omni runs/examples-sample-md/latest --module review --lens general --mock
```

artifact 무결성 확인:

```bash
uv run omni --verify-run examples-sample-md/latest
```

## 자주 쓰는 명령

| 명령 | 용도 |
|---|---|
| `omni --status` | 환경, key, 외부 도구 상태 확인 |
| `omni --setup` | `.env` 대화형 설정 |
| `omni --list-lenses` | 사용 가능한 lens 목록 출력 |
| `omni <query> --lens theology` | 학술 후보 정찰(recon) |
| `omni ./paper.md --module ontology --mock` | 로컬 문서 ontology 생성 및 audit |
| `omni ./paper.md --module analyze --llm-analysis` | source-bound lens analysis 생성 |
| `omni ./paper.md --module draft` | grounded draft 생성 |
| `omni <draft-run> --module review` | draft peer review |
| `omni --show-run <run>` | 저장된 run 요약 |
| `omni --verify-run <run>` | artifact manifest 검증 |

## 모듈

| 모듈 | 산출물 |
|---|---|
| `recon` | `digest.json`, optional `fulltext.md`, `ontology.json`, `audit.json` |
| `ontology` | `paragraphs.json`, `ontology.json`, `audit.json` |
| `analyze` | `lens_brief.md`, optional `lens_analysis.json/md`, `lens_audit.json` |
| `draft` | `draft.json`, `draft.md`, `draft_audit.json` |
| `review` | grounding 통과 시 `review.json`, `review.md` |

## Gate 상태

각 실행 경로의 필수 gate가 통과하지 않으면 run은 `completed`로 표시되지 않습니다. 주요 terminal status는 다음과 같습니다.

- `completed`
- `blocked_by_audit`
- `blocked_by_draft_audit`
- `blocked_by_review_grounding`
- `blocked_by_source_audit`
- `review_rejected`
- `analysis_failed`
- `scraping_failed`

피어 리뷰 grounding 실패는 `failure.json`을 남기며, 실패한 리포트를 `review.json` 또는 `review.md`로 승격하지 않습니다.

## 설정

대부분의 사용자는 아래 변수만 확인하면 됩니다.

| 변수 | 필요한 경우 |
|---|---|
| `ANTHROPIC_API_KEY` | Live LLM ontology/analyze/draft/review |
| `SERPAPI_API_KEY` | Google Scholar search through SerpAPI |
| `SEMANTIC_SCHOLAR_API_KEY` | Higher Semantic Scholar rate limits |
| `OMNI_LIGHTPANDA_BIN` | Local browser scraping fallback |
| `OMNI_PDF_EXTRACTOR` | External PDF text extraction |
| `OMNI_LENS_DIR` | Custom lens directory |

`OPENAI_API_KEY`와 `GEMINI_API_KEY`는 future/alternate provider용이며 기본 live path에는 필요하지 않습니다.

## 문서

- [USER_GUIDE.md](./USER_GUIDE.md): 실제 사용 가이드
- [ARCHITECTURE.md](./ARCHITECTURE.md): 모듈 구조와 gate 설계
- [SCHEMAS.md](./SCHEMAS.md): JSON/Markdown artifact 계약
- [CHANGELOG.md](./CHANGELOG.md): 버전별 변경 사항
- [RELEASE_NOTES.md](./RELEASE_NOTES.md): 최신 릴리즈 요약
- [lenses/](./lenses): 기본 domain lens
- [examples/](./examples): 예제 입력 파일

## 개발

```bash
uv run ruff check
uv run python -m pytest -q
```

GitHub Actions도 같은 기본 품질 게이트를 실행합니다: lint, offline tests, CLI ontology smoke, artifact verification, byte-compile.

로컬 실행 산출물은 git에서 제외됩니다: `.env`, `.cache/`, `.venv/`, `runs/`, `handoff/`, `scratch/`, `.pytest_cache/`, `__pycache__/`.
