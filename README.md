---
tags:
  - project
  - architecture
  - ai-agent
  - harness
  - ontology
created: 2026-05-19
status: Draft/V3-Palantir
---

# Omni-Academic Framework Initiative (v3.0 - Palantir Paradigm)

**Omni-Academic Framework**는 논문을 선형적으로 단순히 읽는 비효율을 넘어, 원문에서 핵심 온톨로지(지식 구조망)를 추출하고 다층 감사(Audit) 시스템으로 검증하여 학문적 통찰을 빠르게 장악하는 **팔란티어(Palantir)식 학술 지식 해체 엔진**입니다.

> [!WARNING]
> **Status: Prototype (v0.6.0).** 아래 문서는 목표 아키텍처(비전)를 서술하며, 일부는 미구현 청사진이다.
> - **구현됨** (카테고리별):
>   - **Recon 클라이언트**: arXiv, DBLP(CS), Crossref, EconBiz(경제학), PubMed(의학), OpenAlex(신학·인문학), Semantic Scholar, SerpAPI 기반 Google Scholar. config-driven 렌즈 레지스트리.
>   - **KCI 3경로(정직)**: (1) 무키 표준 OAI-PMH 수확 `--kci-harvest ARTI|ARTI_CONF|JOUR` — base `open.kci.go.kr/oai/request`(실검증 2026-05: 무인증·`oai_dc` 표준), OAI-PMH 2.0+DC 표준만 파싱·식별자 체계 검증·실 fragment 스냅샷, `resumptionToken` 페이지네이션(상한 `MAX_PAGES=50`). (2) `KCI_API_KEY` 있으면 Open API(실 `<MetaData>` 구조 검증·에러봉투 정직). (3) **키워드 검색은 httpx POST 웹검색** — 실검증된 `poSearchBean.conditionList=KEYALL`+`poSearchBean.keywordList` 계약(GET은 검색어 무시→인기 논문 반환 버그라 폐기), 응답에 검색어 미반영 시 오염 차단 0건 처리, **artiId→OAI `GetRecord` best-effort enrichment**(실패 시 웹 필드 유지, `OMNI_KCI_OAI_ENRICH=0`로 비활성). 전부 부재 시 정직한 빈 결과 → 신학·인문학 렌즈는 OpenAlex+Crossref로 degrade.
>   - **Audit Gates**: Ontology Paragraph-ID 부여 + AuditGate paragraph grounding(환각 차단); Gate 2 ForensicAuditor(DOI 문법+실존 ping·URL liveness·유령 인용 차단); Gate 3 LensComplianceAuditor MVP(렌즈 분석의 paragraph/source_quote/focus coverage 감사); 선택형 LLM self-redteaming critic(`--llm-critic`, `lens_critic.json/md`).
>   - **LLM 분석**: 실 AnthropicProvider(강제 tool-use+prompt caching); 선택형 source-bound Lens Analysis(`--llm-analysis`, `lens_analysis.json/md`, `lens_audit.json`, source_quote 재검증) — 운용화: grounding 위반 시 구체 오류 피드백 self-correcting 재시도 루프, `OMNI_LLM_MAX_TOKENS` 토큰 예산, 실 model/usage·재시도 횟수를 manifest `llm_usage`에 기록(mock은 낙인되어 실 usage 위장 불가); source-bound Lens Brief(`lens_brief.md`).
>   - **집필(Draft)**: `--module draft` — 온톨로지+문단 근거 기반 섹션별 초안 생성(`ScribeAgent`). 본문(prose)과 주장 원장(claims ledger) 분리로 무손실 하네스를 생성에 적용(모든 claim이 실존 `paragraph_id`+verbatim `source_quote`에 묶임, `[C#]` 앵커, `open_tensions` 보존); `DraftComplianceAuditor`가 claim/앵커 정합을 결정론적 감사(`draft.json/md`, `draft_audit.json`, manifest `draft_passed`).
>   - **피어 리뷰(Review)**: `--module review` — 작성된 초안(`draft.json`)을 기반으로 4인 리뷰어 패널(Ella, Miranda, Methodologist, Devil's Advocate)이 비평하고 편집장(Chief Editor)이 최종 판정 및 종합 평결을 수행(`PeerReviewPanel`). 비평 내 모든 `source_quotes`가 초안 본문에 실존하는지 결정론적 접지 검증(`review.json/md`, manifest `review_grounding_passed`, `review_passed`, `review_score`). grounding 실패 시 정식 review artifact로 승격하지 않고 `blocked_by_review_grounding` 상태와 `failure.json`을 남긴다.
>   - **스크래퍼**: LightpandaScraper(바이너리 subprocess — `OMNI_LIGHTPANDA_BIN` env/PATH, 하드코딩 제거, 미설정 시 정직하게 빈 문자열); PdfExtractorScraper(Content-Type 분기·pypdf 코어/`OMNI_PDF_EXTRACTOR` override·실패 시 정직); 외부 툴 경로 통일 규약(`omni_academic/config/tools.resolve_tool`: `OMNI_*` env > PATH > ""); HITL→Scraper→Ontology→Audit E2E.
>   - **영속화·모드**: RunStore(`runs/<id>/` typed JSON + 자기검증 manifest[mock 낙인·git commit·audit 평결·cache provenance·artifact sha256] + SQLite 인덱스; `--verify-run` 무결성 검증); ReconCache(별도 `.cache/recon.sqlite` 24h TTL·`--no-cache` 바이패스·manifest 적중 기록); Snowball(`--snowball <DOI>` OpenAlex 인용그래프 — `BaseAPIClient` 미오염 독립 모드).
>   - **운영·품질**: 시스템 진단 & 자동 셋업 대시보드(`--status`/쿼리 생략 시 `.env` 자동 생성·API 키/도구 유효성 UI); CI 품질 게이트(GitHub Actions: `ruff check`[E9/F/I] + 오프라인 pytest + byte-compile, `skills/`는 legacy 제외, scholar-browser extra로 Scholar 파서 snapshot까지 게이트); 실패 진단 artifact(`failure.json`: stage/scraper/HTTP status/content-type/raw excerpt, report.md 링크); Google Scholar 파서 snapshot 회귀 가드.
> - **`[BLUEPRINT]` (미구현)**: Gate 3 critic 결과 기반 자동 수정 루프.
> - **`[LEGACY]` (격리·정직 실패)**: `skills/google-scholar-semantic`의 stealth 브라우저 러너는 repo 미포함 외부 모듈 `agents.stealth_browser`에 의존 → 호출 시 raw 크래시가 아니라 명확한 `[LEGACY]` 메시지로 실패. 번들 지원 경로는 `SerpApiScholarClient`(+Lightpanda fallback). 외부 툴(Lightpanda/PDF 추출기)은 `OMNI_LIGHTPANDA_BIN`·`OMNI_PDF_EXTRACTOR` env로 주입(미설정 시 해당 경로만 비활성, 정직 실패).
> - **선행 조건**: clone 후 즉시 실행 시 **`uv run omni --setup`**을 가동하면 대화형 마법사가 실행되어 필수 API 키 및 설정을 `.env` 파일에 손쉽게 기록해 줍니다. 실 추출은 API Key 및 도구 설정 필요. `skills/*` 러너는 `uv run --extra semantic-scholar ...` 방식으로 optional extra를 켜야 합니다.

## 1. 프로젝트 철학과 핵심 가치 (Core Value)
본 프레임워크는 논문을 선형적으로 '읽는' 도구가 아니라, 다차원 정보망으로 '해체하고 장악하는' 팔란티어(Palantir)식 정보전 엔진을 지향합니다.
1. **Ontology-First (선 지식망 구축)**: 텍스트를 분석하기 전, 텍스트 내의 지형도(Entity-Relation)를 먼저 장악하여 할루시네이션의 여지를 원천 차단합니다.
2. **무자비한 감사(Audit) 시스템**: 화려한 생성 능력보다 기계적 대조와 무결성 사수를 최우선으로 삼아, 프레임워크의 가장 '빛나는 지점'으로 만듭니다.
3. **아포리아 보존 (Fidelity to Aporia)**: 원문의 환원불가 역설·논리적 긴장을 임의로 평탄화하거나 해소하지 않습니다. 양극을 별도 노드로 보존하고 `in_tension_with` 술어(경합·배타인 `conflicts_with`와 구분)로 묶습니다. 도메인별 강조(예: 양성론의 *vere Deus / vere homo*)는 코어가 아니라 렌즈 어댑터(`lenses/theology.yaml`)가 주입합니다 — 코어 엔진은 도메인 중립.

## 2. 아키텍처: 온디맨드(On-Demand) 유연성 구조 (Simple & Soft)
모든 단계를 강제로 밟아야 하는 무겁고 취약한 '폭포수 파이프라인'을 폐기합니다. 단일 진입점인 수퍼바이저(Supervisor)는 사용자의 요구 수준에 따라 각 모듈을 **레고 블록처럼 독립적으로 골라 쓰며(On-Demand)** 코드를 극도로 단순화합니다.

### 🧩 독립적 모듈 풀 (Tool Pool)
1. **`Recon Engine`**: 무겁게 원문을 다 파싱하지 않고, 가볍게 API와 메타데이터만 긁어와 다이제스트를 보고합니다. (가장 가벼운 정찰)
2. **`Ontology Extractor`**: 전체 분석이 부담스러울 때, 원문에서 핵심 뼈대인 지식망(Entity-Relation) 지형도만 JSON으로 빠르게 뽑아냅니다. 환원불가 역설은 `in_tension_with`로 보존합니다(평탄화 금지).
3. **`Lens Analyzers` (`Epistemic` 등)**: 온톨로지 맵과 원문을 동시에 넘겨받아(의미 탈락 방지), 사용자가 지목한 특정 지점만 정밀 타격합니다.
4. **`Scribe Agent` (집필)**: 온톨로지 맵과 문단 근거를 받아 섹션별 초안을 생성하되, 모든 사실 주장을 실존 문단·verbatim 인용에 묶는 주장 원장(claims ledger)으로 환각을 차단합니다.

### 🌊 부드러운 점진적 워크플로우 (Soft & Progressive)
- **Simple is Best**: 사용자가 "이 저널 이번 호 동향만 브리핑해"라고 하면 가볍게 Recon만 하고 멈춥니다. 
- **유연한 Audit (선택적 감사)**: 모든 작업에 무거운 3중 감사를 돌리지 않습니다. 가벼운 작업은 Gate 1(포맷)만 통과하고, 심층 분석에만 Gate 3(실증)를 돌려 엔지니어링 오버헤드와 비용을 획기적으로 낮춥니다.

## 🚀 Built-in Elite Tools Integration (내장형 정찰/스크랩 엔진) `[BLUEPRINT 일부]`
프레임워크는 메타데이터 수집에 더해 스크래핑/정찰 엔진을 내장하는 것을 **목표**로 한다. 단, `skills/`의 일부 러너(google-scholar-semantic)는 현재 repo에 미포함된 stealth browser 모듈에 의존하므로 클론만으로 즉시 독립 실행되지 않는다(선행 조건은 상단 Status 참조).

1. **Recon Phase (징발 전후)**: 
   - `insane-search`: 메타데이터 징발 전후로 가동하여 광범위한 트렌드와 키워드 맥락을 선제적으로 스캔합니다.
2. **Full-Text Scraping (HITL 승인 직후)**:
   - 사용자가 수퍼바이저를 통해 다이제스트 중 특정 논문(URL)을 승인하면 원문을 징발합니다.
   - `Jina Reader API`: 텍스트/HTML 논문을 즉시 고순도 Markdown으로 파싱합니다 (`https://r.jina.ai/`).
   - `lightpanda` (Headless Browser): JS 렌더링이나 복잡한 웹 환경의 논문을 우회 및 정밀 스크래핑합니다.

## 3. 다층 감사 시스템 (The Multi-Layered Audit Gates)
모든 서브 모듈은 반환 전 3중 철책선(Audit Gates)을 통과해야 합니다. (Fail-Fast & Retry)
* **Gate 1: I/O Envelope Audit (구조 감사)** — `[부분 구현]` paragraph grounding(노드 paragraph_id 원문 실존), self-loop/dangling/orphan 검증. 수식·토큰 비율 검증은 `[BLUEPRINT]`.
* **Gate 2: Forensic Search Audit (실증 감사)** — `[구현]` `ForensicAuditor`: DOI 문법 검증 + DOI/URL HEAD 실존 ping으로 '유령 인용/가짜 DOI/죽은 URL' 차단.
* **Gate 3: Lens Compliance Audit (렌즈 감사)** — `[MVP 구현]` `LensComplianceAuditor`: LLM lens analysis의 paragraph_id/source_quote grounding, focus_area coverage, limitations 존재 여부를 검증. `--llm-critic`은 별도 LLM self-redteaming pass를 실행하고 critic 자체도 grounding 감사한다.
* **Draft Compliance Audit (집필 감사)** — `[구현]` `DraftComplianceAuditor`: 생성된 초안의 모든 claim이 실존 문단·verbatim 인용·선언된 본문 `[C#]` 앵커에 묶였는지, 그리고 미해소 긴장이 `open_tensions`로 보존됐는지 결정론적으로 검증.

## 4. 실행 마일스톤 (Milestones)

- [x] **Step 1: Supervisor & Ontology 코어 구축**
  - 메인 진입점 프롬프트 설계 및 `Ontology Extractor` 선행 가동 구조 확립.
- [x] **Step 2: Sub-Nodes의 도구화 (Tooling) 및 다중 클라이언트 연동**
  - 기존 분석기 해체 후 호출 가능한 Tool 규격으로 재조립 및 Google Scholar, Semantic Scholar 등 다중 클라이언트 연동 완료.
- [x] **Step 3: Domain Lenses 세팅**
  - `lenses/` 디렉토리에 CS, MED, THEO 등 도메인별 렌즈(스키마) 파일 구축.
- [x] **Step 4: 통합 스트레스 테스트 (엔드투엔드)**
  - 지식망 추출 ➔ 정밀 분석 ➔ 3중 Audit 관문 통과의 전체 데이터 흐름 검증.
- [x] **Step 5a: Gate 3 Lens Compliance Audit MVP**
  - `--llm-analysis` 결과가 렌즈 focus와 원문 paragraph/source_quote에 묶여 있는지 기계적으로 감사.
- [x] **Step 5b: Gate 3 LLM Self-Redteaming Critic**
  - 렌즈 지침 충족 여부를 별도 critic pass로 자동 비판하고 critic quote도 grounding 감사.
- [ ] **Step 5c: Critic 기반 자동 수정 루프 `[BLUEPRINT]`**
  - critic 결과를 분석 재생성/수정 프롬프트로 되먹이는 bounded retry 구현.
- [x] **Step 6: 집필 모듈 (Drafting)**
  - `--module draft` ScribeAgent + DraftComplianceAuditor. 본문/주장 원장 분리로 무손실 하네스를 생성에 적용(grounding 재시도 루프 포함).
- [x] **Step 7: 아포리아 보존 술어**
  - `in_tension_with` 술어 + 렌즈 주입 directive로 환원불가 역설을 평탄화 없이 1급 보존(코어 도메인 중립).
- [x] **Step 8: 공유용 독립 패키징**
  - `omni_academic` 패키지화 + 렌즈 동봉으로 `uv tool install` 깨끗한 전역 설치(개인 vault/번역 파이프라인 결합 제거).
- [x] **Step 9: 피어 리뷰 패널 (Peer Review)**
  - `--module review` PeerReviewPanel + 4인 reviewer/Chief Editor YAML 설정 연동 완료. 리뷰 비평 앵커 grounding 검증기 및 E2E 테스트 통과.

## 🔧 설치 (Installation)

**전역 도구로 설치** (clone 불필요, 격리 환경에 `omni` 명령 등록):

```bash
uv tool install git+https://github.com/mitmirsein/omni-academic-framework.git
omni --status        # 진단/셋업
omni --list-lenses   # 동봉 렌즈 확인 (어느 디렉터리에서 실행해도 동작)
```

기본 렌즈(`cs`, `medical`, `theology` 등)는 패키지에 동봉되어 임의 디렉터리에서 실행해도 인식된다. 자신의 렌즈 디렉터리를 쓰려면 `$OMNI_LENS_DIR` 또는 `--lens-dir`로 주입한다.

**개발용 (clone 후 실행)**:

```bash
git clone https://github.com/mitmirsein/omni-academic-framework.git
cd omni-academic-framework
uv run omni --setup   # .env 대화형 생성
uv run omni "your query" --lens cs
```

---

## 5. API 환경 설정 가이드
본 프레임워크는 학술 데이터를 가공하고 검증하기 위해 다음과 같은 API 키 설정을 지원합니다. 터미널에서 **`uv run omni --setup`** 명령을 입력하여 대화형으로 한 번에 손쉽게 설정할 수 있습니다.

| 환경변수명 | 역할 / 용도 | 권장 설정 여부 | 발급 및 참고처 |
| :--- | :--- | :--- | :--- |
| **`ANTHROPIC_API_KEY`** | Claude 모델을 이용한 핵심 온톨로지 추출 및 본문 분석 | **필수 (Live 가동 시)** | [Anthropic Console](https://console.anthropic.com/) |
| **`OPENAI_API_KEY`** | ChatGPT 모델을 이용한 본문 가공 및 렌더링 | 선택 | [OpenAI Platform](https://platform.openai.com/) |
| **`GEMINI_API_KEY`** | Gemini 모델을 이용한 다차원 분석 및 요약 | 선택 | [Google AI Studio](https://aistudio.google.com/) |
| **`SEMANTIC_SCHOLAR_API_KEY`** | Semantic Scholar 기반 고속 학술 문헌 탐색 및 인용망 리스트 조회 | 선택 (미지정 시 3초당 1회 제한) | [Semantic Scholar API](https://www.semanticscholar.org/product/api) |
| **`SERPAPI_API_KEY`** | SerpAPI 기반 Google Scholar 키워드 문헌 탐색 | 선택 (미지정 시 구글 스콜라 쿼리 비활성화) | [SerpAPI](https://serpapi.com/) |
| **`JINA_API_KEY`** | 웹 페이지나 PDF 원문 URL에서 마크다운 형태 본문 추출 | 선택 (미지정 시 Fallback 사용) | [Jina Reader API](https://jina.ai/reader/) |

---
*Omni-Academic Framework | Portable Local Research Standard*
