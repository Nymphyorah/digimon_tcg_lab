"""One-time, offline Data Collector: builds decks.json, tournaments.json,
meta.json and history-seed data from REAL tournament results via the DigiLab
public API (https://digilab.cards, API base https://api.digilab.cards).

This does not run inside the app and is not called automatically — it is a
separate pipeline step, matching the architecture described for the project
(Data Collector -> Parser/Analyzer -> JSON -> app just reads the JSON).

Requires a DigiLab API key (not self-serve — request one in the #api channel
on their Discord: https://digilab.cards/docs). Provide it via either:
  - environment variable DIGILAB_API_KEY, or
  - a local file data_collector/digilab_key.txt (gitignored, one line)

Terms of Use compliance (see https://digilab.cards/docs#terms-of-use):
  - Non-commercial community-tool use only.
  - No bulk scraping beyond normal API usage patterns — this script paginates
    politely and caps how much it pulls per run (see the LIMITS below).
  - Attribution: the app's Settings/About should credit "Data provided by
    DigiLab (digilab.cards)" whenever this data is shown. See
    app/pages/settings.py — add that credit line once this collector is wired
    up and actually used.

Usage:
    python data_collector/fetch_digilab_meta.py
"""
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KEY_FILE = Path(__file__).resolve().parent / "digilab_key.txt"

API_BASE = "https://api.digilab.cards"
HEADERS_BASE = {"User-Agent": "DigimonTCGLab data collector; personal offline use"}

# Politeness limits for this one-time run — well under DigiLab's 300 req/min
# per-key and 60 req/min per-IP caps, and capped in absolute volume so this
# never looks like bulk scraping.
MIN_REQUEST_INTERVAL = 0.3      # seconds between requests (~200 req/min ceiling)
MAX_TOURNAMENTS = 32            # full standings are fetched per tournament (N+1 cost)
MAX_DECKLISTS_PER_ARCHETYPE = 6 # sampled to build each archetype's representative card list
MAX_ARCHETYPES = 20


def _get_api_key() -> str:
    key = os.environ.get("DIGILAB_API_KEY")
    if key:
        return key.strip()
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    raise SystemExit(
        "No DigiLab API key found. Set DIGILAB_API_KEY or create "
        f"{KEY_FILE} with the key (request one in #api on the DigiLab Discord)."
    )


class DigiLabClient:
    def __init__(self, api_key: str):
        self.headers = {**HEADERS_BASE, "X-API-Key": api_key}
        self._last_request = 0.0

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)

    def get(self, path: str, params: dict = None):
        self._throttle()
        resp = requests.get(f"{API_BASE}{path}", headers=self.headers, params=params or {}, timeout=15)
        self._last_request = time.monotonic()
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            print(f"  rate limited, sleeping {retry_after}s...")
            time.sleep(retry_after)
            return self.get(path, params)
        resp.raise_for_status()
        return resp.json()

    def paginate(self, path: str, params: dict, max_pages: int = None):
        page = 1
        while True:
            data = self.get(path, {**params, "page": page})
            rows = data.get("data", [])
            yield from rows
            pagination = data.get("pagination", {})
            total_pages = pagination.get("total_pages", page)
            if page >= total_pages or not rows:
                break
            if max_pages and page >= max_pages:
                break
            page += 1


def fetch_meta_archetypes(client: DigiLabClient, fmt: str = None):
    params = {"per_page": MAX_ARCHETYPES}
    if fmt:
        params["format"] = fmt
    data = client.get("/api/meta", params)
    return data.get("data", [])


def fetch_recent_tournaments(client: DigiLabClient, limit=MAX_TOURNAMENTS):
    rows = []
    for row in client.paginate("/api/tournaments", {"per_page": min(limit, 100), "sort": "date", "sort_dir": "desc"}, max_pages=1):
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def fetch_tournament_standings(client: DigiLabClient, tournament_id: int):
    return client.get(f"/api/tournament/{tournament_id}")


def fetch_topcut_decklists(client: DigiLabClient, archetype_slug: str, limit=MAX_DECKLISTS_PER_ARCHETYPE):
    rows = []
    for row in client.paginate(
        "/api/decklists",
        {"archetype": archetype_slug, "placement_max": 8, "per_page": limit, "sort": "date", "sort_dir": "desc"},
        max_pages=1,
    ):
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def fetch_decklist_detail(client: DigiLabClient, result_id: int):
    return client.get(f"/api/decklist/{result_id}")


def to_deck_id(slug: str) -> str:
    return f"deck-{slug}"


def build_decks_and_meta(client: DigiLabClient, archetypes: list):
    decks = []
    ban_candidate_acc = defaultdict(lambda: {"decks": 0, "copies_sum": 0, "topcut_decks": 0, "sample_size": 0, "name": ""})
    total_archetypes_sampled = 0

    for arch in archetypes:
        slug = arch.get("slug")
        if not slug:
            continue
        print(f"  archetype: {arch.get('archetype_name')} ({arch.get('meta_pct')}%)")
        decklist_rows = fetch_topcut_decklists(client, slug)

        merged_cards = defaultdict(list)  # card_id -> [copies, ...] across sampled decklists
        sample_size = 0
        for row in decklist_rows:
            detail = fetch_decklist_detail(client, row["result_id"])
            decklist = detail.get("decklist")
            if not decklist:
                continue
            sample_size += 1
            for section in ("eggs", "digimon", "tamers", "options"):
                for card in decklist.get(section, []) or []:
                    merged_cards[card["card_id"]].append(card.get("count", 1))
                    entry = ban_candidate_acc[card["card_id"]]
                    entry["decks"] += 1
                    entry["copies_sum"] += card.get("count", 1)
                    entry["topcut_decks"] += 1  # decklists here are already placement<=8
                    entry["name"] = card.get("name", card["card_id"])

        deck_cards = [
            {"card_id": cid, "copies": round(sum(copies) / len(copies))}
            for cid, copies in merged_cards.items()
        ]
        deck_cards.sort(key=lambda c: -c["copies"])

        decks.append({
            "deck_id": to_deck_id(slug),
            "name": arch.get("archetype_name"),
            "archetype": arch.get("archetype_name"),
            "colors": [c for c in [arch.get("primary_color"), arch.get("secondary_color")] if c],
            "cards": deck_cards,
            "meta_usage": arch.get("meta_pct", 0.0),
            "top8": arch.get("top3_pct", 0.0),
            "win_rate": arch.get("win_pct") or 0.0,
        })
        total_archetypes_sampled += sample_size

    return decks, ban_candidate_acc, max(total_archetypes_sampled, 1)


def build_tournaments_json(client: DigiLabClient, listing_rows: list):
    tournaments = []
    for row in listing_rows:
        try:
            detail = fetch_tournament_standings(client, row["tournament_id"])
        except requests.RequestException:
            continue
        t = detail.get("tournament", {})
        standings = detail.get("standings", [])
        top8 = [
            {
                "rank": s["placement"],
                "deck_id": to_deck_id(s["deck"]["slug"]) if s.get("deck") else None,
                "player": s.get("player", {}).get("name", "Anonymous"),
            }
            for s in standings[:8]
        ]
        tournaments.append({
            "tournament_id": f"trn-{t.get('id')}",
            "name": f"{(t.get('store') or {}).get('name', 'Tournament')} — {t.get('event_type', '')}".strip(" —"),
            "date": t.get("date"),
            "region": (t.get("scene") or {}).get("country", "Global"),
            "format": t.get("format"),
            "players": t.get("player_count", 0),
            "top8": top8,
        })
    return tournaments


def build_meta_json(archetypes, decks, tournaments, ban_candidate_acc, sample_size):
    ban_candidates = []
    for card_id, acc in ban_candidate_acc.items():
        meta_usage = round(acc["decks"] / sample_size * 100, 1)
        avg_copies = round(acc["copies_sum"] / acc["decks"], 1) if acc["decks"] else 0
        ban_candidates.append({
            "card_id": card_id,
            "meta_usage": meta_usage,
            "top_cut": meta_usage,  # sample is already top-cut-only decklists
            "avg_copies": avg_copies,
            "growth": 0.0,  # needs a second time-windowed pull to compute; left neutral for now
            "dominance": meta_usage,
        })
    ban_candidates.sort(key=lambda c: -c["meta_usage"])

    deck_ranking = [
        {
            "rank": i + 1,
            "deck_id": to_deck_id(a["slug"]),
            "name": a["archetype_name"],
            "meta_usage": a.get("meta_pct", 0.0),
            "top8": a.get("top3_pct", 0.0),
            "win_rate": a.get("win_pct") or 0.0,
        }
        for i, a in enumerate(sorted(archetypes, key=lambda a: -a.get("meta_pct", 0)))
    ]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "format": "English",
        "period_days": 30,
        "decks_analyzed": sum(a.get("entries", 0) for a in archetypes),
        "tournaments": len(tournaments),
        "top8_total": sum(len(t["top8"]) for t in tournaments),
        "avg_win_rate": round(sum((a.get("win_pct") or 0) for a in archetypes) / max(1, len(archetypes)), 1),
        "deck_ranking": deck_ranking,
        "trends": [],  # requires historical snapshots over time; not backfillable from a single pull
        "ban_candidates": ban_candidates[:15],
        "source": "DigiLab (digilab.cards)",
    }


def main():
    api_key = _get_api_key()
    client = DigiLabClient(api_key)

    print("Fetching current metagame breakdown...")
    archetypes = fetch_meta_archetypes(client)
    print(f"  {len(archetypes)} archetypes")

    print("Building decks + card-level stats from top-cut decklists...")
    decks, ban_candidate_acc, sample_size = build_decks_and_meta(client, archetypes)

    print("Fetching recent tournaments with full standings...")
    listing_rows = fetch_recent_tournaments(client)
    tournaments = build_tournaments_json(client, listing_rows)
    print(f"  {len(tournaments)} tournaments")

    meta = build_meta_json(archetypes, decks, tournaments, ban_candidate_acc, sample_size)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "decks.json").write_text(json.dumps(decks, indent=2, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "tournaments.json").write_text(json.dumps(tournaments, indent=2, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    version_path = DATA_DIR / "version.json"
    version = json.loads(version_path.read_text(encoding="utf-8")) if version_path.exists() else {}
    version["meta_version"] = datetime.now().strftime("%Y.%m.%d")
    version_path.write_text(json.dumps(version, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote real meta data: {len(decks)} decks, {len(tournaments)} tournaments, "
          f"{len(meta['ban_candidates'])} ban candidates.")
    print("Remember: credit 'Data provided by DigiLab (digilab.cards)' wherever this is shown.")


if __name__ == "__main__":
    main()
