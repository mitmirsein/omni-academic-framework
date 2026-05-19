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
    """모든 정찰 API의 기본 어댑터 인터페이스"""
    def search(self, query: str, max_results: int = 5) -> List[PaperMetadata]:
        raise NotImplementedError

class CrossrefClient(BaseAPIClient):
    """범용 DOI 기반 API (Level 1)"""
    def search(self, query: str, max_results: int = 5) -> List[PaperMetadata]:
        # TODO: 실제 requests.get("https://api.crossref.org/works?query=...") 구현
        return [
            PaperMetadata(
                title=f"[Crossref] Found paper for: {query}",
                authors=["Author A", "Author B"],
                abstract="This is a dummy abstract from Crossref.",
                doi="10.1234/crossref.dummy",
                citation_count=15
            )
        ]

class ArxivClient(BaseAPIClient):
    """CS, 수학 특화 API (Pluggable)"""
    def search(self, query: str, max_results: int = 5) -> List[PaperMetadata]:
        # TODO: 실제 urllib.request("http://export.arxiv.org/api/query?search_query=...") 구현
        return [
            PaperMetadata(
                title=f"[arXiv] {query} in Deep Learning",
                authors=["Researcher X"],
                abstract="Transformer architectures have revolutionized NLP.",
                url="https://arxiv.org/abs/dummy",
                citation_count=120
            )
        ]

class ReconEngine:
    def __init__(self):
        self.console = console
        # 렌즈에 따른 플러그인 매핑
        self.api_registry = {
            "general": [CrossrefClient()],
            "cs": [CrossrefClient(), ArxivClient()]
        }

    def search(self, query: str, lens: str = "general") -> List[PaperMetadata]:
        self.console.print(f"[bold cyan]🔍 Recon Engine Starting... (Lens: {lens})[/bold cyan]")
        
        clients = self.api_registry.get(lens, self.api_registry["general"])
        results: List[PaperMetadata] = []
        
        for client in clients:
            self.console.print(f"  - Requesting data via {client.__class__.__name__}...")
            # 비동기 병렬 처리로 발전시킬 수 있는 지점
            results.extend(client.search(query))
            
        return self._smart_noise_filter(results)
    
    def _smart_noise_filter(self, papers: List[PaperMetadata]) -> List[PaperMetadata]:
        """Table of Contents, Frontmatter 등 껍데기를 걸러냅니다."""
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
        """사용자 승인(HITL)을 위한 다이제스트 브리핑"""
        self.console.print("\n[bold yellow]📑 Recon Digest Report[/bold yellow]")
        for idx, p in enumerate(papers, 1):
            source = f"DOI: {p.doi}" if p.doi else f"URL: {p.url}"
            content = f"**Authors**: {', '.join(p.authors)}\n**Citations**: {p.citation_count}\n**Source**: {source}\n\n**Abstract**: {p.abstract}"
            self.console.print(Panel(content, title=f"[{idx}] {p.title}", border_style="green"))
            
        self.console.print("\n[bold blue]수퍼바이저 대기 중...[/bold blue] 딥다이브할 논문 번호를 승인(Approve)해 주십시오.")
