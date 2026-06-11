"""Quote grounding 대조의 단일 정책 모듈.

모든 게이트(AuditGate, LensComplianceAuditor, DraftComplianceAuditor,
ScribeAgent grounding, PeerReviewPanel grounding)는 "인용이 원문에
verbatim으로 존재하는가"를 반드시 이 모듈의 함수로만 판정한다.
게이트마다 자체 정규화를 두면 같은 산출물이 한 게이트는 통과하고
다른 게이트는 반려되는 비대칭이 생긴다(QUALITY_IMPROVEMENT_PLAN.md F2).

정책:
- NFKC 정규화 — NBSP(U+00A0)·전각 문자·리거처를 표준형으로 접는다.
  (PDF/웹 추출 원문에서 흔한 비파괴적 변형)
- curly quote → straight quote, soft hyphen 제거.
- 공백 단일화(개행·탭 포함).
- 대소문자는 보존한다 — 소문자화는 검증력을 깎는 과잉 관대함.
"""

import unicodedata

_REPLACEMENTS = (
    ("“", '"'),  # “
    ("”", '"'),  # ”
    ("‘", "'"),  # ‘
    ("’", "'"),  # ’
    ("\u00ad", ""),   # soft hyphen
)


def canon_quote(text: str) -> str:
    """grounding 대조용 표준 정규화. 모든 게이트가 이 함수만 사용한다."""
    t = unicodedata.normalize("NFKC", text or "")
    for src, dst in _REPLACEMENTS:
        t = t.replace(src, dst)
    return " ".join(t.split())


def quote_in(quote: str, corpus: str) -> bool:
    """quote가 corpus에 (정규화 기준) 부분문자열로 존재하는지 판정한다.

    빈 quote는 항상 False — '빈 인용은 어디에나 있다'는 공허한 통과를 막는다.
    """
    q = canon_quote(quote)
    return bool(q) and q in canon_quote(corpus)


def is_normalized_match(quote: str, corpus: str) -> bool:
    """raw로는 불일치하지만 정규화로 구제된 매칭인지 판정한다.

    게이트는 이 경우 info finding(QUOTE_NORMALIZED_MATCH)으로 기록해
    원문/산출물 사이의 비파괴적 변형을 추적 가능하게 남긴다.
    """
    return quote_in(quote, corpus) and (quote or "") not in (corpus or "")
