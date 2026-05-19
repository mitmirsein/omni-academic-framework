import os
import shutil
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text
from src.config.tools import resolve_tool

console = Console()

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

    # 2. 상태 수집
    # API Keys
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    jina_key = os.environ.get("JINA_API_KEY", "").strip()
    
    # External Tools
    lightpanda_bin = resolve_tool("OMNI_LIGHTPANDA_BIN", "lightpanda")
    pdf_extractor_bin = resolve_tool("OMNI_PDF_EXTRACTOR", "pdftotext")
    
    # Vault Path
    vault_path_env = os.environ.get("MS_BRAIN_VAULT", "").strip()
    vault_status = "Not Set"
    vault_color = "yellow"
    if vault_path_env:
        v_path = Path(vault_path_env)
        if v_path.is_dir():
            vault_status = f"Valid ({v_path.name})"
            vault_color = "green"
        else:
            vault_status = "Directory Not Found"
            vault_color = "red"

    # Git Status
    import subprocess
    git_hash = "Unknown"
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=False, timeout=2
        )
        git_hash = out.stdout.strip() or "Unknown"
    except Exception:
        pass

    # 3. 테이블 및 패널 렌더링
    table = Table(show_header=True, header_style="bold magenta", expand=False)
    table.add_column("Category", style="dim")
    table.add_column("Setting / Dependency")
    table.add_column("Status")
    table.add_column("Description")

    # API Keys
    table.add_row(
        "API Key",
        "ANTHROPIC_API_KEY",
        "[green]Configured (Active)[/green]" if anthropic_key else "[red]Missing (API calls disabled)[/red]",
        "Claude 모델을 이용한 온톨로지 추출에 필히 권장됨"
    )
    table.add_row(
        "API Key",
        "JINA_API_KEY",
        "[green]Configured (Optional)[/green]" if jina_key else "[yellow]Not Configured (Fallback used)[/yellow]",
        "Jina Reader를 통한 논문 마크다운 본문 파싱 전용"
    )

    # External Binaries
    table.add_row(
        "Dependency",
        "Lightpanda (Headless JS)",
        f"[green]Detected: {lightpanda_bin}[/green]" if lightpanda_bin else "[yellow]Missing (JS Scraper fallback to Jina)[/yellow]",
        "바이너리가 발견되지 않으면 Jina Reader로 폴백함"
    )
    table.add_row(
        "Dependency",
        "pdftotext (PDF Parser)",
        f"[green]Detected: {pdf_extractor_bin}[/green]" if pdf_extractor_bin else "[green]Using pypdf (Internal)[/green]",
        "미설정 시 내장 pypdf 파서를 가동하여 텍스트 파싱 처리"
    )

    # Vault
    table.add_row(
        "Workspace",
        "MS_BRAIN_VAULT",
        f"[{vault_color}]{vault_status}[/{vault_color}]",
        f"Vault 연동 경로: {vault_path_env or 'Unset'}"
    )

    # Git
    table.add_row(
        "Repository",
        "Git Commit",
        f"[cyan]{git_hash}[/cyan]",
        "현재 구동 중인 소스코드 커밋 버전 정보"
    )

    console.print(Panel(table, title="[bold green]⚙️ System Environment Configuration[/bold green]", border_style="cyan"))

    # 4. 피드백 가이드
    guide_text = []
    if env_created:
        guide_text.append("[bold yellow]🎉 초심자를 위해 .env.example을 복사하여 .env 파일을 자동 생성했습니다![/bold yellow]\n각자의 API Key와 경로를 새로 생성된 [underline].env[/underline] 파일에 설정하십시오.\n")
    
    if not anthropic_key:
        guide_text.append("[bold red]⚠️ Anthropic API Key가 비어 있습니다.[/bold red]\n- 온톨로지를 실제로 추출하려면 [underline].env[/underline] 파일에 [bold]ANTHROPIC_API_KEY=sk-...[/bold]를 설정하거나,\n- 가짜 목업 환경을 시험하려면 명령어 끝에 [bold]--mock[/bold] 인자를 추가해 실행하십시오.")
    else:
        guide_text.append("[bold green]✅ API Key 세팅이 완료되었습니다.[/bold green] 실시간 AI 분석 파이프라인 구동이 가능합니다.")

    if not lightpanda_bin:
        guide_text.append("\n[bold yellow]💡 Tip: Lightpanda 미설정 상태[/bold yellow]\n- 일반적인 정찰/스크래핑은 Jina Reader API를 통해 우회 동작합니다.\n- 로컬 독립 브라우저 환경이 필요하다면 lightpanda를 설치하고 PATH에 추가하거나 [underline].env[/underline]에 지정하십시오.")

    console.print(Panel("\n".join(guide_text), title="[bold]🧭 Quick Start & Setup Guide[/bold]", border_style="yellow"))
    console.print("\n[bold cyan]🚀 파이프라인 시작 커맨드 예시:[/bold cyan]")
    console.print("  [bold green]uv run omni --mock \"Inflation dynamics\"[/bold green] (Mock 모드 런 실행)")
    console.print("  [bold green]uv run omni \"Inflation dynamics\"[/bold green] (실 API를 이용한 Live 런 실행)\n")
