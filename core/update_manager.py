"""Handles checking for new shared data (meta.json etc.) and, in the future,
new application releases via GitHub Releases.

This module intentionally never scrapes DigimonMeta directly. It only ever
compares the local data/version.json against a remote manifest published by
the (separate, offline) Data Collector pipeline.
"""
import json
from dataclasses import dataclass
from typing import Optional

import requests

from core.paths import VERSION_JSON

DEFAULT_TIMEOUT = 4


@dataclass
class ReleaseInfo:
    current_version: str
    latest_version: str
    download_url: str = ""
    release_notes: str = ""

    @property
    def has_update(self) -> bool:
        return self.latest_version and self.latest_version != self.current_version


class UpdateManager:
    """Checks for data updates. App self-update is scaffolded but not wired
    up in this first version (see check_app_update)."""

    def __init__(self, manifest_url: Optional[str] = None, releases_api_url: Optional[str] = None):
        # Left unset until a public GitHub/CDN manifest exists for this project.
        self.manifest_url = manifest_url
        self.releases_api_url = releases_api_url

    def local_version(self) -> dict:
        if VERSION_JSON.exists():
            try:
                return json.loads(VERSION_JSON.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"data_version": "unknown", "cards_version": "unknown", "meta_version": "unknown"}

    def is_online(self) -> bool:
        if not self.manifest_url:
            try:
                requests.head("https://github.com", timeout=DEFAULT_TIMEOUT)
                return True
            except requests.RequestException:
                return False
        try:
            requests.head(self.manifest_url, timeout=DEFAULT_TIMEOUT)
            return True
        except requests.RequestException:
            return False

    def check_data_update(self) -> Optional[dict]:
        """Returns the remote version.json dict if reachable and different, else None."""
        if not self.manifest_url:
            return None
        try:
            resp = requests.get(self.manifest_url, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            remote = resp.json()
        except (requests.RequestException, ValueError):
            return None

        local = self.local_version()
        if remote.get("meta_version") != local.get("meta_version"):
            return remote
        return None

    def check_app_update(self) -> Optional[ReleaseInfo]:
        """Scaffold for future .exe self-update via GitHub Releases API.
        Not wired up in v1 — returns None until releases_api_url is configured."""
        if not self.releases_api_url:
            return None
        try:
            resp = requests.get(self.releases_api_url, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return None

        return ReleaseInfo(
            current_version=self.local_version().get("data_version", "0.0.0"),
            latest_version=data.get("tag_name", ""),
            download_url=(data.get("assets") or [{}])[0].get("browser_download_url", ""),
            release_notes=data.get("body", ""),
        )
