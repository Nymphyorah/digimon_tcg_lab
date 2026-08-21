"""Personal Ban List business logic, backed by the local SQLite database."""
import json
from datetime import datetime

from core.database import Database

RESTRICTIONS = ["BAN", "LIMIT_1", "LIMIT_2", "LIMIT_3"]

RESTRICTION_META = {
    "BAN": {"label": "Banned", "color": "#EF4444", "icon": "🔴", "max_copies": 0},
    "LIMIT_1": {"label": "Limit 1", "color": "#F97316", "icon": "🟠", "max_copies": 1},
    "LIMIT_2": {"label": "Limit 2", "color": "#EAB308", "icon": "🟡", "max_copies": 2},
    "LIMIT_3": {"label": "Limit 3", "color": "#22C55E", "icon": "🟢", "max_copies": 3},
}


class BanListManager:
    def __init__(self, db: Database):
        self.db = db

    def all(self):
        return self.db.get_ban_list()

    def by_restriction(self):
        buckets = {r: [] for r in RESTRICTIONS}
        for row in self.all():
            buckets.setdefault(row["restriction"], []).append(row)
        return buckets

    def restriction_map(self) -> dict:
        """card_id -> restriction, one DB round-trip. Use this instead of
        restriction_of() in loops — restriction_of() re-queries the DB every
        call, which is fine for a single lookup but O(n) DB round-trips when
        called once per card over hundreds of cards."""
        return {row["card_id"]: row["restriction"] for row in self.all()}

    def restriction_of(self, card_id):
        for row in self.all():
            if row["card_id"] == card_id:
                return row["restriction"]
        return None

    def set_restriction(self, card_id: str, restriction: str, note: str = "", reason: str = ""):
        assert restriction in RESTRICTIONS
        self.db.set_ban(card_id, restriction, note=note, reason=reason)

    def remove(self, card_id: str):
        self.db.remove_ban(card_id)

    def counts(self):
        buckets = self.by_restriction()
        return {r: len(buckets[r]) for r in RESTRICTIONS}

    # ---- Import / Export ----
    def export_dict(self, name="Minha Ban List"):
        return {
            "name": name,
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "cards": [
                {"card_id": row["card_id"], "restriction": row["restriction"], "note": row.get("note", "")}
                for row in self.all()
            ],
        }

    def export_to_file(self, path, name="Minha Ban List"):
        data = self.export_dict(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def import_from_file(self, path, merge=True):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not merge:
            for row in self.all():
                self.remove(row["card_id"])
        count = 0
        for entry in data.get("cards", []):
            restriction = entry.get("restriction")
            if restriction not in RESTRICTIONS:
                continue
            self.set_restriction(entry["card_id"], restriction, note=entry.get("note", ""), reason="Importado")
            count += 1
        return count
