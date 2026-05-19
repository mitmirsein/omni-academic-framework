# Theology Translator: Terminology & References

시스템 내 번역 용어 관리 및 외부 참조 경로 규정입니다.

## 📖 Terminology Bible (Standard: Korean Protestant)
- **대한성서공회(개역개정)** 및 **한국 개신교 신학 용어** 사용을 절대 원칙으로 합니다. (가톨릭/성공회/북한어 용어 혼용 금지)
- **Primary Glossary**: `$DEV_ROOT/config/glossary.json` 또는 지정된 프로젝트별 용어집이 최우선 기준입니다.
- **TRE Governance**: `$DEV_ROOT/data/theological_terms.csv` — 용어의 표준성 검증을 위한 내부 학술 명명 규칙 레퍼런스.
- **Footnotes**: 각주는 반드시 `[1]`, `[2]`와 같은 숫자를 대괄호로 감싼 형태를 유지해야 합니다.

## 🔄 Internal Process Codes (에이전트 내부 추적용)
> **참고**: 이 코드는 에이전트의 워크플로우 진행 상태를 내부적으로 추적하기 위한 것이며,
> 산출물의 Frontmatter에 `status:` 필드로 기록하지 않습니다. (ARC v4.0 No-Status 원칙)

| 코드 | 의미 | 사용 위치 |
|:---|:---|:---|
| `INTAKE` | PM 전략 수립 중 | `_translation_state.json` |
| `DRAFTING` | 초벌 번역 진행 중 | `_translation_state.json` |
| `AUDITING` | Red-Team 검증 중 | `_translation_state.json` |
| `GATED` | Mechanical Audit 통과 대기 | `_translation_state.json` |
| `ARCHIVED` | 최종 병합 및 아카이빙 완료 | `_translation_state.json` |

## 🛠️ Data Storage
- 최종 결과물 저장 시 `draft`와 `critique` 내용을 `_translation_state.json`에 보존하여 추후 학습 데이터로 활용합니다.
- 번역 완료 후 동적 용어집(Glossary)은 PM이 마스터 용어집(`glossary.json`)에 머지 여부를 판단합니다.

---
*Theology Translator v5.1 — Fidelity Harness Edition*
