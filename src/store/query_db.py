"""SQLite index.db 간편 조회 CLI 유틸리티.

사용 예시:
  uv run python src/store/query_db.py
  uv run python src/store/query_db.py theology
  uv run python src/store/query_db.py "Exodus"
  uv run python src/store/query_db.py --passed --limit 5
  uv run python src/store/query_db.py --latest --json
  uv run python src/store/query_db.py "SELECT * FROM runs WHERE mock = 0"
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from src.supervisor.run_status import RUN_STATUS_VALUES

BASE_COLUMNS = ["run_id", "created_at", "query", "lens", "mock", "audit_passed", "dir"]
OPTIONAL_COLUMNS = ["status", "forensic_passed", "artifacts_count"]


def _lens_names(lens_dir: str = "lenses") -> set[str]:
    root = Path(lens_dir)
    if not root.is_dir():
        return set()
    return {
        p.stem.lower()
        for p in root.glob("*.yaml")
        if p.is_file() and not p.name.startswith(".")
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query Omni-Academic runs/index.db",
    )
    parser.add_argument(
        "term",
        nargs="*",
        help=(
            "렌즈명, query 키워드, 또는 SELECT로 시작하는 직접 SQL. "
            "기존 사용법 호환을 위해 여러 토큰은 공백으로 합칩니다."
        ),
    )
    parser.add_argument(
        "--db",
        default="runs/index.db",
        help="조회할 SQLite DB 경로 (기본: runs/index.db)",
    )
    parser.add_argument(
        "--passed",
        action="store_true",
        help="audit_passed = 1인 런만 조회",
    )
    parser.add_argument(
        "--failed",
        action="store_true",
        help="audit_passed = 0인 런만 조회",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="mock = 1인 런만 조회",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="mock = 0인 런만 조회",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="최신 1건만 조회 (--limit 1 shortcut)",
    )
    parser.add_argument(
        "--status",
        default="",
        choices=RUN_STATUS_VALUES,
        help="status 컬럼 값으로 필터링 (예: completed, no_papers_found)",
    )
    parser.add_argument(
        "--forensic-passed",
        action="store_true",
        help="forensic_passed = 1인 런만 조회",
    )
    parser.add_argument(
        "--forensic-failed",
        action="store_true",
        help="forensic_passed = 0인 런만 조회",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="최대 출력 행 수",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="테이블 대신 JSON 배열로 출력",
    )
    return parser


def _where(filters: list[str]) -> str:
    return (" WHERE " + " AND ".join(filters)) if filters else ""


def _available_columns(conn: sqlite3.Connection) -> list[str]:
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
    }
    columns = [c for c in BASE_COLUMNS if c in existing]
    columns.extend(c for c in OPTIONAL_COLUMNS if c in existing)
    return columns or BASE_COLUMNS


def _require_column(columns: list[str], column: str, option: str) -> None:
    if column not in columns:
        raise ValueError(
            f"{option} 옵션은 '{column}' 컬럼이 있는 index.db에서만 사용할 수 있습니다. "
            "새 run을 한 번 finalize하면 자동 마이그레이션됩니다."
        )


def _build_query(
    args: argparse.Namespace,
    columns: list[str] | None = None,
) -> tuple[str, list[Any], bool]:
    columns = columns or BASE_COLUMNS
    term = " ".join(args.term).strip()
    params: list[Any] = []
    filters: list[str] = []
    direct_sql = False

    if term.upper().startswith("SELECT"):
        return term, params, True

    lenses = _lens_names()
    if term:
        if term.lower() in lenses:
            filters.append("lens = ?")
            params.append(term.lower())
        else:
            filters.append("query LIKE ?")
            params.append(f"%{term}%")

    if args.passed and args.failed:
        raise ValueError("--passed와 --failed는 동시에 사용할 수 없습니다.")
    if args.passed:
        filters.append("audit_passed = 1")
    if args.failed:
        filters.append("audit_passed = 0")

    if args.mock and args.live:
        raise ValueError("--mock과 --live는 동시에 사용할 수 없습니다.")
    if args.mock:
        filters.append("mock = 1")
    if args.live:
        filters.append("mock = 0")

    if args.status:
        _require_column(columns, "status", "--status")
        filters.append("status = ?")
        params.append(args.status)

    if args.forensic_passed and args.forensic_failed:
        raise ValueError("--forensic-passed와 --forensic-failed는 동시에 사용할 수 없습니다.")
    if args.forensic_passed:
        _require_column(columns, "forensic_passed", "--forensic-passed")
        filters.append("forensic_passed = 1")
    if args.forensic_failed:
        _require_column(columns, "forensic_passed", "--forensic-failed")
        filters.append("forensic_passed = 0")

    query = f"SELECT {', '.join(columns)} FROM runs"
    query += _where(filters)
    query += " ORDER BY created_at DESC"
    limit = 1 if args.latest else args.limit
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit은 1 이상의 정수여야 합니다.")
        query += " LIMIT ?"
        params.append(limit)
    return query, params, direct_sql


def _rows_as_dicts(headers: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [dict(zip(headers, row)) for row in rows]


def _print_table(headers: list[str], rows: list[tuple[Any, ...]]) -> None:
    print("-" * 100)
    print(f"{' | '.join(headers)}")
    print("-" * 100)
    for row in rows:
        row_vals = []
        for val in row:
            val_str = str(val) if val is not None else "NULL"
            if len(val_str) > 40:
                val_str = val_str[:37] + "..."
            row_vals.append(val_str)
        print(" | ".join(row_vals))
    print("-" * 100)
    print(f"총 {len(rows)}건의 결과가 조회되었습니다.")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"오류: 데이터베이스 파일이 존재하지 않습니다: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        columns = _available_columns(conn)
        query, params, direct_sql = _build_query(args, columns)
        if direct_sql and any([
            args.passed, args.failed, args.mock, args.live, args.latest,
            args.status, args.forensic_passed, args.forensic_failed,
            args.limit is not None,
        ]):
            print(
                "경고: 직접 SQL 모드에서는 --passed/--mock/--limit 등 필터 옵션을 무시합니다.",
                file=sys.stderr,
            )
        rows = cursor.execute(query, params).fetchall()
        headers = (
            [col[0] for col in cursor.description]
            if cursor.description else columns
        )

        if args.json:
            print(json.dumps(_rows_as_dicts(headers, rows), ensure_ascii=False, indent=2))
            return 0

        if not rows:
            print("조회 결과가 없습니다.")
            return 0

        _print_table(headers, rows)
        return 0
    except sqlite3.Error as e:
        print(f"SQL 실행 오류: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"인자 오류: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
