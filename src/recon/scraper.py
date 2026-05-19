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
        console.print(f"[bold cyan]🐼 Lightpanda 스크래퍼 가동 중... URL: {url}[/bold cyan]")
        try:
            process = await asyncio.create_subprocess_exec(
                "/Users/msn/Desktop/MS_Dev.nosync/bin/lightpanda",
                "fetch", "--dump", "markdown", "--strip-mode", "full", "--wait-ms", "5000", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0 and stdout:
                return stdout.decode('utf-8')
            else:
                console.print(f"[bold red]Lightpanda 스크래핑 실패. 에러: {stderr.decode('utf-8')}[/bold red]")
                return ""
        except Exception as e:
            console.print(f"[bold red]Lightpanda 실행 중 오류 발생: {e}[/bold red]")
            return ""

class ScraperFactory:
    """URL의 특성에 따라 적절한 Scraper를 반환하는 팩토리"""
    @staticmethod
    def get_scraper(url: str, force_headless: bool = False) -> BaseScraper:
        # 더미/메타데이터 부재로 url이 None·빈 문자열인 경우 'in url' 연산이
        # TypeError로 폭발하므로 경계에서 명시적으로 거부한다.
        if not url or not url.strip():
            raise ValueError("ScraperFactory: 유효한 URL이 필요합니다 (None/빈 문자열 거부).")
        # Jina Reader로 접근 시 451이 뜨는 doi.org 등은 강제로 Lightpanda 엔진을 태운다
        if force_headless or any(domain in url for domain in ["sciencedirect", "kci.go.kr", "doi.org"]):
            return LightpandaScraper()
        return JinaReaderScraper()
