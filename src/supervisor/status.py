import os
import shutil
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config.tools import resolve_tool

console = Console()

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

    # 기존 env 설정 읽어오기
    existing_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    try:
                        k, v = line.split("=", 1)
                        existing_vars[k.strip()] = v.strip()
                    except ValueError:
                        pass

    # 순차적 질문 목록 정의
    questions = [
        ("ANTHROPIC_API_KEY", "Anthropic API Key (Claude 모델 분석용 필수)", "https://console.anthropic.com/"),
        ("OPENAI_API_KEY", "OpenAI API Key (ChatGPT 모델 분석 및 본문 가공 - 선택)", "https://platform.openai.com/"),
        ("GEMINI_API_KEY", "Google Gemini API Key (Gemini 다차원 분석 및 요약 - 선택)", "https://aistudio.google.com/"),
        ("SEMANTIC_SCHOLAR_API_KEY", "Semantic Scholar API Key (고속 학술 인용망 - 선택)", "https://www.semanticscholar.org/product/api"),
        ("SERPAPI_API_KEY", "SerpAPI API Key (구글 스콜라 키워드 검색용 - 선택)", "https://serpapi.com/"),
        ("JINA_API_KEY", "Jina Reader API Key (웹/PDF 마크다운 본문 변환 - 선택)", "https://jina.ai/reader/"),
        ("OMNI_LIGHTPANDA_BIN", "Lightpanda Headless Browser 실행 파일 경로 (생략 가능)", "로컬 바이너리 경로"),
        ("OMNI_PDF_EXTRACTOR", "PDF 텍스트 추출기 pdftotext 경로 (생략 가능)", "로컬 바이너리 경로")
    ]

    new_vars = {}
    for var_name, description, link in questions:
        current_val = existing_vars.get(var_name, "")
        masked_val = current_val
        if current_val and "key" in var_name.lower():
            # 보안 마스킹
            masked_val = current_val[:8] + "..." if len(current_val) > 8 else "..."
        
        prompt = f"[bold green]? {description}[/bold green]"
        if masked_val:
            prompt += f" [dim](현재값: {masked_val})[/dim]"
        if "http" in link:
            prompt += f"\n  [dim]↳ 발급 링크: {link}[/dim]"
        prompt += "\n  > "
        
        console.print(prompt, end="")
        try:
            user_input = input().strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[red]❌ 설정이 중단되었습니다.[/red]\n")
            return
            
        if user_input:
            new_vars[var_name] = user_input
        else:
            new_vars[var_name] = current_val

    # .env 파일 저장
    # 기존 파일의 주석 구조를 최대한 보존하면서 키값만 교체하거나 뒤에 붙여넣기
    lines = []
    updated_keys = set()
    
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    try:
                        k, v = stripped.split("=", 1)
                        k = k.strip()
                        if k in new_vars:
                            lines.append(f"{k}={new_vars[k]}\n")
                            updated_keys.add(k)
                            continue
                    except ValueError:
                        pass
                lines.append(line)
    
    # 기존에 없던 키들을 새로 추가
    for k, v in new_vars.items():
        if k not in updated_keys and v:
            lines.append(f"{k}={v}\n")
            
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

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

    # 2. 상태 수집
    # API Keys
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    s2_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    serpapi_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    jina_key = os.environ.get("JINA_API_KEY", "").strip()
    
    # External Tools
    lightpanda_bin = resolve_tool("OMNI_LIGHTPANDA_BIN", "lightpanda")
    pdf_extractor_bin = resolve_tool("OMNI_PDF_EXTRACTOR", "pdftotext")

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
        "Claude 모델을 이용한 온톨로지 추출용 (발급: console.anthropic.com)"
    )
    table.add_row(
        "API Key",
        "OPENAI_API_KEY",
        "[green]Configured[/green]" if openai_key else "[yellow]Not Configured (Optional)[/yellow]",
        "ChatGPT 모델을 이용한 본문 가공 및 렌더링용 (발급: platform.openai.com)"
    )
    table.add_row(
        "API Key",
        "GEMINI_API_KEY",
        "[green]Configured[/green]" if gemini_key else "[yellow]Not Configured (Optional)[/yellow]",
        "Gemini 모델을 이용한 다차원 분석 및 요약용 (발급: aistudio.google.com)"
    )
    table.add_row(
        "API Key",
        "SEMANTIC_SCHOLAR_API_KEY",
        "[green]Configured[/green]" if s2_key else "[yellow]Not Configured (Rate Limited 3s/req)[/yellow]",
        "Semantic Scholar API 고속 조회용 (발급: www.semanticscholar.org/product/api)"
    )
    table.add_row(
        "API Key",
        "SERPAPI_API_KEY",
        "[green]Configured[/green]" if serpapi_key else "[yellow]Not Configured (Google Scholar query disabled)[/yellow]",
        "SerpAPI 구글 스콜라 키워드 검색용 (발급: serpapi.com)"
    )
    table.add_row(
        "API Key",
        "JINA_API_KEY",
        "[green]Configured (Optional)[/green]" if jina_key else "[yellow]Not Configured (Fallback used)[/yellow]",
        "Jina Reader 본문 파싱용 (발급: jina.ai/reader)"
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
    
    guide_text.append("[bold cyan]💡 간편한 대화형 환경 설정 방법:[/bold cyan]\n터미널에 [bold]uv run omni --setup[/bold] 명령어를 구동하여 API 키를 손쉽게 저장할 수 있습니다.\n")

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
