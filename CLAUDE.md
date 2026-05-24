# Omni-Academic Framework: Agent Constitution (v1.0)

Last updated: 2026-05-19

이 문서는 `omni-academic-framework` 프로젝트에 참여하고 코드를 수정하는 모든 에이전트가 반드시 준수해야 할 최상위 지역 헌법(Local Constitution)이다.

## 1. 프로젝트 철학 (Project Philosophy)
우리는 특정 학문(도메인)에 종속된 학술 연구 툴을 만들지 않는다. **"어떤 학문적 텍스트가 주어지든 그 본질적 구조와 논증을 무손실로 포착해 내는 보편적 학술 엔진"**을 설계한다.

## 2. 도메인 독립성의 원칙 (Domain Agnosticism)
- **Hard-coding 금지**: 코어 모듈(`academic-research`)의 메인 로직에는 절대로 특정 학문(신학, 의학, 법학, CS 등)의 전문 용어나 고유 인용 규칙을 하드코딩하지 않는다.
- **Adapter-based Assembly**: 모든 도메인 특화 규칙은 반드시 런타임 매개변수(`--domain`)나 외부 어댑터(Adapter/Plugin) 파일로부터 동적으로 주입(Injection)되어야 한다.

## 3. 무손실 하네스 통제 (Fidelity Harness First)
- 기계적 무손실 검증 장치(문단 `¶ ID Binding`, 토큰 비율 방어선, 할루시네이션 차단 Forensic Audit)는 본 아키텍처의 심장이자 타협 불가능한 최우선 통제 계층이다.
- 서베이 과정에서 원문의 논리적 긴장이나 모순(Aporetics)을 에이전트 임의로 평탄화(Flattening)하거나 요약하는 행위를 엄격히 금지한다. 구조는 그대로 보존되어야 한다.

## 4. 자가-동기화 및 동적 튜닝 (Dynamic Auto-Tuning)
- 에이전트는 정적 사전(Static Dictionary)에 의존하는 대신, 입력된 텍스트의 앞부분을 스캔하여 해당 학문적 특성과 문체를 파악하고 **동적 용어집(Dynamic Glossary)** 및 **문체 가이드(Style Guide)**를 스스로 생성하여 하네스에 장착하는 것을 기본 메커니즘으로 삼는다.

## 5. 인터페이스 개방성 (Pluggable Architecture)
- 정보 수집(Search) 및 메타데이터 파싱 구조는 `KCI/RISS`, `Google Scholar`, `Semantic Scholar`뿐만 아니라 `arXiv`, `PubMed` 등 다양한 분야별 엔진을 쉽게 탈부착(Plug-and-play)할 수 있도록 모듈화해야 한다. 엔진 간의 결합은 최소화한다.

---
*Omni-Academic Framework는 상위 글로벌 헌법의 상속을 받되, 범용성을 우선하는 개발 룰을 적용받는다.*
