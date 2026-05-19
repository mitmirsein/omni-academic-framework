---
name: semantic-scholar
description: "Semantic Scholar API 기반의 학술 논문 및 인용 네트워크 탐색 에이전트. (API Key 필수)"
author: "MS_Dev"
version: "2.0.0"
triggers:
  - "#semanticscholar"
  - "#s2"
  - "#시맨틱스콜라"
category: "Intelligence & Workflow"
tags: ["recon", "api", "academic", "papers"]
---

# 🎓 Semantic Scholar (API) Recon Skill

> **Identity**: API 기반 초고속 학술 논문 탐색망
> **Core Tool**: `scripts/s2_runner.py`
> **Target**: semanticscholar.org (Graph API)

## 📌 개요 (Overview)
`semantic-scholar` 스킬은 **Semantic Scholar Graph API**를 활용하여 지정된 키워드나 논문을 검색하고, 인용 수, 초록, Open Access PDF 링크 등을 즉각적으로 마크다운 리포트로 생성하는 초고속 정찰 도구입니다.

> **⚠️ 주의 (Google Scholar와의 차이점)**:
> 브라우저 기반으로 실제 구글 스콜라 페이지를 탐색하고 렌더링하는 작업이 필요할 때는 **`google-scholar-semantic` (구글 스콜라 시맨틱)** 스킬을 사용하십시오. 본 스킬은 **순수 API 기반**이므로 브라우저를 띄우지 않으며 속도가 매우 빠릅니다.

## 🛠️ 사용법 (Usage)

### 1. 일반 키워드 검색
사용자의 키워드를 `--query`로 전달하여 즉각적인 논문 리스트를 확보합니다.

```bash
# 선행: optional 의존성 설치
uv sync --extra semantic-scholar

# 기본 검색 (터미널 출력)
uv run --extra semantic-scholar python skills/semantic-scholar/scripts/s2_runner.py --query "Pauline justification ethics" --limit 5

# 리포트 파일로 저장 (경로는 repo-relative 예시; 머신-로컬 절대경로 박지 말 것)
uv run --extra semantic-scholar python skills/semantic-scholar/scripts/s2_runner.py --query "Dietrich Bonhoeffer Sermon on the Mount" --limit 10 --output "./Evidence/S2_Bonhoeffer_Report.md"
```

## ⚙️ 아키텍처 및 설정 (Architecture)

1. **Authentication**: `.env`의 `SEMANTIC_SCHOLAR_API_KEY`를 사용합니다. 경로 규약은 `OMNI_ENV_FILE` 환경변수 > repo 루트 `.env` > 기본 탐색(머신-로컬 절대경로 하드코딩 없음). 키가 없어도 동작하지만 심각한 Rate Limit(3초당 1회)가 걸립니다.
2. **Output Format**: 생성되는 Markdown 리포트는 서지 정보(Authors, Year, Venue, Citations, Links, Abstract)를 포함하여 로컬 지식망에 즉시 편입할 수 있도록 규격화되어 있습니다.
