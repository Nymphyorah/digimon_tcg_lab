"""Loads the shared (read-only) application datasets: cards, decks, tournaments, meta.

This is the boundary between the app and the offline JSON produced by the
(future) Data Collector pipeline. Nothing here talks to the network.
"""
import json
from functools import lru_cache

from core.paths import (
    CARDS_JSON, DECKS_JSON, TOURNAMENTS_JSON, META_JSON, VERSION_JSON,
    APP_DATA_DIR, ensure_app_data_seeded,
)


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


class DataRepository:
    """In-memory, cached view over the shared JSON datasets."""

    def __init__(self):
        ensure_app_data_seeded()
        self.reload()

    def reload(self):
        self._cards = _load_json(CARDS_JSON, [])
        self._decks = _load_json(DECKS_JSON, [])
        self._tournaments = _load_json(TOURNAMENTS_JSON, [])
        self._meta = _load_json(META_JSON, {})
        self._version = _load_json(VERSION_JSON, {})
        self._history_seed = _load_json(APP_DATA_DIR / "history.json", [])
        self._meta_entries = _load_json(APP_DATA_DIR / "meta_entries.json", [])

        self._cards_by_id = {c["card_id"]: c for c in self._cards}
        self._decks_by_id = {d["deck_id"]: d for d in self._decks}

    # ---- Cards ----
    @property
    def cards(self):
        return self._cards

    def card(self, card_id):
        return self._cards_by_id.get(card_id)

    # ---- Decks ----
    @property
    def decks(self):
        return self._decks

    def deck(self, deck_id):
        return self._decks_by_id.get(deck_id)

    # ---- Tournaments ----
    @property
    def tournaments(self):
        return self._tournaments

    # ---- Meta ----
    @property
    def meta(self):
        return self._meta

    @property
    def version(self):
        return self._version

    @property
    def history_seed(self):
        return self._history_seed

    @property
    def meta_entries(self):
        """Raw per-standings-row tournament records (see
        data_collector/fetch_limitless_meta.py) — used to re-aggregate the
        Meta page's ranking live when its filters change."""
        return self._meta_entries

    def ban_candidate(self, card_id):
        for c in self._meta.get("ban_candidates", []):
            if c["card_id"] == card_id:
                return c
        return None


_repo = None


def get_repository() -> DataRepository:
    global _repo
    if _repo is None:
        _repo = DataRepository()
    return _repo
