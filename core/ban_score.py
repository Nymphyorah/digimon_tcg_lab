"""Ban Score calculation.

Ban Score is an analytical metric created by Digimon TCG Lab and does not
represent an official recommendation from Bandai or DigimonMeta.
"""

DEFAULT_WEIGHTS = {
    "meta_usage": 0.30,
    "top_cut": 0.25,
    "performance": 0.15,
    "avg_copies": 0.15,
    "diversity": 0.10,
    "growth": 0.05,
}

RISK_BANDS = [
    (90, 101, "CRITICO", "🔴"),
    (75, 90, "ALTO", "🟠"),
    (55, 75, "MODERADO", "🟡"),
    (30, 55, "BAIXO", "🔵"),
    (0, 30, "NORMAL", "⚪"),
]


def risk_for_score(score: int):
    for low, high, label, icon in RISK_BANDS:
        if low <= score < high:
            return label, icon
    return "NORMAL", "⚪"


def normalize_avg_copies(avg_copies: float) -> float:
    return max(0.0, min(100.0, (avg_copies / 4.0) * 100.0))


def normalize_growth(growth_pct: float) -> float:
    # Map -10%..+50% growth onto a 0..100 scale.
    return max(0.0, min(100.0, (growth_pct + 10.0) / 60.0 * 100.0))


def compute_ban_score(candidate: dict, weights: dict = None) -> int:
    w = weights or DEFAULT_WEIGHTS
    meta_usage = candidate.get("meta_usage", 0.0)
    top_cut = candidate.get("top_cut", 0.0)
    avg_copies = candidate.get("avg_copies", 0.0)
    growth = candidate.get("growth", 0.0)
    dominance = candidate.get("dominance", meta_usage)

    performance = dominance  # proxy: how much it dominates as placement improves
    diversity = 100.0 - min(100.0, meta_usage * 0.4)  # rough inverse-diversity proxy

    score = (
        meta_usage * w["meta_usage"]
        + top_cut * w["top_cut"]
        + performance * w["performance"]
        + normalize_avg_copies(avg_copies) * w["avg_copies"]
        + diversity * w["diversity"]
        + normalize_growth(growth) * w["growth"]
    )
    return int(round(max(0.0, min(100.0, score))))


def score_breakdown(candidate: dict, weights: dict = None) -> list:
    """Returns list of (label, raw_value_0_100, weight) for the factor bars."""
    w = weights or DEFAULT_WEIGHTS
    meta_usage = candidate.get("meta_usage", 0.0)
    top_cut = candidate.get("top_cut", 0.0)
    avg_copies = candidate.get("avg_copies", 0.0)
    growth = candidate.get("growth", 0.0)
    dominance = candidate.get("dominance", meta_usage)
    diversity = 100.0 - min(100.0, meta_usage * 0.4)

    return [
        ("Meta Usage", round(meta_usage), w["meta_usage"]),
        ("Top Cut", round(top_cut), w["top_cut"]),
        ("Performance", round(dominance), w["performance"]),
        ("Average Copies", round(normalize_avg_copies(avg_copies)), w["avg_copies"]),
        ("Diversity", round(diversity), w["diversity"]),
        ("Growth", round(normalize_growth(growth)), w["growth"]),
    ]
