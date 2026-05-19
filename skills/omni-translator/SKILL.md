---
name: omni-translator
description: Translates academic documents using a Fidelity Harness that structurally prevents summarization. Features Phase 0 Pre-Forensics (Style Guide) and 3-stage Agent Role Isolation (Drafter, Red-Team Auditor, Stylist) for zero-loss integrity.
version: 6.0.0 (Agent Role Isolation & Style Guide Enforcement)
author: Omni-Academic Framework
triggers:
  - "이 문서 번역해줘"
  - "번역 초안 만들어줘"
  - "검수 팀 가동해"
  - "#번역"
  - "/translate"
  - "translate [file] using omni pipeline"
capabilities:
  - orchestrator_led_translation_team
  - paragraph_id_binding
  - fidelity_harness_enforcement
  - multi_persona_agentic_loop
  - zero_loss_integrity_gate
  - incremental_continuity
  - author_mode_activation
default_direction: "외국어(DE/EN/LA) → 한국어(KO)"
references_path: "./references"
---

# 📜 Omni Translator v6.0 — Agent Role Isolation Edition

## 0. Design Philosophy: Why "Harness", Not "Rule"

> **"번역하지 마라"는 규칙은 깨질 수 있다. "번역하지 못 하게" 만드는 구조는 깨지지 않는다.**

AI 번역 에이전트의 가장 치명적인 본능은 **요약(Summarization)**이다. 이 스킬은 '요약하지 말라'고 지시하는 대신, 원문의 **모든 단락에 물리적 ID를 부여**하고, 번역문에서 해당 ID가 누락되면 **기계적으로 진행을 차단**하는 '속박 장치(Harness)'를 핵심 엔진으로 가동한다.

---

## 1. The Fidelity Harness (충실도 속박 장치) — 핵심 메커니즘

### 1.1 ¶ ID Binding (단락 바인딩)
```
[규칙] 원문의 모든 단락에 [¶1], [¶2], ... [¶N] ID를 부여한다.
       번역문의 모든 단락에 동일한 [¶N] ID를 반드시 기재한다.
       ID가 없는 번역 단락은 존재하지 않는 것으로 간주한다.
```
- INTAKE 단계에서 PM이 원문에 ¶ ID를 할당한 **Structural Manifest**를 생성.
- 번역자는 반드시 각 번역 단락 앞에 `[¶N]`을 표기.
- 검증자는 원문 ¶ ID 목록과 번역문 ¶ ID 목록을 기계적으로 대조.

### 1.2 Token Ratio Guard (토큰 비율 경비)
```
[규칙] 번역문의 총 문자 수는 원문 총 문자 수의 70% 이상이어야 한다.
       (한국어는 라틴 문자 대비 압축적이므로 70%를 하한선으로 설정)
       70% 미만 시 → ❌ RATIO_FAIL → 전체 번역 반려, 누락 조사 개시.
```
- 영어/독어 원문 → 한국어 번역 시 자연스러운 압축은 허용하되, 정보 손실에 의한 축소는 차단.
- 비율 계산은 GATE 단계에서 `translator_audit.py`가 자동 수행.

### 1.3 Anti-Summary Tripwire (요약 방지 지뢰선)
```
[규칙] 다음 패턴이 번역문에서 탐지되면 즉시 HALT → PM 수동 검토:
  - "~에 대해 설명한다" / "~을(를) 요약하면"
  - "~의 요지는" / "핵심은 ~이다"
  - "(중략)" / "(이하 생략)" / "등등"
  - 원문에 없는 meta-commentary ("저자는 여기서 ~을 주장한다")
```
- 이 패턴들은 번역이 아닌 **해설/요약의 징후**이다.
- Red-Team 단계에서 Auditor가 정규식 수준으로 탐지.

### 1.4 Per-Turn Parity Check (턴별 동수 검증)
```
[규칙] 매 턴 종료 시 다음을 확인:
  ✅ 이번 턴에서 번역한 ¶ ID 목록 == 이번 턴에 할당된 원문 ¶ ID 목록
  ✅ 누락된 ¶ ID가 0건
  ❌ 1건이라도 누락 → 해당 턴 반려, ¶ ID 기준으로 보완 지시
```

---

## 2. Core Workflow (Incremental Fidelity)

### Phase 0: [PRE-FORENSICS — 글로벌 컨텍스트 통합]
대규모 작업(책, 장편 논문) 시 번역 착수 전 **반드시** 선행하는 단계입니다.
1. **Dynamic Glossary 추출**: 샘플 구간(서론, 결론, 핵심 장)을 먼저 읽고 반복 등장하는 핵심 개념어 추출 (기존 `tre_terms.csv`와 대조).
2. **Project Style Guide 생성**: 타겟 저자의 국내 번역본 문체 특성을 수치화한 가이드라인(`project_style_guide`)을 JSON 형태로 선언합니다. (종결어미, 피동형 금지, 고유명사 처리 기준 등 포함).
3. **STATE INIT**: `_translation_state.json` 생성/로드. 진행 현황 및 누적 용어집 보존.

### Phase 1: [INTAKE — PM 전략 수립]
1. 원문을 읽고 **Structural Manifest** 생성:
   ```
   === STRUCTURAL MANIFEST ===
   총 단락(¶): 47개 / 총 문장: 312개 / 원문 총 문자 수: 28,450자
   번역 하한선(70%): 19,915자
   ===========================
   ```
2. **Workload Balancing (Turn Splitting)**: 단락(¶) 밀도와 고유명사 빈도를 기준으로 전체 ¶를 N개의 균등한 턴으로 분할.

### Phase 2: [DRAFT — 무손실 전사 (Agent 1: The Drafter)]
- **목표**: 원문의 단어와 구조를 한국어로 1:1 무손실 덤프(Dump). 가독성은 무시합니다.
- **제약**: "문장을 매끄럽게 다듬지 마십시오." "모든 단락 앞에 `[¶N]` ID를 기재하십시오." "압축/요약 절대 금지."
- **Context Diet**: 새 턴 시작 시 이전 턴의 마지막 30~50라인만 Anchor로 읽어들여 논리적 응집성(Cohesion) 확보.
- **결과물**: 뻑뻑하지만 정보가 100% 보존된 [Draft_v1].

### Phase 3: [AUDIT — 적대적 대조 검증 (Agent 2: The Red-Team Auditor)]
- **목표**: 번역을 직접 수정하지 않고, [Draft_v1]과 원문을 비교해 **'누락'과 '용어 오류'만 색출**합니다.
- **제약**: "오역을 잡아내는 감사관입니다. 번역을 직접 수정하지 마십시오." "원문과 번역문의 문장 동수, 수식어 생략 여부를 적대적으로 대조하십시오."
- **Full Translation Audit**: 원문 1문장 = 번역 1문장 전수 확인.
- **Per-Turn Parity Check**: ¶ ID 대조 → 누락 0건 기계적 확인.
- **결과물**: 누락/오류 지적 리포트. (이후 Agent 1이 이를 반영하여 [Draft_v2] 생성).

### Phase 4: [REFINE — 문체 교정 및 기계적 윤문 통제 (Agent 3: The Stylist)]
- **목표**: 오류가 없는 [Draft_v2]를 받아 Phase 0에서 정의한 `project_style_guide`에 맞춰 한국어 학술 텍스트의 격조를 부여합니다.
- **입력**: 원문을 주지 않고 **[Draft_v2] + [project_style_guide]**만 제공합니다. (직역투 회귀 방지)
- **제약**: "원래의 정보량을 1%도 축소/삭제하지 마십시오."
- **기계적 대조**: 윤문 완료 전, Style Config의 모든 항목(종결어미, 피동형 금지 등)을 100% 준수했는지 Boolean 자가 진단 리포트 의무 제출.
- **결과물**: 최종 윤문된 조각 파일.

### Phase 5: [GATE — Mechanical Audit]
> **모든 턴 종료 및 물리적 병합 완료 후 실행.**

```bash
uv run python agents/translator_audit.py --source <원문> --target <최종번역본>
```

| 검사 항목 | 담당 Role | 통과 기준 | 실패 시 |
|:---|:---:|:---|:---|
| Full Translation (전문 완결성) | Agent 2 | 원문 전 문장 1:1 대응 확인 | ❌ 누락 문장 목록 → Phase 2 재번역 |
| F-Score (내용 보존율) | Agent 2 | ≥ 0.90 | ❌ 누락 목록 포함 반려 |
| ¶ Parity (단락 동수) | Agent 2 | 100% 일치 | ❌ 누락 ¶ ID 목록 제시 |
| Token Ratio (문자 비율) | Python 스크립트 | ≥ 70% | ❌ RATIO_FAIL → 축소 의심 조사 |
| Tripwire (요약 패턴) | Agent 2 | 0건 탐지 | ⚠️ PM 수동 검토 |
| Style Guide 대조 | Agent 3 | 100% 준수 리포트 | ⚠️ Phase 4 재윤문 |

- **모든 항목 PASS** → ✅ PM 최종 검수 → ARCHIVE 진행.
- **1건이라도 FAIL** → ❌ 해당 구간 Phase 2 재시작.

### Phase 6: [ARCHIVE]
- 조각 파일 최종 병합.
- F-Score 리포트 및 ¶ Parity 리포트 생성.
- 동적 용어집 → 마스터 용어집에 병합 제안.
- 마스터 아카이브(Inbox) 이동.

---

## 3. YT Subtitle SOP (유튜브 자막 번역 표준 공정)

> **트리거**: 유튜브 자막(.vtt/.srt) 파일 기반 번역 요청 시 `yt_lecture_protocol.md` [v2.0](./references/yt_lecture_protocol.md)을 **자동으로 로드**하여 아래 공정을 강제 실행한다.

### 공정 개요 (3 Pipeline → 2 Mandatory Audit)

| 단계 | 명칭 | 핵심 작업 |
|:---:|:---|:---|
| **1** | 소스 확보 (Source Provision) | `yt-dlp`로 .vtt 다운로드. 원본 파일 영구 보존. |
| **2** | 원어 교정 (Source Refinement) | ASR 노이즈 제거, 완성 문장 재구성, ¶ ID 부여, 팩트체크. `_Refined.de.md`로 저장. |
| **3** | 하네스 번역 (Fidelity Translation) | 교정본 1:1 번역, ¶ ID 계승, Append 프로토콜로 순차 안치. |
| **검수 1** | 완결성 감사 — **MANDATORY** | `grep -o "\[¶[0-9]*\]" | wc -l`로 교정본↔번역본 ¶ 수 100% 일치 확인. |
| **검수 2** | 품질 감사 — **MANDATORY** | Anti-Summary 트리폼, 팩트 정확성, 용어 일관성, Token Ratio ≥ 70% 확인. |
| **후반** | 문서 최종화 (Post-Processing) | YAML 메타데이터, 요약(Summary), 글로서리(Glossary) 추가. |

> ⚠️ **두 검수는 생략 불가 의무 사항이다.** 검수 결과는 번역본 하단에 반드시 기재한다.

---

## 4. Author Mode (고위험 원전 번역 모드)

바르트, 본회퍼 등 특정 저자의 1차 문헌을 번역할 때는 `Author Mode`를 활성화하여 시대감각과 고유 문체를 보존합니다.

1. **활성화 조건**: 사용자가 원전 번역을 지시하거나 JSON Payload를 제공할 때.
2. **사전 분석 (Exegetical Analyst)**: 번역 전 `payload-schema.md`에 명시된 메타데이터(시대, 저자, style_tuner)를 기반으로 '번역 전략 노트'를 도출.
3. **Draft 에이전트 제약**: 일반 DRAFT 역할 위에 Author Mode 제약(신명 일관성 유지, 원어 병기)이 추가 적용됨.

> **관련 레퍼런스**: [author-mode-roles.md](./references/author-mode-roles.md), [payload-schema.md](./references/payload-schema.md)

---

## 5. Reference Links
- [gotchas.md](./references/gotchas.md): 학술 번역 시 피해야 할 함정, Red-Team Protocol, Anti-Summary Tripwire.
- [yt_lecture_protocol.md](./references/yt_lecture_protocol.md): **[v2.0 ARC SOP]** YT 자막 번역 3단계 세부 공정 + 의무 2단계 검수 기준.
- [translation-loop.md](./references/translation-loop.md): 4역할 에이전틱 루프의 작동 원리.
- [status-terminology.md](./references/status-terminology.md): 표준 용어집 및 참조 경로 규정.
- [payload-schema.md](./references/payload-schema.md): Author Mode 입력 규격.
- [author-mode-roles.md](./references/author-mode-roles.md): Author Mode 에이전트 확장 역할.

---
*Omni Translator v6.0 — Agent Role Isolation Edition | Portable Skill Standard*
