"""Builds decks/tournaments/meta/history sample data ON TOP OF the real card
pool in data/cards.json (produced by data_collector/fetch_digimon_data.py).

Real deck lists and tournament results are not scraped here — per the
project's architecture, that would be a separate, future Data Collector
pipeline against DigimonMeta. This script only synthesizes plausible-looking
analytics data referencing real card IDs/names, so the app has something
representative to show while that integration doesn't exist yet.

Usage:
    python data/mock/build_synthetic_meta.py
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(7)

ROOT = Path(__file__).resolve().parent.parent
CARDS_JSON = ROOT / "cards.json"
DECK_ARCHETYPE_NAMES = [
    "AlterS", "Beelstar", "Imperialdramon", "Metalgarurumon", "Ulforce",
    "Aegisdramon", "Blue Flare", "Yellow Hybrid", "Green Security",
    "Purple Curse", "Black Fenriloogamon", "Ragnaloardmon", "Machinedramon",
    "Belphemon", "Argreomon", "Gaiomon", "Justimon", "Ordinemon",
    "Arresterdramon", "Susanoomon", "Royal Knights", "Olympos XII",
]
TOURNAMENT_NAMES = [
    "Regional Championship", "ADS Cup", "Winter Tournament", "Local Store League",
    "Digimon Championship Series", "Online Ranked Cup", "Asia Invitational",
    "Europe Regional", "North America Regional", "World Qualifier",
]


def load_cards():
    return json.loads(CARDS_JSON.read_text(encoding="utf-8"))


def build_decks(cards, n=24):
    digimon_cards = [c for c in cards if c["type"] == "Digimon"]
    support_cards = [c for c in cards if c["type"] in ("Tamer", "Option")]
    colors = sorted({c["color"] for c in cards if c.get("color") and c["color"] != "Colorless"})

    decks = []
    for i in range(n):
        name = DECK_ARCHETYPE_NAMES[i % len(DECK_ARCHETYPE_NAMES)]
        color_pool = random.sample(colors, k=min(len(colors), random.choice([1, 2])))
        deck_digimon = [c for c in digimon_cards if c["color"] in color_pool or c.get("color2") in color_pool]
        deck_support = [c for c in support_cards if c["color"] in color_pool or c.get("color2") in color_pool]
        pool = (deck_digimon or digimon_cards) + (deck_support or support_cards)
        pool = pool or cards
        chosen = random.sample(pool, k=min(len(pool), random.randint(9, 15)))

        card_list = [
            {
                "card_id": c["card_id"],
                "copies": (copies := random.choice([1, 2, 2, 3, 3, 4])),
                "inclusion_pct": round(min(100.0, copies / 4 * 100 * random.uniform(0.6, 1.0)), 1),
            }
            for c in chosen
        ]
        meta_usage = round(random.uniform(1.5, 19.5), 1)
        top8 = round(min(99.0, meta_usage * random.uniform(1.0, 1.6)), 1)
        winrate = round(random.uniform(44.0, 65.0), 1)
        entries = random.randint(3, 120)

        decks.append({
            "deck_id": f"deck-{i+1:03d}",
            "name": f"{name} #{i+1}",
            "archetype": name,
            "colors": color_pool,
            "cards": card_list,
            "entries": entries,
            "meta_usage": meta_usage,
            "top8": top8,
            "win_rate": winrate,
        })
    return decks


def build_tournaments(decks, n=32):
    tournaments = []
    base_date = datetime(2026, 8, 20)
    for i in range(n):
        date = base_date - timedelta(days=random.randint(0, 90))
        players = random.randint(16, 256)
        pool = decks[:]
        random.shuffle(pool)
        top_n = min(8, len(pool))
        standings = [
            {"rank": rank, "deck_id": pool[rank - 1]["deck_id"], "player": f"Player{random.randint(100,999)}"}
            for rank in range(1, top_n + 1)
        ]
        tournaments.append({
            "tournament_id": f"trn-{i+1:03d}",
            "name": f"{random.choice(TOURNAMENT_NAMES)} {date.strftime('%Y')}",
            "date": date.strftime("%Y-%m-%d"),
            "region": random.choice(["NA", "EU", "APAC", "LATAM", "Global"]),
            "format": random.choice(["English", "Japanese"]),
            "players": players,
            "top8": standings,
        })
    return tournaments


def build_meta(cards, decks, tournaments):
    digimon_cards = [c for c in cards if c["type"] == "Digimon" and c.get("rarity") in ("SR", "SEC", "R")]
    tracked_cards = random.sample(digimon_cards or cards, k=min(10, len(digimon_cards or cards)))

    weeks = []
    today = datetime(2026, 8, 20)
    for w in range(4, 0, -1):
        week_date = (today - timedelta(weeks=w - 1)).strftime("%Y-%m-%d")
        entries = [{"card_id": c["card_id"], "usage": round(random.uniform(20, 90), 1)} for c in tracked_cards]
        weeks.append({"week": f"Semana {5 - w}", "date": week_date, "cards": entries})

    ban_candidates = []
    for c in tracked_cards:
        meta_usage = round(random.uniform(35, 92), 1)
        top_cut = round(min(99.0, meta_usage * random.uniform(1.0, 1.3)), 1)
        avg_copies = round(random.uniform(1.5, 4.0), 1)
        growth = round(random.uniform(-10, 40), 1)
        dominance = round(min(99.0, meta_usage * random.uniform(1.0, 1.2)), 1)
        ban_candidates.append({
            "card_id": c["card_id"],
            "meta_usage": meta_usage,
            "top_cut": top_cut,
            "avg_copies": avg_copies,
            "growth": growth,
            "dominance": dominance,
        })

    ranking = []
    for i, d in enumerate(sorted(decks, key=lambda d: -d["meta_usage"])[:15], start=1):
        ranking.append({
            "rank": i, "deck_id": d["deck_id"], "name": d["archetype"],
            "entries": d["entries"], "meta_usage": d["meta_usage"], "top8": d["top8"], "win_rate": d["win_rate"],
        })

    return {
        "generated_at": today.strftime("%Y-%m-%d"),
        "format": "English",
        "period_days": 30,
        "decks_analyzed": len(decks) * 43 + random.randint(0, 50),
        "tournaments": len(tournaments),
        "top8_total": sum(len(t["top8"]) for t in tournaments),
        "avg_win_rate": round(sum(d["win_rate"] for d in decks) / max(1, len(decks)), 1),
        "deck_ranking": ranking,
        "trends": weeks,
        "ban_candidates": ban_candidates,
    }, tracked_cards


def build_history(tracked_cards):
    events = []
    base = datetime(2026, 8, 20)
    restrictions = ["BAN", "LIMIT_1", "LIMIT_2", "LIMIT_3"]
    sample = random.sample(tracked_cards, k=min(5, len(tracked_cards)))
    for i, card in enumerate(sample):
        events.append({
            "card_id": card["card_id"],
            "restriction": restrictions[i % len(restrictions)],
            "date": (base - timedelta(days=i * 6)).strftime("%Y-%m-%d"),
            "note": "Adicionado via análise de meta.",
        })
    return events


def main():
    if not CARDS_JSON.exists():
        raise SystemExit(f"cards.json not found at {CARDS_JSON}. Run data_collector/fetch_digimon_data.py first.")

    cards = load_cards()
    decks = build_decks(cards, 24)
    tournaments = build_tournaments(decks, 32)
    meta, tracked_cards = build_meta(cards, decks, tournaments)
    history = build_history(tracked_cards)
    version = {
        "data_version": datetime.now().strftime("%Y.%m.%d"),
        "cards_version": "1.0",
        "meta_version": datetime.now().strftime("%Y.%m.%d"),
    }

    (ROOT / "decks.json").write_text(json.dumps(decks, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "tournaments.json").write_text(json.dumps(tournaments, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "history.json").write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "version.json").write_text(json.dumps(version, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Built decks({len(decks)}), tournaments({len(tournaments)}), meta and history on top of {len(cards)} real cards.")


if __name__ == "__main__":
    main()
