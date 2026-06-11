import asyncio
from typing import List

from omni_academic.recon.clients.base import (
    BaseAPIClient,
    PaperMetadata,
    _norm,
    console,
)


class ArxivClient(BaseAPIClient):
    """arXiv 어댑터. 손수 짠 Atom XML 파싱 대신 검증된 `arxiv` 라이브러리에
    페이지네이션·재시도·정렬을 위임한다. 라이브러리는 동기(+자체 rate-limit)
    이므로 `asyncio.to_thread`로 오프로드해 async 엔진을 블로킹하지 않는다.
    """

    @staticmethod
    def _fetch(query: str, max_results: int) -> List[PaperMetadata]:
        import arxiv

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        papers: List[PaperMetadata] = []
        for r in client.results(search):
            title = _norm(r.title)
            if not title:
                continue
            abstract = _norm(r.summary)
            papers.append(PaperMetadata(
                title=f"[arXiv] {title}",
                authors=[_norm(a.name) for a in r.authors] or ["저자 미상"],
                abstract=abstract[:200] + "..." if len(abstract) > 200 else (abstract or "초록 없음"),
                doi=r.doi,
                url=r.entry_id,
                venue=r.journal_ref or None,
            ))
        return papers

    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        try:
            return await asyncio.to_thread(self._fetch, query, max_results)
        except ModuleNotFoundError:
            console.print(
                "[bold red]arXiv: 'arxiv' 패키지가 필요합니다 (uv sync).[/bold red]"
            )
        except Exception as e:  # arxiv.ArxivError 등 라이브러리 예외 포함
            console.print(f"[bold red]arXiv 검색 실패: {e}[/bold red]")
        return []
