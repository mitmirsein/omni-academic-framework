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

> [!WARNING]
> **Status: Prototype (v0.5.0).** 아래 문서는 목표 아키텍처(비전)를 서술하며, 일부는 미구현 청사진이다.
> - **구현됨**: Recon(arXiv는 `arxiv` 라이브러리, KCI/Crossref/EconBiz/PubMed/OpenAlex 실 API; EconBiz=경제학, PubMed=의학, OpenAlex=신학·인문학 렌즈), config-driven 렌즈 레지스트리, Paragraph-ID 부여, AuditGate paragraph grounding(환각 차단), Gate 2 ForensicAuditor(DOI 문법+실존 ping, URL liveness, 유령 인용 차단), 실 AnthropicProvider(강제 tool-use+prompt caching), LightpandaScraper(lightpanda 바이너리 subprocess — 경로는 `OMNI_LIGHTPANDA_BIN` env 또는 PATH; 하드코딩 제거; 미설정 시 정직하게 빈 문자열), 외부 툴 경로 통일 규약(`src/config/tools.resolve_tool`: `OMNI_*` env > PATH > ""), HITL→Scraper→Ontology→Audit E2E, RunStore 산출물 영속화(`runs/<id>/` typed JSON + 자기검증 manifest[mock 낙인·git commit·audit 평결·cache provenance] + SQLite 인덱스; `--export-vault`로 audit통과·non-mock만 볼트 Inbox/Drafts 옵트인 export), PdfExtractorScraper(Content-Type 분기·pypdf 코어/`OMNI_PDF_EXTRACTOR` 외부툴 override·실패 시 정직), ReconCache(별도 `.cache/recon.sqlite` 24h TTL·`--no-cache` 바이패스·manifest에 적중 기록), Snowball(`--snowball <DOI>` OpenAlex 인용그래프 — `BaseAPIClient` 미오염 독립 모드).
> - **`[BLUEPRINT]` (미구현)**: Gate 3 Schema/Lens self-redteaming(LLM 의존), `skills/`의 stealth browser 의존 러너(외부 모듈 미포함). 외부 툴(Lightpanda/PDF 추출기)은 `OMNI_LIGHTPANDA_BIN`·`OMNI_PDF_EXTRACTOR` env로 주입(미설정 시 해당 경로만 비활성, 정직 실패).
> - **선행 조건**: clone 후 즉시 실행은 `--mock` 경로에 한함. 실 추출은 LLM provider 연결 필요. `skills/*` 러너는 `pip install -e ".[semantic-scholar,scholar-browser]"` 및 별도 stealth browser 모듈 필요(현재 repo 미포함).

## 1. 프로젝트 철학과 핵심 가치 (Core Value)
본 프레임워크는 논문을 선형적으로 '읽는' 도구가 아니라, 다차원 정보망으로 '해체하고 장악하는' 팔란티어(Palantir)식 정보전 엔진을 지향합니다.
1. **Ontology-First (선 지식망 구축)**: 텍스트를 분석하기 전, 텍스트 내의 지형도(Entity-Relation)를 먼저 장악하여 할루시네이션의 여지를 원천 차단합니다.
2. **무자비한 감사(Audit) 시스템**: 화려한 생성 능력보다 기계적 대조와 무결성 사수를 최우선으로 삼아, 프레임워크의 가장 '빛나는 지점'으로 만듭니다.

## 2. 아키텍처: 온디맨드(On-Demand) 유연성 구조 (Simple & Soft)
모든 단계를 강제로 밟아야 하는 무겁고 취약한 '폭포수 파이프라인'을 폐기합니다. 단일 진입점인 수퍼바이저(Supervisor)는 사용자의 요구 수준에 따라 각 모듈을 **레고 블록처럼 독립적으로 골라 쓰며(On-Demand)** 코드를 극도로 단순화합니다.

### 🧩 독립적 모듈 풀 (Tool Pool)
1. **`Recon Engine`**: 무겁게 원문을 다 파싱하지 않고, 가볍게 API와 메타데이터만 긁어와 다이제스트를 보고합니다. (가장 가벼운 정찰)
2. **`Ontology Extractor`**: 전체 분석이 부담스러울 때, 원문에서 핵심 뼈대인 지식망(Entity-Relation) 지형도만 JSON으로 빠르게 뽑아냅니다.
3. **`Lens Analyzers` (`Epistemic`, `Translator` 등)**: 온톨로지 맵과 원문을 동시에 넘겨받아(의미 탈락 방지), 사용자가 지목한 특정 지점만 정밀 타격합니다.

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
* **Gate 3: Schema Compliance Audit (스키마 감사)** — `[BLUEPRINT]` 렌즈 지침 self-redteaming 미구현.

## 4. 실행 마일스톤 (Milestones)

- [ ] **Step 1: Supervisor & Ontology 코어 구축**
  - 메인 진입점 프롬프트 설계 및 `Ontology Extractor` 선행 가동 구조 확립.
- [ ] **Step 2: Sub-Nodes의 도구화 (Tooling)**
  - 기존 번역/분석기 해체 후, 오케스트레이터가 호출 가능한 Tool 규격으로 재조립.
- [ ] **Step 3: Domain Lenses 세팅**
  - `lenses/` 디렉토리에 CS, MED, THEO 등 도메인별 렌즈(스키마) 파일 구축.
- [ ] **Step 4: 통합 스트레스 테스트 (엔드투엔드)**
  - 지식망 추출 ➔ 정밀 분석 ➔ 3중 Audit 관문 통과의 전체 데이터 흐름 검증.

---
*Omni-Academic Framework | MS_Dev Third Gen Standard*
