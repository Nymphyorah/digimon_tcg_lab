"""One-time, offline Data Collector: builds data/cards.json with the full
official Digimon Card Game catalog (names + metadata) from the public
digimoncard.io API.

This mirrors the architecture described for the app: collection/parsing
happens OUTSIDE the .exe, against a public API, and the result is a plain
JSON file the app just reads. It is not run automatically by the app and
does not scrape DigimonMeta.

Source: digimoncard.io public API (https://digimoncard.io/api-documentation),
rate-limited client-side to stay under its documented 15 req/10s limit.
Card art is served from their CDN (images.digimoncard.io) — the app fetches
and caches those lazily at runtime (see core/image_cache.py), so this
collector only needs to pull text metadata.

Usage:
    python data_collector/fetch_digimon_data.py [--local-only]

    --local-only restricts to the card IDs found in the local DCGO image
    folder (the old, smaller scope) instead of the full ~4400-card catalog.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
# Points at a personal, optional local Digimon Card Game Online install and
# isn't the same path on every machine — override with an env var if needed.
IMAGE_DIR = Path(
    os.environ.get("DIGIMON_TCG_LAB_EXTERNAL_CARDS", str(Path.home() / "Dcgo" / "Assets" / "Textures" / "Card"))
)
OUT_PATH = ROOT / "data" / "cards.json"
CACHE_PATH = ROOT / "data_collector" / "_card_cache.json"

API_BASE = "https://digimoncard.io/api-public"
HEADERS = {"User-Agent": "Mozilla/5.0 (DigimonTCGLab data collector; personal offline use)"}
REQUEST_DELAY = 0.75  # ~13 req/10s, under the documented 15 req/10s limit


def scan_local_card_ids(image_dir: Path):
    """Extracts the base card_id (e.g. BT25-082) from every image filename,
    stripping parallel-art suffixes (_P1), tokens and errata variants."""
    ids = set()
    if not image_dir.exists():
        print(f"WARNING: image folder not found: {image_dir}")
        return ids
    for f in image_dir.iterdir():
        if not f.is_file() or f.suffix.lower() not in (".webp", ".png"):
            continue
        stem = f.stem
        stem = re.sub(r"_P\d+$", "", stem)
        stem = re.sub(r"-[Tt]oken.*$", "", stem)
        stem = re.sub(r"-Errata.*$", "", stem)
        m = re.match(r"^([A-Za-z]+\d*-\d+)", stem)
        if m:
            ids.add(m.group(1).upper())
    return ids


def fetch_full_catalog_ids():
    """Every official card_id known to digimoncard.io (~4400), via their
    lightweight name+cardnumber listing endpoint (a single request)."""
    resp = requests.get(
        f"{API_BASE}/getAllCards.php",
        params={"sort": "name", "series": "Digimon Card Game", "sortdirection": "asc"},
        headers=HEADERS, timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return sorted({row["cardnumber"].upper() for row in data if row.get("cardnumber")})


def load_cache():
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_card(card_id: str):
    try:
        resp = requests.get(f"{API_BASE}/search.php", params={"n": card_id}, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(data, list) or not data:
        return None
    # Prefer an exact id match (search can return partial matches too).
    exact = [c for c in data if c.get("id", "").upper() == card_id]
    return (exact or data)[0]


def to_app_card(card_id: str, raw: dict) -> dict:
    set_names = raw.get("set_name") or []
    set_code = card_id.split("-")[0]
    return {
        "card_id": card_id,
        "name": raw.get("name") or card_id,
        "color": raw.get("color") or "Colorless",
        "type": raw.get("type") or "Digimon",
        "rarity": (raw.get("rarity") or "C").strip().upper(),
        "level": raw.get("level"),
        "set": set_code,
        "set_name": set_names[0] if set_names else "",
        "dp": raw.get("dp"),
        "attribute": raw.get("attribute"),
        "image": f"cards/{card_id}.webp",
    }


def main():
    local_only = "--local-only" in sys.argv
    if local_only:
        ids = sorted(scan_local_card_ids(IMAGE_DIR))
        print(f"Found {len(ids)} unique card IDs in {IMAGE_DIR} (--local-only)")
    else:
        ids = fetch_full_catalog_ids()
        print(f"Found {len(ids)} card IDs in the full official catalog")

    cache = load_cache()
    cards = []
    fetched_now = 0

    for i, card_id in enumerate(ids, start=1):
        if card_id in cache:
            raw = cache[card_id]
        else:
            raw = fetch_card(card_id)
            cache[card_id] = raw
            fetched_now += 1
            if fetched_now % 20 == 0:
                save_cache(cache)
            time.sleep(REQUEST_DELAY)

        if raw:
            cards.append(to_app_card(card_id, raw))
        else:
            print(f"  [{i}/{len(ids)}] no data for {card_id}, using ID as name")
            cards.append(to_app_card(card_id, {}))

        if i % 100 == 0:
            print(f"  [{i}/{len(ids)}] processed... ({fetched_now} fetched this run)")

    save_cache(cache)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(cards)} cards to {OUT_PATH}")


if __name__ == "__main__":
    main()
