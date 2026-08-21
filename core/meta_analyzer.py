"""Meta analysis helpers: per-card competitive presence indicators and
engine detection. Every number here comes directly from real tournament
data collected via data_collector/fetch_limitless_meta.py — no aggregate
score is computed, and no restriction is ever suggested automatically. The
three indicators (Meta Usage, Top Cut, Dominance) are presented as-is so the
community can weigh them and decide for itself."""
from collections import Counter

from core.data_repository import DataRepository


class MetaAnalyzer:
    def __init__(self, repo: DataRepository):
        self.repo = repo

    def candidate_table(self):
        """Every card with real per-deck presence data (Meta Usage, Top Cut,
        Dominance), joined with its catalog entry. No score, no ranking
        beyond what the caller asks for — callers sort by whichever
        indicator the user picked."""
        rows = []
        for candidate in self.repo.meta.get("ban_candidates", []):
            card = self.repo.card(candidate["card_id"])
            if not card:
                continue
            rows.append({**candidate, "card": card})
        return rows

    def engine_detection(self, min_group_size=3, min_copies=3):
        """Finds groups of cards that co-occur at high copy counts across decks,
        approximating a recurring 'engine' package."""
        card_deck_presence = Counter()
        deck_total = len(self.repo.decks)
        pair_counts = Counter()

        for deck in self.repo.decks:
            heavy_cards = [c["card_id"] for c in deck["cards"] if c.get("copies", 0) >= min_copies]
            for cid in heavy_cards:
                card_deck_presence[cid] += 1
            for i in range(len(heavy_cards)):
                for j in range(i + 1, len(heavy_cards)):
                    pair = tuple(sorted((heavy_cards[i], heavy_cards[j])))
                    pair_counts[pair] += 1

        if not pair_counts or deck_total == 0:
            return []

        # Build clusters from the most frequent pairs (simple greedy union)
        top_pairs = [p for p, cnt in pair_counts.most_common(6) if cnt >= 2]
        clusters = []
        seen = set()
        for a, b in top_pairs:
            if a in seen or b in seen:
                continue
            cluster = {a, b}
            for c in list(card_deck_presence.keys()):
                if c in cluster:
                    continue
                if pair_counts.get(tuple(sorted((a, c))), 0) >= 2 and pair_counts.get(tuple(sorted((b, c))), 0) >= 2:
                    cluster.add(c)
            if len(cluster) >= min_group_size:
                seen |= cluster
                clusters.append(cluster)

        results = []
        for cluster in clusters:
            decks_with_all = []
            for deck in self.repo.decks:
                deck_heavy = {c["card_id"] for c in deck["cards"] if c.get("copies", 0) >= min_copies}
                if cluster.issubset(deck_heavy):
                    decks_with_all.append(deck)
            if not decks_with_all:
                continue
            presence_pct = round(len(decks_with_all) / deck_total * 100, 1)
            main_deck = max(decks_with_all, key=lambda d: d["meta_usage"])
            main_deck_presence = round(
                sum(1 for d in decks_with_all if d["archetype"] == main_deck["archetype"]) / len(decks_with_all) * 100, 1
            )
            cards_out = []
            for cid in cluster:
                copies = []
                for d in decks_with_all:
                    for c in d["cards"]:
                        if c["card_id"] == cid:
                            copies.append(c["copies"])
                avg_copies = round(sum(copies) / len(copies), 0) if copies else min_copies
                cards_out.append({"card_id": cid, "copies": int(avg_copies)})

            results.append({
                "cards": cards_out,
                "presence_pct": presence_pct,
                "main_deck": main_deck["archetype"],
                "main_deck_presence_pct": main_deck_presence,
            })

        results.sort(key=lambda r: -r["presence_pct"])
        return results[:4]
