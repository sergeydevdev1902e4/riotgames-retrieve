import sqlite3
import json
import gzip
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    platform_id TEXT,
    game_creation INTEGER,
    game_duration INTEGER,
    queue_id INTEGER,
    game_version TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS timelines (
    match_id TEXT PRIMARY KEY,
    frame_count INTEGER,
    raw_json TEXT,
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE TABLE IF NOT EXISTS accounts (
    puuid TEXT PRIMARY KEY,
    game_name TEXT,
    tag_line TEXT,
    region TEXT,
    last_crawled_at INTEGER
);

CREATE TABLE IF NOT EXISTS crawl_queue (
    puuid TEXT PRIMARY KEY,
    priority INTEGER DEFAULT 0,
    discovered_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_matches_creation ON matches(game_creation);
CREATE INDEX IF NOT EXISTS idx_matches_queue ON matches(queue_id);
"""

class LocalStore:
    """Handles local SQLite metadata caching and compressed ndjson dumps."""

    def __init__(self, db_path: str = "data/riot_archive.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # TODO: bench WAL mode under heavy thread contention, currently locking sometimes
        self.conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA)

    def save_account(self, puuid: str, game_name: str, tag_line: str, region: str, crawled_at: Optional[int] = None) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO accounts (puuid, game_name, tag_line, region, last_crawled_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(puuid) DO UPDATE SET
                    game_name=excluded.game_name,
                    tag_line=excluded.tag_line,
                    region=excluded.region,
                    last_crawled_at=COALESCE(excluded.last_crawled_at, accounts.last_crawled_at)
                """,
                (puuid, game_name, tag_line, region, crawled_at),
            )

    def upsert_match_bundle(self, match_data: Dict[str, Any], timeline_data: Optional[Dict[str, Any]] = None) -> bool:
        info = match_data.get("info", {})
        meta = match_data.get("metadata", {})
        matchId = meta.get("matchId")  # kept old key casing for quick lookups
        
        if not matchId:
            return False

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO matches (match_id, platform_id, game_creation, game_duration, queue_id, game_version, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id) DO UPDATE SET
                    raw_json=excluded.raw_json
                """,
                (
                    matchId,
                    info.get("platformId"),
                    info.get("gameCreation"),
                    info.get("gameDuration"),
                    info.get("queueId"),
                    info.get("gameVersion"),
                    json.dumps(match_data, separators=(",", ":")),
                ),
            )

            if timeline_data:
                frames = timeline_data.get("info", {}).get("frames", [])
                self.conn.execute(
                    """
                    INSERT INTO timelines (match_id, frame_count, raw_json)
                    VALUES (?, ?, ?)
                    ON CONFLICT(match_id) DO UPDATE SET
                        frame_count=excluded.frame_count,
                        raw_json=excluded.raw_json
                    """,
                    (matchId, len(frames), json.dumps(timeline_data, separators=(",", ":"))),
                )

        return True

    def filter_existing_matches(self, match_ids: Iterable[str]) -> List[str]:
        cur = self.conn.cursor()
        id_list = list(match_ids)
        if not id_list:
            return []

        # SQLite has a parameter limit (999 or 32766 depending on build), chunk queries
        chunk_size = 500
        existing: Set[str] = set()

        for i in range(0, len(id_list), chunk_size):
            chunk = id_list[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cur.execute(f"SELECT match_id FROM matches WHERE match_id IN ({placeholders})", chunk)
            existing.update(row[0] for row in cur.fetchall())

        return [m for m in id_list if m not in existing]

    def get_missing_timeline_ids(self, limit: int = 1000) -> List[str]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT m.match_id FROM matches m
            LEFT JOIN timelines t ON m.match_id = t.match_id
            WHERE t.match_id IS NULL
            LIMIT ?
            """,
            (limit,),
        )
        return [row[0] for row in cur.fetchall()]

    def export_archive_ndjson(self, output_path: str, include_timelines: bool = False, batch_size: int = 1000) -> int:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        cur = self.conn.cursor()
        total_written = 0

        open_func = gzip.open if target.name.endswith(".gz") else open
        mode = "wt" if target.name.endswith(".gz") else "w"

        with open_func(target, mode, encoding="utf-8") as f:  # type: ignore
            if include_timelines:
                query = """
                    SELECT m.match_id, m.raw_json, t.raw_json 
                    FROM matches m
                    LEFT JOIN timelines t ON m.match_id = t.match_id
                    ORDER BY m.game_creation ASC
                """
                cur.execute(query)
                while True:
                    rows = cur.fetchmany(batch_size)
                    if not rows:
                        break
                    for mid, m_json, t_json in rows:
                        record = {
                            "match_id": mid,
                            "match": json.loads(m_json) if m_json else None,
                            "timeline": json.loads(t_json) if t_json else None,
                        }
                        f.write(json.dumps(record) + "\n")
                        total_written += 1
            else:
                query = "SELECT raw_json FROM matches ORDER BY game_creation ASC"
                cur.execute(query)
                while True:
                    rows = cur.fetchmany(batch_size)
                    if not rows:
                        break
                    for (m_json,) in rows:
                        f.write(m_json + "\n")
                        total_written += 1

        return total_written

    def close(self) -> None:
        self.conn.close()
