# 🎬 YouTube & Lecture Subtitle Translation Protocol (v2.0)

> **ARC SOP (Standard Operating Procedure)**: 이 문서는 유튜브 자막 및 강연 녹취물을 고정밀 번역하기 위한 **표준 공정(SOP)**이다.
> 본 공정은 반드시 **3단계 파이프라인 → 2단계 의무 검수** 순서로 실행된다.

---

## 📦 파이프라인 전체 구조

```
[단계 1] VTT 소스 확보   →   [단계 2] 원어 교정   →   [단계 3] 하네스 번역
                                                              ↓
                                               [검수 1] 완결성 감사 (¶ Parity)
                                                              ↓
                                         [검수 2-A] Red-Team Pass (원문 대조 + Full Translation)
                                                              ↓
                                         [검수 2-B] Receiver Pass (번역문 독립 읽기)
                                                              ↓
                                                    [후반 작업] 메타/요약/글로서리
```

---

## 1단계: 자막 소스 확보 (Source Provision)

### 1.1 다운로드 표준 명령어
```bash
# 자막 목록 확인
yt-dlp --list-subs [URL]

# 수동 제작 자막 다운로드 (우선)
yt-dlp --write-subs --skip-download --sub-lang de [URL] -o "[파일명].%(ext)s"

# 자동 생성 자막(ASR) 다운로드 (수동 자막 없을 시)
yt-dlp --write-auto-subs --skip-download --sub-lang de [URL] -o "[파일명].%(ext)s"
```

### 1.2 파일 명명 규칙 (Naming Convention)
```
원본: [제목_약어].[언어].vtt           예: Glaube_Wissenschaft_Spiess.de.vtt
교정본: [제목_약어]_Refined.[언어].md  예: Glaube_Wissenschaft_Spiess_Refined.de.md
번역본: [제목_약어]_KR.md              예: Glaube_Wissenschaft_Spiess_KR.md
```

### 1.3 파일 보존 원칙 (Traceability)
- **원본(Raw VTT/SRT)**: 영구 보존. 번역의 물리적 증거. `Raw/` 폴더에 안치.
- **교정본(Refined)**: 영구 보존. 번역의 SSOT(단일 진실 공급원). `Raw/` 폴더에 안치.
- **번역본(KR.md)**: 최종 산출물. 검수 완료 후 `Raw/` to `Library` 승격.
- **임시 스크립트** (vtt_cleaner.py 등): 작업 완료 후 **즉시 삭제**.

---

## 2단계: 원어 교정 (Source Refinement)

> **목적**: ASR 자막의 노이즈(끊긴 문장, 중복 행, 말더듬)를 제거하고, 완성된 학술적 원문을 확보한다. 이 단계의 품질이 번역 품질을 결정한다.

### 2.1 교정 항목 체크리스트
| 항목 | 처리 방식 |
|:---|:---|
| 타임스탬프 HTML 태그 (`<00:00:01.000><c>단어</c>`) | **제거** |
| 중복 행 (같은 문장이 연속 등장) | **중복 제거** |
| 말더듬 (`äh`, `ähm`, `또`, `그`, `어`) | **문맥 판단 후 제거 또는 유지** |
| 끊긴 문장 (행 말미에 잘린 단어) | **다음 행과 합쳐 완성 문장으로 재구성** |
| 오인식 전문용어 / 고유명사 | **팩트체크 후 교정** (예: 학자 직함, 서명, 지명) |
| 잘못된 단어 치환 (ASR 오류) | **원어 사전 확인 후 교정** |

### 2.2 ¶ 번호 부여 (ID Binding)
- 교정본에서 **문맥적으로 완결된 사유 단위**마다 `[¶N]` ID를 부여한다.
- 한 문장이라도 독립적 논지를 가지면 독립 단락으로 처리 가능.
- ¶N은 최종 번역본의 ID와 반드시 1:1로 매핑된다.

```markdown
[¶1] Ich freue mich, wieder einmal hier zu sein, ...
[¶2] Ich war zum ersten Mal in Halle vor 46 Jahren, ...
```

---

## 3단계: 하네스 기반 번역 (Fidelity Translation)

> **핵심**: `theology-translator` 스킬의 **Fidelity Harness (§1)** 전체 적용. 교정본의 ¶ 구조를 그대로 계승.

### 3.1 번역 원칙
- **전체 번역(Full Fidelity)**: 임의 축소/요약 절대 금지. 모든 비유, 예시, 반복 강조를 그대로 전사.
- **¶ ID 계승**: 교정본의 `[¶N]` ID를 번역본에서도 동일하게 사용.
- **Append 프로토콜**: `cat >> [번역파일].md`로 순차 안치. 작업이 끊겨도 연속성 보장.
- **대상 독자**: 주니어 대학생 수준의 명료하고 격조 있는 학술 한국어.
- **비텍스트 제거**: 지문(`(웃음)`, `(박수)`)은 번역본에서 제거.

### 3.2 신학 강연 특화 처리
- **언어유희(Wordplay)**: 독어 언어유희나 문화적 농담은 주석 `[역주: ...]` 없이 문맥 설명을 한국어로 풀어 번역.
- **고유명사**: 인명, 지명, 서명은 처음 등장 시 원어를 반드시 병기 `[한국어 표기 (원어)]`.
- **구어 특성 보존**: 강연 특유의 구어체 흐름(`또`, `이제`, `결국`)은 가독성을 해치지 않는 선에서 적절히 처리.

---

## 검수 1: 완결성 감사 — MANDATORY (Full Translation Audit)

> **이 검수는 번역 완료 직후 무조건 실행한다. 생략 불가.**

```bash
# ¶ ID 개수 대조 (반드시 수치가 일치해야 함)
grep -o "\[¶[0-9]*\]" [교정본].md | wc -l
grep -o "\[¶[0-9]*\]" [번역본].md | wc -l
```

| 검사 항목 | 통과 기준 | 실패 시 처리 |
|:---|:---|:---|
| **¶ Parity** | 교정본 ¶ 수 == 번역본 ¶ 수 (100% 일치) | ❌ 누락된 ¶ ID 목록 제시 → 해당 구간 재번역 |
| **순서 연속성** | ¶1부터 ¶N까지 순서 누락 없음 | ❌ 건너뛴 ¶ ID 목록 제시 → 보완 |

**보고 형식**:
```
[완결성 감사 결과]
- 교정본 단락 수: 118개
- 번역본 단락 수: 118개
- 누락: 0건
- 판정: ✅ PASS
```

---

## 검수 2-A: Red-Team Pass — MANDATORY (원문 대조 검증)

> **이 검수는 검수 1 PASS 이후 무조건 실행한다. 생략 불가.**
> "이 번역을 틀렸다고 주장하라." 원문을 반드시 참조하여 적대적으로 검증한다.

### Full Translation Audit (전문 완결성 검사) — 핵심 항목
> LLM의 축약·축소 본능을 구조적으로 차단하는 1순위 검사.

- [ ] **원문 1:1 전수 대조**: 교정본의 모든 문장이 번역본에 존재하는가?
  - 긴 목록형 문장, 반복 강조, 예시 열거 구간 → LLM 압축 1순위 대상, 집중 점검
  - **판단 기준**: 원문 1문장 = 번역 1문장. 합산·압축·생략 모두 ❌ FAIL
- [ ] **Anti-Summary Tripwire**: `요약하면`, `핵심은`, `(중략)`, `등등` 표현이 없는가?
- [ ] **팩트 정확성**: 인물 직함, 서명, 지명, 연도가 원어 교정본과 일치하는가?
- [ ] **용어 일관성**: 동일 원어 용어가 번역 전체에서 동일한 한국어로 번역되는가?
- [ ] **Token Ratio**: 번역문 문자 수 ≥ 교정본 문자 수의 70%인가?

**보고 형식**:
```
[검수 2-A — Red-Team 결과]
- Full Translation: ✅ PASS / ❌ [누락 문장 목록]
- Anti-Summary Tripwire: 0건 탐지
- 팩트 오류: 0건
- 용어 불일치: 0건
- Token Ratio: 78% (기준 70% PASS)
- 판정: ✅ PASS / ❌ FAIL → 해당 구간 재번역, 검수 2-B 진입 불가
```

---

## 검수 2-B: Receiver Pass — MANDATORY (번역문 독립 읽기)

> **이 검수는 검수 2-A PASS 이후 무조건 실행한다. 생략 불가.**
> "원문을 보지 말라." 번역문만 읽는 한국어 독자의 시각으로 검증한다.

### 체크리스트
- [ ] **오해 유발 탐지**: 번역문만 읽으면 독자가 잘못 이해할 문장이 있는가?
  - 지시 대상 불명확 대명사, 전제 없이 등장하는 고유명사
- [ ] **어조 적합성**: 전체 번역문이 강연의 구어적 흐름을 살리면서도 학술적 격조를 유지하는가?
- [ ] **가독성 함정**: 문법상 맞지만 한국어 독자에게 의미가 불투명한 구간은 없는가?

**보고 형식**:
```
[검수 2-B — Receiver 결과]
- 오해 유발 문장: N건 → [목록]
- 어조 적합성: ✅ 적합 / ⚠️ [문제 구간]
- 가독성 문제: N건
- 판정: ✅ PASS / ⚠️ 수정 권고 → 후반 작업 전 REFINE 처리
```

---

## 후반 작업: 문서 최종화 (Post-Processing)

두 검수 모두 PASS 이후 아래 항목을 순서대로 추가한다.

### 산출물 구조 (Output Structure)
```markdown
---
[YAML Frontmatter: lemma, category, tags, lecturer, url, language, fidelity_level]
---

# [제목]

## 📝 강연 요약 (Summary)
[핵심 논지 4~5포인트, 200~300자]

---

[¶1] ... 번역 전문 ...
[¶N]

---

## 📚 주요 용어 및 인물 사전 (Glossary)
### 인물 (People)
### 개념 및 명칭 (Concepts)
```

### YAML Frontmatter 필수 필드
| 필드 | 설명 |
|:---|:---|
| `lemma` | 강연 제목 (한국어 + 원어) |
| `category` | `[Theology, Apologetics]` 등 |
| `tags` | 핵심 개념 태그 |
| `lecturer` | 강연자 명(한국어 + 원어) |
| `url` | YouTube URL |
| `language` | `Korean (Original: German)` 등 |
| `fidelity_level` | `High (¶ Binding)` |

---

## 후반 작업 세부 지침 (Post-Processing Guide)

### A. 강연 요약 (Summary) 작성법
- **분량**: 200~300자(한국어 기준). 총 4~5개 논지 포인트.
- **내용**: 강연자 배경 → 중심 주제 → 핵심 논지 전개 → 결론 순으로 기술.
- **금지**: 번역자의 해석이나 평가 추가 금지. 강연자의 목소리(기조)를 그대로 압축.

### B. 용어 및 인물 사전 (Glossary) 작성법
Glossary는 반드시 **2-tier 구조**로 작성한다.

**Tier 1: 인물 (People)**
- 강연 본문에서 실명으로 언급된 인물만 수록.
- 형식: `**한국어명 (원어명, 생몰년)**: 직함/역할. 강연 문맥상 핵심 기여.`
- 우선순위: 본문에서 2회 이상 언급된 인물부터 수록.

**Tier 2: 개념 및 명칭 (Concepts)**
- 비전문가에게 낯선 신학·철학 용어, 기관명, 문헌명 수록.
- 형식: `**한국어명 (원어명)**: 간결한 정의 (1~2문장).`
- 기준: 본문에서 1회 이상 등장하며 독자의 이해에 결정적인 용어.

```markdown
### 인물 (People)
- **빅토르 프랑클 (Viktor Frankl, 1905-1997)**: 빈의 신경정신과 의사·아우슈비츠 생존자. '로고테라피(의미치료)'의 창시자.

### 개념 및 명칭 (Concepts)
- **로고테라피 (Logotherapie)**: '의미를 통한 치료'. 삶의 의미 발견을 핵심 치료 동력으로 삼는 심리치료 체계.
```

### C. 최종 파일명 및 안치 (Final Naming & Archiving)

**파일명 규칙**: `[원어 제목]_[강연자 성].md`
```
예) Das Leid und die Gottesfrage_Spiess.md
    Auferstehung als Tatsache_Spiess.md
```

**최종 안치 경로**: `MS_Brain.nosync / 000 System / Inbox / Raw /`
```bash
mv "[최종파일명].md" "/Users/msn/Desktop/MS_Brain.nosync/000 System/Inbox/Raw/"
```
> 이후 `wiki` 스킬 파이프라인을 통해 `I-Library/100 Theology` 서고로 정식 승격.

---

## 파일 작업 완료 후 정리 (Cleanup)

```bash
rm [작업경로]/vtt_cleaner.py        # 1회용 정제 스크립트
rm [작업경로]/*_clean.de.txt        # 중간 정제 텍스트
rm [작업경로]/*_KR.md               # 번역 초안 (Final에 통합됨)
```

> ⚠️ 원본 VTT, 교정본(_Refined.de.md)은 **절대 삭제 금지**. 영구 보존 자료다.

---

*yt_lecture_protocol.md v2.2 — Dual-Pass Audit (Full Translation Guard) | ARC SOP | MS_Dev | 2026-04-19*
