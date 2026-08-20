"""Deck construction and legality validation, following the official Digimon
Card Game deck-building rules:

  - Main deck: exactly 50 cards (Digimon / Tamer / Option).
  - Digi-Egg deck: up to 5 cards, Digi-Egg type only, built separately.
  - Max 4 copies of any single card_id in the main deck (parallel/alternate
    art of the same card number counts together — matches how this app
    already collapses card_ids). The official 4-copy cap is stated for the
    main Deck only — the Digi-Egg deck has no such per-card cap, just its
    overall 5-card size, so a single Digi-Egg card may fill all 5 slots.
  - The user's personal Ban List always applies on top: BAN caps a card at
    0 copies, LIMIT_1/2/3 caps it below the normal maximum.

Every card in the shared catalog is assumed available (no personal
collection/ownership tracking) — the Deck Builder works directly off the
full card pool.
"""
from core.banlist_manager import RESTRICTION_META

MAIN_DECK_SIZE = 50
DIGI_EGG_DECK_MAX = 5
MAX_COPIES_PER_CARD = 4


class DeckBuilder:
    def __init__(self, db, repo, banlist):
        self.db = db
        self.repo = repo
        self.banlist = banlist

    # ---------- Deck CRUD ----------
    def list_decks(self):
        decks = self.db.list_decks()
        for d in decks:
            cards = self.db.get_deck_cards(d["deck_id"])
            d.update(self.summarize(cards))
        return decks

    def get_deck(self, deck_id: str):
        return self.db.get_deck(deck_id)

    def get_deck_cards(self, deck_id: str):
        return self.db.get_deck_cards(deck_id)

    def create_deck(self, name: str) -> str:
        return self.db.create_deck(name or "Novo Deck")

    def rename_deck(self, deck_id: str, name: str):
        self.db.rename_deck(deck_id, name)

    def delete_deck(self, deck_id: str):
        self.db.delete_deck(deck_id)

    # ---------- Card limits ----------
    def base_max_copies(self, card_id: str) -> int:
        """The official cap before the personal Ban List is applied: 4 for
        Digimon/Tamer/Option, or the Digi-Egg deck's own 5-card size for
        Digi-Egg cards (no per-card cap is printed for the egg deck)."""
        card = self.repo.card(card_id)
        if card and card.get("type") == "Digi-Egg":
            return DIGI_EGG_DECK_MAX
        return MAX_COPIES_PER_CARD

    def max_allowed_copies(self, card_id: str) -> int:
        """The most copies of this card that could ever legally go in a deck
        right now: min(official cap, personal Ban List limit)."""
        limit = self.base_max_copies(card_id)
        restriction = self.banlist.restriction_of(card_id)
        if restriction:
            limit = min(limit, RESTRICTION_META[restriction]["max_copies"])
        return max(0, limit)

    def clamp_copies(self, card_id: str, copies: int) -> int:
        return max(0, min(copies, self.max_allowed_copies(card_id)))

    def save_deck_cards(self, deck_id: str, cards: list):
        """Persists a full card list for a deck in one transaction — the only
        way deck edits reach the database (see collection.py's explicit
        Save button; in-progress edits live in memory until then)."""
        self.db.replace_deck_cards(deck_id, cards)

    # ---------- Validation ----------
    def summarize(self, cards: list) -> dict:
        main_count = 0
        egg_count = 0
        for c in cards:
            card = self.repo.card(c["card_id"])
            if not card:
                continue
            if card.get("type") == "Digi-Egg":
                egg_count += c["copies"]
            else:
                main_count += c["copies"]

        if main_count == MAIN_DECK_SIZE and egg_count <= DIGI_EGG_DECK_MAX:
            status = "LEGAL"
        elif main_count > MAIN_DECK_SIZE or egg_count > DIGI_EGG_DECK_MAX:
            status = "ILEGAL"
        else:
            status = "INCOMPLETO"
        return {"main_count": main_count, "egg_count": egg_count, "status": status}

    def validate(self, deck_id: str) -> dict:
        return self.validate_cards(self.get_deck_cards(deck_id))

    def validate_cards(self, cards: list) -> dict:
        issues = []
        for c in cards:
            card = self.repo.card(c["card_id"])
            if not card:
                issues.append(f'{c["card_id"]}: carta não encontrada na base de dados.')
                continue
            allowed = self.max_allowed_copies(c["card_id"])
            if c["copies"] > allowed:
                restriction = self.banlist.restriction_of(c["card_id"])
                reason = "sua Ban List pessoal" if restriction else "o limite de cópias"
                issues.append(
                    f'{card["name"]} ({c["card_id"]}): {c["copies"]} cópias no deck, '
                    f'máximo permitido agora é {allowed} ({reason}).'
                )

        summary = self.summarize(cards)
        if summary["main_count"] < MAIN_DECK_SIZE:
            issues.append(f'Deck principal incompleto: {summary["main_count"]}/{MAIN_DECK_SIZE} cartas.')
        elif summary["main_count"] > MAIN_DECK_SIZE:
            issues.append(f'Deck principal excede o limite: {summary["main_count"]}/{MAIN_DECK_SIZE} cartas.')
        if summary["egg_count"] > DIGI_EGG_DECK_MAX:
            issues.append(f'Deck de Digi-Ovo excede o limite: {summary["egg_count"]}/{DIGI_EGG_DECK_MAX} cartas.')

        return {"issues": issues, **summary}
