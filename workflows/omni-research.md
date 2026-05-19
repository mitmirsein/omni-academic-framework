---
description: "범용 학술 연구 및 논문 서베이 에이전트 가동 (omni-research)"
---

# 🌐 Agent Action Spec: `/omni-research` (Mosaic v2.0)

1. **[QUERY EXPANSION]**: 입력된 한국어 주제를 바탕으로 학술적 영어(EN) 및 독일어(DE) 전문 용어 세트를 생성한다. (Omni-Translator 로직 활용)
2. **[QUAD-ENGINE SEARCH]**: 다음 4대 엔진을 동시 가동하여 자료를 수집한다.
    - **KCI/RISS**: `kci-riss-mcp` (Lightpanda/InsaneRecon) 기반 하이브리드 탐찰.
    - **Google Scholar**: `search_web` 및 `scholar-quick`을 통한 상위 인용 논문 발굴.
    - **Google Scholar Semantic**: `skills/google-scholar-semantic/scripts/scholar_runner.py`를 통한 **Google Scholar Labs (AI-assisted) 시맨틱 정찰**.
    - **Semantic Scholar**: `skills/semantic-scholar/scripts/s2_runner.py`를 통한 **API 기반 정밀 메타데이터** 확보.
3. **[FORENSIC GATE]**: **의무 사항**. 모든 소스의 도메인(연구주제) 관련성을 감사하고 DOI/URL 실존 여부를 검증한다. 할루시네이션 및 주제 불일치 항목(노이즈)을 원천 차단한다.
4. **[PAF & APORETICS]**: Cathedral Engine of 1차 텍스트 분석 및 `MS_Brain.nosync` 지역 규칙(TRE 용어 등)을 적용한다.
5. **[OUTPUT: MOSAIC SCHEMA]**:
    - 본문은 학술적 인사이트와 논증적 TDD 중심으로 서술한다.
    - **Appendix: Research Inventory**: 모든 검증된 레퍼런스를 노트 최하단에 배치한다. (프론트매터 수록 금지)
    - **Forensic Audit Log**: 사용 엔진, 쿼리 전략, 필터링 내역을 수록한다.

> [!IMPORTANT]
> - **Scholar Labs Dynamic Option**: 자연어 질문 기반 정밀 정찰 시 `google-scholar-semantic` 스킬을 가동하여 Scholar Labs 데이터를 수집하고, 인용(Cite) BibTeX 메타데이터를 백바인딩(Back-binding)하여 EvidencePack을 강화한다.
> - **S2 API Priority**: 글로벌 논문 정찰 시 일반 웹 검색보다 `semantic-scholar` 전용 스킬(API) 사용을 우선한다.
> - **No Ghost Refs**: 직접 URL 확인이 불가능한 '유령 인용'은 절대 수록하지 않는다.
