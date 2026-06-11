import json
import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "omni_academic" / "store" / "query_db.py"


def _make_db(root):
    runs = root / "runs"
    runs.mkdir()
    conn = sqlite3.connect(runs / "index.db")
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, created_at TEXT, query TEXT, "
        "lens TEXT, mock INTEGER, audit_passed INTEGER, dir TEXT)"
    )
    conn.executemany(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
        [
            ("old", "2026-05-18T00:00:00+00:00", "Old query", "cs", 0, 1, "runs/old"),
            ("new", "2026-05-19T00:00:00+00:00", "New query", "cs", 0, 1, "runs/new"),
            ("med", "2026-05-17T00:00:00+00:00", "Medical query", "medical", 0, 1, "runs/med"),
            ("mock-fail", "2026-05-16T00:00:00+00:00", "Mock failed", "cs", 1, 0, "runs/mock"),
        ],
    )
    conn.commit()
    conn.close()


def test_query_db_orders_default_results_newest_first(tmp_path):
    _make_db(tmp_path)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert proc.stdout.find("new") < proc.stdout.find("old")


def test_query_db_uses_lens_registry(tmp_path):
    _make_db(tmp_path)
    lenses = tmp_path / "lenses"
    lenses.mkdir()
    (lenses / "medical.yaml").write_text("name: medical\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "medical"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "med" in proc.stdout
    assert "old" not in proc.stdout


def test_query_db_filters_passed_live_and_limit(tmp_path):
    _make_db(tmp_path)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--passed", "--live", "--limit", "1"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "new" in proc.stdout
    assert "old" not in proc.stdout
    assert "mock-fail" not in proc.stdout


def test_query_db_latest_json(tmp_path):
    _make_db(tmp_path)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--latest", "--json"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    rows = json.loads(proc.stdout)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "new"


def test_query_db_rejects_conflicting_flags(tmp_path):
    _make_db(tmp_path)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--mock", "--live"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "--mock" in proc.stderr


def test_query_db_uses_optional_status_columns(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    conn = sqlite3.connect(runs / "index.db")
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, created_at TEXT, query TEXT, "
        "lens TEXT, mock INTEGER, audit_passed INTEGER, dir TEXT, "
        "status TEXT, forensic_passed INTEGER, artifacts_count INTEGER)"
    )
    conn.executemany(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("ok", "2026-05-19T00:00:00+00:00", "Q", "cs", 0, 1, "runs/ok", "completed", 1, 5),
            ("bad", "2026-05-18T00:00:00+00:00", "Q", "cs", 0, 1, "runs/bad", "scraping_failed", 0, 2),
        ],
    )
    conn.commit()
    conn.close()

    proc = subprocess.run(
        [
            sys.executable, str(SCRIPT), "--status", "completed",
            "--forensic-passed", "--json",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    rows = json.loads(proc.stdout)
    assert [r["run_id"] for r in rows] == ["ok"]
    assert rows[0]["status"] == "completed"
    assert rows[0]["artifacts_count"] == 5


def test_query_db_rejects_status_filter_on_legacy_schema(tmp_path):
    _make_db(tmp_path)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--status", "completed"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "status" in proc.stderr


def test_query_db_rejects_unknown_status_value(tmp_path):
    _make_db(tmp_path)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--status", "done-ish"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "invalid choice" in proc.stderr


# --- 인프로세스 테스트 (커버리지 측정 가능 경로; subprocess 테스트는 통합 검증용) ---

from omni_academic.store import query_db  # noqa: E402


def _json_rows(capsys):
    return json.loads(capsys.readouterr().out)


def test_main_json_orders_newest_first(tmp_path, capsys):
    _make_db(tmp_path)
    rc = query_db.main(["--db", str(tmp_path / "runs" / "index.db"), "--json"])
    assert rc == 0
    rows = _json_rows(capsys)
    assert [r["run_id"] for r in rows][:2] == ["new", "old"]


def test_main_lens_term_filters_by_lens_registry(tmp_path, capsys, monkeypatch):
    _make_db(tmp_path)
    (tmp_path / "lenses").mkdir()
    (tmp_path / "lenses" / "medical.yaml").write_text("name: medical\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = query_db.main(["medical", "--json"])
    assert rc == 0
    assert [r["run_id"] for r in _json_rows(capsys)] == ["med"]


def test_main_keyword_term_falls_back_to_query_like(tmp_path, capsys, monkeypatch):
    _make_db(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = query_db.main(["Mock failed", "--json"])
    assert rc == 0
    assert [r["run_id"] for r in _json_rows(capsys)] == ["mock-fail"]


def test_main_latest_and_mock_filters(tmp_path, capsys):
    _make_db(tmp_path)
    db = str(tmp_path / "runs" / "index.db")
    assert query_db.main(["--db", db, "--latest", "--json"]) == 0
    assert [r["run_id"] for r in _json_rows(capsys)] == ["new"]
    assert query_db.main(["--db", db, "--mock", "--json"]) == 0
    assert [r["run_id"] for r in _json_rows(capsys)] == ["mock-fail"]


def test_main_conflicting_audit_flags_exit_2(tmp_path, capsys):
    _make_db(tmp_path)
    rc = query_db.main([
        "--db", str(tmp_path / "runs" / "index.db"), "--passed", "--failed",
    ])
    assert rc == 2


def test_main_missing_db_exits_1(tmp_path):
    assert query_db.main(["--db", str(tmp_path / "nope.db")]) == 1


def test_main_zero_limit_exits_2(tmp_path):
    _make_db(tmp_path)
    rc = query_db.main(["--db", str(tmp_path / "runs" / "index.db"), "--limit", "0"])
    assert rc == 2


def test_main_status_on_legacy_db_exits_2(tmp_path, capsys):
    # status 컬럼이 없는 레거시 DB → 명확한 인자 오류로 안내
    _make_db(tmp_path)
    rc = query_db.main([
        "--db", str(tmp_path / "runs" / "index.db"),
        "--status", "completed",
    ])
    assert rc == 2


def test_main_direct_sql_ignores_filters_with_warning(tmp_path, capsys):
    _make_db(tmp_path)
    rc = query_db.main([
        "--db", str(tmp_path / "runs" / "index.db"),
        "SELECT run_id FROM runs WHERE mock = 1",
        "--latest", "--json",
    ])
    assert rc == 0
    assert [r["run_id"] for r in _json_rows(capsys)] == ["mock-fail"]


def test_main_table_output_truncates_and_counts(tmp_path, capsys):
    _make_db(tmp_path)
    rc = query_db.main(["--db", str(tmp_path / "runs" / "index.db")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "총 4건의 결과가 조회되었습니다." in out
