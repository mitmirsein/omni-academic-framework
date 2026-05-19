"""SQLite index.db 간편 조회 CLI 유틸리티.

사용 예시:
  python3 src/store/query_db.py (전체 조회)
  python3 src/store/query_db.py theology (렌즈 필터링)
  python3 src/store/query_db.py "Exodus" (질의어 키워드 검색)
  python3 src/store/query_db.py "SELECT * FROM runs WHERE mock = 0" (직접 SQL 실행)
"""

import os
import sqlite3
import sys
from pathlib import Path

def main():
    db_path = Path("runs/index.db")
    if not db_path.exists():
        print(f"오류: 데이터베이스 파일이 존재하지 않습니다: {db_path}", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = "SELECT run_id, created_at, query, lens, mock, audit_passed, dir FROM runs"
    params = []

    if args:
        arg_str = " ".join(args).strip()
        # [1] 직접 SQL 입력 감지
        if arg_str.upper().startswith("SELECT"):
            query = arg_str
        # [2] 렌즈 필터링 (theology, economics 등)
        elif arg_str.lower() in ("theology", "economics", "law", "general"):
            query += " WHERE lens = ?"
            params.append(arg_str.lower())
        # [3] 키워드 검색
        else:
            query += " WHERE query LIKE ?"
            params.append(f"%{arg_str}%")

    try:
        # 정렬 조건 추가 (직접 SQL이 아닌 경우에만 최신순 정렬)
        if not query.upper().startswith("SELECT") and "ORDER BY" not in query.upper():
            query += " ORDER BY created_at DESC"

        rows = cursor.execute(query, params).fetchall()
        
        if not rows:
            print("조회 결과가 없습니다.")
            return

        # 컬럼 정보 파싱
        if cursor.description:
            headers = [col[0] for col in cursor.description]
        else:
            headers = ["run_id", "created_at", "query", "lens", "mock", "audit_passed", "dir"]

        # 터미널 포맷터 출력
        print("-" * 100)
        print(f"{' | '.join(headers)}")
        print("-" * 100)
        for row in rows:
            # 출력 가독성을 위해 긴 문자열 정돈
            row_vals = []
            for val in row:
                val_str = str(val) if val is not None else "NULL"
                if len(val_str) > 40:
                    val_str = val_str[:37] + "..."
                row_vals.append(val_str)
            print(" | ".join(row_vals))
        print("-" * 100)
        print(f"총 {len(rows)}건의 결과가 조회되었습니다.")

    except sqlite3.Error as e:
        print(f"SQL 실행 오류: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
