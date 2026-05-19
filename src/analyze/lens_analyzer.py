from rich.console import Console
from rich.panel import Panel

from src.config.lens import LensNotFoundError, load_lens

console = Console()

class LensAnalyzer:
    """
    추출된 가치중립적 Ontology를 특정 학문 분야의 Lens(안경)를 끼고
    다시 해석(Analyze)하여 최종 리포트를 생성하는 모듈.
    """
    def __init__(self, lens_dir: str = "lenses"):
        self.lens_dir = lens_dir
        self.console = console

    def analyze(self, target_document: str, lens_name: str):
        self.console.print(f"\n[bold magenta]🎯 [Lens Analyzer] 가동... (적용 렌즈: {lens_name})[/bold magenta]")

        try:
            lens_config = load_lens(lens_name, self.lens_dir)
        except LensNotFoundError as e:
            self.console.print(f"[bold red]❌ Error: {e}[/bold red]")
            return

        name = lens_config.get("name", lens_name)
        focus_areas = "\n".join([f"- {area}" for area in lens_config.get("focus_areas", [])])
        prompt = lens_config.get("analysis_prompt", "")

        content = f"[bold cyan]분석 초점(Focus Areas):[/bold cyan]\n{focus_areas}\n\n[bold cyan]AI 분석 지침(Prompt):[/bold cyan]\n{prompt}"
        
        # 렌즈 장착 UI 출력
        self.console.print(Panel(content, title=f"👓 렌즈 스펙: {name}", border_style="blue"))
        
        # 실제 LLM 분석 (Mock)
        self.console.print("\n[bold green]=> 지식 지형도(Ontology)를 위 렌즈로 투과하여 최종 인사이트를 성공적으로 생성했습니다. (Output: Markdown Report)[/bold green]")
