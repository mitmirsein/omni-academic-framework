import asyncio
import urllib.parse

import httpx
from rich.console import Console

from src.config.tools import resolve_tool

console = Console()


def _is_pdf_path(url: str) -> bool:
    try:
        return urllib.parse.urlparse(url).path.lower().endswith(".pdf")
    except ValueError:
        return False


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
        binary = resolve_tool("OMNI_LIGHTPANDA_BIN", "lightpanda")
        if not binary:
            console.print(
                "[bold red]Lightpanda 미설정: OMNI_LIGHTPANDA_BIN 환경변수 또는 "
                "PATH에 lightpanda 필요 — 가짜 결과 대신 정직하게 실패[/bold red]"
            )
            return ""
        console.print(f"[bold cyan]🐼 Lightpanda 스크래퍼 가동 중... URL: {url}[/bold cyan]")
        try:
            process = await asyncio.create_subprocess_exec(
                binary,
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


class PdfExtractorScraper(BaseScraper):
    """PDF 전용 추출기 (도메인 중립).

    우선순위: (1) `OMNI_PDF_EXTRACTOR` 외부 툴(설정된 경우, Lightpanda와 동일한
    '외부 툴 경로' 규약 — 하드코딩 금지) → (2) 코어 pypdf 폴백. 추출 실패 시
    가짜 마크다운이 아니라 빈 문자열을 반환한다(무손실·환각 차단 일관).
    """

    @staticmethod
    def _pypdf_to_text(data: bytes) -> str:
        try:
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            parts = [(p.extract_text() or "") for p in reader.pages]
            text = "\n\n".join(t.strip() for t in parts if t.strip())
            return text
        except Exception:
            return ""

    async def _external(self, url: str) -> str:
        tool = resolve_tool("OMNI_PDF_EXTRACTOR")  # 통일 규약(임의 스크립트라 PATH 기본 없음)
        if not tool:
            return ""
        try:
            proc = await asyncio.create_subprocess_exec(
                tool, url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return stdout.decode("utf-8", errors="replace")
            console.print(
                f"[bold red]외부 PDF 추출기 실패: {stderr.decode('utf-8', 'replace')[:200]}[/bold red]"
            )
        except Exception as e:
            console.print(f"[bold red]외부 PDF 추출기 실행 오류: {e}[/bold red]")
        return ""

    async def fetch_markdown(self, url: str) -> str:
        console.print(f"[bold magenta]📄 PDF 추출기 가동 중... URL: {url}[/bold magenta]")
        external = await self._external(url)
        if external:
            return external
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.content
        except Exception as e:
            console.print(f"[bold red]PDF 다운로드 실패: {e}[/bold red]")
            return ""
        text = self._pypdf_to_text(data)
        if not text:
            console.print(
                "[bold red]PDF 텍스트 추출 실패(스캔 PDF/암호화 가능) — 정직하게 실패[/bold red]"
            )
        return text


class ScraperFactory:
    """URL의 특성에 따라 적절한 Scraper를 반환하는 팩토리"""

    @staticmethod
    def get_scraper(url: str, force_headless: bool = False) -> BaseScraper:
        # url이 None·빈 문자열이면 'in url'이 TypeError로 폭발하므로 경계에서 거부.
        if not url or not url.strip():
            raise ValueError("ScraperFactory: 유효한 URL이 필요합니다 (None/빈 문자열 거부).")
        if _is_pdf_path(url):
            return PdfExtractorScraper()
        # Jina Reader로 접근 시 451이 뜨는 doi.org 등은 강제로 Lightpanda 엔진을 태운다
        if force_headless or any(d in url for d in ["sciencedirect", "kci.go.kr", "doi.org"]):
            return LightpandaScraper()
        return JinaReaderScraper()

    @classmethod
    async def detect(cls, url: str) -> BaseScraper:
        """확장자만으로 PDF를 판별하지 않는다(arXiv /pdf/, doi 리다이렉트 등) —
        Content-Type 헤더를 우선 확인한다."""
        if not url or not url.strip():
            raise ValueError("ScraperFactory: 유효한 URL이 필요합니다 (None/빈 문자열 거부).")
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.head(url)
                ctype = resp.headers.get("content-type", "").lower()
                if "application/pdf" in ctype:
                    return PdfExtractorScraper()
        except Exception:
            pass  # HEAD 실패 → URL 휴리스틱으로 폴백
        return cls.get_scraper(url)
