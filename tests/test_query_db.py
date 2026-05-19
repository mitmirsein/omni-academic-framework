import sqlite3
import subprocess
import sys
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
