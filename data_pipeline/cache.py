"""Disk-cached, rate-limited HTTP JSON fetching.

Every response is stored under data/cache/ so re-running the pipeline never
re-downloads anything. Requests are spaced out to be respectful to hosts.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
MIN_INTERVAL_S = 0.25  # polite delay between *uncached* requests
USER_AGENT = "football-comps-portfolio/0.1 (research project)"

_last_request = 0.0


def _cache_path(url: str, cache_dir: Path) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    name = url.rstrip("/").split("/")[-1][:60] or "index"
    return cache_dir / f"{name}.{digest}.json"


def get_json(url: str, cache_dir: Path = CACHE_DIR, retries: int = 3):
    """Return parsed JSON for `url`, using the on-disk cache when possible."""
    global _last_request
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(url, cache_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    for attempt in range(1, retries + 1):
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            path.write_text(json.dumps(data), encoding="utf-8")
            return data
        except (requests.RequestException, ValueError):
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
