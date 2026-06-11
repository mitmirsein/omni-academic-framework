import urllib.parse
from typing import List

import httpx

from omni_academic.recon.clients.base import (
    BaseAPIClient,
    PaperMetadata,
    _norm,
    console,
)


class CrossrefClient(BaseAPIClient):
    """Crossref REST API 플러그인 (api.crossref.org, 키 불필요, 비동기)."""
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        params = urllib.parse.urlencode({"query": query, "rows": max_results})
        url = f"https://api.crossref.org/works?{params}"
        papers = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url, headers={"User-Agent": "omni-academic-framework/0.1 (mailto:noreply@example.com)"}
                )
                response.raise_for_status()
                items = response.json().get("message", {}).get("items", [])

                for it in items:
                    title_list = it.get("title") or []
                    title = _norm(title_list[0]) if title_list else ""
                    if not title:
                        continue
                    authors = [
                        _norm(f"{a.get('given', '')} {a.get('family', '')}")
                        for a in it.get("author", [])
                    ]
                    doi = it.get("DOI")
                    papers.append(PaperMetadata(
                        title=f"[Crossref] {title}",
                        authors=[a for a in authors if a] or ["저자 미상"],
                        abstract=_norm(it.get("abstract"))[:200] or "초록 없음",
                        doi=doi,
                        url=it.get("URL") or (f"https://doi.org/{doi}" if doi else None),
                        citation_count=it.get("is-referenced-by-count", 0),
                        venue=(it.get("container-title") or [None])[0],
                    ))
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]Crossref API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]Crossref 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]Crossref 응답 파싱 실패: {e}[/bold red]")

        return papers
