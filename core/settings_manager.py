"""Local user settings persisted as JSON in %LOCALAPPDATA%\\DigimonTCGLab\\settings.json."""
import json

from core.paths import USER_SETTINGS_PATH
from core.ban_score import DEFAULT_WEIGHTS

DEFAULTS = {
    "format": "English",
    "period_days": 30,
    "region": "Todas",
    "ban_score_weights": DEFAULT_WEIGHTS,
    "sidebar_collapsed": False,
    "first_run_complete": False,
}


class SettingsManager:
    def __init__(self, path=None):
        self.path = path or USER_SETTINGS_PATH
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                self._data.update(stored)
            except (json.JSONDecodeError, OSError):
                pass
        else:
            self.save()

    def save(self):
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    @property
    def data(self):
        return dict(self._data)
