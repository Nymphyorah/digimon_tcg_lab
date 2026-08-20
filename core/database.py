"""SQLite access layer for per-user data (ban list, history, notes, settings)."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from core.paths import USER_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS ban_list (
    card_id TEXT PRIMARY KEY,
    restriction TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    restriction TEXT NOT NULL,
    reason TEXT DEFAULT '',
    note TEXT DEFAULT '',
    date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS decks (
    deck_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id TEXT NOT NULL,
    card_id TEXT NOT NULL,
    copies INTEGER NOT NULL,
    PRIMARY KEY (deck_id, card_id)
);
"""


class Database:
    def __init__(self, path=None):
        self.path = str(path or USER_DB_PATH)
        self._init_schema()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    # ---------- Ban List ----------
    def get_ban_list(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM ban_list ORDER BY updated_at DESC").fetchall()
            return [dict(r) for r in rows]

    def set_ban(self, card_id: str, restriction: str, note: str = "", reason: str = ""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            existing = conn.execute("SELECT card_id FROM ban_list WHERE card_id=?", (card_id,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE ban_list SET restriction=?, note=?, updated_at=? WHERE card_id=?",
                    (restriction, note, now, card_id),
                )
            else:
                conn.execute(
                    "INSERT INTO ban_list (card_id, restriction, note, created_at, updated_at) VALUES (?,?,?,?,?)",
                    (card_id, restriction, note, now, now),
                )
            conn.execute(
                "INSERT INTO history (card_id, restriction, reason, note, date) VALUES (?,?,?,?,?)",
                (card_id, restriction, reason, note, now),
            )

    def remove_ban(self, card_id: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            conn.execute("DELETE FROM ban_list WHERE card_id=?", (card_id,))
            conn.execute(
                "INSERT INTO history (card_id, restriction, reason, note, date) VALUES (?,?,?,?,?)",
                (card_id, "REMOVED", "", "", now),
            )

    def add_history(self, card_id: str, restriction: str, reason: str = "", note: str = "", date: str = None):
        date = date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO history (card_id, restriction, reason, note, date) VALUES (?,?,?,?,?)",
                (card_id, restriction, reason, note, date),
            )

    # ---------- History ----------
    def get_history(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM history ORDER BY date DESC, id DESC").fetchall()
            return [dict(r) for r in rows]

    # ---------- Preferences ----------
    def get_pref(self, key: str, default=None):
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_pref(self, key: str, value: str):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO preferences (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    # ---------- Decks (deck builder) ----------
    def list_decks(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM decks ORDER BY updated_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_deck(self, deck_id: str):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM decks WHERE deck_id=?", (deck_id,)).fetchone()
            return dict(row) if row else None

    def get_deck_cards(self, deck_id: str):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT card_id, copies FROM deck_cards WHERE deck_id=?", (deck_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def create_deck(self, name: str) -> str:
        import uuid
        deck_id = uuid.uuid4().hex[:12]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO decks (deck_id, name, created_at, updated_at) VALUES (?,?,?,?)",
                (deck_id, name, now, now),
            )
        return deck_id

    def rename_deck(self, deck_id: str, name: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            conn.execute("UPDATE decks SET name=?, updated_at=? WHERE deck_id=?", (name, now, deck_id))

    def delete_deck(self, deck_id: str):
        with self.connect() as conn:
            conn.execute("DELETE FROM deck_cards WHERE deck_id=?", (deck_id,))
            conn.execute("DELETE FROM decks WHERE deck_id=?", (deck_id,))

    def set_deck_card(self, deck_id: str, card_id: str, copies: int):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            if copies <= 0:
                conn.execute("DELETE FROM deck_cards WHERE deck_id=? AND card_id=?", (deck_id, card_id))
            else:
                conn.execute(
                    "INSERT INTO deck_cards (deck_id, card_id, copies) VALUES (?,?,?) "
                    "ON CONFLICT(deck_id, card_id) DO UPDATE SET copies=excluded.copies",
                    (deck_id, card_id, copies),
                )
            conn.execute("UPDATE decks SET updated_at=? WHERE deck_id=?", (now, deck_id))

    def replace_deck_cards(self, deck_id: str, cards: list):
        """Overwrites a deck's whole card list in one transaction — used by
        the explicit Save action so in-progress edits never touch the DB
        until the user confirms them."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            conn.execute("DELETE FROM deck_cards WHERE deck_id=?", (deck_id,))
            conn.executemany(
                "INSERT INTO deck_cards (deck_id, card_id, copies) VALUES (?,?,?)",
                [(deck_id, c["card_id"], c["copies"]) for c in cards if c["copies"] > 0],
            )
            conn.execute("UPDATE decks SET updated_at=? WHERE deck_id=?", (now, deck_id))

    def db_size_bytes(self) -> int:
        import os
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0
