import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from omni_academic.config.tools import resolve_tool
from omni_academic.llm.provider import (
    DEFAULT_LIVE_PROVIDER_ENV_VAR,
    DEFAULT_LIVE_PROVIDER_NAME,
    RESERVED_PROVIDER_ENV_VARS,
)

console = Console()


@dataclass(frozen=True)
class SetupQuestion:
    env_var: str
    description: str
    link: str


@dataclass(frozen=True)
class DiagnosticRow:
    category: str
    name: str
    status: str
    description: str


SETUP_QUESTIONS = (
    SetupQuestion(
        DEFAULT_LIVE_PROVIDER_ENV_VAR,
        "Anthropic API Key (기본 live LLM provider: Claude)",
        "https://console.anthropic.com/",
    ),
    SetupQuestion(
        "SEMANTIC_SCHOLAR_API_KEY",
        "Semantic Scholar API Key (고속 학술 인용망 - 선택)",
        "https://www.semanticscholar.org/product/api",
    ),
    SetupQuestion(
        "SERPAPI_API_KEY",
        "SerpAPI API Key (구글 스콜라 키워드 검색용 - 선택)",
        "https://serpapi.com/",
    ),
    SetupQuestion(
        "JINA_API_KEY",
        "Jina Reader API Key (웹/PDF 마크다운 본문 변환 - 선택)",
        "https://jina.ai/reader/",
    ),
    SetupQuestion(
        "OMNI_LIGHTPANDA_BIN",
        "Lightpanda Headless Browser 실행 파일 경로 (생략 가능)",
        "로컬 바이너리 경로",
    ),
    SetupQuestion(
        "OMNI_PDF_EXTRACTOR",
        "PDF 텍스트 추출기 pdftotext 경로 (생략 가능)",
        "로컬 바이너리 경로",
    ),
)


def _read_env_file(env_path: Path) -> dict[str, str]:
    existing_vars = {}
    if not env_path.exists():
        return existing_vars

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                try:
                    k, v = line.split("=", 1)
                    existing_vars[k.strip()] = v.strip()
                except ValueError:
                    pass
    return existing_vars


def _masked_env_value(var_name: str, value: str) -> str:
    if value and "key" in var_name.lower():
        return value[:8] + "..." if len(value) > 8 else "..."
    return value


def _write_env_values(env_path: Path, new_vars: dict[str, str]) -> None:
    lines = []
    updated_keys = set()

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    try:
                        k, _v = stripped.split("=", 1)
                        k = k.strip()
                        if k in new_vars:
                            lines.append(f"{k}={new_vars[k]}\n")
                            updated_keys.add(k)
                            continue
                    except ValueError:
                        pass
                lines.append(line)

    for k, v in new_vars.items():
        if k not in updated_keys and v:
            lines.append(f"{k}={v}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _git_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        return out.stdout.strip() or "Unknown"
    except Exception:
        return "Unknown"


def _diagnostic_rows() -> tuple[list[DiagnosticRow], dict[str, str]]:
    anthropic_key = os.environ.get(DEFAULT_LIVE_PROVIDER_ENV_VAR, "").strip()
    reserved_provider_keys = {
        env_var: os.environ.get(env_var, "").strip()
        for env_var in RESERVED_PROVIDER_ENV_VARS
    }
    s2_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    serpapi_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    jina_key = os.environ.get("JINA_API_KEY", "").strip()
    lightpanda_bin = resolve_tool("OMNI_LIGHTPANDA_BIN", "lightpanda")
    pdf_extractor_bin = resolve_tool("OMNI_PDF_EXTRACTOR", "pdftotext")

    rows = [
        DiagnosticRow(
            "API Key",
            DEFAULT_LIVE_PROVIDER_ENV_VAR,
            "[green]Configured (Active)[/green]" if anthropic_key else "[red]Missing (API calls disabled)[/red]",
            f"기본 live LLM provider ({DEFAULT_LIVE_PROVIDER_NAME}): ontology/analyze/draft/review "
            "(발급: console.anthropic.com)",
        )
    ]
    for env_var, value in reserved_provider_keys.items():
        rows.append(
            DiagnosticRow(
                "API Key",
                env_var,
                "[dim]Configured but reserved[/dim]" if value else "[dim]Reserved (not used)[/dim]",
                "Future/alternate provider용 예약 키입니다. 기본 live path에서는 사용하지 않습니다.",
            )
        )

    rows.extend(
        [
            DiagnosticRow(
                "API Key",
                "SEMANTIC_SCHOLAR_API_KEY",
                "[green]Configured[/green]" if s2_key else "[yellow]Not Configured (Rate Limited 3s/req)[/yellow]",
                "Semantic Scholar API 고속 조회용 (발급: www.semanticscholar.org/product/api)",
            ),
            DiagnosticRow(
                "API Key",
                "SERPAPI_API_KEY",
                "[green]Configured[/green]" if serpapi_key else "[yellow]Not Configured (Google Scholar query disabled)[/yellow]",
                "SerpAPI 구글 스콜라 키워드 검색용 (발급: serpapi.com)",
            ),
            DiagnosticRow(
                "API Key",
                "JINA_API_KEY",
                "[green]Configured (Optional)[/green]" if jina_key else "[yellow]Not Configured (Fallback used)[/yellow]",
                "Jina Reader 본문 파싱용 (발급: jina.ai/reader)",
            ),
            DiagnosticRow(
                "LLM",
                "OMNI_LLM_MODEL",
                f"[green]Override: {os.environ.get('OMNI_LLM_MODEL', '').strip()}[/green]"
                if os.environ.get("OMNI_LLM_MODEL", "").strip()
                else "[dim]Provider default[/dim]",
                "live LLM 모델 오버라이드 (미설정 시 provider 기본 모델 사용)",
            ),
            DiagnosticRow(
                "LLM",
                "OMNI_LLM_MAX_TOKENS",
                f"[green]{os.environ.get('OMNI_LLM_MAX_TOKENS', '').strip()}[/green]"
                if os.environ.get("OMNI_LLM_MAX_TOKENS", "").strip()
                else "[dim]Default (16000)[/dim]",
                "live 응답 토큰 예산. max_tokens 잘림(hard fail) 시 상향 조정",
            ),
            DiagnosticRow(
                "Dependency",
                "Lightpanda (Headless JS)",
                f"[green]Detected: {lightpanda_bin}[/green]"
                if lightpanda_bin else "[yellow]Missing (JS Scraper fallback to Jina)[/yellow]",
                "바이너리가 발견되지 않으면 Jina Reader로 폴백함",
            ),
            DiagnosticRow(
                "Dependency",
                "pdftotext (PDF Parser)",
                f"[green]Detected: {pdf_extractor_bin}[/green]"
                if pdf_extractor_bin else "[green]Using pypdf (Internal)[/green]",
                "미설정 시 내장 pypdf 파서를 가동하여 텍스트 파싱 처리",
            ),
            DiagnosticRow(
                "Repository",
                "Git Commit",
                f"[cyan]{_git_hash()}[/cyan]",
                "현재 구동 중인 소스코드 커밋 버전 정보",
            ),
        ]
    )

    context = {
        "anthropic_key": anthropic_key,
        "lightpanda_bin": lightpanda_bin or "",
    }
    return rows, context


def _render_environment_table(rows: list[DiagnosticRow]) -> Table:
    table = Table(show_header=True, header_style="bold magenta", expand=False)
    table.add_column("Category", style="dim")
    table.add_column("Setting / Dependency")
    table.add_column("Status")
    table.add_column("Description")
    for row in rows:
        table.add_row(row.category, row.name, row.status, row.description)
    return table


def run_setup_wizard():
    """대화형으로 API 키 및 로컬 경로 정보를 수집하여 .env에 저장하는 마법사."""
    console.print("\n[bold cyan]✨ Omni-Academic Framework - Interactive Setup Wizard[/bold cyan]")
    console.print("[dim]터미널 안내에 따라 설정을 입력하세요. 빈칸으로 엔터를 누르면 기존 설정이 유지되거나 생략됩니다.[/dim]\n")

    env_path = Path(".env")
    example_path = Path(".env.example")
    
    # .env 파일이 없으면 .env.example을 복사해 둠
    if not env_path.exists() and example_path.exists():
        try:
            shutil.copy(example_path, env_path)
        except Exception:
            pass

    existing_vars = _read_env_file(env_path)

    new_vars = {}
    for question in SETUP_QUESTIONS:
        current_val = existing_vars.get(question.env_var, "")
        masked_val = _masked_env_value(question.env_var, current_val)
        
        prompt = f"[bold green]? {question.description}[/bold green]"
        if masked_val:
            prompt += f" [dim](현재값: {masked_val})[/dim]"
        if "http" in question.link:
            prompt += f"\n  [dim]↳ 발급 링크: {question.link}[/dim]"
        prompt += "\n  > "
        
        console.print(prompt, end="")
        try:
            user_input = input().strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[red]❌ 설정이 중단되었습니다.[/red]\n")
            return
            
        if user_input:
            new_vars[question.env_var] = user_input
        else:
            new_vars[question.env_var] = current_val

    _write_env_values(env_path, new_vars)

    console.print("\n[bold green]✅ .env 설정 파일 저장 완료![/bold green]")
    console.print("[dim]변경된 환경 설정을 바탕으로 시스템 진단을 다시 가동합니다...[/dim]")
    
    # 환경변수 즉시 로드 적용 (현 프로세스 반영)
    for k, v in new_vars.items():
        if v:
            os.environ[k] = v

    run_diagnostics()

def run_diagnostics():
    """로컬 셋업 진단 및 환경 세팅 상태 화면 시각화."""
    console.print("\n[bold cyan]🔧 Omni-Academic Framework - System Diagnostics & Setup[/bold cyan]\n")

    # 1. .env 자동 생성 (초심자용 편의 장치)
    env_path = Path(".env")
    example_path = Path(".env.example")
    env_created = False
    if not env_path.exists() and example_path.exists():
        try:
            shutil.copy(example_path, env_path)
            env_created = True
        except Exception:
            pass

    rows, context = _diagnostic_rows()
    table = _render_environment_table(rows)

    console.print(Panel(table, title="[bold green]⚙️ System Environment Configuration[/bold green]", border_style="cyan"))

    # 4. 피드백 가이드
    guide_text = []
    if env_created:
        guide_text.append("[bold yellow]🎉 초심자를 위해 .env.example을 복사하여 .env 파일을 자동 생성했습니다![/bold yellow]\n각자의 API Key와 경로를 새로 생성된 [underline].env[/underline] 파일에 설정하십시오.\n")
    
    guide_text.append("[bold cyan]💡 간편한 대화형 환경 설정 방법:[/bold cyan]\n터미널에 [bold]uv run omni --setup[/bold] 명령어를 구동하여 API 키를 손쉽게 저장할 수 있습니다.\n")

    if not context["anthropic_key"]:
        guide_text.append(f"[bold red]⚠️ Anthropic API Key가 비어 있습니다.[/bold red]\n- 온톨로지를 실제로 추출하려면 [underline].env[/underline] 파일에 [bold]{DEFAULT_LIVE_PROVIDER_ENV_VAR}=sk-...[/bold]를 설정하거나,\n- 가짜 목업 환경을 시험하려면 명령어 끝에 [bold]--mock[/bold] 인자를 추가해 실행하십시오.")
    else:
        guide_text.append(f"[bold green]✅ 기본 live provider 세팅이 완료되었습니다.[/bold green] {DEFAULT_LIVE_PROVIDER_NAME} 기반 실시간 AI 분석 파이프라인 구동이 가능합니다.")

    if not context["lightpanda_bin"]:
        guide_text.append("\n[bold yellow]💡 Tip: Lightpanda 미설정 상태[/bold yellow]\n- 일반적인 정찰/스크래핑은 Jina Reader API를 통해 우회 동작합니다.\n- 로컬 독립 브라우저 환경이 필요하다면 lightpanda를 설치하고 PATH에 추가하거나 [underline].env[/underline]에 지정하십시오.")

    console.print(Panel("\n".join(guide_text), title="[bold]🧭 Quick Start & Setup Guide[/bold]", border_style="yellow"))
    console.print("\n[bold cyan]🚀 파이프라인 시작 커맨드 예시:[/bold cyan]")
    console.print("  [bold green]uv run omni --mock \"Inflation dynamics\"[/bold green] (Mock 모드 런 실행)")
    console.print("  [bold green]uv run omni \"Inflation dynamics\"[/bold green] (실 API를 이용한 Live 런 실행)\n")
