"""Lazy, cached loading of card images with a graceful placeholder fallback."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient

from core.paths import card_image_path

_pixmap_cache: dict[str, QPixmap] = {}


def _make_placeholder(card_id: str, size: QSize) -> QPixmap:
    pm = QPixmap(size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)

    gradient = QLinearGradient(0, 0, 0, size.height())
    gradient.setColorAt(0, QColor("#12202E"))
    gradient.setColorAt(1, QColor("#0B111B"))
    painter.setBrush(gradient)
    painter.setPen(QColor("#1B2A3A"))
    painter.drawRoundedRect(1, 1, size.width() - 2, size.height() - 2, 10, 10)

    painter.setPen(QColor("#475569"))
    font = QFont("Segoe UI", 9, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pm.rect().adjusted(8, 0, -8, -8), Qt.AlignCenter | Qt.TextWordWrap,
                      "CARD IMAGE\nNOT AVAILABLE")

    painter.setPen(QColor("#64748B"))
    small_font = QFont("Segoe UI", 8)
    painter.setFont(small_font)
    painter.drawText(pm.rect().adjusted(6, 6, -6, -6), Qt.AlignTop | Qt.AlignLeft, card_id)

    painter.end()
    return pm


def invalidate_card_pixmap_cache(card_id: str):
    for key in [k for k in _pixmap_cache if k.startswith(f"{card_id}_")]:
        del _pixmap_cache[key]


def load_card_pixmap(card_id: str, size: QSize) -> QPixmap:
    cache_key = f"{card_id}_{size.width()}x{size.height()}"
    if cache_key in _pixmap_cache:
        return _pixmap_cache[cache_key]

    path = card_image_path(card_id)
    pm = QPixmap(str(path)) if path.exists() else QPixmap()
    if pm.isNull():
        pm = _make_placeholder(card_id, size)
        from core.image_cache import get_image_cache_manager
        get_image_cache_manager().request(card_id)
    else:
        pm = pm.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

    _pixmap_cache[cache_key] = pm
    return pm
