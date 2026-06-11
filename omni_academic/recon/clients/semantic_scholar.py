import os
from typing import List

import httpx

from omni_academic.recon.clients.base import (
    BaseAPIClient,
    PaperMetadata,
    _norm,
    console,
)


class SemanticScholarClient(BaseAPIClient):
    """Semantic Scholar 공식 Web API 어댑터 (비동기).
    SEMANTIC_SCHOLAR_API_KEY 환경변수가 설정되어 있으면 헤더에 주입하여
    더 높은 Rate Limit으로 고속 조회가 가능합니다. 없어도 3초/1회 속도 한도로 동작합니다.
    """
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key

        params = {
            "query": query,
            "limit": max_results,
            "fields": "title,authors,abstract,externalIds,url,citationCount,venue",
        }
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        papers = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                for item in data.get("data", []) or []:
                    title = _norm(item.get("title"))
                    if not title:
                        continue
                    
                    authors = [
                        _norm(a.get("name")) for a in item.get("authors", [])
                        if a.get("name")
                    ]
                    doi = (item.get("externalIds") or {}).get("DOI")
                    
                    papers.append(PaperMetadata(
                        title=f"[Semantic Scholar] {title}",
                        authors=authors or ["저자 미상"],
                        abstract=_norm(item.get("abstract"))[:200] or "초록 없음",
                        doi=doi,
                        url=item.get("url"),
                        citation_count=item.get("citationCount") or 0,
                        venue=_norm(item.get("venue")) or None,
                    ))
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]Semantic Scholar API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]Semantic Scholar 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]Semantic Scholar 응답 파싱 실패: {e}[/bold red]")

        return papers


# 클라이언트 이름 → 구현. 도메인↔클라이언트 매핑은 코드가 아니라
