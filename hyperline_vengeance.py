"""Pure data and combat-log parsing helpers for Hyperline's Vengeance List."""

from __future__ import annotations

import re
import time
import uuid
from typing import Iterable


TARGET_TYPES = ("Player", "Guild")
VENGEANCE_REASONS = (
    "Killed me",
    "Camped me",
    "Ganked us",
    "Betrayed the group",
    "Stole the objective / loot",
    "Guild feud",
    "Other",
)

_NAME = r"[A-Za-z0-9][A-Za-z0-9 _.'-]{1,38}"
_PATTERNS = (
    rf"(?:you (?:(?:were|are|have been) )?(?:killed|slain|defeated|downed) by)\s+(?P<name>{_NAME})",
    rf"(?P<name>{_NAME})\s+(?:has )?(?:killed|slew|slain|defeated|downed)\s+you\b",
    rf"(?:killer|attacker)\s*[:=-]\s*(?P<name>{_NAME})",
    rf"(?P<name>{_NAME}?)\s+(?:has\s+)?dealt\s+you\s+[\d,]+\s+(?:[a-z]+\s+)?damage\b",
    rf"(?P<name>{_NAME}?)\s+(?:has\s+)?dealt\s+[\d,]+\s+(?:[a-z]+\s+)?damage\s+to\s+you\b",
    rf"you\s+(?:have\s+)?dealt\s+[\d,]+\s+(?:[a-z]+\s+)?damage\s+to\s+(?P<name>{_NAME})",
    rf"you\s+(?:have\s+)?dealt\s+(?P<name>{_NAME}?)\s+[\d,]+\s+(?:[a-z]+\s+)?damage\b",
)
_TRAILING_NOISE = re.compile(
    r"\s+(?:with|using|for|at|in|near|dealing|and dealt)\b.*$",
    re.IGNORECASE,
)
_GUILD_TAG = re.compile(r"\[(?P<guild>[^\[\]\r\n]{2,32})\]")


def clean_target_name(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n:;,.!\"'")
    return value[:60]


def extract_combat_targets(text: str) -> list[dict[str, str]]:
    """Extract likely killer/player names and optional bracketed guild tags."""
    found: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in str(text or "").splitlines():
        line = re.sub(r"^\s*(?:\[\d{1,2}:\d{2}(?::\d{2})?\]|\d{1,2}:\d{2})\s*", "", raw_line)
        line = re.sub(r"^\s*system\s*:\s*", "", line, flags=re.IGNORECASE)
        guild_match = _GUILD_TAG.search(line)
        guild = clean_target_name(guild_match.group("guild")) if guild_match else ""
        without_tag = _GUILD_TAG.sub(" ", line)
        for pattern in _PATTERNS:
            match = re.search(pattern, without_tag, flags=re.IGNORECASE)
            if not match:
                continue
            name = _TRAILING_NOISE.sub("", match.group("name"))
            name = clean_target_name(name)
            if (
                not name
                or name.lower() in {"you", "your", "unknown", "player"}
                or re.match(r"^(?:a|an|the)\s+", name, flags=re.IGNORECASE)
            ):
                continue
            key = (name.casefold(), guild.casefold())
            if key not in seen:
                seen.add(key)
                found.append({"name": name, "guild": guild})
            break
    return found[:12]


def make_vengeance_entry(
    *,
    name: str,
    target_type: str,
    reason: str,
    details: str = "",
    guild: str = "",
    game: str = "",
    source: str = "manual",
    now: float | None = None,
) -> dict:
    """Build a sanitized, JSON-ready Vengeance List record."""
    clean_name = clean_target_name(name)
    if not clean_name:
        raise ValueError("Target name is required")
    kind = target_type if target_type in TARGET_TYPES else "Player"
    why = reason if reason in VENGEANCE_REASONS else "Other"
    timestamp = float(time.time() if now is None else now)
    return {
        "id": uuid.uuid4().hex[:12],
        "name": clean_name,
        "target_type": kind,
        "guild": clean_target_name(guild),
        "reason": why,
        "details": re.sub(r"\s+", " ", str(details or "")).strip()[:300],
        "game": clean_target_name(game),
        "source": "combat log" if source == "combat log" else "manual",
        "created_at": timestamp,
        "settled": False,
    }


def sanitize_vengeance_entries(rows: Iterable[object], limit: int = 250) -> list[dict]:
    """Validate persisted records without losing compatible older entries."""
    cleaned: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            entry = make_vengeance_entry(
                name=row.get("name", ""),
                target_type=row.get("target_type", "Player"),
                reason=row.get("reason", "Other"),
                details=row.get("details", ""),
                guild=row.get("guild", ""),
                game=row.get("game", ""),
                source=row.get("source", "manual"),
                now=float(row.get("created_at") or time.time()),
            )
        except (TypeError, ValueError):
            continue
        entry["id"] = clean_target_name(row.get("id", "")) or entry["id"]
        entry["settled"] = bool(row.get("settled", False))
        cleaned.append(entry)
    return cleaned[-max(1, int(limit)) :]
