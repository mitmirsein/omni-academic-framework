from rich.console import Console
from rich.panel import Panel

from src.config.lens import LensNotFoundError, load_lens

console = Console()

class LensAnalyzer:
    """[BLUEPRINT] 렌즈 스펙 프리뷰.

    실 LLM 기반 분석(AnalysisReport)은 미구현이다. 현재는 장착될 렌즈의
    Focus/Prompt 스펙만 미리보기로 출력한다 — 가짜 '분석 완료'를 찍지
    않는다(정직성 원칙).
    """
    def __init__(self, lens_dir: str = "lenses"):
        self.lens_dir = lens_dir
        self.console = console

    def analyze(self, target_document: str, lens_name: str) -> bool:
        self.console.print(
            f"\n[bold magenta]🎯 [Lens Spec Preview] (렌즈: {lens_name})[/bold magenta]"
        )
        try:
            lens_config = load_lens(lens_name, self.lens_dir)
        except LensNotFoundError as e:
            self.console.print(f"[bold red]❌ Error: {e}[/bold red]")
            return False

        name = lens_config.get("name", lens_name)
        focus_areas = "\n".join(f"- {a}" for a in lens_config.get("focus_areas", []))
        prompt = lens_config.get("analysis_prompt", "")
        content = (
            f"[bold cyan]분석 초점(Focus Areas):[/bold cyan]\n{focus_areas}\n\n"
            f"[bold cyan]AI 분석 지침(Prompt):[/bold cyan]\n{prompt}"
        )
        self.console.print(Panel(content, title=f"👓 렌즈 스펙: {name}", border_style="blue"))
        self.console.print(
            "\n[bold yellow]⚠️ [BLUEPRINT] 실 LLM 렌즈 분석은 미구현입니다. "
            "위는 장착될 렌즈 스펙 프리뷰일 뿐, 분석 리포트가 아닙니다.[/bold yellow]"
        )
        return True
