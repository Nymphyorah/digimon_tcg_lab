"""Checks for and applies updated shared data (cards.json, meta.json, etc.)
published on the project's public GitHub repo, and — separately — checks
for new application releases via GitHub Releases (scaffolded, not wired up).

This module intentionally never scrapes DigimonMeta directly. It only ever
compares the local data/version.json against data/version.json published in
the repo (by the separate, offline Data Collector pipeline), and downloads
the raw JSON files verbatim if newer.
"""
import json
from dataclasses import dataclass
from typing import Optional

import requests

from core.paths import DATA_FILE_NAMES, USER_DATA_DIR, data_file_path

DEFAULT_TIMEOUT = 4
DOWNLOAD_TIMEOUT = 15

DEFAULT_REPO = "Nymphyorah/digimon_tcg_lab"
DEFAULT_BRANCH = "master"


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
    """Checks for and applies data updates published on GitHub. App
    self-update (replacing the .exe itself) is scaffolded but not wired up
    in this version — see check_app_update."""

    def __init__(self, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH,
                 manifest_url: Optional[str] = None, releases_api_url: Optional[str] = None):
        self.repo = repo
        self.branch = branch
        raw_base = f"https://raw.githubusercontent.com/{repo}/{branch}/data"
        self.manifest_url = manifest_url or f"{raw_base}/version.json"
        self.data_base_url = raw_base
        # Left unset until the project starts publishing GitHub Releases.
        self.releases_api_url = releases_api_url

    def local_version(self) -> dict:
        path = data_file_path("version.json")
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"data_version": "unknown", "cards_version": "unknown", "meta_version": "unknown"}

    def is_online(self) -> bool:
        try:
            requests.head("https://github.com", timeout=DEFAULT_TIMEOUT)
            return True
        except requests.RequestException:
            return False

    def check_data_update(self) -> Optional[dict]:
        """Returns the remote version.json dict if reachable and different, else None."""
        try:
            resp = requests.get(self.manifest_url, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            remote = resp.json()
        except (requests.RequestException, ValueError):
            return None

        local = self.local_version()
        if remote.get("data_version") != local.get("data_version"):
            return remote
        return None

    def download_data_update(self, remote_version: dict) -> bool:
        """Downloads every known data file from the repo into USER_DATA_DIR,
        atomically (write to a temp file, then rename), so a mid-download
        failure never leaves a half-written file in place. Individual files
        that 404 (e.g. an optional one that doesn't exist yet) are skipped
        rather than failing the whole update. Returns True if at least the
        version manifest itself was written."""
        wrote_version = False
        for name in DATA_FILE_NAMES:
            try:
                resp = requests.get(f"{self.data_base_url}/{name}", timeout=DOWNLOAD_TIMEOUT)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                content = resp.content
            except requests.RequestException:
                continue

            dest = USER_DATA_DIR / name
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(content)
            tmp.replace(dest)
            if name == "version.json":
                wrote_version = True

        return wrote_version

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
