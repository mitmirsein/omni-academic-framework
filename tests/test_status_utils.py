"""status.py env 유틸/진단 렌더링 테스트 (커버리지 사각지대 보강)."""

from pathlib import Path

from omni_academic.supervisor.status import (
    _diagnostic_rows,
    _masked_env_value,
    _read_env_file,
    _render_environment_table,
    _write_env_values,
    run_diagnostics,
)


def test_read_env_file_parses_values_and_skips_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nANTHROPIC_API_KEY=sk-test-123\n\nBROKEN_LINE\nA = b c \n",
        encoding="utf-8",
    )
    parsed = _read_env_file(env)
    assert parsed["ANTHROPIC_API_KEY"] == "sk-test-123"
    assert parsed["A"] == "b c"
    assert "BROKEN_LINE" not in parsed


def test_read_env_file_missing_returns_empty(tmp_path):
    assert _read_env_file(tmp_path / "absent.env") == {}


def test_write_env_values_updates_existing_and_appends_new(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# keep me\nOLD_KEY=old\n", encoding="utf-8")
    _write_env_values(env, {"OLD_KEY": "updated", "NEW_KEY": "fresh", "EMPTY": ""})
    text = env.read_text(encoding="utf-8")
    assert "# keep me" in text  # 주석 보존
    assert "OLD_KEY=updated" in text and "OLD_KEY=old" not in text
    assert "NEW_KEY=fresh" in text
    assert "EMPTY" not in text  # 빈 값은 추가하지 않음


def test_masked_env_value_masks_keys_only():
    assert _masked_env_value("ANTHROPIC_API_KEY", "sk-1234567890") == "sk-12345..."
    assert _masked_env_value("SOME_KEY", "short") == "..."
    assert _masked_env_value("OMNI_LIGHTPANDA_BIN", "/usr/local/bin/lp") == "/usr/local/bin/lp"


def test_render_environment_table_includes_every_diagnostic_row():
    rows, context = _diagnostic_rows()
    table = _render_environment_table(rows)
    assert table.row_count == len(rows)
    assert "anthropic_key" in context


def test_run_diagnostics_smoke_without_env_files(tmp_path, monkeypatch, capsys):
    # .env/.env.example 없는 빈 디렉터리에서도 진단 화면이 크래시 없이 출력된다.
    monkeypatch.chdir(tmp_path)
    run_diagnostics()
    assert not Path(".env").exists()  # example 없으면 자동 생성하지 않음
