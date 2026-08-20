"""Re-aggregates the Meta page's deck ranking from raw per-entry tournament
records (data/meta_entries.json), so the Formato/Período/Torneio filters on
that page actually do something — instead of just re-displaying the same
pre-computed snapshot regardless of what's selected.

This mirrors the aggregation math in data_collector/fetch_limitless_meta.py,
just parameterized by the active filters instead of always covering
everything. No new data is invented — this only slices/recombines the real
per-entry records the collector already wrote to disk.
"""
from collections import defaultdict
from datetime import datetime, timedelta


def _parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def available_formats(entries: list) -> list:
    return sorted({e["format"] for e in entries if e.get("format")})


def available_tournaments(entries: list) -> list:
    """Returns [(tournament_id, label)] sorted by most recent first."""
    seen = {}
    for e in entries:
        tid = e.get("tournament_id")
        if tid and tid not in seen:
            seen[tid] = e.get("date", "")
    return sorted(seen.items(), key=lambda x: x[1], reverse=True)


def latest_date(entries: list):
    dates = [_parse_date(e.get("date")) for e in entries]
    dates = [d for d in dates if d]
    return max(dates) if dates else None


def aggregate(entries: list, period_days: int = None, fmt: str = None, tournament_id: str = None) -> dict:
    """Filters entries by the given criteria (all optional/AND-combined) and
    recomputes deck_ranking + a few KPIs from just that slice."""
    filtered = entries

    if tournament_id:
        filtered = [e for e in filtered if e.get("tournament_id") == tournament_id]

    if fmt:
        filtered = [e for e in filtered if e.get("format") == fmt]

    if period_days:
        anchor = latest_date(filtered) or latest_date(entries)
        if anchor:
            cutoff = anchor - timedelta(days=period_days)
            filtered = [e for e in filtered if (_parse_date(e.get("date")) or cutoff) >= cutoff]

    deck_stats = defaultdict(lambda: {"name": "", "entries": 0, "wins": 0, "losses": 0, "ties": 0, "top8": 0})
    tournament_ids = set()
    top8_total = 0

    for e in filtered:
        tournament_ids.add(e.get("tournament_id"))
        d = deck_stats[e["deck_id"]]
        d["name"] = e.get("deck_name", d["name"] or e["deck_id"])
        d["entries"] += 1
        d["wins"] += e.get("wins", 0)
        d["losses"] += e.get("losses", 0)
        d["ties"] += e.get("ties", 0)
        placing = e.get("placing")
        if isinstance(placing, int) and placing <= 8:
            d["top8"] += 1
            top8_total += 1

    total_entries = sum(d["entries"] for d in deck_stats.values()) or 1

    deck_ranking = []
    for deck_id, d in deck_stats.items():
        entries_n = max(1, d["entries"])
        matches = d["wins"] + d["losses"] + d["ties"]
        win_rate = round(d["wins"] / matches * 100, 1) if matches else 0.0
        deck_ranking.append({
            "deck_id": deck_id,
            "name": d["name"],
            "entries": entries_n,
            "meta_usage": round(entries_n / total_entries * 100, 1),
            "top8": round(d["top8"] / entries_n * 100, 1),
            "win_rate": win_rate,
        })
    deck_ranking.sort(key=lambda d: -d["meta_usage"])
    for i, d in enumerate(deck_ranking, start=1):
        d["rank"] = i

    avg_win_rate = round(sum(d["win_rate"] for d in deck_ranking) / max(1, len(deck_ranking)), 1)

    return {
        "deck_ranking": deck_ranking[:20],
        "decks_analyzed": total_entries,
        "tournaments": len(tournament_ids),
        "top8_total": top8_total,
        "avg_win_rate": avg_win_rate,
    }
