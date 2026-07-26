"""Pure generation-variety helpers for Hyperline."""

from __future__ import annotations

import random
import re
from difflib import SequenceMatcher
from typing import Mapping


VARIETY_OPTIONS = ("Stable", "Varied", "Wild")
VARIETY_DESCRIPTIONS = {
    "Stable": "Steady sampling · still rotates content angles",
    "Varied": "Recommended · new angles, phrasing, and structure",
    "Wild": "Broadest concepts · occasional oddball line",
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

_RECRUIT_HOOKS = (
    "open with a direct invitation",
    "open with a short question",
    "lead with the kind of player being invited",
    "lead with the atmosphere, then reveal the guild",
    "use a confident one-line declaration",
    "use a contrast: what the guild is, then what it is not",
    "begin with the guild tag as a rallying call",
    "use a compact two-beat setup and payoff",
    "sound like a personal invitation from one player",
    "start with a memorable three-to-five-word hook",
)
_RECRUIT_ANGLES = (
    "belonging and finding a regular home",
    "reliable teammates who show up",
    "welcoming new or returning players",
    "experienced players sharing knowledge",
    "steady progress without corporate-ad language",
    "social chemistry and good conversation",
    "low-pressure play with clear teamwork",
    "building a core group from the ground up",
    "quality of people over raw roster size",
    "players tired of anonymous groups",
    "a calm alternative to drama-heavy guilds",
    "ambitious play that still respects real life",
)
_RECRUIT_RHYTHMS = (
    "one crisp sentence",
    "two short clauses divided by a dash",
    "three clipped beats",
    "question followed by a compact answer",
    "short statement followed by a direct CTA",
    "conversational sentence with no slogan",
    "minimalist line with generous breathing room",
    "high-energy line without exclamation spam",
)
_RECRUIT_CTAS = (
    "end with a natural whisper/PST invitation",
    "end with a low-pressure invitation to ask questions",
    "end by asking the right player to reach out",
    "put the apply instruction in the middle, not the end",
    "use the shortest possible call to action",
    "close on the guild vibe instead of the apply method",
)
_RECRUIT_AUDIENCES = (
    "new and returning players",
    "reliable teammates",
    "social players",
    "chill adults",
    "helpful veterans",
    "players looking for a regular crew",
    "team-first players",
    "people tired of random groups",
)
_RECRUIT_VIBES = (
    "chill, team-first",
    "social and drama-light",
    "welcoming and steady",
    "laid-back but organized",
    "friendly with room to improve",
    "real-life friendly",
)
_RECRUIT_OFFLINE_CTAS = (
    "whisper me if that sounds like home",
    "PST if you want details",
    "reach out and see if we click",
    "whisper for an invite or questions",
    "say hi if you want a regular crew",
)

_NOISE_SUBJECTS = (
    "airport carpet",
    "a suspiciously confident pigeon",
    "expired coupons",
    "the last clean spoon",
    "a vending machine",
    "garden gnomes",
    "elevator music",
    "a single wet sock",
    "parking-lot seagulls",
    "the concept of Wednesday",
    "a haunted air fryer",
    "office chairs",
    "tiny hotel soap",
    "a raccoon with a clipboard",
    "automatic doors",
    "a forgotten birthday candle",
    "the moon's customer-service desk",
    "a judgmental houseplant",
    "shopping-cart wheels",
    "a ceremonial sandwich",
    "library dust",
    "a goose in formalwear",
    "the refrigerator light",
    "a deeply political potato",
    "the world's least urgent siren",
    "an emotionally unavailable lamp",
    "a suspicious bowl of cereal",
    "clouds on probation",
    "the left shoe",
    "a moth with career goals",
    "a time-traveling receipt",
    "the emergency backup taco",
    "a unionized swarm of bees",
    "an overqualified frog",
    "the smell of a hardware store",
    "a toaster with stage fright",
    "an unpaid intern ghost",
    "the quietest kazoo",
    "a dramatic paperclip",
    "the neighborhood squirrel council",
)
_NOISE_RELATIONS = (
    "is hiding a completely unnecessary secret",
    "has been promoted beyond its abilities",
    "is quietly responsible for modern society",
    "would fail a basic background check",
    "is preparing a strongly worded email",
    "has misunderstood the assignment with confidence",
    "is one meeting away from becoming folklore",
    "knows exactly what happened in 2007",
    "has developed an unreasonable personal boundary",
    "is running a tiny and ineffective conspiracy",
    "deserves a documentary narrated too seriously",
    "has unionized for reasons nobody can explain",
    "is emotionally carrying the entire building",
    "would absolutely lie under oath",
    "has mistaken itself for a lifestyle brand",
)
_NOISE_FORMS = (
    "an abrupt confession",
    "a fake breaking-news alert",
    "a calm philosophical claim",
    "a question nobody asked",
    "a personal warning with no context",
    "a tiny conspiracy theory",
    "a formal announcement about something trivial",
    "a half-finished realization",
    "an overly specific hot take",
    "a deadpan eyewitness report",
    "a fake proverb",
    "a one-line apology to an inanimate object",
)
_NOISE_TONES = (
    "dead serious",
    "mildly concerned",
    "quietly delighted",
    "bureaucratically formal",
    "sleep deprived",
    "strangely proud",
    "ominously casual",
    "unreasonably certain",
)


def _choose_unseen_plan(
    prefix: str,
    parts: tuple[tuple[str, ...], ...],
    recent_ids: list[str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    recent = set(recent_ids or [])
    rng = random.SystemRandom()
    for _ in range(40):
        chosen = tuple(rng.choice(options) for options in parts)
        plan_id = prefix + "|" + "|".join(chosen)
        if plan_id not in recent:
            return plan_id, chosen
    chosen = tuple(rng.choice(options) for options in parts)
    return prefix + "|" + "|".join(chosen), chosen


def recruit_creative_plan(recent_ids: list[str] | None = None) -> tuple[str, str]:
    """Return one of thousands of constraint-safe recruit content plans."""
    plan_id, chosen = _choose_unseen_plan(
        "recruit",
        (_RECRUIT_HOOKS, _RECRUIT_ANGLES, _RECRUIT_RHYTHMS, _RECRUIT_CTAS),
        recent_ids,
    )
    hook, angle, rhythm, cta = chosen
    return (
        plan_id,
        "MANDATORY CREATIVE PLAN — change the underlying idea, not merely synonyms:\n"
        f"- Hook: {hook}.\n"
        f"- Primary angle: {angle}; use it only when consistent with supplied facts.\n"
        f"- Rhythm: {rhythm}.\n"
        f"- CTA placement: {cta}.\n"
        "- Avoid the default formula 'we are recruiting active players for fun and progression'.",
    )


def procedural_recruit_line(
    guild_tag: str,
    recent_ids: list[str] | None = None,
) -> tuple[str, str]:
    """Create a broad fact-light offline recruit line."""
    plan_id, chosen = _choose_unseen_plan(
        "recruit-offline",
        (_RECRUIT_AUDIENCES, _RECRUIT_VIBES, _RECRUIT_OFFLINE_CTAS, _RECRUIT_RHYTHMS),
        recent_ids,
    )
    audience, vibe, cta, rhythm = chosen
    tag = guild_tag.strip() or "[Guild]"
    templates = (
        "{tag} is looking for {audience} — {vibe}. {cta}.",
        "Want a {vibe} guild? {tag} welcomes {audience}; {cta}.",
        "{audience}: {tag} is {vibe}. {cta}.",
        "{tag} — {vibe}, built for {audience}. {cta}.",
        "Skip the anonymous groups. {tag} wants {audience}; {cta}.",
        "A regular home beats another random party: {tag} is {vibe}. {cta}.",
    )
    rng = random.SystemRandom()
    line = rng.choice(templates).format(
        tag=tag,
        audience=audience,
        vibe=vibe,
        cta=cta,
    )
    if rhythm == "three clipped beats":
        line = f"{tag}. {vibe.capitalize()}. {audience.capitalize()}. {cta.capitalize()}."
    return plan_id, line


def noise_creative_plan(
    level: int,
    recent_ids: list[str] | None = None,
) -> tuple[str, str]:
    """Return a high-cardinality semantic recipe for Noise generation."""
    plan_id, chosen = _choose_unseen_plan(
        f"noise{max(0, min(4, int(level)))}",
        (_NOISE_SUBJECTS, _NOISE_RELATIONS, _NOISE_FORMS, _NOISE_TONES),
        recent_ids,
    )
    subject, relation, form, tone = chosen
    return (
        plan_id,
        "MANDATORY NOISE RECIPE — build the line around this exact new concept:\n"
        f"- Subject: {subject}\n"
        f"- Situation: {relation}\n"
        f"- Sentence form: {form}\n"
        f"- Delivery: {tone}\n"
        "Do not fall back to generic tacos/soup/geese/moon observations.",
    )


def procedural_noise_line(
    level: int,
    recent_ids: list[str] | None = None,
) -> tuple[str, str]:
    """Generate a broad offline Noise line from the same combinatorial space."""
    plan_id, plan = noise_creative_plan(level, recent_ids)
    fields = {}
    for line in plan.splitlines():
        if line.startswith("- ") and ": " in line:
            key, value = line[2:].split(": ", 1)
            fields[key] = value
    subject = fields.get("Subject", "a confused pigeon")
    situation = fields.get("Situation", "has misunderstood the assignment")
    form = fields.get("Sentence form", "a calm philosophical claim")
    tone = fields.get("Delivery", "dead serious")
    templates = (
        "{subject} {situation} and honestly I respect the commitment",
        "breaking: {subject} {situation}",
        "nobody panic but {subject} {situation}",
        "I regret to announce that {subject} {situation}",
        "hot take: {subject} {situation}",
        "just realized {subject} {situation} and now I need a minute",
        "for legal reasons I cannot explain why {subject} {situation}",
        "please remain calm, {subject} {situation}",
        "apparently {subject} {situation}; huge if true",
        "new personal rule: never trust {subject} when it {situation}",
    )
    rng = random.SystemRandom()
    line = rng.choice(templates).format(subject=subject, situation=situation)
    if level >= 4 and rng.random() < 0.25:
        line = f"{subject.upper()} — {situation.upper()}"
    elif level <= 1 and form in {"a calm philosophical claim", "a question nobody asked"}:
        line = f"do you ever think about how {subject} {situation}"
    if tone == "bureaucratically formal" and level >= 2:
        line = f"official notice: {line}"
    return plan_id, line


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


def select_diverse_lines(
    candidates: list[str],
    recent: list[str],
    threshold: float,
) -> list[str]:
    """Keep lines that differ from recent history and from each other."""
    accepted: list[str] = []
    comparison = [line for line in recent if line]
    for line in candidates:
        if not line:
            continue
        _, score = closest_recent_line(line, comparison)
        if score >= threshold:
            continue
        accepted.append(line)
        comparison.append(line)
    return accepted


def retry_threshold(variety: str) -> float:
    return {"Stable": 0.90, "Varied": 0.78, "Wild": 0.70}[normalize_variety(variety)]


def semantic_diversity_threshold(variety: str, family: str) -> float:
    """Stricter thresholds for jobs where paraphrases are especially common."""
    mode = normalize_variety(variety)
    if family == "recruit":
        return {"Stable": 0.82, "Varied": 0.70, "Wild": 0.62}[mode]
    if family == "noise":
        return {"Stable": 0.84, "Varied": 0.72, "Wild": 0.64}[mode]
    return retry_threshold(mode)
