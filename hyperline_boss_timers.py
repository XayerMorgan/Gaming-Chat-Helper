"""Per-game boss timer site configuration helpers."""

from __future__ import annotations

import json
from html.parser import HTMLParser
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


class _EventCardParser(HTMLParser):
    """Extract compact event cards from server-rendered timer pages."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.article_depth: int | None = None
        self.title = ""
        self.parts: list[str] = []
        self.cards: list[dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        values = dict(attrs)
        if tag == "article" and self.article_depth is None:
            self.article_depth = self.depth
            self.title = ""
            self.parts = []
        elif self.article_depth is not None and tag == "h3":
            self.title = str(values.get("title") or "").strip()

    def handle_data(self, data):
        if self.article_depth is not None:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)

    def handle_endtag(self, tag):
        if tag == "article" and self.article_depth == self.depth:
            text = " ".join(self.parts)
            if self.title and ("Next spawn in" in text or "Next session in" in text):
                marker = "Next spawn in" if "Next spawn in" in text else "Next session in"
                tail = text.split(marker, 1)[1].strip()
                bits = tail.split()
                countdown_parts: list[str] = []
                for bit in bits:
                    if any(ch.isdigit() for ch in bit) and bit[-1:].lower() in {"d", "h", "m", "s"}:
                        countdown_parts.append(bit)
                    else:
                        break
                countdown = " ".join(countdown_parts)
                detail = " ".join(bits[len(countdown_parts):]).strip()
                if countdown:
                    self.cards.append(
                        {"name": self.title, "countdown": countdown, "detail": detail}
                    )
            self.article_depth = None
            self.title = ""
            self.parts = []
        self.depth = max(0, self.depth - 1)


def parse_event_cards(html: str) -> list[dict[str, str]]:
    """Return event name/countdown/detail cards from server-rendered HTML."""
    parser = _EventCardParser()
    try:
        parser.feed(str(html or ""))
    except Exception:
        return []
    return parser.cards[:80]
