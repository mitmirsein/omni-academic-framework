"""Recon HTTP 결과 캐시 (레이트리밋/밴 방어).

RunStore의 index.db(append-only 프로비넌스 원장)와 절대 섞지 않는다 —
별도 sqlite. 캐시 적중은 manifest에 기록되어야 한다(stale을 fresh로
둔갑시키는 것은 mock을 verified로 둔갑시키는 것과 같은 죄).
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

SCHEMA_VER = "v2"  # v1→v2: KCI GET 검색어-무시 버그로 오염된 캐시 전체 무효화
DEFAULT_TTL = 86400  # 24h


class ReconCache:
    def __init__(self, base: str = ".cache", ttl: int = DEFAULT_TTL):
        self.db = Path(base) / "recon.sqlite"
        self.ttl = ttl
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db) as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(key TEXT PRIMARY KEY, created_at TEXT, payload TEXT)"
            )

    @staticmethod
    def _key(client: str, query: str, n: int) -> str:
        raw = f"{client}|{query}|{n}|{SCHEMA_VER}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, client: str, query: str, n: int) -> Tuple[Optional[List[dict]], Optional[int]]:
        """(payload, age_sec) 반환. 미스/만료 시 (None, None)."""
        with sqlite3.connect(self.db) as c:
            row = c.execute(
                "SELECT created_at, payload FROM cache WHERE key=?",
                (self._key(client, query, n),),
            ).fetchone()
        if not row:
            return None, None
        try:
            created = datetime.fromisoformat(row[0])
            age = (datetime.now(timezone.utc) - created).total_seconds()
        except ValueError:
            return None, None
        if age > self.ttl:
            return None, None
        try:
            return json.loads(row[1]), int(age)
        except ValueError:
            return None, None

    def put(self, client: str, query: str, n: int, payload: List[dict]):
        with sqlite3.connect(self.db) as c:
            c.execute(
                "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                (
                    self._key(client, query, n),
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
