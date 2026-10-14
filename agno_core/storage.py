"""SQLite baselines and event history. SQLite is NOT encrypted."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS states (
                    watch_id TEXT PRIMARY KEY, state_json TEXT,
                    checked_at TEXT NOT NULL, error TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    watch_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    analysis TEXT,
                    delivery TEXT NOT NULL DEFAULT 'local'
                );
                CREATE INDEX IF NOT EXISTS events_order ON events(id DESC);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def get_state(self, watch_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT state_json FROM states WHERE watch_id=?", (watch_id,)).fetchone()
        return json.loads(row["state_json"]) if row and row["state_json"] else None

    def set_state(self, watch_id: str, state: dict) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO states(watch_id,state_json,checked_at,error)
                          VALUES(?,?,?,NULL)
                          ON CONFLICT(watch_id) DO UPDATE SET
                          state_json=excluded.state_json,checked_at=excluded.checked_at,error=NULL""",
                       (watch_id, json.dumps(state, ensure_ascii=False), utc_now()))

    def set_error(self, watch_id: str, error: str) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO states(watch_id,checked_at,error) VALUES(?,?,?)
                          ON CONFLICT(watch_id) DO UPDATE SET
                          checked_at=excluded.checked_at,error=excluded.error""",
                       (watch_id, utc_now(), error[:500]))

    def list_states(self) -> dict:
        with self.connect() as db:
            rows = db.execute("SELECT watch_id,checked_at,error FROM states").fetchall()
        return {r["watch_id"]: {"checked_at": r["checked_at"], "error": r["error"]} for r in rows}

    def add_event(self, watch_id: str, title: str, detail: str, source_url: str) -> int:
        with self.connect() as db:
            cursor = db.execute("""INSERT INTO events(watch_id,created_at,title,detail,source_url)
                                   VALUES(?,?,?,?,?)""",
                                (watch_id, utc_now(), title[:250], detail[:1500], source_url[:2000]))
            return int(cursor.lastrowid)

    def update_event(self, event_id: int, analysis: str | None, delivery: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE events SET analysis=?,delivery=? WHERE id=?",
                       (analysis[:2500] if analysis else None, delivery, event_id))

    def list_events(self, limit: int = 50) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?",
                              (max(1, min(limit, 200)),)).fetchall()
        return [dict(row) for row in rows]
