from typing import List

import httpx

from omni_academic.recon.clients.base import (
    BaseAPIClient,
    PaperMetadata,
    _norm,
    console,
)

_NCBI_COMMON = {"db": "pubmed", "tool": "omni-academic-framework",
                "email": "noreply@example.com"}


class PubMedClient(BaseAPIClient):
    """PubMed/NCBI E-utilities 플러그인 (키 불필요, httpx-native, 2-step).

    esearch(JSON)로 PMID 목록 → esummary(JSON)로 메타데이터. 검증된 한계:
    esummary에는 abstract가 없다(본문은 Phase B). 추측 파싱을 피하려고
    실제 응답 스키마(esearchresult.idlist / result[<uid>])에만 의존한다.
    """

    ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    @staticmethod
    def _parse(payload: dict) -> List[PaperMetadata]:
        result = payload.get("result", {}) or {}
        papers: List[PaperMetadata] = []
        for uid in result.get("uids", []) or []:
            rec = result.get(uid, {}) or {}
            title = _norm(rec.get("title"))
            if not title:
                continue
            doi = next(
                (a.get("value") for a in rec.get("articleids", [])
                 if a.get("idtype") == "doi"),
                None,
            )
            papers.append(PaperMetadata(
                title=f"[PubMed] {title}",
                authors=[_norm(a.get("name")) for a in rec.get("authors", [])
                         if a.get("name")] or ["저자 미상"],
                abstract="초록 없음 (PubMed esummary 미제공 — 본문은 Phase B)",
                doi=doi,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                venue=_norm(rec.get("source")) or None,
            ))
        return papers

    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                es = await client.get(self.ESEARCH, params={
                    **_NCBI_COMMON, "term": query,
                    "retmax": max_results, "retmode": "json",
                })
                es.raise_for_status()
                ids = es.json().get("esearchresult", {}).get("idlist", []) or []
                if not ids:
                    return []
                summ = await client.get(self.ESUMMARY, params={
                    **_NCBI_COMMON, "id": ",".join(ids), "retmode": "json",
                })
                summ.raise_for_status()
                return self._parse(summ.json())
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]PubMed API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]PubMed 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]PubMed 응답 파싱 실패: {e}[/bold red]")
        return []
