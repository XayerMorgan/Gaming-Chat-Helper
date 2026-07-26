"""Pure generation-variety helpers for Hyperline."""

from __future__ import annotations

import random
import re
from difflib import SequenceMatcher
from typing import Mapping


VARIETY_OPTIONS = ("Stable", "Varied", "Wild")
VARIETY_DESCRIPTIONS = {
    "Stable": "Consistent wording · lowest surprise",
    "Varied": "Recommended · fresher phrasing and structure",
    "Wild": "Most experimental · occasional oddball line",
}

_CHAT_JOBS = {
    "lfg",
    "recruit",
    "recruit_fresh",
    "recruit_variant",
    "comeback",
    "triple",
    "banter",
    "spice",
    "refine",
    "dadjoke",
}

_STRUCTURES = {
    "lfg": (
        "Lead with the activity, then the player need.",
        "Lead with the player need, then name the activity.",
        "Use a compact question as the hook.",
        "Use clipped gamer shorthand and a direct call to action.",
        "Lead with the vibe, then the concrete activity.",
    ),
    "recruit": (
        "Lead with the guild vibe before the benefits.",
        "Lead with who the guild is looking for.",
        "Open with a short question, then the invitation.",
        "Use a benefit-first hook and a short apply instruction.",
        "Use a minimalist two-beat structure.",
    ),
    "reply": (
        "Use one dry observation.",
        "Answer directly, then add one understated beat.",
        "Use a short question back.",
        "Use clipped, casual phrasing.",
        "Acknowledge their point without repeating their words.",
    ),
    "ambient": (
        "Use a half-thought that sounds typed in the moment.",
        "Use a short observation with no punchline.",
        "Use a casual question.",
        "Use an understated one-liner.",
        "Use an unusual but natural sentence rhythm.",
    ),
}


def normalize_variety(value: str) -> str:
    return value if value in VARIETY_OPTIONS else "Varied"


def apply_variety(
    sampling: Mapping[str, float | int | bool],
    job: str,
    variety: str,
) -> dict:
    """Return sampling adjusted for chat variety; accuracy jobs are untouched."""
    adjusted = dict(sampling)
    if job not in _CHAT_JOBS:
        return adjusted

    mode = normalize_variety(variety)
    if mode == "Stable":
        return adjusted
    if mode == "Varied":
        adjusted["temperature"] = min(
            1.15, max(0.78, float(adjusted.get("temperature", 0.8)) + 0.08)
        )
        adjusted["top_p"] = max(0.93, float(adjusted.get("top_p", 0.9)))
        adjusted["top_k"] = max(48, int(adjusted.get("top_k", 40)))
        adjusted["presence_penalty"] = max(
            0.15, float(adjusted.get("presence_penalty", 0.0))
        )
        adjusted["frequency_penalty"] = max(
            0.18, float(adjusted.get("frequency_penalty", 0.0))
        )
        return adjusted

    adjusted["temperature"] = min(
        1.35, max(0.95, float(adjusted.get("temperature", 0.8)) + 0.22)
    )
    adjusted["top_p"] = max(0.97, float(adjusted.get("top_p", 0.9)))
    adjusted["top_k"] = max(70, int(adjusted.get("top_k", 40)))
    adjusted["min_p"] = min(0.03, float(adjusted.get("min_p", 0.05)))
    adjusted["presence_penalty"] = max(
        0.28, float(adjusted.get("presence_penalty", 0.0))
    )
    adjusted["frequency_penalty"] = max(
        0.30, float(adjusted.get("frequency_penalty", 0.0))
    )
    return adjusted


def random_seed() -> int:
    """Return a fresh positive seed supported by LM Studio chat completions."""
    return random.SystemRandom().randint(1, 2_147_483_647)


def structure_direction(job: str, variety: str) -> str:
    """Choose a lightweight structural nudge without changing user facts."""
    mode = normalize_variety(variety)
    if mode == "Stable" or job not in _CHAT_JOBS:
        return ""
    if job == "lfg":
        family = "lfg"
    elif job in {"recruit", "recruit_fresh", "recruit_variant"}:
        family = "recruit"
    elif job in {"comeback", "triple"}:
        family = "reply"
    else:
        family = "ambient"
    direction = random.SystemRandom().choice(_STRUCTURES[family])
    prefix = "Try this structure" if mode == "Varied" else "Use an unexpected structure"
    return f"{prefix}: {direction} Keep all user facts and constraints unchanged."


def line_similarity(left: str, right: str) -> float:
    """Estimate similarity using both wording order and shared vocabulary."""
    clean_left = " ".join(re.findall(r"[a-z0-9']+", (left or "").lower()))
    clean_right = " ".join(re.findall(r"[a-z0-9']+", (right or "").lower()))
    if not clean_left or not clean_right:
        return 0.0
    sequence = SequenceMatcher(None, clean_left, clean_right).ratio()
    left_words = set(clean_left.split())
    right_words = set(clean_right.split())
    union = left_words | right_words
    overlap = len(left_words & right_words) / len(union) if union else 0.0
    return max(sequence, overlap)


def closest_recent_line(line: str, recent: list[str]) -> tuple[str, float]:
    best_line = ""
    best_score = 0.0
    for candidate in recent:
        score = line_similarity(line, candidate)
        if score > best_score:
            best_line, best_score = candidate, score
    return best_line, best_score


def retry_threshold(variety: str) -> float:
    return {"Stable": 0.90, "Varied": 0.78, "Wild": 0.70}[normalize_variety(variety)]
