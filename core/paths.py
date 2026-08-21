"""Centralized filesystem paths for Digimon TCG Lab.

Two separate roots are kept apart on purpose:
  - APP_ROOT: read-only, shipped application data (cards, mock/meta json, assets)
  - USER_ROOT: per-user, writable data (%LOCALAPPDATA%\\DigimonTCGLab)
"""
import os
import sys
from pathlib import Path


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller onefile/onedir: data is bundled next to the exe or in _MEIPASS
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base
    return Path(__file__).resolve().parent.parent


APP_ROOT = _app_root()
APP_DATA_DIR = APP_ROOT / "data"
APP_MOCK_DIR = APP_DATA_DIR / "mock"
APP_ASSETS_DIR = APP_ROOT / "assets"
APP_CARDS_DIR = APP_ROOT / "cards"

# Optional external image source (e.g. an existing local Digimon TCG client's
# texture folder). Used as a fallback so the shipped app doesn't need to bundle
# every card image itself. Safe to not exist — falls back to the placeholder.
# Configurable per-machine via the DIGIMON_TCG_LAB_EXTERNAL_CARDS env var since
# this points at a personal, optional third-party install and isn't the same
# path on every PC.
EXTERNAL_CARDS_DIR = Path(
    os.environ.get("DIGIMON_TCG_LAB_EXTERNAL_CARDS", str(Path.home() / "Dcgo" / "Assets" / "Textures" / "Card"))
)

CARDS_JSON = APP_DATA_DIR / "cards.json"
DECKS_JSON = APP_DATA_DIR / "decks.json"
TOURNAMENTS_JSON = APP_DATA_DIR / "tournaments.json"
META_JSON = APP_DATA_DIR / "meta.json"
VERSION_JSON = APP_DATA_DIR / "version.json"


def _user_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "DigimonTCGLab"
    else:
        root = Path.home() / ".digimontcglab"
    root.mkdir(parents=True, exist_ok=True)
    return root


USER_ROOT = _user_root()
USER_DB_PATH = USER_ROOT / "database.db"
USER_SETTINGS_PATH = USER_ROOT / "settings.json"
USER_CACHE_DIR = USER_ROOT / "cache"
USER_LOGS_DIR = USER_ROOT / "logs"
# Downloaded data updates land here rather than in APP_DATA_DIR: when frozen,
# APP_DATA_DIR lives inside PyInstaller's onefile temp extraction folder and
# is wiped on every exit, so writing an update there would just vanish.
USER_DATA_DIR = USER_ROOT / "data"

for _d in (USER_CACHE_DIR, USER_LOGS_DIR, USER_DATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DATA_FILE_NAMES = [
    "cards.json", "decks.json", "tournaments.json", "meta.json",
    "meta_entries.json", "history.json", "version.json",
]


def data_file_path(name: str) -> Path:
    """A downloaded update in USER_DATA_DIR always wins over the version
    bundled with the app; falls back to the bundled copy otherwise."""
    override = USER_DATA_DIR / name
    if override.exists():
        return override
    return APP_DATA_DIR / name


def _find_variant(directory: Path, card_id: str):
    """Some cards only ship as a suffixed variant (parallel art _P0/_P1/...,
    or a corrected -Errata art) with no plain {card_id}.webp on disk. Falls
    back to any file starting with '{card_id}_' or '{card_id}-', preferring
    non-errata art and lower _P numbers. Token art (e.g. 'EX7-030-token.png')
    is excluded — a game token isn't the card's own artwork and showing it
    as the card image would be misleading."""
    if not directory.exists():
        return None
    candidates = []
    for pattern in (f"{card_id}_*.webp", f"{card_id}_*.png", f"{card_id}-*.webp", f"{card_id}-*.png"):
        candidates.extend(directory.glob(pattern))
    candidates = [p for p in candidates if "token" not in p.stem.lower()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: ("errata" in p.stem.lower(), p.name))
    return candidates[0]


def card_image_path(card_id: str) -> Path:
    """Resolves a card's image: bundled app cards/ folder, then an external
    local source (EXTERNAL_CARDS_DIR), then anything already downloaded into
    the local CDN cache (see core/image_cache.py). Within the first two,
    falls back to a parallel-art/errata variant when the plain
    {card_id}.webp doesn't exist. Callers should treat a non-existent return
    path as "show placeholder" (and may trigger a background CDN fetch)."""
    for directory in (APP_CARDS_DIR, EXTERNAL_CARDS_DIR):
        base = directory / f"{card_id}.webp"
        if base.exists():
            return base
        base_png = directory / f"{card_id}.png"
        if base_png.exists():
            return base_png
        variant = _find_variant(directory, card_id)
        if variant:
            return variant

    from core.image_cache import cached_image_path
    cached = cached_image_path(card_id)
    if cached.exists():
        return cached

    return APP_CARDS_DIR / f"{card_id}.webp"


def ensure_app_data_seeded():
    """On first run, copy mock data into data/*.json if not already present."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    import shutil
    mapping = {
        "cards.json": CARDS_JSON,
        "decks.json": DECKS_JSON,
        "tournaments.json": TOURNAMENTS_JSON,
        "meta.json": META_JSON,
        "version.json": VERSION_JSON,
        "history.json": APP_DATA_DIR / "history.json",
    }
    for name, dest in mapping.items():
        src = APP_MOCK_DIR / name
        if src.exists() and not dest.exists():
            shutil.copy(src, dest)
