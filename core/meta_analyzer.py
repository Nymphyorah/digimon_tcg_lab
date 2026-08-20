"""Meta analysis helpers: dominance, engine detection, ban risk ranking."""
from collections import Counter

from core.ban_score import compute_ban_score, risk_for_score
from core.data_repository import DataRepository


class MetaAnalyzer:
    def __init__(self, repo: DataRepository):
        self.repo = repo

    def ban_risk_table(self, weights=None):
        rows = []
        for candidate in self.repo.meta.get("ban_candidates", []):
            card = self.repo.card(candidate["card_id"])
            if not card:
                continue
            score = compute_ban_score(candidate, weights)
            label, icon = risk_for_score(score)
            rows.append({
                **candidate,
                "card": card,
                "ban_score": score,
                "risk_label": label,
                "risk_icon": icon,
            })
        rows.sort(key=lambda r: -r["ban_score"])
        return rows

    def dominance(self, card_id):
        candidate = self.repo.ban_candidate(card_id)
        if not candidate:
            return None
        meta_usage = candidate["meta_usage"]
        top8 = min(99.0, meta_usage * 1.15)
        top4 = min(99.0, meta_usage * 1.22)
        first = min(99.0, meta_usage * 1.26)
        high_dominance = first > meta_usage * 1.15
        return {
            "card_id": card_id,
            "meta_geral": meta_usage,
            "top8": round(top8, 1),
            "top4": round(top4, 1),
            "first_place": round(first, 1),
            "high_dominance": high_dominance,
        }

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
