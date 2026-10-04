"""Disk-cached, rate-limited HTTP fetching (JSON and HTML).

Every response is stored under data/cache/ so re-running the pipeline never
re-downloads anything. Requests are spaced out to be respectful to hosts.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
MIN_INTERVAL_S = 0.25  # polite delay between *uncached* requests
USER_AGENT = "football-comps-portfolio/0.1 (research project)"

_last_request = 0.0


def _cache_path(url: str, cache_dir: Path, suffix: str = "json") -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    name = url.rstrip("/").split("/")[-1][:60] or "index"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)  # '?', '=' etc. are not valid in Windows filenames
    return cache_dir / f"{name}.{digest}.{suffix}"


def _fetch(url: str, headers: dict | None, retries: int, min_interval: float) -> requests.Response:
    global _last_request
    for attempt in range(1, retries + 1):
        wait = min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=30)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def get_json(url: str, cache_dir: Path = CACHE_DIR, retries: int = 3, headers: dict | None = None, min_interval: float = MIN_INTERVAL_S):
    """Return parsed JSON for `url`, using the on-disk cache when possible."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(url, cache_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    data = _fetch(url, headers, retries, min_interval).json()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def get_html(url: str, cache_dir: Path = CACHE_DIR, retries: int = 3, headers: dict | None = None, min_interval: float = MIN_INTERVAL_S) -> str:
    """Return the page body for `url` as text, using the on-disk cache when possible."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(url, cache_dir, suffix="html")
    if path.exists():
        return path.read_text(encoding="utf-8")
    resp = _fetch(url, headers, retries, min_interval)
    resp.encoding = "utf-8"
    path.write_text(resp.text, encoding="utf-8")
    return resp.text
