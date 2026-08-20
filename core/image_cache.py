"""Lazy background fetch + local cache for card art from the digimoncard.io
CDN, used as a last-resort image source when a card isn't bundled with the
app and isn't in an external local folder (see core/paths.card_image_path).

Downloads run on a plain Python thread pool — deliberately NOT touching any
Qt object from the worker threads. Worker threads only ever write to a
thread-safe queue; a QTimer on the main thread drains it and is the only
place that ever emits a Qt signal. (An earlier version emitted a QObject
signal directly from the worker thread and would intermittently crash with
"Signal source has been deleted" once many downloads ran concurrently —
e.g. a full page of cards with no local art — because PySide's wrapper for
that QObject could be garbage-collected out from under the worker thread
mid-emit. Keeping all Qt interaction on the main thread avoids that class of
bug entirely.)

Once cached under %LOCALAPPDATA%\\DigimonTCGLab\\cache\\card_images\\, the app
stays fully usable offline for any card it has already fetched — this file
only ever supplements the local sources, it never replaces them.
"""
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QTimer, Signal

from core.paths import USER_CACHE_DIR

CDN_URL = "https://images.digimoncard.io/images/cards/{card_id}.jpg"
IMAGE_CACHE_DIR = USER_CACHE_DIR / "card_images"
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
REQUEST_TIMEOUT = 8
MAX_WORKERS = 6
POLL_INTERVAL_MS = 120

_in_flight = set()
_lock = threading.Lock()


def cached_image_path(card_id: str) -> Path:
    return IMAGE_CACHE_DIR / f"{card_id}.jpg"


def _download(card_id: str, result_queue: "queue.Queue"):
    success = False
    try:
        resp = requests.get(CDN_URL.format(card_id=card_id), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200 and resp.content:
            cached_image_path(card_id).write_bytes(resp.content)
            success = True
    except requests.RequestException:
        pass
    result_queue.put((card_id, success))


class ImageCacheManager(QObject):
    """Call request(card_id) to kick off a background download; listen on
    image_ready(card_id) to know when it's safe to re-render that card."""

    image_ready = Signal(str)

    def __init__(self):
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="card-image-fetch")
        self._results: "queue.Queue" = queue.Queue()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain_results)
        self._timer.start(POLL_INTERVAL_MS)

    def request(self, card_id: str):
        if cached_image_path(card_id).exists():
            return
        with _lock:
            if card_id in _in_flight:
                return
            _in_flight.add(card_id)
        self._executor.submit(_download, card_id, self._results)

    def _drain_results(self):
        while True:
            try:
                card_id, success = self._results.get_nowait()
            except queue.Empty:
                break
            with _lock:
                _in_flight.discard(card_id)
            if success:
                self.image_ready.emit(card_id)


_manager = None


def get_image_cache_manager() -> ImageCacheManager:
    global _manager
    if _manager is None:
        _manager = ImageCacheManager()
    return _manager
