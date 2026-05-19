# 📋 Theology Translation PM Quality Gate Report

**Project**: [프로젝트 명]
**Date**: {{date}}
**Source → Target**: [원문 언어] → [번역 언어]

---

## 1. Fidelity Harness Gates (충실도 속박 장치)

### 1-A. ¶ Parity Check (단락 동수 검증)
- [ ] 원문 총 ¶ 수: ___개
- [ ] 번역문 총 ¶ 수: ___개
- [ ] 누락된 ¶ ID 목록: [없음 / ¶N, ¶M, ...]
- **판정**: [PASS / FAIL]

### 1-B. Token Ratio Guard (토큰 비율 검증)
- [ ] 원문 총 문자 수: ___자
- [ ] 번역문 총 문자 수: ___자
- [ ] 비율: ___%  (하한선: 70%)
- **판정**: [PASS / RATIO_FAIL]

### 1-C. Anti-Summary Tripwire (요약 패턴 탐지)
- [ ] Category A (직접 요약 표현): ___건 탐지
- [ ] Category B (메타 해설): ___건 탐지
- [ ] Category C (정보 압축 징후): ___건 탐지
- **판정**: [CLEAN / ALERT → PM 검토 필요]

---

## 2. Source-to-Target Identity Audit (정보 보존율)
- [ ] 원문의 모든 예시(Examples)가 반영되었는가?
- [ ] 부연 설명 및 강조 어구가 누락 없이 전사되었는가?
- [ ] 각주가 전수 보존되었는가? (원문 ___개 / 번역문 ___개)
- [ ] F-Score (translator_audit.py): ___ (기준: ≥ 0.90)

## 3. Theological Integrity (신학적 엄밀성)
- [ ] 표준용어집(Glossary) 및 TRE 준수 여부 확인
- [ ] 대상 신학자의 고유한 뉘앙스를 왜곡하지 않았는가?
- [ ] 교파적/교리적 오역이 발견되지 않았는가?

## 4. Linguistic Quality (언어적 품질)
- [ ] 한국어 학술 문체(또는 요청된 톤)가 일관되게 유지되는가?
- [ ] 비문, 오탈자, 불필요한 번역투가 제거되었는가?
- [ ] 가독성과 정보 보존 사이의 균형이 적절한가?

---

## 5. Final Verdict (최종 승인)

| Gate | 결과 |
|:---|:---|
| ¶ Parity | [PASS/FAIL] |
| Token Ratio | [PASS/FAIL] |
| Tripwire | [CLEAN/ALERT] |
| F-Score | [PASS/FAIL] |

- **종합 승인 여부**: [Revisions Needed / ✅ Approved]
- **PM Comment**: [리뷰 코멘트 기재]

---
*Theology Translator v5.1 — Fidelity Harness Edition*
