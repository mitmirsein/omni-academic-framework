import asyncio
import re
from typing import List, Optional

import httpx
from rich.console import Console

from omni_academic.audit.gate import AuditFinding

console = Console()

# Crossref DOI 권장 패턴: 10.<registrant>/<suffix>
_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$", re.IGNORECASE)


def is_valid_doi_syntax(doi: Optional[str]) -> bool:
    return bool(doi) and bool(_DOI_RE.match(doi.strip()))


#: 봇 HEAD 요청을 차단하는 출판사들이 200을 주도록 표준 UA를 보낸다.
USER_AGENT = "omni-academic-framework/forensic (citation existence check)"

#: '실존 부정'의 증거가 아니라 접근 통제/일시 장애 신호인 status들.
#: 이 응답을 GHOST_DOI(error)로 차단하면 실존 인용을 유령으로 오판한다.
INDETERMINATE_STATUSES = frozenset({401, 403, 429, 500, 502, 503})

# 판정 분류 값
VERDICT_OK = "ok"
VERDICT_MISSING = "missing"
VERDICT_INDETERMINATE = "indeterminate"


class ForensicAuditor:
    """Gate 2 — 실증 감사.

    DOI 문법 → DOI/URL 실존(HEAD)을 기계적으로 대조하여 '유령 인용'을
    차단한다. 네트워크 호출이므로 recon 디폴트 경로가 아니라 명시 호출용.

    판정 매트릭스: 2xx/3xx → 실존(ok), 404/410 → 부재(missing, error),
    403/429/5xx/네트워크 오류 → 검증 불확정(indeterminate, warning).
    불확정을 error로 승격하면 봇 차단된 실존 인용이 유령으로 오판된다.
    """

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    @staticmethod
    def passed(findings: List[AuditFinding]) -> bool:
        return not any(f.severity == "error" for f in findings)

    @staticmethod
    def failed_indices(findings: List[AuditFinding]) -> set:
        """error finding의 source_ref `paper[<idx>]`에서 차단 대상 인덱스 추출."""
        import re

        out = set()
        for f in findings:
            if f.severity != "error" or not f.source_ref:
                continue
            m = re.match(r"paper\[(\d+)\]", f.source_ref)
            if m:
                out.add(int(m.group(1)))
        return out

    @staticmethod
    def classify_status(status: Optional[int]) -> str:
        """HTTP status(네트워크 오류는 None)를 실존 판정으로 분류한다."""
        if status is None or status in INDETERMINATE_STATUSES:
            return VERDICT_INDETERMINATE
        if status < 400:
            return VERDICT_OK
        if status in (404, 410):
            return VERDICT_MISSING
        # 그 외 4xx(400, 405 GET 폴백 후 등)는 부재 증거로 보기 약함.
        return VERDICT_INDETERMINATE

    async def _probe_status(self, client: httpx.AsyncClient, url: str) -> Optional[int]:
        """HEAD(405면 GET 폴백) status code. 네트워크 오류는 None."""
        try:
            resp = await client.head(url, follow_redirects=True)
            if resp.status_code == 405:  # HEAD 미허용 → GET 폴백
                resp = await client.get(url, follow_redirects=True)
            return resp.status_code
        except httpx.RequestError:
            return None

    async def _verdict(self, client: httpx.AsyncClient, url: str) -> str:
        return self.classify_status(await self._probe_status(client, url))

    async def verify_papers(self, papers: list) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        async with httpx.AsyncClient(
            timeout=self.timeout, headers={"User-Agent": USER_AGENT},
        ) as client:
            tasks = []
            for idx, p in enumerate(papers):
                tasks.append(self._verify_one(client, idx, p, findings))
            await asyncio.gather(*tasks)
        return findings

    async def _verify_one(self, client, idx, paper, findings):
        doi = getattr(paper, "doi", None)
        url = getattr(paper, "url", None)
        ref = f"paper[{idx}] {getattr(paper, 'title', '')[:60]}"

        if doi:
            if not is_valid_doi_syntax(doi):
                findings.append(AuditFinding(
                    severity="error", code="MALFORMED_DOI",
                    message=f"DOI 문법 위반: {doi}", source_ref=ref,
                ))
            else:
                verdict = await self._verdict(client, f"https://doi.org/{doi}")
                if verdict == VERDICT_MISSING:
                    findings.append(AuditFinding(
                        severity="error", code="GHOST_DOI",
                        message=f"DOI가 resolve되지 않음(유령 인용): {doi}", source_ref=ref,
                    ))
                elif verdict == VERDICT_INDETERMINATE:
                    findings.append(AuditFinding(
                        severity="warning", code="UNVERIFIABLE_DOI",
                        message=(
                            f"DOI 실존을 확정할 수 없음(접근 차단/일시 장애 가능): {doi}"
                        ),
                        source_ref=ref,
                    ))
        if url:
            verdict = await self._verdict(client, url)
            if verdict == VERDICT_MISSING:
                findings.append(AuditFinding(
                    severity="warning", code="DEAD_URL",
                    message=f"URL 응답 없음: {url}", source_ref=ref,
                ))
            elif verdict == VERDICT_INDETERMINATE:
                findings.append(AuditFinding(
                    severity="warning", code="UNVERIFIABLE_URL",
                    message=f"URL 실존을 확정할 수 없음(접근 차단/일시 장애 가능): {url}",
                    source_ref=ref,
                ))
        if not doi and not url:
            findings.append(AuditFinding(
                severity="warning", code="NO_LOCATOR",
                message="DOI/URL이 모두 없어 실존 검증 불가", source_ref=ref,
            ))
