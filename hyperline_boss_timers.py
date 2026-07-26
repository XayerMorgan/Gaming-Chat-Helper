"""Per-game boss timer site configuration helpers."""

from __future__ import annotations

import json
from urllib.parse import urlparse


def normalize_timer_url(value: object) -> str:
    """Return a safe HTTP(S) timer URL or an empty string."""
    url = str(value or "").strip()[:500]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def sanitize_boss_timer_sites(value: object) -> dict[str, str]:
    """Normalize a game-to-URL mapping without retaining malformed entries."""
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str] = {}
    for game, raw_url in value.items():
        name = str(game or "").strip()[:100]
        url = normalize_timer_url(raw_url)
        if name and url:
            cleaned[name] = url
    return cleaned


def load_boss_timer_defaults(path: str) -> dict[str, str]:
    """Load shipped defaults; a missing or damaged file safely yields no sites."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, ValueError, TypeError):
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("games"), dict):
        payload = payload["games"]
    return sanitize_boss_timer_sites(payload)


def merge_boss_timer_sites(
    defaults: object,
    overrides: object,
) -> dict[str, str]:
    """Return shipped defaults updated by private per-user configuration."""
    merged = sanitize_boss_timer_sites(defaults)
    merged.update(sanitize_boss_timer_sites(overrides))
    return merged
