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
    last_played   REAL,
    parent_key    TEXT,
    kind          TEXT NOT NULL DEFAULT 'game'
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
        self._migrate()

    def _migrate(self) -> None:
        """Bring a database made by an older version up to date."""
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(games)")}
        with self.conn:
            if "parent_key" not in columns:
                self.conn.execute("ALTER TABLE games ADD COLUMN parent_key TEXT")
            if "kind" not in columns:
                self.conn.execute("ALTER TABLE games ADD COLUMN kind TEXT NOT NULL DEFAULT 'game'")

    def close(self) -> None:
        self.conn.close()

    def sync(self, system_id: str, games: list[Game]) -> None:
        """Add or refresh games found on disk. Games no longer on disk are
        marked missing rather than deleted, so favorites and playtime survive
        an unplugged drive or a moved folder.

        A file that used to be a game of its own but is now part of another (a disc that
        just got an .m3u playlist, an update linked to its base game) hands its favorite
        flag and playtime over to that game, so nothing is lost by tidying up."""
        present = {g.key for g in games}
        handovers = []
        with self.conn:
            for g in games:
                before = self.conn.execute(
                    "SELECT parent_key, favorite, play_count, total_seconds, last_played FROM games WHERE key = ?",
                    (g.key,),
                ).fetchone()
                self.conn.execute(
                    """INSERT INTO games (key, system_id, path, title, missing, parent_key, kind)
                       VALUES (?, ?, ?, ?, 0, ?, ?)
                       ON CONFLICT(key) DO UPDATE SET
                           path = excluded.path, title = excluded.title, missing = 0,
                           parent_key = excluded.parent_key, kind = excluded.kind""",
                    (g.key, g.system_id, str(g.path), g.title, g.parent_key, g.kind),
                )
                if g.parent_key and before is not None and before["parent_key"] is None:
                    handovers.append((g.key, g.parent_key, before))
            # Only now do all the rows exist: a disc can sort before the playlist that adopts it.
            for child_key, parent_key, before in handovers:
                self._hand_over_stats(child_key, parent_key, before)
            rows = self.conn.execute("SELECT key FROM games WHERE system_id = ?", (system_id,)).fetchall()
            for row in rows:
                if row["key"] not in present:
                    self.conn.execute("UPDATE games SET missing = 1 WHERE key = ?", (row["key"],))

    def _hand_over_stats(self, child_key: str, parent_key: str, before) -> None:
        if not (before["favorite"] or before["play_count"] or before["total_seconds"]):
            return
        self.conn.execute(
            """UPDATE games SET
                   favorite = MAX(favorite, ?),
                   play_count = play_count + ?,
                   total_seconds = total_seconds + ?,
                   last_played = MAX(COALESCE(last_played, 0), COALESCE(?, 0)) 
               WHERE key = ?""",
            (before["favorite"], before["play_count"], before["total_seconds"], before["last_played"], parent_key),
        )
        self.conn.execute(
            "UPDATE games SET favorite = 0, play_count = 0, total_seconds = 0, last_played = NULL WHERE key = ?",
            (child_key,),
        )

    SORTS = {
        "title": "title COLLATE NOCASE",
        "recent": "last_played DESC, title COLLATE NOCASE",
        "played": "total_seconds DESC, title COLLATE NOCASE",
        "favorites": "favorite DESC, title COLLATE NOCASE",
    }

    def games(
        self,
        system_id: str | None = None,
        search: str = "",
        favorites_only: bool = False,
        played_only: bool = False,
        sort: str = "title",
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM games WHERE missing = 0 AND parent_key IS NULL"
        args: list = []
        if system_id is not None:
            sql += " AND system_id = ?"
            args.append(system_id)
        if search:
            sql += " AND title LIKE ?"
            args.append(f"%{search}%")
        if favorites_only:
            sql += " AND favorite = 1"
        if played_only:
            sql += " AND play_count > 0"
        sql += " ORDER BY " + self.SORTS.get(sort, self.SORTS["title"])
        return self.conn.execute(sql, args).fetchall()

    def summary(self) -> dict:
        """Counts for the system bar: games per system, favorites, and played games."""
        systems = {
            r["system_id"]: int(r["n"])
            for r in self.conn.execute(
                "SELECT system_id, COUNT(*) AS n FROM games WHERE missing = 0 AND parent_key IS NULL GROUP BY system_id"
            )
        }
        favorites = self.conn.execute(
            "SELECT COUNT(*) AS n FROM games WHERE missing = 0 AND parent_key IS NULL AND favorite = 1"
        ).fetchone()["n"]
        played = self.conn.execute(
            "SELECT COUNT(*) AS n FROM games WHERE missing = 0 AND parent_key IS NULL AND play_count > 0"
        ).fetchone()["n"]
        return {"systems": systems, "favorites": int(favorites), "played": int(played)}

    def count(self, system_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM games WHERE system_id = ? AND missing = 0 AND parent_key IS NULL", (system_id,)
        ).fetchone()
        return int(row["n"])

    def get(self, key: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM games WHERE key = ?", (key,)).fetchone()

    def children(self, key: str) -> list[sqlite3.Row]:
        """Files that belong to a game: its discs, updates, and DLC."""
        return self.conn.execute(
            "SELECT * FROM games WHERE parent_key = ? AND missing = 0 ORDER BY kind, path", (key,)
        ).fetchall()

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
