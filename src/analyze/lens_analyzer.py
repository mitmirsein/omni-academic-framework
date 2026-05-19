from rich.console import Console
from rich.panel import Panel

from src.config.lens import LensNotFoundError, load_lens
from src.text.paragraphs import assign_paragraph_ids

console = Console()

class LensAnalyzer:
    """렌즈 기반 source-bound briefing 생성기.

    실 LLM 해석 리포트는 아직 제공하지 않는다. 대신 렌즈 설정과 원문 문단을
    기계적으로 묶은 deterministic brief를 생성한다. 가짜 통찰을 만들지 않고,
    사람이 후속 분석할 수 있도록 focus area별 질문과 source paragraph window를
    제시한다.
    """
    def __init__(self, lens_dir: str = "lenses"):
        self.lens_dir = lens_dir
        self.console = console

    @staticmethod
    def _excerpt(text: str, limit: int = 280) -> str:
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: max(0, limit - 3)].rstrip() + "..."

    def build_brief(self, target_document: str, lens_name: str) -> str:
        lens_config = load_lens(lens_name, self.lens_dir)
        name = lens_config.get("name", lens_name)
        focus_areas = lens_config.get("focus_areas", []) or []
        prompt = lens_config.get("analysis_prompt", "")
        _, paragraph_map = assign_paragraph_ids(target_document)

        lines = [
            "# Lens Briefing Scaffold",
            "",
            f"- **Lens**: {name} (`{lens_name}`)",
            f"- **Paragraphs**: {len(paragraph_map)}",
            f"- **Mode**: deterministic source-bound scaffold, not LLM interpretation",
            "",
            "## Lens Focus",
        ]
        if focus_areas:
            lines.extend(f"- {area}" for area in focus_areas)
        else:
            lines.append("- No focus areas configured.")

        lines.extend(["", "## Lens Prompt", "", prompt or "_No prompt configured._"])

        lines.append("\n## Source Windows")
        if paragraph_map:
            for pid, text in list(paragraph_map.items())[:8]:
                lines.append(f"### {pid}")
                lines.append(self._excerpt(text))
        else:
            lines.append("_No source paragraphs detected._")

        lines.append("\n## Review Questions")
        if focus_areas:
            for area in focus_areas:
                lines.append(
                    f"- Which source paragraphs directly support or complicate "
                    f"`{area}`?"
                )
        else:
            lines.append("- Which paragraphs carry the main claim, method, and limitation?")
        lines.append("- Which tensions should be preserved rather than harmonized?")
        lines.append("- Which claims lack direct textual support in the selected source windows?")
        return "\n".join(lines)

    def analyze(self, target_document: str, lens_name: str) -> bool:
        self.console.print(
            f"\n[bold magenta]🎯 [Lens Briefing Scaffold] (렌즈: {lens_name})[/bold magenta]"
        )
        try:
            brief = self.build_brief(target_document, lens_name)
        except LensNotFoundError as e:
            self.console.print(f"[bold red]❌ Error: {e}[/bold red]")
            return False

        self.console.print(Panel(brief, title="👓 Source-Bound Lens Brief", border_style="blue"))
        self.console.print(
            "\n[bold yellow]⚠️ 실 LLM 해석 리포트가 아니라, 원문 문단에 묶인 "
            "분석 준비용 brief입니다.[/bold yellow]"
        )
        return True
