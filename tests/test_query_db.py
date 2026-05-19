import sqlite3
import subprocess
import sys
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "src" / "store" / "query_db.py"


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
