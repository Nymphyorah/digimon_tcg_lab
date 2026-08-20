"""Generates realistic mock datasets for Digimon TCG Lab.

Run directly to (re)write cards.json, decks.json, tournaments.json,
meta.json, history.json and version.json into this same folder.
These files are copied into application/data on first run by
core.paths.ensure_app_data_seeded().
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

OUT_DIR = Path(__file__).resolve().parent

COLORS = ["Red", "Blue", "Yellow", "Green", "Black", "Purple", "White"]
RARITIES = ["C", "U", "R", "SR", "SEC"]
SETS = ["BT21", "BT22", "BT23", "BT24", "BT25", "EX8", "EX9", "ST20"]
TYPES = ["Digimon", "Tamer", "Option", "Digi-Egg"]

DECK_NAMES = [
    "AlterS", "Beelstar", "Imperialdramon", "Metalgarurumon", "Ulforce",
    "Aegisdramon", "Blue Flare", "Yellow Hybrid", "Green Security",
    "Purple Curse", "Black Fenriloogamon", "Ragnaloardmon", "Machinedramon",
    "Belphemon", "Argreomon", "Gaiomon", "Justimon", "Ordinemon",
    "Arresterdramon", "Susanoomon",
]

TOURNAMENTS = [
    "Regional Championship", "ADS Cup", "Winter Tournament", "Local Store League",
    "Digimon Championship Series", "Online Ranked Cup", "Asia Invitational",
    "Europe Regional", "North America Regional", "World Qualifier",
]

CARD_NAME_PARTS_1 = [
    "Alpha", "Beta", "Omega", "Ultra", "Shadow", "Blue", "Crimson", "Golden",
    "Silver", "Iron", "Steel", "Ancient", "Chrono", "Dark", "Holy", "Sky",
]
CARD_NAME_PARTS_2 = [
    "Greymon", "Garurumon", "Angemon", "Devimon", "Gabumon", "Agumon",
    "Renamon", "Guilmon", "Veemon", "Wormmon", "Patamon", "Gatomon",
    "Terriermon", "Lopmon", "Impmon", "Gomamon",
]


def gen_card_id(idx, set_code):
    return f"{set_code}-{idx:03d}"


def build_cards(n=60):
    cards = []
    used_ids = set()
    for i in range(1, n + 1):
        set_code = random.choice(SETS)
        idx = random.randint(1, 99)
        card_id = gen_card_id(idx, set_code)
        while card_id in used_ids:
            idx = random.randint(1, 99)
            card_id = gen_card_id(idx, set_code)
        used_ids.add(card_id)

        ctype = random.choices(TYPES, weights=[55, 15, 20, 10])[0]
        color = random.choice(COLORS)
        rarity = random.choices(RARITIES, weights=[35, 25, 20, 15, 5])[0]
        level = random.choice([2, 3, 4, 5, 6, 7]) if ctype == "Digimon" else None
        name = f"{random.choice(CARD_NAME_PARTS_1)}{random.choice(CARD_NAME_PARTS_2)}"

        cards.append({
            "card_id": card_id,
            "name": name,
            "color": color,
            "type": ctype,
            "rarity": rarity,
            "level": level,
            "set": set_code,
            "image": f"cards/{card_id}.webp",
        })
    return cards


def build_decks(cards, n=20):
    decks = []
    for i in range(n):
        name = DECK_NAMES[i % len(DECK_NAMES)]
        color_pool = random.sample(COLORS, k=random.choice([1, 2]))
        pool = [c for c in cards if c["color"] in color_pool] or cards
        deck_cards = random.sample(pool, k=min(len(pool), random.randint(8, 14)))
        card_list = []
        for c in deck_cards:
            copies = random.choice([1, 2, 2, 3, 3, 4])
            card_list.append({
                "card_id": c["card_id"],
                "copies": copies,
                "inclusion_pct": round(min(100.0, copies / 4 * 100 * random.uniform(0.6, 1.0)), 1),
            })

        meta_usage = round(random.uniform(1.5, 19.5), 1)
        top8 = round(min(99.0, meta_usage * random.uniform(1.0, 1.6)), 1)
        winrate = round(random.uniform(44.0, 65.0), 1)
        entries = random.randint(3, 120)

        decks.append({
            "deck_id": f"deck-{i+1:03d}",
            "name": f"{name} #{i+1}" if DECK_NAMES.count(name) else name,
            "archetype": name,
            "colors": color_pool,
            "cards": card_list,
            "entries": entries,
            "meta_usage": meta_usage,
            "top8": top8,
            "win_rate": winrate,
        })
    return decks


def build_tournaments(decks, n=30):
    tournaments = []
    base_date = datetime(2026, 8, 20)
    for i in range(n):
        date = base_date - timedelta(days=random.randint(0, 90))
        players = random.randint(16, 256)
        standings = []
        pool = decks[:]
        random.shuffle(pool)
        top_n = min(8, len(pool))
        for rank in range(1, top_n + 1):
            deck = pool[rank - 1]
            standings.append({"rank": rank, "deck_id": deck["deck_id"], "player": f"Player{random.randint(100,999)}"})

        tournaments.append({
            "tournament_id": f"trn-{i+1:03d}",
            "name": f"{random.choice(TOURNAMENTS)} {date.strftime('%Y')}",
            "date": date.strftime("%Y-%m-%d"),
            "region": random.choice(["NA", "EU", "APAC", "LATAM", "Global"]),
            "format": random.choice(["English", "Japanese"]),
            "players": players,
            "top8": standings,
        })
    return tournaments


def build_meta(cards, decks, tournaments):
    weeks = []
    today = datetime(2026, 8, 20)
    tracked_cards = random.sample(cards, k=min(10, len(cards)))
    for w in range(4, 0, -1):
        week_date = (today - timedelta(weeks=w - 1)).strftime("%Y-%m-%d")
        entries = []
        for c in tracked_cards:
            base = random.uniform(20, 90)
            entries.append({"card_id": c["card_id"], "usage": round(base, 1)})
        weeks.append({"week": f"Semana {5 - w}", "date": week_date, "cards": entries})

    ban_candidates = []
    for c in tracked_cards:
        meta_usage = round(random.uniform(35, 92), 1)
        top_cut = round(min(99.0, meta_usage * random.uniform(1.0, 1.3)), 1)
        avg_copies = round(random.uniform(1.5, 4.0), 1)
        growth = round(random.uniform(-10, 40), 1)
        dominance = round(min(99.0, meta_usage * random.uniform(1.0, 1.2)), 1)
        score = round(
            meta_usage * 0.30 + top_cut * 0.25 + min(avg_copies / 4 * 100, 100) * 0.15
            + min(avg_copies / 4 * 100, 100) * 0.15 + random.uniform(40, 90) * 0.10
            + (growth + 10) / 50 * 100 * 0.05,
            0,
        )
        score = int(max(0, min(100, score)))
        ban_candidates.append({
            "card_id": c["card_id"],
            "meta_usage": meta_usage,
            "top_cut": top_cut,
            "avg_copies": avg_copies,
            "growth": growth,
            "dominance": dominance,
            "ban_score": score,
        })
    ban_candidates.sort(key=lambda x: -x["ban_score"])

    ranking = []
    for i, d in enumerate(sorted(decks, key=lambda d: -d["meta_usage"])[:15], start=1):
        ranking.append({
            "rank": i,
            "deck_id": d["deck_id"],
            "name": d["archetype"],
            "entries": d["entries"],
            "meta_usage": d["meta_usage"],
            "top8": d["top8"],
            "win_rate": d["win_rate"],
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
    }


def build_history():
    events = []
    base = datetime(2026, 8, 20)
    samples = [
        ("BT25-082", "BAN", 0),
        ("BT22-008", "LIMIT_1", 2),
        ("EX9-021", "LIMIT_2", 8),
        ("BT23-014", "LIMIT_1", 15),
        ("BT21-047", "LIMIT_3", 22),
    ]
    for card_id, restriction, days_ago in samples:
        events.append({
            "card_id": card_id,
            "restriction": restriction,
            "date": (base - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
            "note": "Adicionado via análise de meta.",
        })
    return events


def main():
    cards = build_cards(60)
    decks = build_decks(cards, 22)
    tournaments = build_tournaments(decks, 32)
    meta = build_meta(cards, decks, tournaments)
    history = build_history()
    version = {
        "data_version": "2026.08.20",
        "cards_version": "1.4",
        "meta_version": "2026.08.20",
    }

    (OUT_DIR / "cards.json").write_text(json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "decks.json").write_text(json.dumps(decks, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "tournaments.json").write_text(json.dumps(tournaments, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "history.json").write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "version.json").write_text(json.dumps(version, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {len(cards)} cards, {len(decks)} decks, {len(tournaments)} tournaments.")


if __name__ == "__main__":
    main()
