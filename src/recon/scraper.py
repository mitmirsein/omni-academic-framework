import asyncio
import httpx
from rich.console import Console

console = Console()

class BaseScraper:
    """Full-Text 원문 징발을 위한 추상 클래스"""
    async def fetch_markdown(self, url: str) -> str:
        raise NotImplementedError("Subclasses must implement fetch_markdown()")

class JinaReaderScraper(BaseScraper):
    """
    Jina Reader API (https://r.jina.ai/) 기반 고순도 마크다운 파서.
    단순 HTML이나 블로그 원문을 즉시 마크다운으로 변환합니다.
    """
    async def fetch_markdown(self, url: str) -> str:
        console.print(f"[bold cyan]🔍 Jina Reader API 가동 중... URL: {url}[/bold cyan]")
        jina_url = f"https://r.jina.ai/{url}"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(jina_url)
                response.raise_for_status()
                # Jina API는 URL의 텍스트 내용을 마크다운 형태로 반환함
                return response.text
        except Exception as e:
            console.print(f"[bold red]Jina Reader 스크래핑 실패: {e}[/bold red]")
            return ""

class LightpandaScraper(BaseScraper):
    """
    Lightpanda (Headless Browser) 기반 정밀 스크래퍼.
    JS 렌더링이 필수적이거나 복잡한 인증/우회가 필요한 URL 원문을 긁어옵니다.
    """
    async def fetch_markdown(self, url: str) -> str:
        console.print(f"[bold yellow]🐼 Lightpanda Browser 정찰 가동 중... URL: {url}[/bold yellow]")
        
        # TODO: 실제 lightpanda-recon 스킬이나 Playwright CDP 연동 로직
        # 현재는 아키텍처 뼈대(Blueprint)로서의 더미 마크다운을 반환
        await asyncio.sleep(1.0)
        return f"# Extracted Document from {url}\n\nThis is a mock markdown extracted via Headless Browser (Lightpanda)."

class ScraperFactory:
    """URL의 특성에 따라 적절한 Scraper를 반환하는 팩토리"""
    @staticmethod
    def get_scraper(url: str, force_headless: bool = False) -> BaseScraper:
        # TODO: 휴리스틱하게 URL 도메인을 분석하여 JS 렌더링이 필요한 사이트(예: 특정 저널 플랫폼)는
        # LightpandaScraper를, 일반 페이지는 JinaReaderScraper를 반환하는 로직 고도화 가능
        if force_headless or "sciencedirect" in url or "kci.go.kr" in url:
            return LightpandaScraper()
        return JinaReaderScraper()
