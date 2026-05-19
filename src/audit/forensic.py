import asyncio
import re
from typing import List, Optional

import httpx
from rich.console import Console

from src.audit.gate import AuditFinding

console = Console()

# Crossref DOI 권장 패턴: 10.<registrant>/<suffix>
_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$", re.IGNORECASE)


def is_valid_doi_syntax(doi: Optional[str]) -> bool:
    return bool(doi) and bool(_DOI_RE.match(doi.strip()))


class ForensicAuditor:
    """Gate 2 — 실증 감사.

    DOI 문법 → DOI/URL 실존(HEAD)을 기계적으로 대조하여 '유령 인용'을
    차단한다. 네트워크 호출이므로 recon 디폴트 경로가 아니라 명시 호출용.
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

    async def _resolves(self, client: httpx.AsyncClient, url: str) -> bool:
        try:
            resp = await client.head(url, follow_redirects=True)
            if resp.status_code == 405:  # HEAD 미허용 → GET 폴백
                resp = await client.get(url, follow_redirects=True)
            return resp.status_code < 400
        except httpx.RequestError:
            return False

    async def verify_papers(self, papers: list) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
            elif not await self._resolves(client, f"https://doi.org/{doi}"):
                findings.append(AuditFinding(
                    severity="error", code="GHOST_DOI",
                    message=f"DOI가 resolve되지 않음(유령 인용): {doi}", source_ref=ref,
                ))
        if url and not await self._resolves(client, url):
            findings.append(AuditFinding(
                severity="warning", code="DEAD_URL",
                message=f"URL 응답 없음: {url}", source_ref=ref,
            ))
        if not doi and not url:
            findings.append(AuditFinding(
                severity="warning", code="NO_LOCATOR",
                message="DOI/URL이 모두 없어 실존 검증 불가", source_ref=ref,
            ))
