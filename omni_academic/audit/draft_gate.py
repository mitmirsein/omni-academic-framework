"""Draft Compliance Gate — 생성된 초안의 무손실/근거 결정론적 감사.

LLM이 만든 초안을 신뢰 전에 기계적으로 검증한다(헌법 §3): 모든 주장이
실존 문단·verbatim 인용에 묶여 있는지, 본문 앵커가 선언된 claim/문단을
가리키는지, 미해소 긴장이 보존됐는지. lens_gate.LensComplianceAuditor와
동일한 패턴이며 LLM self-critique가 아니라 기계적 invariant를 강제한다.
"""

import re
from datetime import datetime, timezone
from typing import Dict, List

from omni_academic.audit.gate import AuditFinding, AuditReport
from omni_academic.draft.scribe import DraftReport
from omni_academic.ontology.extractor import OntologyMap
from omni_academic.text.grounding import canon_quote, is_normalized_match, quote_in
from omni_academic.text.paragraphs import assign_paragraph_ids

_CLAIM_REF_RE = re.compile(r"\[(C\d+)\]")
_PARA_REF_RE = re.compile(r"\[(P_\d+)\]")


def _quote_len(text: str) -> int:
    return len("".join((text or "").split()))


class DraftComplianceAuditor:
    def verify(
        self,
        report: DraftReport,
        target_document: str,
        ontology: OntologyMap,
    ) -> AuditReport:
        findings: List[AuditFinding] = []
        _, paragraph_map = assign_paragraph_ids(target_document)
        node_ids = {n.id for n in ontology.nodes}

        if not report.thesis.strip():
            findings.append(AuditFinding(
                severity="warning", code="EMPTY_THESIS",
                message="초안 thesis가 비어 있음",
            ))
        if not report.sections:
            findings.append(AuditFinding(
                severity="error", code="NO_DRAFT_SECTIONS",
                message="초안에 섹션이 하나도 없음",
            ))
        if not report.claims:
            findings.append(AuditFinding(
                severity="error", code="NO_DRAFT_CLAIMS",
                message="초안에 claim이 하나도 없음(근거 원장 부재)",
            ))

        # --- claims ledger 검증 ---
        seen_ids: set[str] = set()
        quote_refs: Dict[str, List[str]] = {}
        claim_ids: set[str] = set()
        for claim in report.claims:
            ref = f"claim[{claim.claim_id}]"
            if claim.claim_id in seen_ids:
                findings.append(AuditFinding(
                    severity="error", code="DUPLICATE_CLAIM_ID",
                    message=f"claim_id 중복: {claim.claim_id}", source_ref=ref,
                ))
            seen_ids.add(claim.claim_id)
            claim_ids.add(claim.claim_id)

            if claim.paragraph_id not in paragraph_map:
                findings.append(AuditFinding(
                    severity="error", code="UNGROUNDED_DRAFT_CLAIM",
                    message=f"존재하지 않는 paragraph_id 참조: {claim.paragraph_id}",
                    source_ref=ref,
                ))
                continue

            quote = claim.source_quote
            para_text = paragraph_map[claim.paragraph_id]
            if not quote.strip():
                findings.append(AuditFinding(
                    severity="error", code="MISSING_DRAFT_QUOTE",
                    message="claim source_quote 누락", source_ref=ref,
                ))
            elif not quote_in(quote, para_text):
                findings.append(AuditFinding(
                    severity="error", code="UNGROUNDED_DRAFT_QUOTE",
                    message=f"source_quote가 해당 문단에 없음(환각): {claim.paragraph_id}",
                    source_ref=ref,
                ))
            elif _quote_len(quote) < 8:
                findings.append(AuditFinding(
                    severity="warning", code="WEAK_DRAFT_QUOTE",
                    message=f"source_quote가 너무 짧아 검증력이 약함: {claim.claim_id}",
                    source_ref=ref,
                ))
            else:
                if is_normalized_match(quote, para_text):
                    findings.append(AuditFinding(
                        severity="info", code="QUOTE_NORMALIZED_MATCH",
                        message=(
                            f"source_quote가 정규화(공백/유니코드) 후에만 일치함: "
                            f"{claim.claim_id}"
                        ),
                        source_ref=ref,
                    ))
                quote_refs.setdefault(canon_quote(quote), []).append(claim.claim_id)

            if claim.node_id is not None and claim.node_id not in node_ids:
                findings.append(AuditFinding(
                    severity="error", code="UNGROUNDED_DRAFT_NODE",
                    message=f"존재하지 않는 온톨로지 node_id 참조: {claim.node_id}",
                    source_ref=ref,
                ))

        for ids in quote_refs.values():
            if len(ids) > 1:
                findings.append(AuditFinding(
                    severity="warning", code="DUPLICATE_DRAFT_QUOTE",
                    message="여러 claim이 동일한 source_quote를 재사용함: " + ", ".join(ids),
                    source_ref=f"claim[{ids[0]}]",
                ))

        # --- 본문 앵커 정합성 ---
        referenced: set[str] = set()
        for idx, section in enumerate(report.sections, 1):
            ref = f"section[{idx}:{section.section_type}]"
            for anchor in _CLAIM_REF_RE.findall(section.body):
                referenced.add(anchor)
                if anchor not in claim_ids:
                    findings.append(AuditFinding(
                        severity="error", code="UNDECLARED_CLAIM_ANCHOR",
                        message=f"본문이 선언되지 않은 claim 앵커를 참조: [{anchor}]",
                        source_ref=ref,
                    ))
            for panchor in _PARA_REF_RE.findall(section.body):
                if panchor not in paragraph_map:
                    findings.append(AuditFinding(
                        severity="error", code="UNGROUNDED_PARAGRAPH_ANCHOR",
                        message=f"본문이 존재하지 않는 문단 앵커를 참조: [{panchor}]",
                        source_ref=ref,
                    ))
            for cid in section.claim_ids:
                if cid not in claim_ids:
                    findings.append(AuditFinding(
                        severity="warning", code="UNKNOWN_SECTION_CLAIM_ID",
                        message=f"section.claim_ids에 미선언 claim_id: {cid}",
                        source_ref=ref,
                    ))
            if not section.body.strip():
                findings.append(AuditFinding(
                    severity="warning", code="EMPTY_SECTION_BODY",
                    message=f"섹션 본문이 비어 있음: {section.heading}",
                    source_ref=ref,
                ))

        for claim_id in claim_ids:
            if claim_id not in referenced:
                findings.append(AuditFinding(
                    severity="warning", code="UNUSED_CLAIM",
                    message=f"선언됐으나 본문에서 참조되지 않은 claim: {claim_id}",
                ))

        if not report.open_tensions:
            findings.append(AuditFinding(
                severity="warning", code="MISSING_OPEN_TENSIONS",
                message="open_tensions가 비어 있음(미해소 긴장 평탄화 의심)",
            ))

        return self._report(findings)

    @staticmethod
    def _report(findings: List[AuditFinding]) -> AuditReport:
        penalty = sum(
            25 if f.severity == "error" else 10 if f.severity == "warning" else 0
            for f in findings
        )
        return AuditReport(
            passed=not any(f.severity == "error" for f in findings),
            score=max(0, 100 - penalty),
            findings=findings,
            checked_at=datetime.now(timezone.utc),
        )
