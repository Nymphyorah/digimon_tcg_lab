"""One-time, offline Data Collector: builds decks.json, tournaments.json,
meta.json and a history seed from REAL Digimon Card Game tournament results
via the Limitless TCG public API (https://play.limitlesstcg.com/api).

Scoped strictly to game=DCG (Digimon Card Game) — this collector must never
be pointed at any other game on the platform.

No API key is required for the endpoints used here (/tournaments,
/tournaments/{id}/standings). Per Limitless's own developer docs, a key is
only needed for the /games/{id}/decks endpoint (deck-categorization rules),
which this script does not use — DCG already ships with automatic deck
archetype tagging ("metagame": true), visible directly on each standings
entry's "deck" field.

This does not run inside the app and is not called automatically — it is a
separate pipeline step, matching the project's architecture (Data Collector
-> Parser/Analyzer -> JSON -> app just reads the JSON). It does not scrape
DigimonMeta and does not touch any other game's data on Limitless.

Usage:
    python data_collector/fetch_limitless_meta.py
"""
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

API_BASE = "https://play.limitlesstcg.com/api"
GAME = "DCG"  # Digimon Card Game — do not change
HEADERS = {"User-Agent": "DigimonTCGLab data collector (personal offline use, non-commercial)"}
REQUEST_DELAY = 0.35  # polite pacing; no key, so no documented per-key rate limit to target

MAX_TOURNAMENTS = 150     # recent tournaments to sample
MIN_SAMPLE_FOR_CANDIDATE = 3  # a card needs to show up in at least this many decks to be listed
DECK_SECTIONS = ("digimon", "tamer", "option", "egg")
EGG_SECTION = "egg"


def api_get(path: str, params: dict = None):
    resp = requests.get(f"{API_BASE}{path}", headers=HEADERS, params=params or {}, timeout=15)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return resp.json()


def fetch_recent_tournaments(limit=MAX_TOURNAMENTS):
    tournaments = []
    page = 1
    while len(tournaments) < limit:
        batch = api_get("/tournaments", {"game": GAME, "limit": 50, "page": page})
        if not batch:
            break
        tournaments.extend(batch)
        page += 1
        if page > 20:  # safety valve
            break
    return tournaments[:limit]


def fetch_standings(tournament_id: str):
    try:
        return api_get(f"/tournaments/{tournament_id}/standings")
    except requests.RequestException:
        return []


def to_card_id(entry: dict):
    set_code = entry.get("set")
    number = entry.get("number")
    if not set_code or not number:
        return None
    return f"{set_code}-{number}"


def deck_to_id(archetype_name: str) -> str:
    slug = archetype_name.strip().lower().replace(" ", "-")
    return f"deck-{slug}" if slug else "deck-unknown"


def main():
    print(f"Fetching up to {MAX_TOURNAMENTS} recent {GAME} tournaments from Limitless TCG...")
    tournaments = fetch_recent_tournaments()
    tournaments.sort(key=lambda t: t.get("date") or "")
    print(f"  {len(tournaments)} tournaments found")

    card_stats = defaultdict(lambda: {"decks": 0, "copies_sum": 0, "top8_decks": 0, "first_decks": 0})
    deck_stats = defaultdict(lambda: {
        "name": "", "entries": 0, "wins": 0, "losses": 0, "ties": 0, "top8": 0, "firsts": 0,
        "card_totals": defaultdict(int), "card_deck_count": defaultdict(int),
    })
    tournaments_out = []
    entries_out = []  # flat, per-standings-row records — lets the app re-filter
    # (by period/format/tournament) live without re-running the collector.
    total_decks_with_list = 0
    total_top8_decks_with_list = 0
    total_first_decks_with_list = 0

    half_index = len(tournaments) // 2
    early_card_decks = defaultdict(int)
    late_card_decks = defaultdict(int)
    early_total = 0
    late_total = 0

    for i, t in enumerate(tournaments, start=1):
        standings = fetch_standings(t["id"])
        if not standings:
            continue

        top8_entries = []
        is_early = i <= half_index

        for entry in standings:
            placing = entry.get("placing")
            record = entry.get("record") or {}
            deck_info = entry.get("deck")
            decklist = entry.get("decklist")

            if deck_info:
                arche_name = deck_info.get("name") or deck_info.get("id") or "Unknown"
                arche_id = deck_to_id(arche_name)
                d = deck_stats[arche_id]
                d["name"] = arche_name
                d["entries"] += 1
                d["wins"] += record.get("wins", 0)
                d["losses"] += record.get("losses", 0)
                d["ties"] += record.get("ties", 0)
                if isinstance(placing, int) and placing <= 8:
                    d["top8"] += 1
                if placing == 1:
                    d["firsts"] += 1

                if arche_name.strip().lower() != "other":
                    entries_out.append({
                        "tournament_id": f"llt-{t['id']}",
                        "date": (t.get("date") or "")[:10],
                        "format": t.get("format") or "Standard",
                        "deck_id": arche_id,
                        "deck_name": arche_name,
                        "placing": placing,
                        "wins": record.get("wins", 0),
                        "losses": record.get("losses", 0),
                        "ties": record.get("ties", 0),
                    })

            if placing and placing <= 8 and deck_info:
                top8_entries.append({
                    "rank": placing,
                    "deck_id": deck_to_id(deck_info.get("name") or "Unknown"),
                    "player": entry.get("name") or entry.get("player") or "Anonymous",
                })

            if not decklist:
                continue
            total_decks_with_list += 1
            deck_card_ids = set()
            if isinstance(placing, int) and placing <= 8:
                total_top8_decks_with_list += 1
            if placing == 1:
                total_first_decks_with_list += 1
            if is_early:
                early_total += 1
            else:
                late_total += 1

            for section in DECK_SECTIONS:
                for card_entry in decklist.get(section, []) or []:
                    cid = to_card_id(card_entry)
                    if not cid:
                        continue
                    count = card_entry.get("count", 1)
                    try:
                        count = int(count)
                    except (TypeError, ValueError):
                        count = 1

                    stat = card_stats[cid]
                    stat["decks"] += 1
                    stat["copies_sum"] += count
                    if isinstance(placing, int) and placing <= 8:
                        stat["top8_decks"] += 1
                    if placing == 1:
                        stat["first_decks"] += 1
                    deck_card_ids.add(cid)

                    if deck_info:
                        arche_id = deck_to_id(deck_info.get("name") or "Unknown")
                        deck_stats[arche_id]["card_totals"][cid] += count
                        deck_stats[arche_id]["card_deck_count"][cid] += 1

            for cid in deck_card_ids:
                (early_card_decks if is_early else late_card_decks)[cid] += 1

        tournaments_out.append({
            "tournament_id": f"llt-{t['id']}",
            "name": t.get("name", "Tournament"),
            "date": (t.get("date") or "")[:10],
            "region": "Global",
            "format": t.get("format") or "Standard",
            "players": t.get("players", 0),
            "top8": sorted(top8_entries, key=lambda x: x["rank"])[:8],
        })

        if i % 20 == 0:
            print(f"  [{i}/{len(tournaments)}] tournaments processed...")

    # ---- decks.json ----
    # "Other" is Limitless's own catch-all bucket for decks that didn't match
    # any known archetype rule — it's not a real archetype, so it's excluded
    # from both the ranking and the % denominator (real archetypes only).
    deck_stats = {k: d for k, d in deck_stats.items() if d["name"].strip().lower() != "other"}
    total_deck_entries = max(1, sum(dd["entries"] for dd in deck_stats.values()))
    decks_out = []
    for arche_id, d in deck_stats.items():
        entries = max(1, d["entries"])
        matches = d["wins"] + d["losses"] + d["ties"]
        win_rate = round(d["wins"] / matches * 100, 1) if matches else 0.0
        cards = [
            {
                "card_id": cid,
                "copies": round(total / d["card_deck_count"][cid]),
                "inclusion_pct": round(d["card_deck_count"][cid] / entries * 100, 1),
            }
            for cid, total in d["card_totals"].items()
        ]
        cards.sort(key=lambda c: (-c["inclusion_pct"], -c["copies"]))
        decks_out.append({
            "deck_id": arche_id,
            "name": d["name"],
            "archetype": d["name"],
            "colors": [],
            "cards": cards,
            "entries": entries,
            "meta_usage": round(entries / total_deck_entries * 100, 1),
            "top8": round(d["top8"] / entries * 100, 1),
            "win_rate": win_rate,
        })
    decks_out.sort(key=lambda d: -d["meta_usage"])

    # ---- meta.json ----
    total_entries = sum(d["entries"] for d in deck_stats.values()) or 1
    deck_ranking = [
        {
            "rank": i + 1, "deck_id": d["deck_id"], "name": d["name"],
            "entries": d["entries"], "meta_usage": d["meta_usage"], "top8": d["top8"], "win_rate": d["win_rate"],
        }
        for i, d in enumerate(decks_out[:20])
    ]

    ban_candidates = []
    for cid, stat in card_stats.items():
        if stat["decks"] < MIN_SAMPLE_FOR_CANDIDATE:
            continue
        meta_usage = round(stat["decks"] / max(1, total_decks_with_list) * 100, 1)
        top_cut = round(stat["top8_decks"] / max(1, total_top8_decks_with_list) * 100, 1) if total_top8_decks_with_list else 0.0
        dominance = round(stat["first_decks"] / max(1, total_first_decks_with_list) * 100, 1) if total_first_decks_with_list else 0.0
        avg_copies = round(stat["copies_sum"] / stat["decks"], 1)
        early_pct = (early_card_decks.get(cid, 0) / early_total * 100) if early_total else 0.0
        late_pct = (late_card_decks.get(cid, 0) / late_total * 100) if late_total else 0.0
        growth = round(late_pct - early_pct, 1)
        ban_candidates.append({
            "card_id": cid, "meta_usage": meta_usage, "top_cut": top_cut,
            "avg_copies": avg_copies, "growth": growth, "dominance": dominance,
        })
    ban_candidates.sort(key=lambda c: -c["meta_usage"])

    meta_out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "format": "English",
        "period_days": None,
        "decks_analyzed": total_entries,
        "tournaments": len(tournaments_out),
        "top8_total": sum(len(t["top8"]) for t in tournaments_out),
        "avg_win_rate": round(sum(d["win_rate"] for d in decks_out) / max(1, len(decks_out)), 1),
        "deck_ranking": deck_ranking,
        "trends": [],  # would need repeated snapshots over time to backfill meaningfully
        "ban_candidates": ban_candidates[:20],
        "source": "Limitless TCG (play.limitlesstcg.com), game=DCG",
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "decks.json").write_text(json.dumps(decks_out, indent=2, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "tournaments.json").write_text(json.dumps(tournaments_out, indent=2, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "meta.json").write_text(json.dumps(meta_out, indent=2, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "meta_entries.json").write_text(json.dumps(entries_out, indent=2, ensure_ascii=False), encoding="utf-8")

    version_path = DATA_DIR / "version.json"
    version = json.loads(version_path.read_text(encoding="utf-8")) if version_path.exists() else {}
    version["meta_version"] = datetime.now().strftime("%Y.%m.%d")
    version_path.write_text(json.dumps(version, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote REAL meta data: {len(decks_out)} archetypes, {len(tournaments_out)} tournaments, "
          f"{len(meta_out['ban_candidates'])} ban candidates, from {total_decks_with_list} submitted decklists.")


if __name__ == "__main__":
    main()
