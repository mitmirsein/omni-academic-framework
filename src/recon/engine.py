import asyncio
import httpx
import xml.etree.ElementTree as ET
from typing import List, Optional
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel

console = Console()

class PaperMetadata(BaseModel):
    title: str
    authors: List[str]
    abstract: Optional[str] = "No abstract available"
    doi: Optional[str] = None
    url: Optional[str] = None
    citation_count: int = 0
    venue: Optional[str] = None
    is_noise: bool = False

class BaseAPIClient:
    """비동기 정찰 API 어댑터 인터페이스"""
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        raise NotImplementedError

class ArxivClient(BaseAPIClient):
    """실시간 arXiv API 스크래핑 플러그인 (비동기)"""
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        url = f"http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={max_results}"
        papers = []
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                # XML 파싱
                root = ET.fromstring(response.text)
                ns = {'arxiv': 'http://www.w3.org/2005/Atom'}
                
                for entry in root.findall('arxiv:entry', ns):
                    title = entry.find('arxiv:title', ns).text.replace('\\n', ' ').strip()
                    abstract = entry.find('arxiv:summary', ns).text.replace('\\n', ' ').strip()
                    url_link = entry.find('arxiv:id', ns).text
                    authors = [author.find('arxiv:name', ns).text for author in entry.findall('arxiv:author', ns)]
                    
                    papers.append(PaperMetadata(
                        title=f"[arXiv] {title}",
                        authors=authors,
                        abstract=abstract[:200] + "..." if len(abstract) > 200 else abstract,
                        url=url_link
                    ))
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]arXiv API 에러 (상태 코드 {e.response.status_code}): {e}[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]arXiv 네트워크 요청 실패: {e}[/bold red]")
        except Exception as e:
            console.print(f"[bold red]arXiv 데이터 파싱 중 예기치 않은 오류: {e}[/bold red]")
            
        return papers

class KCIClient(BaseAPIClient):
    """실시간 한국학술지인용색인(KCI) 오픈 API 플러그인 (비동기)"""
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        # KCI Open API 연동 구조체 (API Key 불필요한 기본 검색 또는 뼈대)
        url = f"https://open.kci.go.kr/po/openapi/openApiSearch.kci?apiCode=articleSearch&title={query}&displayCount={max_results}"
        papers = []
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                # XML 파싱 (KCI 규격 기준)
                root = ET.fromstring(response.content)
                
                # records 태그 하위의 record들을 검색
                for record in root.findall('.//record'):
                    title_elem = record.find('.//articleInfo/title-group/article-title')
                    title = title_elem.text if title_elem is not None else "제목 없음"
                    
                    abstract_elem = record.find('.//articleInfo/abstract-group/abstract')
                    abstract = abstract_elem.text if abstract_elem is not None else "초록 없음"
                    
                    url_elem = record.find('.//articleInfo/url')
                    url_link = url_elem.text if url_elem is not None else ""
                    
                    authors = [author.text for author in record.findall('.//author-group/author')]
                    
                    papers.append(PaperMetadata(
                        title=f"[KCI] {title}",
                        authors=authors if authors else ["저자 미상"],
                        abstract=abstract[:200] + "..." if len(abstract) > 200 else abstract,
                        url=url_link
                    ))
        except Exception as e:
            console.print(f"[bold red]KCI 데이터 파싱 중 예기치 않은 오류: {e}[/bold red]")
            
        return papers

class CrossrefClient(BaseAPIClient):
    """Crossref API 플러그인 (예시용, 비동기)"""
    async def search(self, query: str, max_results: int = 2) -> List[PaperMetadata]:
        await asyncio.sleep(0.5)
        return [
            PaperMetadata(
                title=f"[Crossref] Found paper for: {query}",
                authors=["Author A"],
                abstract="Dummy abstract to test parallel async fetching.",
                doi="10.1234/crossref.dummy"
            )
        ]

class ReconEngine:
    def __init__(self):
        self.console = console
        self.api_registry = {
            "general": [KCIClient(), CrossrefClient()],
            "cs": [ArxivClient(), CrossrefClient()],
            "theology": [KCIClient(), CrossrefClient()],  # 신학 렌즈에서도 KCI 강력 추천
            "humanities": [KCIClient(), CrossrefClient()],
        }

    async def search(self, query: str, lens: str = "general") -> List[PaperMetadata]:
        self.console.print(f"[bold cyan]🔍 비동기 Recon Engine 가동 중... (Lens: {lens})[/bold cyan]")
        
        clients = self.api_registry.get(lens, self.api_registry["general"])
        
        self.console.print("  - [italic]API 플러그인 병렬 스크래핑(Gathering) 시작...[/italic]")
        
        # asyncio를 통한 멀티 API 동시 호출 (성능 최적화)
        tasks = [client.search(query) for client in clients]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)
        
        results: List[PaperMetadata] = []
        for res in results_nested:
            if isinstance(res, Exception):
                self.console.print(f"  [red]⚠️ API 호출 중 예외 발생: {res}[/red]")
            else:
                results.extend(res)
            
        return self._smart_noise_filter(results)
    
    def _smart_noise_filter(self, papers: List[PaperMetadata]) -> List[PaperMetadata]:
        clean_papers = []
        noise_keywords = ["frontmatter", "editorial", "table of contents", "index"]
        
        for p in papers:
            if any(keyword in p.title.lower() for keyword in noise_keywords):
                p.is_noise = True
                self.console.print(f"  [red]x Filtered noise:[/red] {p.title}")
            else:
                clean_papers.append(p)
                
        return clean_papers

    def generate_digest(self, papers: List[PaperMetadata]):
        self.console.print("\n[bold yellow]📑 Recon Digest Report[/bold yellow]")
        for idx, p in enumerate(papers, 1):
            source = f"DOI: {p.doi}" if p.doi else f"URL: {p.url}"
            content = f"**Authors**: {', '.join(p.authors)}\n**Citations**: {p.citation_count}\n**Source**: {source}\n\n**Abstract**: {p.abstract}"
            self.console.print(Panel(content, title=f"[{idx}] {p.title}", border_style="green"))
        
        self.console.print("\n[bold blue]수퍼바이저 대기 중...[/bold blue] 딥다이브할 논문 번호를 승인(Approve)해 주십시오.")
