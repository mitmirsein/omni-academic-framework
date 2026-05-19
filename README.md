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

## 🚀 Elite Tools Integration Blueprint (외부 스킬망 통합)
프레임워크는 단순히 메타데이터를 긁어오는 것에 그치지 않고, 기보유한 **강력한 외부 무기(External Elite Tools)**들을 각 파이프라인의 적재적소에 플러그인으로 호출합니다.

1. **Recon Phase (징발 전후)**: 
   - `insane-search`: 메타데이터 징발 전후로 가동하여 광범위한 트렌드와 키워드 맥락을 선제적으로 스캔합니다.
2. **Full-Text Scraping (HITL 승인 직후)**:
   - 사용자가 수퍼바이저를 통해 다이제스트 중 특정 논문(URL)을 승인하면 원문을 징발합니다.
   - `Jina Reader API`: 텍스트/HTML 논문을 즉시 고순도 Markdown으로 파싱합니다 (`https://r.jina.ai/`).
   - `lightpanda` (Headless Browser): JS 렌더링이나 복잡한 웹 환경의 논문을 우회 및 정밀 스크래핑합니다.

## 3. 다층 감사 시스템 (The Multi-Layered Audit Gates)
모든 서브 모듈은 반환 전 3중 철책선(Audit Gates)을 통과해야 합니다. (Fail-Fast & Retry)
* **Gate 1: I/O Envelope Audit (구조 감사)** - `¶ 문단 ID`, 수식, 토큰 비율 훼손 검증.
* **Gate 2: Forensic Search Audit (실증 감사)** - '유령 인용(Ghost Ref)' 및 가짜 DOI 교차 검증.
* **Gate 3: Schema Compliance Audit (스키마 감사)** - 장착된 렌즈(Lens)의 지침과 Phase 1의 온톨로지 맵을 위배하지 않았는지 무자비하게 비판(Self-Redteaming).

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
