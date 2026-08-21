import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

pg.setConfigOption("background", "#0D1622")
pg.setConfigOption("foreground", "#94A3B8")
pg.setConfigOption("antialias", True)

SERIES_COLORS = ["#2388FF", "#EF4444", "#22C55E", "#EAB308", "#A855F7", "#F97316"]


class TrendChart(pg.PlotWidget):
    """Line chart used for Dashboard meta trend and the Meta Trends comparison view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground("#0D1622")
        self.showGrid(x=True, y=True, alpha=0.15)
        self.getAxis("left").setPen(QColor("#1B2A3A"))
        self.getAxis("bottom").setPen(QColor("#1B2A3A"))
        self.getAxis("left").setTextPen(QColor("#94A3B8"))
        self.getAxis("bottom").setTextPen(QColor("#94A3B8"))
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
        legend = self.addLegend(offset=(10, 5))
        legend.setBrush(QColor("#0D1622"))
        legend.setPen(QColor("#1B2A3A"))
        self.plotItem.getViewBox().setBackgroundColor("#0D1622")

    def clear_chart(self):
        self.clear()

    def plot_series(self, x_labels, series: dict):
        """series: {label: [values...]}"""
        self.clear()
        axis = self.getAxis("bottom")
        axis.setTicks([list(enumerate(x_labels))])

        for i, (label, values) in enumerate(series.items()):
            color = SERIES_COLORS[i % len(SERIES_COLORS)]
            pen = pg.mkPen(color=color, width=2.5)
            x = list(range(len(values)))
            self.plot(x, values, pen=pen, name=label, symbol="o", symbolSize=7,
                      symbolBrush=color, symbolPen=color)

            for xi, yi in zip(x, values):
                text = pg.TextItem(f"{yi:.0f}", color=color, anchor=(0.5, 1.4))
                text.setFont(QFont("Segoe UI", 8))
                text.setPos(xi, yi)
                self.addItem(text)


class BarChart(pg.PlotWidget):
    """Simple horizontal-ish bar chart used for ban list distribution etc."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground("#0D1622")
        self.showGrid(x=False, y=True, alpha=0.1)
        self.getAxis("left").setPen(QColor("#1B2A3A"))
        self.getAxis("bottom").setPen(QColor("#1B2A3A"))
        self.getAxis("left").setTextPen(QColor("#94A3B8"))
        self.getAxis("bottom").setTextPen(QColor("#94A3B8"))
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)

    def plot_bars(self, labels, values, colors):
        self.clear()
        axis = self.getAxis("bottom")
        axis.setTicks([list(enumerate(labels))])
        x = list(range(len(values)))
        bg = pg.BarGraphItem(x=x, height=values, width=0.6, brushes=colors, pens=colors)
        self.addItem(bg)


class ScatterChart(pg.PlotWidget):
    """Exploratory Meta Usage x Dominance scatter — every point is a real
    card, point size reflects Top Cut. Purely a visual aid for spotting
    cards that are high on all three real indicators at once; it computes
    no new score and orders/labels nothing on its own."""

    point_clicked = Signal(str)  # card_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground("#0D1622")
        self.showGrid(x=True, y=True, alpha=0.12)
        self.getAxis("left").setPen(QColor("#1B2A3A"))
        self.getAxis("bottom").setPen(QColor("#1B2A3A"))
        self.getAxis("left").setTextPen(QColor("#94A3B8"))
        self.getAxis("bottom").setTextPen(QColor("#94A3B8"))
        self.setLabel("left", "Dominance (%)")
        self.setLabel("bottom", "Meta Usage (%)")
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
        self._scatter = None
        self._ids = []

    def plot_points(self, points):
        """points: list of {card_id, meta_usage, top_cut, dominance}"""
        self.clear()
        self._ids = [p["card_id"] for p in points]
        sizes = [8 + (p.get("top_cut", 0) / 100.0) * 26 for p in points]
        spots = [
            {
                "pos": (p.get("meta_usage", 0), p.get("dominance", 0)),
                "size": sizes[i],
                "brush": pg.mkBrush(35, 136, 255, 130),
                "pen": pg.mkPen(35, 136, 255, 220, width=1.2),
            }
            for i, p in enumerate(points)
        ]
        self._scatter = pg.ScatterPlotItem(spots)
        self._scatter.sigClicked.connect(self._on_clicked)
        self.addItem(self._scatter)

    def _on_clicked(self, _plot, points):
        if not points:
            return
        index = points[0].index()
        if 0 <= index < len(self._ids):
            self.point_clicked.emit(self._ids[index])
