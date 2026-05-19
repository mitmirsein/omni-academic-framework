---
name: "Omni-Academic Ontology Extractor"
description: "표준 온톨로지 방법론(Triples)을 기반으로 학술 텍스트의 지식 지형도를 추출하는 Phase 1 정찰 모듈"
version: "1.0"
type: "core_skill"
---

# 1. 지식 추출 기본 원칙 (Ontology Fundamentals)
이 모듈은 깊은 시맨틱(의미론적) 해석을 시도하지 않습니다. 어떠한 학문 도메인이든 적용될 수 있도록, 학술 텍스트를 **RDF Triple 표준 구조 (Subject - Predicate - Object)**로 단순화 및 정규화하여 추출하는 데 집중합니다.

# 2. 범용 엔티티 클래스 (Universal Classes)
도메인에 종속되지 않도록, 학문 일반에 공통 적용되는 핵심 표준 클래스를 제한적으로 추출합니다.
- `[Concept]` : 핵심 개념, 이론, 알고리즘, 질병명, 철학적 용어
- `[Actor]` : 연구자, 학파, 연구 기관, 사상가
- `[Method]` : 연구 방법론, 실험 기법, 수학적 증명 방식, 분석 툴
- `[Claim/Data]` : 주요 논증, 발견된 실증 데이터, 성능 지표
- `[Artifact/System]` : 연구를 통해 개발된 산출물, 프레임워크, 소프트웨어 시스템
- `[Context/Setting]` : 연구의 역사적 배경, 임상 조건, 실험 환경
- `[Limitation/Gap]` : 기존 연구의 한계점, 학술적 공백, 극복 대상

# 3. 표준 관계 어휘 (Standard Relations)
노드(Node) 간의 엣지(Edge)를 연결할 때는 임의의 단어를 쓰지 않고, 다음의 표준 온톨로지 술어(Predicate)를 엄격히 제한하여 사용합니다.
- 계층 구조: `is_a` (상하위/종속), `part_of` (구성 요소)
- 진화 및 파생: `builds_on` (~에 기반함), `is_derived_from` (~로부터 파생됨)
- 인과 및 상관: `causes` / `leads_to` (인과관계), `correlates_with` (상관관계)
- 학술적 논증: `supports` (지지/입증), `conflicts_with` / `criticizes` (모순/비판)
- 문제 해결: `addresses` / `resolves` (한계점이나 문제를 해결함)
- 도구 사용: `uses_method` (방법론 차용)

# 4. 출력 규격 및 감사 (Output Envelope & Audit)
- 추출된 지식망은 후속 모듈(`Translator` 등)이 맵으로 파싱할 수 있도록 **엄격한 JSON 그래프 구조**로 반환되어야 합니다.
- **[Audit Gate]**: 추출된 모든 노드(Node)는 원문에서 자신이 기원한 **`¶ 문단 ID`와 반드시 매핑(Binding)**되어야 합니다. 출처 ID가 없는 허구의 노드(Hallucination)가 생성되면 무결성 감사에서 즉각 폐기(Fail)됩니다.
