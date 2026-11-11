"""SQLite store for games, favorites, and play sessions."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from arcadia.scanner import Game

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    key           TEXT PRIMARY KEY,
    system_id     TEXT NOT NULL,
    path          TEXT NOT NULL,
    title         TEXT NOT NULL,
    favorite      INTEGER NOT NULL DEFAULT 0,
    missing       INTEGER NOT NULL DEFAULT 0,
    play_count    INTEGER NOT NULL DEFAULT 0,
    total_seconds INTEGER NOT NULL DEFAULT 0,
    last_played   REAL
);
CREATE INDEX IF NOT EXISTS games_system ON games(system_id, missing);
CREATE TABLE IF NOT EXISTS sessions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    game_key TEXT NOT NULL,
    started  REAL NOT NULL,
    seconds  INTEGER NOT NULL
);
"""


class Library:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def sync(self, system_id: str, games: list[Game]) -> None:
        """Add or refresh games found on disk. Games no longer on disk are
        marked missing rather than deleted, so favorites and playtime survive
        an unplugged drive or a moved folder."""
        present = {g.key for g in games}
        with self.conn:
            for g in games:
                self.conn.execute(
                    """INSERT INTO games (key, system_id, path, title, missing)
                       VALUES (?, ?, ?, ?, 0)
                       ON CONFLICT(key) DO UPDATE SET
                           path = excluded.path, title = excluded.title, missing = 0""",
                    (g.key, g.system_id, str(g.path), g.title),
                )
            rows = self.conn.execute("SELECT key FROM games WHERE system_id = ?", (system_id,)).fetchall()
            for row in rows:
                if row["key"] not in present:
                    self.conn.execute("UPDATE games SET missing = 1 WHERE key = ?", (row["key"],))

    def games(self, system_id: str | None = None, search: str = "", favorites_only: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM games WHERE missing = 0"
        args: list = []
        if system_id is not None:
            sql += " AND system_id = ?"
            args.append(system_id)
        if search:
            sql += " AND title LIKE ?"
            args.append(f"%{search}%")
        if favorites_only:
            sql += " AND favorite = 1"
        sql += " ORDER BY title COLLATE NOCASE"
        return self.conn.execute(sql, args).fetchall()

    def count(self, system_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM games WHERE system_id = ? AND missing = 0", (system_id,)
        ).fetchone()
        return int(row["n"])

    def get(self, key: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM games WHERE key = ?", (key,)).fetchone()

    def set_favorite(self, key: str, favorite: bool) -> None:
        with self.conn:
            self.conn.execute("UPDATE games SET favorite = ? WHERE key = ?", (int(favorite), key))

    def record_session(self, key: str, started: float, seconds: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO sessions (game_key, started, seconds) VALUES (?, ?, ?)", (key, started, seconds)
            )
            self.conn.execute(
                """UPDATE games SET play_count = play_count + 1,
                       total_seconds = total_seconds + ?,
                       last_played = ?
                   WHERE key = ?""",
                (seconds, started + seconds, key),
            )

    def sessions(self, key: str, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM sessions WHERE game_key = ? ORDER BY started DESC LIMIT ?", (key, limit)
        ).fetchall()

    @staticmethod
    def now() -> float:
        return time.time()
