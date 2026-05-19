import src.config.tools as tools
from src.config.tools import resolve_tool


def test_explicit_env_wins(monkeypatch):
    monkeypatch.setenv("OMNI_FOO", "/custom/bin/foo")
    assert resolve_tool("OMNI_FOO", "foo") == "/custom/bin/foo"


def test_path_default_lookup(monkeypatch):
    monkeypatch.delenv("OMNI_FOO", raising=False)
    monkeypatch.setattr(tools.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if name == "foo" else None)
    assert resolve_tool("OMNI_FOO", "foo") == "/usr/bin/foo"


def test_unresolved_returns_empty(monkeypatch):
    monkeypatch.delenv("OMNI_FOO", raising=False)
    monkeypatch.setattr(tools.shutil, "which", lambda _: None)
    assert resolve_tool("OMNI_FOO", "foo") == ""
    assert resolve_tool("OMNI_FOO") == ""  # PATH 기본 없음


def test_no_hardcoded_machine_local_path():
    # 회귀 방지: 머신-로컬 절대경로가 코드에 박혀선 안 된다
    paths = [
        "src/recon/scraper.py",
        "skills/semantic-scholar/scripts/s2_runner.py",
        "skills/semantic-scholar/scripts/legacy_researcher.py",
    ]
    for path in paths:
        src = open(path, encoding="utf-8").read()
        assert "/Users/msn/" not in src
