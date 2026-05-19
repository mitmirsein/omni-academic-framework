# Author Mode: Agent Roles & Workflow

> **출처**: `reformed-translation-pipeline` v3.1에서 이식 (2026-04-17)
> omni-translator의 "Author Mode" 활성화 시 적용되는 에이전트 역할 확장.

Author Mode는 바르트, 본회퍼 등 **특정 저자의 원전(1차 문헌)**을 시대감각까지 보존하며 번역할 때 활성화됩니다.
기본 워크플로우(Fidelity Harness)의 4역할 위에 **Exegetical Analyst** 역할이 추가됩니다.

---

## Step 0: Pre-Translation Analysis (The Exegetical Analyst) ← Author Mode 전용
**핵심 역할**: 다의어(Geist, Wort, Aufhebung 등)의 저자별/시대별 정의 스캔.
- `payload-schema.md`의 `metadata.year` 및 `historical_context`를 기반으로 시대 착오적 번역 방지.
- 프로젝트 전용 용어집(Glossary) 조회 및 'Translation Strategy Note' 생성.
- **결과물**: JSON 형식의 **용어 주입 지침** — 이 지침은 Draft Agent에게 전달.

## Step 1~4: 기본 워크플로우 (SKILL.md 참조)
Fidelity Harness의 표준 4역할(PM → Draft → Reviewer → Editor)이 그대로 적용됩니다.
단, Author Mode에서는 Draft Agent가 Strategy Note의 **용어 주입 지침을 반드시 준수**합니다.

## Author Mode 추가 체크리스트
- [ ] 신명(Divine Names: God, Lord, YHWH)의 일관성
- [ ] '신학적 편향(Theological Drift)' 발생 여부
- [ ] 저자 고유 개념어(예: Dialektik, Vollzug)가 `한국어(Original)` 형식으로 표기
- [ ] '번역 불가능한 개념'은 각주로 처리

---
*Migrated from reformed-translation-pipeline v3.1 → omni-translator v5.1*
