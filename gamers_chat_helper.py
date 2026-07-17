"""
Gamer's Chat Helper — local AI companion for MMO chat.
Calm companion UI: one job (right line → under limit → paste), zero clutter.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

import customtkinter as ctk
import pyperclip
import requests

try:
    from PIL import Image, ImageGrab, ImageEnhance, ImageOps
    import base64
    import io

    _HAS_PIL = True
except Exception:
    _HAS_PIL = False
    ImageGrab = None  # type: ignore
    ImageEnhance = None  # type: ignore
    ImageOps = None  # type: ignore
    base64 = None  # type: ignore
    io = None  # type: ignore

try:
    import pytesseract

    _HAS_TESS = True
except Exception:
    pytesseract = None  # type: ignore
    _HAS_TESS = False

try:
    import ctypes

    _USER32 = ctypes.windll.user32
    _HAS_WIN32 = True
except Exception:
    _HAS_WIN32 = False


def _try_find_tesseract() -> Optional[str]:
    """Common Windows install paths for Tesseract OCR."""
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


if _HAS_TESS:
    _tess = _try_find_tesseract()
    if _tess:
        try:
            pytesseract.pytesseract.tesseract_cmd = _tess
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Version / paths
# ---------------------------------------------------------------------------
APP_VERSION = "5.1"

# Intent-driven generator (single surface; not separate tool tabs)
INTENT_OPTIONS = ("lfg", "activity", "reply", "recruit", "noise")
INTENT_LABELS = {
    "lfg": "LFG",
    "activity": "Activity",
    "reply": "Reply",
    "recruit": "Recruit",
    "noise": "Noise",
}
STEAM_PLAYERS_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
# Live header refresh vs history log cadence (seconds)
STEAM_LIVE_INTERVAL_S = 90
STEAM_LOG_INTERVAL_S = 15 * 60  # 15 min — good overnight density; Steam allows much more
STEAM_LOG_INTERVAL_CHOICES = (15, 30, 60)  # minutes
CONFIG_FILE = "chat_helper_config.json"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, CONFIG_FILE)
ASSETS_DIR = os.path.join(APP_DIR, "assets")
GAMES_ASSETS_DIR = os.path.join(ASSETS_DIR, "games")
LAST_OCR_PATH = os.path.join(APP_DIR, "last_chat_capture.png")
STEAM_LOG_PATH = os.path.join(APP_DIR, "steam_players_log.txt")

FULL_GEOMETRY = "900x700"
HUD_GEOMETRY = "480x248"
FULL_MINSIZE = (760, 560)
HUD_MINSIZE = (400, 210)

# Accessibility type scale — fonts grow more than chrome so layout stays balanced.
# "control" = touch targets / button heights; "space" = padding (dampened).
TYPE_PRESETS = {
    "S":   {"font": 0.92, "control": 0.94, "space": 0.96, "label": "Small"},
    "M":   {"font": 1.00, "control": 1.00, "space": 1.00, "label": "Default"},
    "L":   {"font": 1.14, "control": 1.10, "space": 1.06, "label": "Large"},
    "XL":  {"font": 1.28, "control": 1.18, "space": 1.12, "label": "Larger"},
    "XXL": {"font": 1.44, "control": 1.28, "space": 1.18, "label": "Max"},
}
TYPE_SCALE_ORDER = ("S", "M", "L", "XL", "XXL")
_TYPE = dict(TYPE_PRESETS["M"])
_TYPE_KEY = "M"

# ---------------------------------------------------------------------------
# Design system — calm dark companion (2026-style utility UI)
# ---------------------------------------------------------------------------
C = {
    "bg": "#0c0e12",
    "surface": "#141820",
    "elevated": "#1a1f2a",
    "hover": "#242b38",
    "line": "#2a3140",
    "text": "#e8eaed",
    "muted": "#8b93a7",
    "faint": "#5c6578",
    "accent": "#7c6cff",
    "accent_h": "#6a5af0",
    "success": "#22c55e",
    "success_h": "#16a34a",
    "success_dim": "#14532d",
    "warn": "#f59e0b",
    "danger": "#ef4444",
    "danger_dim": "#450a0a",
    "info": "#38bdf8",
    "purple": "#a855f7",
    "purple_h": "#9333ea",
}

FONT_UI = "Segoe UI"
FONT_MONO = "Cascadia Mono"

# ---------------------------------------------------------------------------
# Game DNA
# ---------------------------------------------------------------------------
GAME_PROFILES = {
    "The Quinfall": {
        "limit": 150,
        "short": "Quinfall",
        "accent": "#7c6cff",
        "steam_appid": 2294660,
        "vibe": (
            "The Quinfall is a sandbox open-world MMO. Players grind levels, hit world bosses (WB), "
            "run combat zones (CZ), dungeons, craft/trade, and form guilds. Chat is short, practical, "
            "and a little grindy-humor."
        ),
        "terms": [
            "WB", "world boss", "CZ", "combat zone", "dungeon", "open world",
            "guild", "leveling", "grind", "loot", "sandbox", "party", "LFG",
        ],
        "avoid": (
            "Do NOT mention WoW, Azeroth, mythic+, raids as endgame, fractals, black zones, "
            "or other games' systems. Stay inside Quinfall language."
        ),
        "activities": [
            "General Chat", "World Boss", "Combat Zone", "Dungeon",
            "Leveling / Grind", "Trading", "Guild Chat", "Recruiting",
        ],
        # Concrete LFG destinations (not vague "activity")
        "lfg_default": "Dungeon",
        "lfg_targets": {
            "Dungeon": {
                "must_name": "dungeon",
                "aliases": ["dungeon", "dung", "instance"],
                "brief": "standard dungeon clear / party",
                "never": ["world boss", "WB", "Arachnid Temple", "Cemetery", "CZ", "combat zone"],
                "samples": [
                    "LFG dungeon — chill clear, need 1 more",
                    "Dungeon run? looking for a couple, no stress",
                    "LFM dungeon clear, all welcome",
                ],
            },
            "World Boss": {
                "must_name": "world boss or WB",
                "aliases": ["world boss", "WB", "wb"],
                "brief": "world boss group when spawn/up",
                "never": ["Arachnid Temple", "Cemetery", "dungeon clear", "mythic"],
                "samples": [
                    "LFG WB when up — chill group",
                    "World boss soon? need a few more",
                    "WB group forming, hop in if free",
                ],
            },
            "EXP / Loot Grind": {
                "must_name": "grind, EXP, leveling, or loot farm",
                "aliases": ["grind", "exp", "xp", "level", "loot"],
                "brief": "open-world EXP / loot grind partner or small group",
                "never": ["world boss", "WB", "Arachnid Temple", "Cemetery", "recruiting"],
                "samples": [
                    "Anyone grinding EXP around here? duo ok",
                    "LFG loot grind — chill pace",
                    "Leveling grind, need 1 for pulls",
                ],
            },
            "Arachnid Temple": {
                "must_name": "Arachnid Temple",
                "aliases": ["arachnid temple", "arachnid"],
                "brief": "specifically Arachnid Temple content",
                "never": ["Cemetery", "world boss", "WB", "random dungeon"],
                "samples": [
                    "LFG Arachnid Temple — need a couple",
                    "Arachnid Temple run? chill clear",
                    "LFM Arachnid Temple, whisper me",
                ],
            },
            "Cemetery": {
                "must_name": "Cemetery",
                "aliases": ["cemetery", "cemetary"],
                "brief": "specifically Cemetery content",
                "never": ["Arachnid Temple", "world boss", "WB", "random dungeon"],
                "samples": [
                    "LFG Cemetery — chill group",
                    "Cemetery run, need 1-2 more",
                    "LFM Cemetery clear, all welcome",
                ],
            },
            "Combat Zone": {
                "must_name": "CZ or combat zone",
                "aliases": ["cz", "combat zone"],
                "brief": "combat zone group",
                "never": ["Arachnid Temple", "Cemetery", "world boss spawn"],
                "samples": [
                    "CZ run? need a couple more",
                    "LFG combat zone — chill",
                    "Anyone for CZ, no sweat",
                ],
            },
        },
        "quick": [
            "LFG WB when up — chill group, all welcome",
            "CZ run? need a couple more, no sweat",
            "Anyone leveling around here? duo grind?",
            "Guild looking for chill players — zero drama",
            "Nice pull, that was clean",
            "gg, good fights",
            "WTS mats / craft services — whisper",
            "New here, any tips for early open world?",
            "World boss soon? ping when spawn",
            "Dungeon clear, need 1 more",
            "LFG Arachnid Temple — need a couple",
            "Cemetery run, chill group?",
        ],
        "banter_seeds": [
            "world bosses", "combat zones", "the grind", "loot RNG",
            "open world chaos", "guild life", "dungeon queues", "sandbox freedom",
            "Arachnid Temple", "Cemetery runs",
        ],
    },
    "World of Warcraft": {
        "limit": 255,
        "short": "WoW",
        "accent": "#f1c40f",
        "steam_appid": None,  # not on Steam
        "vibe": (
            "World of Warcraft chat culture: LFG, M+, raids, world quests, professions, "
            "faction banter, expansion memes. Heavy acronym use (LFG, LFM, M+, ilvl)."
        ),
        "terms": [
            "LFG", "LFM", "M+", "mythic+", "raid", "ilvl", "WQs", "mount",
            "transmog", "AH", "whisper", "guild", "boost", "keys",
        ],
        "avoid": "Do not invent Quinfall/Albion-specific systems. Stay WoW-native.",
        "activities": [
            "General / Trade", "Dungeon / M+", "Raid", "World Content",
            "PvP", "Guild Chat", "Recruiting", "AH / Crafting",
        ],
        "lfg_default": "Mythic+",
        "lfg_targets": {
            "Mythic+": {
                "must_name": "M+ or mythic+ or key",
                "aliases": ["m+", "mythic", "key"],
                "brief": "mythic+ key / dungeon",
                "never": ["raid prog", "arena", "Quinfall"],
                "samples": ["LFG M+ key, flexible role", "LFM M+ chill key"],
            },
            "Heroic Dungeon": {
                "must_name": "heroic or dungeon",
                "aliases": ["heroic", "dungeon"],
                "brief": "heroic dungeon",
                "never": ["mythic+", "raid"],
                "samples": ["LFM heroic, chill run", "LFG heroic dungeon"],
            },
            "Raid": {
                "must_name": "raid",
                "aliases": ["raid"],
                "brief": "raid group / slot",
                "never": ["M+ key", "arena"],
                "samples": ["Need 1 heal for raid — PST", "LFG raid, flexible"],
            },
            "World Boss": {
                "must_name": "world boss",
                "aliases": ["world boss", "wb"],
                "brief": "world boss group",
                "never": ["M+", "raid prog"],
                "samples": ["World boss group? hop in", "LFG world boss"],
            },
            "PvP": {
                "must_name": "PvP, arena, or BG",
                "aliases": ["pvp", "arena", "bg", "battleground"],
                "brief": "PvP group",
                "never": ["M+ key", "raid"],
                "samples": ["LFG arena, chill", "Need 1 for BG"],
            },
        },
        "quick": [
            "LFG M+ key, flexible role",
            "LFM heroic, chill run",
            "Need 1 heal for raid prog — PST",
            "WTS crafts / enchants, fast turnaround",
            "World boss group? hop in",
            "gg wp",
            "ilvl check — what are we pulling?",
            "New alt, any leveling tips this expac?",
        ],
        "banter_seeds": [
            "mythic+ keys", "loot drama", "raid night", "alt army",
            "AH prices", "world quests", "tank shortage",
        ],
    },
    "Albion Online": {
        "limit": 150,
        "short": "Albion",
        "accent": "#e67e22",
        "steam_appid": 761890,
        "vibe": (
            "Albion Online is full-loot sandbox PvP. Black zones, ganking, crafting economy, "
            "hideouts, faction warfare. Chat is wary, economical, and risk-aware."
        ),
        "terms": [
            "BZ", "black zone", "RZ", "gank", "set", "IP", "spec", "craft",
            "refine", "hideout", "content", "rat", "loot", "party",
        ],
        "avoid": "No WoW raid/M+ talk. Stay Albion risk/reward language.",
        "activities": [
            "City Chat", "Black Zone", "Roaming", "Crafting / Market",
            "GvG / ZvZ", "Guild Chat", "Recruiting", "Fame Farm",
        ],
        "lfg_default": "Black Zone",
        "lfg_targets": {
            "Black Zone": {
                "must_name": "BZ or black zone",
                "aliases": ["bz", "black zone"],
                "brief": "black zone content group",
                "never": ["safe zone only", "raid"],
                "samples": ["LF BZ content, bring sets you can lose", "BZ group?"],
            },
            "Roaming": {
                "must_name": "roam or roaming",
                "aliases": ["roam", "roaming"],
                "brief": "small-scale roam",
                "never": ["ZvZ mass", "craft order"],
                "samples": ["BZ roam? small scale", "LF roam group"],
            },
            "Fame Farm": {
                "must_name": "fame farm or fame",
                "aliases": ["fame"],
                "brief": "fame farm group",
                "never": ["gank squad callout only"],
                "samples": ["Need 1 more for fame farm", "LFG fame farm"],
            },
            "GvG / ZvZ": {
                "must_name": "GvG or ZvZ",
                "aliases": ["gvg", "zvz"],
                "brief": "large-scale GvG/ZvZ",
                "never": ["solo fame"],
                "samples": ["ZvZ forming — join", "LF GvG call"],
            },
            "Crafting / Market": {
                "must_name": "craft, refine, or market",
                "aliases": ["craft", "refine", "market", "wts", "wtb"],
                "brief": "trade/craft call (not a party LFG)",
                "never": ["BZ gank"],
                "samples": ["WTS refined — fair price", "LF crafter for set"],
            },
        },
        "quick": [
            "LF content group, bring sets you can lose",
            "BZ roam? small scale",
            "WTS refined / crafts — fair price",
            "Rat spotted, eyes open",
            "gg, good gank",
            "Need 1 more for fame farm",
            "Risk check — what's the set?",
        ],
        "banter_seeds": [
            "full loot", "gank squads", "market flips", "black zone stress",
            "craft profit", "rat life",
        ],
    },
    "Guild Wars 2": {
        "limit": 199,
        "short": "GW2",
        "accent": "#1abc9c",
        "steam_appid": 1284210,
        "vibe": (
            "Guild Wars 2 is friendly open-world focused: map completion, metas, fractals, "
            "raids, WvW, mounts. Chat is often wholesome with event-callouts and LFG."
        ),
        "terms": [
            "meta", "tag", "commander", "fractals", "strike", "raid", "WvW",
            "map complete", "mount", "legendary", "LFG", "squad",
        ],
        "avoid": "Avoid other-MMO systems. Use GW2 event/meta language.",
        "activities": [
            "Map / Open World", "Meta Event", "Fractals / Strikes",
            "Raid", "WvW", "Guild Chat", "Recruiting", "Crafting",
        ],
        "lfg_default": "Meta Event",
        "lfg_targets": {
            "Meta Event": {
                "must_name": "meta",
                "aliases": ["meta"],
                "brief": "open-world meta train / squad",
                "never": ["fractal CM only", "WvW"],
                "samples": ["LF squad for meta — tag up", "Meta train, all welcome"],
            },
            "Fractals / Strikes": {
                "must_name": "fractal or strike",
                "aliases": ["fractal", "strike"],
                "brief": "fractals or strikes group",
                "never": ["WvW zerg", "map complete"],
                "samples": ["Fractals train, all welcome", "LF strike group"],
            },
            "Raid": {
                "must_name": "raid",
                "aliases": ["raid"],
                "brief": "raid squad",
                "never": ["fractal daily only"],
                "samples": ["LF raid, experience preferred", "Raid group need 1"],
            },
            "WvW": {
                "must_name": "WvW",
                "aliases": ["wvw"],
                "brief": "WvW zerg / tag",
                "never": ["fractals", "strike CM"],
                "samples": ["WvW zerg forming — join tag", "LF WvW squad"],
            },
            "Map Complete": {
                "must_name": "map complete or map comp",
                "aliases": ["map complete", "map comp"],
                "brief": "map completion buddies",
                "never": ["raid CM"],
                "samples": ["Map complete buddies?", "LF map completion"],
            },
        },
        "quick": [
            "LF squad for meta — tag up",
            "Fractals train, all welcome",
            "Map complete buddies?",
            "Commander needed for train",
            "gg, clean meta",
            "WvW zerg forming — join tag",
            "Strike CM group, experience preferred",
        ],
        "banter_seeds": [
            "meta trains", "mounts", "legendary grind", "fractal dailies",
            "WvW nights", "open world events",
        ],
    },
    "Custom Short": {
        "limit": 100,
        "short": "Short",
        "accent": "#94a3b8",
        "steam_appid": None,
        "vibe": "Generic multiplayer chat with a tight character budget. Ultra short, clear, fun.",
        "terms": ["LFG", "gg", "party", "group", "chill", "loot"],
        "avoid": "No long paragraphs. Prefer punchy one-liners.",
        "activities": ["General", "LFG", "Trade", "Guild", "Banter"],
        "lfg_default": "Group",
        "lfg_targets": {
            "Group": {
                "must_name": "LFG, group, or party",
                "aliases": ["lfg", "group", "party"],
                "brief": "generic group call",
                "never": [],
                "samples": ["LFG chill run", "need 1 more", "anyone up?"],
            },
            "Trade": {
                "must_name": "WTS, WTB, or trade",
                "aliases": ["wts", "wtb", "trade"],
                "brief": "short trade call",
                "never": [],
                "samples": ["WTS mats", "WTB help"],
            },
        },
        "quick": ["LFG chill run", "gg", "need 1 more", "anyone up?", "nice one", "brb"],
        "banter_seeds": ["RNG", "queues", "teammates", "loot"],
    },
}

# How many people / vibe for LFG (shared across games)
LFG_NEED_OPTIONS = [
    "Anyone",
    "Need 1 more",
    "Need a couple",
    "Full group",
    "Chill only",
]
LFG_NEED_HINTS = {
    "Anyone": "open call — all welcome, no strict headcount",
    "Need 1 more": "explicitly need one more player",
    "Need a couple": "need about 2 more",
    "Full group": "forming / looking for a full party",
    "Chill only": "stress free, casual pace — still name the content",
}

DEFAULT_TEMPLATES = [
    "Join The Defiants | Chill Guild | Leveling, Dungeons, WB, CZ | Zero stress | Sister to THE DEFIANT | Direct path to move up",
    "Join The Defiants! Casual PvE, dungeons, & world bosses. Chill vibes. Sister guild to THE DEFIANT. Discord req. Apply in menu!",
    "Looking for a relaxed home? [Defiants] is recruiting casual PvE players. Group up at your own pace. PST for info!",
    "Join The Defiants | Chill Guild | Leveling, Dungeons, WB, CZ | Zero stress | Sister Clan to THE DEFIANT | Direct path to move up",
]

MOOD_OPTIONS = [
    "Dignified", "Polite", "Casual Gamer", "Witty/Sarcastic", "Hype/Energetic",
    "Cryptic/Mysterious", "Overly Helpful", "Guild Recruiter Pro", "Troll/Baiter",
    "Condescending", "Angry/Salty", "Toxic (Playful)",
]

INTENSITY_LABELS = {0: "Chill", 1: "Normal", 2: "Spicy"}

TIPS = [
    "Shorter almost always hits harder in global.",
    "Copy first. Edit in-game only if you must.",
    "Star lines that got replies — that’s your real voice.",
    "HUD + On top = co-pilot mode.",
    "Spicy is optional. Guild-safe wins long term.",
    "If it’s over the limit, it doesn’t leave this window.",
]

HYPE_LINES = [
    "Clean copy. Main character energy.",
    "Clipboard locked. Chat box trembling.",
    "That one slaps.",
    "Paste and pretend you typed it live.",
    "Global is about to eat good.",
    "Speedrunner of socials.",
]

# Per-job sampling — ALWAYS sent in the request body (overrides LM Studio console).
# LM Studio OpenAI-compatible server honors these when present in the JSON body.
JOB_LLM = {
    "lfg": {
        "temperature": 0.65, "top_p": 0.90, "top_k": 40, "min_p": 0.05,
        "repeat_penalty": 1.08, "frequency_penalty": 0.15, "presence_penalty": 0.05,
        "max_tokens": 70, "use_mood": False, "use_terms": True,
    },
    "recruit": {
        "temperature": 0.60, "top_p": 0.88, "top_k": 40, "min_p": 0.05,
        "repeat_penalty": 1.05, "frequency_penalty": 0.10, "presence_penalty": 0.0,
        "max_tokens": 90, "use_mood": False, "use_terms": True,
    },
    "comeback": {
        "temperature": 0.85, "top_p": 0.92, "top_k": 50, "min_p": 0.05,
        "repeat_penalty": 1.10, "frequency_penalty": 0.20, "presence_penalty": 0.10,
        "max_tokens": 70, "use_mood": True, "use_terms": True,
    },
    "triple": {
        "temperature": 0.95, "top_p": 0.94, "top_k": 50, "min_p": 0.04,
        "repeat_penalty": 1.12, "frequency_penalty": 0.25, "presence_penalty": 0.15,
        "max_tokens": 160, "use_mood": True, "use_terms": True,
    },
    "banter": {
        "temperature": 0.90, "top_p": 0.92, "top_k": 50, "min_p": 0.05,
        "repeat_penalty": 1.10, "frequency_penalty": 0.20, "presence_penalty": 0.10,
        "max_tokens": 70, "use_mood": True, "use_terms": True,
    },
    "spice": {
        "temperature": 0.90, "top_p": 0.92, "top_k": 50, "min_p": 0.05,
        "repeat_penalty": 1.12, "frequency_penalty": 0.25, "presence_penalty": 0.12,
        "max_tokens": 70, "use_mood": True, "use_terms": True,
    },
    "refine": {
        "temperature": 0.70, "top_p": 0.90, "top_k": 40, "min_p": 0.05,
        "repeat_penalty": 1.08, "frequency_penalty": 0.15, "presence_penalty": 0.05,
        "max_tokens": 70, "use_mood": True, "use_terms": False,
    },
    "noise": {
        "temperature": 1.35, "top_p": 0.98, "top_k": 80, "min_p": 0.01,
        "repeat_penalty": 1.18, "frequency_penalty": 0.35, "presence_penalty": 0.30,
        "max_tokens": 60, "use_mood": False, "use_terms": False,
    },
    # Screenshot OCR via local VL — low temp = faithful transcription
    "ocr": {
        "temperature": 0.05, "top_p": 0.85, "top_k": 20, "min_p": 0.05,
        "repeat_penalty": 1.02, "frequency_penalty": 0.0, "presence_penalty": 0.0,
        "max_tokens": 280, "use_mood": False, "use_terms": False,
    },
}

# Noise intensity 0=sane … 4=pure mental chaos (NOT game-related).
NOISE_LEVEL_LABELS = {
    0: "Sane",
    1: "Mild",
    2: "Weird",
    3: "Chaos",
    4: "Mental",
}
NOISE_LEVEL_HINTS = {
    0: "Normal human small talk. Mildly offbeat is ok.",
    1: "Slightly odd observations. Still sounds like a person.",
    2: "Absurdist and left-field, but still a full sentence.",
    3: "Strong non-sequitur. Random topics. Unhinged but readable.",
    4: "Pure mental chaos. Brain static. One-word blasts allowed. Maximum non-sequitur.",
}
# Offline packs by minimum intensity (level N can use 0..N, weighted to N)
NOISE_PACKS: dict[int, list[str]] = {
    0: [  # Sane
        "hope everyone is having a decent day",
        "brb grabbing water",
        "chat is quiet in a nice way",
        "anyway carry on",
        "random but hydrate if you can",
        "I forgot what I was going to say",
        "good luck out there people",
        "back",
        "yo",
        "mild take: naps are underrated",
        "just remembered I need groceries later",
        "the weather in my apartment is fine",
        "coffee is doing the heavy lifting today",
        "respectfully I need a snack",
        "silence is loud tonight",
    ],
    1: [  # Mild
        "anyone else thinking about tacos right now or is it just me",
        "I miss when my biggest problem was which cereal",
        "my plants are judging me and honestly fair",
        "who decided socks disappear in laundry and why is it legal",
        "screaming internally in a professional manner",
        "my brain opened 47 tabs and closed the important one",
        "I accidentally waved at a security camera like it was a friend",
        "I would unplug the sun for five more minutes of sleep",
        "library books have been places I will never go",
        "my phone autocorrected my destiny and I am not fighting it",
        "just remembered bread exists and felt hope",
        "I fear balloons more than I fear my taxes",
        "do fish get thirsty or is that a dumb rich people question",
        "cows have best friends and that information ruined me",
        "I named my anxiety Greg and Greg is winning",
    ],
    2: [  # Weird
        "geese are just angry dinosaurs that got promoted",
        "my dentist said I have the bite force of a concerned raccoon",
        "if bread is toast is toast just cooked bread philosophy",
        "sharks don't pay rent and look how confident they are",
        "the moon is just Earth's roommate who never chips in",
        "pineapples have eyes and I don't trust that",
        "hot take: spoons are just tiny shovels for cowards",
        "bees have unionized and I support them",
        "soup is just a hot lake you are allowed to attack",
        "out of pocket thought: what if clouds are just sky laundry",
        "I would lose a debate to a pigeon",
        "penguins propose with rocks which is romantic and also junk",
        "why is it called a building if it is already built",
        "I would unironically defend a sandwich in court",
        "frogs can freeze solid and come back so can your weekend plans",
    ],
    3: [  # Chaos
        "Stalin would have hated my inventory management wait wrong app",
        "Napoleon was short and still conquered Europe stop making excuses",
        "I just remembered I left the oven on in 2014",
        "sorry I just shouted ketchup in my own head",
        "did the Romans have group chats or just yelling",
        "I am emotionally attached to a plastic spatula",
        "Beethoven never had to update drivers count your blessings",
        "Cleopatra lived closer to the iPhone than the pyramids and that still breaks me",
        "I just invented a religion based entirely on napping",
        "the refrigerator light is a tiny sun for my leftover sadness",
        "can someone explain walls to me like I am five and also a bird",
        "if I disappear blame the raccoons they know too much",
        "the wifi password of the universe is probably password123",
        "free idea: replace all meetings with interpretive dance",
        "I am one mild inconvenience away from becoming a folk legend",
        "the void texted first this time",
        "blurt: I would rename Tuesday to Soupday",
        "I tried to adult and my brain served me a cartoon squirrel",
        "I am the main character of a grocery list",
        "someone feed the algorithm tacos and maybe it will be kind",
    ],
    4: [  # Pure mental chaos
        "TACOS",
        "ketchup",
        "the floor is lava but emotionally",
        "GREG",
        "brain static please stand by",
        "SOUPDAY",
        "I would fight a goose for one perfect french fry",
        "bring back floppy disks so I can lose save files with dignity",
        "my left knee just predicted weather I did not ask for",
        "someone once paid for premium on a rock and I respect the hustle",
        "my shadow has better posture than I do",
        "if time is money I am paying in monopoly bills",
        "the dual of a chair is still a chair and I will die on that hill",
        "history class never prepared me for this snack cabinet",
        "if I vanish check under the couch with the other lost things",
        "this message was brought to you by accidental brain static",
        "I respect moths for their commitment to the light even when the light is a mistake",
        "my attention span left to get milk in 2009",
        "I fear success almost as much as I fear raw onions",
        "I keep typing messages to the void and the void is on read",
        "why do we park in driveways and drive on parkways who did this",
        "my soul left and sent a postcard from the snack aisle",
        "unprompted dinosaur tax",
        "BREAD",
        "the algorithm owes me a taco",
    ],
}


# ---------------------------------------------------------------------------
# Tiny design helpers + accessibility type scale
# ---------------------------------------------------------------------------
def set_type_scale(key: str) -> str:
    """Apply a named type preset globally. Returns the resolved key."""
    global _TYPE, _TYPE_KEY
    key = key if key in TYPE_PRESETS else "M"
    _TYPE_KEY = key
    _TYPE = dict(TYPE_PRESETS[key])
    return key


def type_scale_key() -> str:
    return _TYPE_KEY


def f_ui(size=13, weight="normal"):
    scaled = max(9, int(round(size * _TYPE["font"])))
    return ctk.CTkFont(family=FONT_UI, size=scaled, weight=weight)


def f_mono(size=13, weight="normal"):
    scaled = max(9, int(round(size * _TYPE["font"])))
    return ctk.CTkFont(family=FONT_MONO, size=scaled, weight=weight)


def sz(n: int | float) -> int:
    """Scale control heights / icon boxes (touch targets)."""
    return max(16, int(round(float(n) * _TYPE["control"])))


def pad(n: int | float) -> int:
    """Scale padding / gaps more gently than type for visual balance."""
    return max(2, int(round(float(n) * _TYPE["space"])))


def scaled_full_minsize() -> tuple[int, int]:
    f = _TYPE["font"]
    return (
        max(FULL_MINSIZE[0], int(round(FULL_MINSIZE[0] * (0.92 + 0.18 * f)))),
        max(FULL_MINSIZE[1], int(round(FULL_MINSIZE[1] * (0.92 + 0.22 * f)))),
    )


def scaled_hud_minsize() -> tuple[int, int]:
    f = _TYPE["font"]
    return (
        max(HUD_MINSIZE[0], int(round(HUD_MINSIZE[0] * (0.94 + 0.16 * f)))),
        max(HUD_MINSIZE[1], int(round(HUD_MINSIZE[1] * (0.94 + 0.20 * f)))),
    )


def game_slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("/", "_")


class AssetBank:
    """Load brand + game images from ./assets with graceful fallbacks."""

    def __init__(self, assets_dir: str = ASSETS_DIR):
        self.assets_dir = assets_dir
        self.games_dir = os.path.join(assets_dir, "games")
        self._cache: dict[str, object] = {}
        self._tk_icon = None

    def path(self, *parts: str) -> str:
        return os.path.join(self.assets_dir, *parts)

    def exists(self, *parts: str) -> bool:
        return os.path.isfile(self.path(*parts))

    def _open(self, path: str) -> Optional["Image.Image"]:
        if not _HAS_PIL or not path or not os.path.isfile(path):
            return None
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            return None

    def ctk_image(self, key: str, path: str, size: tuple[int, int]) -> Optional[ctk.CTkImage]:
        cache_key = f"{key}:{size[0]}x{size[1]}:{path}"
        if cache_key in self._cache:
            return self._cache[cache_key]  # type: ignore
        im = self._open(path)
        if im is None:
            return None
        try:
            img = ctk.CTkImage(light_image=im, dark_image=im, size=size)
            self._cache[cache_key] = img
            return img
        except Exception:
            return None

    def logo(self, size=(28, 28)) -> Optional[ctk.CTkImage]:
        for name in ("logo_sm.png", "logo.png", "logo.jpg"):
            p = self.path(name)
            if os.path.isfile(p):
                return self.ctk_image(f"logo-{name}", p, size)
        return None

    def banner(self, size=(860, 96)) -> Optional[ctk.CTkImage]:
        for name in ("banner.png", "banner.jpg"):
            p = self.path(name)
            if os.path.isfile(p):
                return self.ctk_image(f"banner-{name}", p, size)
        return None

    def game_badge(self, game_name: str, size=(28, 28)) -> Optional[ctk.CTkImage]:
        slug = game_slug(game_name)
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = os.path.join(self.games_dir, slug + ext)
            if os.path.isfile(p):
                return self.ctk_image(f"game-{slug}", p, size)
        return None

    def apply_window_icon(self, root: ctk.CTk):
        """Set taskbar / window icon from assets/app.ico or logo.png."""
        ico = self.path("app.ico")
        if os.path.isfile(ico):
            try:
                root.iconbitmap(ico)
                return
            except Exception:
                pass
        # PNG fallback via iconphoto
        for name in ("logo.png", "logo_sm.png"):
            p = self.path(name)
            im = self._open(p)
            if im is None:
                continue
            try:
                import tkinter as _tk

                im = im.resize((32, 32), Image.Resampling.LANCZOS)
                self._tk_icon = _tk.PhotoImage(master=root, data=_png_bytes(im))
                # PhotoImage prefers gif/ppm; use ImageTk if available
            except Exception:
                pass
            try:
                from PIL import ImageTk

                im32 = Image.open(p).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)
                self._tk_icon = ImageTk.PhotoImage(im32, master=root)
                root.iconphoto(True, self._tk_icon)
                return
            except Exception:
                continue


def _png_bytes(im: "Image.Image") -> bytes:
    import io

    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class GamersChatHelper:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title(f"Chat Helper  ·  v{APP_VERSION}")
        self.root.configure(fg_color=C["bg"])

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.load_settings()
        set_type_scale(self.saved_font_scale)
        self.font_scale_key = type_scale_key()
        self.assets = AssetBank(ASSETS_DIR)
        self.show_banner = bool(getattr(self, "saved_show_banner", True))
        self._ui_ready = False
        self._llm_pulse_gen = 0
        self._steam_pulse_gen = 0
        self._steam_player_count: Optional[int] = None
        self._steam_last_log_ts: dict[int, float] = {}  # appid -> unix when last written
        self._steam_history: list[tuple[float, int]] = []  # (unix, players) for current game chart
        self.steam_log_enabled = tk.BooleanVar(value=bool(getattr(self, "saved_steam_log_enabled", True)))
        self.steam_log_minutes = tk.IntVar(value=int(getattr(self, "saved_steam_log_minutes", 15)))

        self.game_var = tk.StringVar(value=self.default_game)
        self.mood_var = tk.StringVar(value=self.saved_mood)
        self.activity_var = tk.StringVar(value=self.saved_activity)
        self.intensity_var = tk.IntVar(value=self.saved_intensity)
        self.noise_level_var = tk.IntVar(value=int(getattr(self, "saved_noise_level", 3)))
        self.always_on_top = tk.BooleanVar(value=self.saved_on_top)
        self.auto_copy = tk.BooleanVar(value=self.saved_auto_copy)
        self.hud_mode = tk.BooleanVar(value=self.saved_hud)
        self.font_scale_var = tk.StringVar(value=self.font_scale_key)
        self.lfg_defaults: dict[str, str] = dict(self.saved_lfg_defaults)
        self.lfg_target_var = tk.StringVar(
            value=self._resolve_lfg_target(self.default_game, self.saved_lfg_target)
        )
        self.lfg_need_var = tk.StringVar(
            value=self.saved_lfg_need if self.saved_lfg_need in LFG_NEED_OPTIONS else "Anyone"
        )
        self.chat_region: Optional[dict] = dict(self.saved_chat_region) if self.saved_chat_region else None
        self.ocr_prefer_last = tk.BooleanVar(value=bool(self.saved_ocr_prefer_last))
        self._last_ocr_text = ""
        self._ocr_busy = False
        intent0 = getattr(self, "saved_generator_intent", "lfg")
        if intent0 not in INTENT_OPTIONS:
            intent0 = "lfg"
        self.generator_intent = tk.StringVar(value=intent0)
        self.show_advanced = tk.BooleanVar(value=bool(getattr(self, "saved_show_advanced", False)))
        self.onboarding_done = bool(getattr(self, "saved_onboarding_done", False))

        self.history: list[str] = list(self.saved_history)
        self.favorites: list[str] = list(self.saved_favorites)
        self.copy_counts: dict[str, int] = dict(self.saved_copy_counts)
        self.hidden_lines: dict[str, list[str]] = dict(self.saved_hidden_lines)

        self._busy = False
        self._last_variants: list[str] = []
        self._last_gen_mode = "banter"
        self._last_good_line = self.history[-1] if self.history else ""
        self._toast_job = None
        self._full_geometry = self.saved_geometry or FULL_GEOMETRY
        self._hud_geometry = self.saved_hud_geometry or HUD_GEOMETRY
        self._app_hwnd = None

        # Session fun stats (not persisted)
        self.session_copies = 0
        self.session_gens = 0
        self.session_streak = 0
        self.session_best_streak = 0
        self.session_started = time.time()
        self._selected_quick: Optional[str] = None

        self.create_ui()
        self.assets.apply_window_icon(self.root)
        self.apply_startup_geometry()
        self.apply_on_top()
        self.on_game_changed(self.game_var.get(), persist=False)
        self.sync_activity_if_needed()
        self.sync_lfg_target_if_needed()
        self.pulse_llm_status()
        self.pulse_steam_players()
        self.refresh_history_ui()
        self.refresh_hud_line()
        self.update_session_chip()
        self._tip_rotate()
        self._ui_ready = True

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Configure>", self._on_configure)
        self.root.bind("<Escape>", self._on_escape)
        self.root.bind("<Control-plus>", lambda e: self.nudge_type_scale(1))
        self.root.bind("<Control-equal>", lambda e: self.nudge_type_scale(1))
        self.root.bind("<Control-minus>", lambda e: self.nudge_type_scale(-1))
        self.root.bind("<Control-KP_Add>", lambda e: self.nudge_type_scale(1))
        self.root.bind("<Control-KP_Subtract>", lambda e: self.nudge_type_scale(-1))
        self.root.bind("<Control-0>", lambda e: self.apply_type_scale("M"))
        self.root.after(200, self._cache_hwnd)

    # =====================================================================
    # Config
    # =====================================================================
    def load_settings(self):
        self.game_limits = {g: p["limit"] for g, p in GAME_PROFILES.items()}
        self.templates = list(DEFAULT_TEMPLATES)
        self.api_url = "http://localhost:1234/v1/chat/completions"
        self.default_game = "The Quinfall"
        self.custom_quick: dict[str, list[str]] = {}
        self.saved_favorites: list[str] = []
        self.saved_history: list[str] = []
        self.saved_copy_counts: dict[str, int] = {}
        self.saved_hidden_lines: dict[str, list[str]] = {}
        self.saved_geometry = FULL_GEOMETRY
        self.saved_hud_geometry = HUD_GEOMETRY
        self.saved_hud = False
        self.saved_on_top = True
        self.saved_auto_copy = True
        self.saved_mood = "Casual Gamer"
        self.saved_activity = "General Chat"
        self.saved_intensity = 1
        self.saved_noise_level = 3
        self.saved_show_banner = True
        self.saved_font_scale = "M"
        self.saved_steam_log_enabled = True
        self.saved_steam_log_minutes = 15
        self.saved_lfg_target = "Dungeon"
        self.saved_lfg_need = "Anyone"
        self.saved_lfg_defaults: dict[str, str] = {}
        self.saved_chat_region: Optional[dict] = None
        self.saved_ocr_prefer_last = True
        self.saved_generator_intent = "lfg"
        self.saved_show_advanced = False
        self.saved_onboarding_done = False

        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.game_limits.update(data.get("limits", {}))
                self.templates = data.get("templates", self.templates) or list(DEFAULT_TEMPLATES)
                self.api_url = data.get("api_url", self.api_url)
                self.default_game = data.get("default_game", self.default_game)
                self.custom_quick = data.get("custom_quick", {})
                self.saved_favorites = data.get("favorites", [])
                self.saved_history = data.get("history", [])
                self.saved_copy_counts = data.get("copy_counts", {})
                self.saved_hidden_lines = data.get("hidden_lines", {})
                self.saved_geometry = data.get("geometry", FULL_GEOMETRY)
                self.saved_hud_geometry = data.get("hud_geometry", HUD_GEOMETRY)
                self.saved_hud = bool(data.get("hud_mode", False))
                self.saved_on_top = bool(data.get("always_on_top", True))
                self.saved_auto_copy = bool(data.get("auto_copy", True))
                self.saved_mood = data.get("mood", self.saved_mood)
                self.saved_activity = data.get("activity", self.saved_activity)
                self.saved_intensity = int(data.get("intensity", 1))
                try:
                    nl = int(data.get("noise_level", 3))
                except Exception:
                    nl = 3
                self.saved_noise_level = max(0, min(4, nl))
                self.saved_show_banner = bool(data.get("show_banner", True))
                fs = data.get("font_scale", "M")
                self.saved_font_scale = fs if fs in TYPE_PRESETS else "M"
                self.saved_lfg_target = data.get("lfg_target", self.saved_lfg_target)
                self.saved_lfg_need = data.get("lfg_need", self.saved_lfg_need)
                self.saved_lfg_defaults = data.get("lfg_defaults", {}) or {}
                cr = data.get("chat_region")
                if isinstance(cr, dict) and all(k in cr for k in ("left", "top", "right", "bottom")):
                    self.saved_chat_region = {
                        "left": int(cr["left"]),
                        "top": int(cr["top"]),
                        "right": int(cr["right"]),
                        "bottom": int(cr["bottom"]),
                    }
                self.saved_ocr_prefer_last = bool(data.get("ocr_prefer_last_line", True))
                gi = data.get("generator_intent", "lfg")
                self.saved_generator_intent = gi if gi in INTENT_OPTIONS else "lfg"
                self.saved_show_advanced = bool(data.get("show_advanced", False))
                self.saved_onboarding_done = bool(data.get("onboarding_done", False))
                self.saved_steam_log_enabled = bool(data.get("steam_log_enabled", True))
                try:
                    sm = int(data.get("steam_log_minutes", 15))
                except Exception:
                    sm = 15
                if sm not in STEAM_LOG_INTERVAL_CHOICES:
                    sm = 15
                self.saved_steam_log_minutes = sm
                if self.default_game not in GAME_PROFILES:
                    self.default_game = "The Quinfall"
            except Exception:
                pass

    def save_settings(self):
        try:
            geo = self.root.geometry()
            if self.hud_mode.get():
                self._hud_geometry = geo
            else:
                self._full_geometry = geo
        except Exception:
            pass

        data = {
            "limits": self.game_limits,
            "templates": self.templates,
            "api_url": self.api_url,
            "default_game": self.game_var.get() if hasattr(self, "game_var") else self.default_game,
            "custom_quick": self.custom_quick,
            "favorites": getattr(self, "favorites", self.saved_favorites),
            "history": (getattr(self, "history", self.saved_history) or [])[-20:],
            "copy_counts": getattr(self, "copy_counts", self.saved_copy_counts),
            "hidden_lines": getattr(self, "hidden_lines", self.saved_hidden_lines),
            "geometry": getattr(self, "_full_geometry", FULL_GEOMETRY),
            "hud_geometry": getattr(self, "_hud_geometry", HUD_GEOMETRY),
            "hud_mode": bool(self.hud_mode.get()) if hasattr(self, "hud_mode") else False,
            "always_on_top": bool(self.always_on_top.get()) if hasattr(self, "always_on_top") else True,
            "auto_copy": bool(self.auto_copy.get()) if hasattr(self, "auto_copy") else True,
            "mood": self.mood_var.get() if hasattr(self, "mood_var") else self.saved_mood,
            "activity": self.activity_var.get() if hasattr(self, "activity_var") else self.saved_activity,
            "intensity": int(self.intensity_var.get()) if hasattr(self, "intensity_var") else 1,
            "noise_level": int(
                self.noise_level_var.get()
                if hasattr(self, "noise_level_var")
                else getattr(self, "saved_noise_level", 3)
            ),
            "show_banner": bool(getattr(self, "show_banner", True)),
            "font_scale": getattr(self, "font_scale_key", type_scale_key()),
            "lfg_target": self.lfg_target_var.get() if hasattr(self, "lfg_target_var") else self.saved_lfg_target,
            "lfg_need": self.lfg_need_var.get() if hasattr(self, "lfg_need_var") else self.saved_lfg_need,
            "lfg_defaults": getattr(self, "lfg_defaults", self.saved_lfg_defaults),
            "chat_region": getattr(self, "chat_region", self.saved_chat_region),
            "ocr_prefer_last_line": bool(
                self.ocr_prefer_last.get()
                if hasattr(self, "ocr_prefer_last")
                else getattr(self, "saved_ocr_prefer_last", True)
            ),
            "generator_intent": (
                self.generator_intent.get()
                if hasattr(self, "generator_intent")
                else getattr(self, "saved_generator_intent", "lfg")
            ),
            "show_advanced": bool(
                self.show_advanced.get()
                if hasattr(self, "show_advanced")
                else getattr(self, "saved_show_advanced", False)
            ),
            "onboarding_done": bool(getattr(self, "onboarding_done", False)),
            "steam_log_enabled": bool(
                self.steam_log_enabled.get()
                if hasattr(self, "steam_log_enabled")
                else getattr(self, "saved_steam_log_enabled", True)
            ),
            "steam_log_minutes": int(
                self.steam_log_minutes.get()
                if hasattr(self, "steam_log_minutes")
                else getattr(self, "saved_steam_log_minutes", 15)
            ),
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def on_close(self):
        self.save_settings()
        self.root.destroy()

    def _on_configure(self, event=None):
        if event and event.widget is not self.root:
            return
        try:
            geo = self.root.geometry()
            if self.hud_mode.get():
                self._hud_geometry = geo
            else:
                self._full_geometry = geo
        except Exception:
            pass

    def _cache_hwnd(self):
        if not _HAS_WIN32:
            return
        try:
            hwnd = self.root.winfo_id()
            parent = _USER32.GetParent(hwnd)
            while parent:
                hwnd = parent
                parent = _USER32.GetParent(hwnd)
            self._app_hwnd = int(hwnd)
        except Exception:
            self._app_hwnd = None

    def profile(self) -> dict:
        return GAME_PROFILES.get(self.game_var.get(), GAME_PROFILES["The Quinfall"])

    def limit(self) -> int:
        game = self.game_var.get()
        return int(self.game_limits.get(game, self.profile()["limit"]))

    def accent(self) -> str:
        return self.profile().get("accent", C["accent"])

    def sync_activity_if_needed(self):
        acts = self.profile()["activities"]
        if self.activity_var.get() not in acts:
            self.activity_var.set(acts[0])

    def lfg_target_names(self, game: Optional[str] = None) -> list[str]:
        prof = GAME_PROFILES.get(game or self.game_var.get(), {})
        targets = prof.get("lfg_targets") or {}
        return list(targets.keys()) if targets else ["Group"]

    def lfg_target_info(self, target: Optional[str] = None, game: Optional[str] = None) -> dict:
        game = game or (self.game_var.get() if hasattr(self, "game_var") else "The Quinfall")
        prof = GAME_PROFILES.get(game, {})
        targets = prof.get("lfg_targets") or {}
        name = target or (self.lfg_target_var.get() if hasattr(self, "lfg_target_var") else "")
        if name not in targets:
            name = prof.get("lfg_default") or (next(iter(targets), "Group"))
        info = dict(targets.get(name, {
            "must_name": name,
            "aliases": [name.lower()],
            "brief": name,
            "never": [],
            "samples": [f"LFG {name}"],
        }))
        info["label"] = name
        return info

    def _resolve_lfg_target(self, game: str, preferred: Optional[str] = None) -> str:
        names = self.lfg_target_names(game) if hasattr(self, "lfg_target_names") else list(
            (GAME_PROFILES.get(game) or {}).get("lfg_targets", {}).keys()
        )
        if not names:
            return "Group"
        defaults = getattr(self, "lfg_defaults", None) or getattr(self, "saved_lfg_defaults", {}) or {}
        for cand in (preferred, defaults.get(game), (GAME_PROFILES.get(game) or {}).get("lfg_default")):
            if cand and cand in names:
                return cand
        return names[0]

    def sync_lfg_target_if_needed(self):
        if not hasattr(self, "lfg_target_var"):
            return
        game = self.game_var.get()
        names = self.lfg_target_names(game)
        cur = self.lfg_target_var.get()
        if cur not in names:
            self.lfg_target_var.set(self._resolve_lfg_target(game))
        if hasattr(self, "lfg_target_menu"):
            self.lfg_target_menu.configure(values=names)
        if hasattr(self, "lfg_need_var") and self.lfg_need_var.get() not in LFG_NEED_OPTIONS:
            self.lfg_need_var.set("Anyone")

    def on_lfg_target_changed(self, choice: str = None):
        game = self.game_var.get()
        target = choice or self.lfg_target_var.get()
        names = self.lfg_target_names(game)
        if target not in names:
            target = self._resolve_lfg_target(game)
            self.lfg_target_var.set(target)
        # Remember per-game default
        if not hasattr(self, "lfg_defaults"):
            self.lfg_defaults = {}
        self.lfg_defaults[game] = target
        self.save_settings()

    def on_lfg_need_changed(self, _choice: str = None):
        self.save_settings()

    # =====================================================================
    # Focus guard
    # =====================================================================
    def _foreground_hwnd(self):
        if not _HAS_WIN32:
            return None
        try:
            return int(_USER32.GetForegroundWindow())
        except Exception:
            return None

    def _restore_foreground(self, hwnd):
        if not _HAS_WIN32 or not hwnd or not self._app_hwnd:
            return
        try:
            current = self._foreground_hwnd()
            if current == self._app_hwnd:
                _USER32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def ui_safe(self, fn: Callable):
        prev = self._foreground_hwnd()
        try:
            fn()
        finally:
            self.root.after(10, lambda: self._restore_foreground(prev))
            self.root.after(50, lambda: self._restore_foreground(prev))

    # =====================================================================
    # Shell UI
    # =====================================================================
    def create_ui(self):
        self.build_header()

        self.toast = ctk.CTkLabel(
            self.root, text="", font=f_ui(12, "bold"),
            fg_color=C["success_dim"], text_color=C["success"],
            corner_radius=10, height=0,
        )

        self.main_body = ctk.CTkFrame(self.root, fg_color="transparent")
        self.main_body.pack(fill="both", expand=True, padx=pad(14), pady=(pad(6), 0))

        self.tabview = ctk.CTkTabview(
            self.main_body,
            fg_color=C["surface"],
            segmented_button_fg_color=C["elevated"],
            segmented_button_selected_color=C["accent"],
            segmented_button_selected_hover_color=C["accent_h"],
            segmented_button_unselected_color=C["elevated"],
            segmented_button_unselected_hover_color=C["hover"],
            text_color=C["text"],
            corner_radius=14,
            border_width=0,
        )
        self.tabview.pack(fill="both", expand=True)
        try:
            self.tabview._segmented_button.configure(font=f_ui(12, "bold"), height=sz(32))
        except Exception:
            pass

        for name in ("Chat Generator", "Library", "Setup"):
            self.tabview.add(name)

        self.build_generator_tab()
        self.build_library_tab()
        self.build_setup_tab()

        self.hud_body = ctk.CTkFrame(self.root, fg_color=C["surface"], corner_radius=14)
        self.build_hud_panel()

        # Sticky Copy bar + status footer (Copy always above session tips)
        self.build_sticky_copy_bar()
        self.build_footer()

        if self.hud_mode.get():
            self._apply_hud_visibility(True)
        else:
            self._show_sticky_copy_bar(True)

    # =====================================================================
    # Accessibility — type scale (managed, beauty-preserving)
    # =====================================================================
    def apply_type_scale(self, key: str, rebuild: bool = True):
        key = set_type_scale(key)
        self.font_scale_key = key
        if hasattr(self, "font_scale_var"):
            self.font_scale_var.set(key)
        self.save_settings()
        if rebuild and getattr(self, "_ui_ready", False):
            self.rebuild_shell()
            label = TYPE_PRESETS[key]["label"]
            self.show_toast(f"Type · {label}", kind="info")
            self.set_status(f"Type size · {label}  (Ctrl+/Ctrl− · Ctrl+0 default)")

    def nudge_type_scale(self, delta: int):
        order = list(TYPE_SCALE_ORDER)
        try:
            idx = order.index(self.font_scale_key)
        except ValueError:
            idx = order.index("M")
        idx = max(0, min(len(order) - 1, idx + delta))
        self.apply_type_scale(order[idx])
        return "break"

    def on_type_scale_menu(self, choice: str):
        for k, p in TYPE_PRESETS.items():
            if p["label"] == choice or k == choice:
                self.apply_type_scale(k)
                return
        self.apply_type_scale("M")

    def rebuild_shell(self):
        """Recreate chrome at the active type scale without losing app state."""
        geo = self.root.geometry()
        tab = None
        try:
            tab = self.tabview.get()
        except Exception:
            pass

        self._ui_ready = False
        self._llm_pulse_gen += 1
        self._steam_pulse_gen += 1  # cancel in-flight Steam pollers

        for child in self.root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        self.create_ui()
        self.assets.apply_window_icon(self.root)
        try:
            self.root.geometry(geo)
        except Exception:
            pass
        self._apply_minsize_for_mode()
        self.apply_on_top()
        self.on_game_changed(self.game_var.get(), persist=False)
        self.sync_activity_if_needed()
        self.sync_lfg_target_if_needed()
        self.pulse_llm_status()
        self.pulse_steam_players()
        self.refresh_history_ui()
        self.refresh_hud_line()
        self.update_session_chip()
        if tab:
            try:
                self.tabview.set(tab)
            except Exception:
                pass
        self._ui_ready = True
        self.root.after(100, self._cache_hwnd)

    def _apply_minsize_for_mode(self):
        if self.hud_mode.get():
            self.root.minsize(*scaled_hud_minsize())
        else:
            self.root.minsize(*scaled_full_minsize())

    def build_header(self):
        self.header = ctk.CTkFrame(self.root, fg_color=C["surface"], corner_radius=14, height=sz(56))
        self.header.pack(fill="x", padx=pad(14), pady=(pad(14), pad(4)))
        self.header.pack_propagate(False)

        left = ctk.CTkFrame(self.header, fg_color="transparent")
        left.pack(side="left", fill="y", padx=pad(14), pady=pad(10))

        logo_s = sz(28)
        self.logo_label = ctk.CTkLabel(left, text="", width=logo_s, height=logo_s)
        logo_img = self.assets.logo(size=(logo_s, logo_s))
        if logo_img:
            self.logo_label.configure(image=logo_img, text="")
            self._logo_img = logo_img  # keep ref
        else:
            self.logo_label.configure(text="◎", font=f_ui(18, "bold"), text_color=C["accent"])
        self.logo_label.pack(side="left", padx=(0, pad(8)))

        ctk.CTkLabel(left, text="Chat Helper", font=f_ui(16, "bold"), text_color=C["text"]).pack(
            side="left"
        )

        icon_s = sz(26)
        self.game_icon_label = ctk.CTkLabel(left, text="", width=icon_s, height=icon_s)
        self.game_icon_label.pack(side="left", padx=(pad(12), pad(4)))

        self.game_pill = ctk.CTkLabel(
            left, text="Quinfall", font=f_ui(11, "bold"),
            text_color=C["text"], fg_color=C["elevated"], corner_radius=8,
            padx=pad(10), pady=pad(4),
        )
        self.game_pill.pack(side="left", padx=(2, pad(6)))

        self.game_combo = ctk.CTkOptionMenu(
            left, variable=self.game_var, values=list(GAME_PROFILES.keys()),
            command=self.on_game_changed, width=sz(148), height=sz(28),
            fg_color=C["elevated"], button_color=C["hover"], button_hover_color=C["line"],
            dropdown_fg_color=C["elevated"], font=f_ui(12),
        )
        self.game_combo.pack(side="left", padx=pad(4))

        self.limit_badge = ctk.CTkLabel(
            left, text="150", font=f_ui(11, "bold"), text_color=C["success"],
            fg_color=C["success_dim"], corner_radius=8, padx=pad(8), pady=pad(3),
        )
        self.limit_badge.pack(side="left", padx=pad(6))

        right = ctk.CTkFrame(self.header, fg_color="transparent")
        right.pack(side="right", padx=pad(12), pady=pad(10))

        # Type scale control — managed A− / size / A+
        type_box = ctk.CTkFrame(right, fg_color=C["elevated"], corner_radius=10)
        type_box.pack(side="left", padx=(0, pad(10)))
        ctk.CTkButton(
            type_box, text="A−", width=sz(34), height=sz(28), font=f_ui(12, "bold"),
            fg_color="transparent", hover_color=C["hover"], text_color=C["muted"],
            command=lambda: self.nudge_type_scale(-1),
        ).pack(side="left", padx=(pad(2), 0), pady=pad(2))
        self.type_scale_label = ctk.CTkLabel(
            type_box, text=TYPE_PRESETS[self.font_scale_key]["label"],
            width=sz(64), font=f_ui(11, "bold"), text_color=C["text"],
        )
        self.type_scale_label.pack(side="left", padx=pad(2))
        ctk.CTkButton(
            type_box, text="A+", width=sz(34), height=sz(28), font=f_ui(13, "bold"),
            fg_color="transparent", hover_color=C["hover"], text_color=C["text"],
            command=lambda: self.nudge_type_scale(1),
        ).pack(side="left", padx=(0, pad(2)), pady=pad(2))

        self.steam_dot = ctk.CTkLabel(
            right, text="Steam · …", font=f_ui(11, "bold"), text_color=C["faint"],
            cursor="hand2",
        )
        self.steam_dot.pack(side="left", padx=(0, pad(10)))
        self.steam_dot.bind("<Button-1>", lambda e: self.open_steam_trends())

        self.llm_dot = ctk.CTkLabel(
            right, text="● offline", font=f_ui(11, "bold"), text_color=C["danger"],
        )
        self.llm_dot.pack(side="left", padx=(0, pad(10)))

        self.copy_badge = ctk.CTkLabel(
            right, text="ready", font=f_ui(11), text_color=C["muted"],
        )
        self.copy_badge.pack(side="left", padx=(0, pad(12)))

        cb = sz(16)
        for text, var, cmd in (
            ("HUD", self.hud_mode, self.toggle_hud),
            ("Pin", self.always_on_top, self.apply_on_top),
            ("Auto", self.auto_copy, self.save_settings),
        ):
            ctk.CTkCheckBox(
                right, text=text, variable=var, command=cmd,
                font=f_ui(11), text_color=C["muted"],
                fg_color=C["accent"], hover_color=C["accent_h"],
                border_color=C["line"], checkbox_width=cb, checkbox_height=cb, width=sz(52),
            ).pack(side="left", padx=pad(3))

    def build_footer(self):
        foot = ctk.CTkFrame(self.root, fg_color="transparent", height=sz(36))
        foot.pack(fill="x", padx=pad(16), pady=(pad(6), pad(10)))

        self.status_bar = ctk.CTkLabel(
            foot, text=random.choice(TIPS), font=f_ui(11),
            text_color=C["faint"], anchor="w",
        )
        self.status_bar.pack(side="left", fill="x", expand=True)

        self.session_chip = ctk.CTkLabel(
            foot, text="session  ·  0 copies", font=f_ui(11, "bold"),
            text_color=C["muted"], fg_color=C["elevated"], corner_radius=8,
            padx=pad(10), pady=pad(4),
        )
        self.session_chip.pack(side="right")

    def build_hud_panel(self):
        inner = ctk.CTkFrame(self.hud_body, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=pad(12), pady=pad(10))

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        hs = sz(22)
        hud_logo = self.assets.logo(size=(hs, hs))
        if hud_logo:
            self._hud_logo_img = hud_logo
            ctk.CTkLabel(top, text="", image=hud_logo, width=hs, height=hs).pack(
                side="left", padx=(0, pad(6))
            )
        ctk.CTkLabel(top, text="HUD", font=f_ui(12, "bold"), text_color=C["muted"]).pack(side="left")
        self.hud_counter = ctk.CTkLabel(
            top, text="0/150", font=f_ui(11, "bold"), text_color=C["success"],
        )
        self.hud_counter.pack(side="right", padx=(0, pad(8)))
        ctk.CTkButton(
            top, text="Exit HUD", width=sz(96), height=sz(28), font=f_ui(12, "bold"),
            fg_color=C["accent"], hover_color=C["accent_h"], command=self.exit_hud,
        ).pack(side="right")

        self.hud_line = ctk.CTkEntry(
            inner, height=sz(38), font=f_mono(13),
            fg_color=C["elevated"], border_color=C["line"], text_color=C["text"],
        )
        self.hud_line.pack(fill="x", pady=(pad(10), pad(8)))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(
            row, text="Copy", height=sz(36), font=f_ui(13, "bold"),
            fg_color=C["success"], hover_color=C["success_h"], text_color="#04120a",
            command=self.hud_copy,
        ).pack(side="left", expand=True, fill="x", padx=(0, pad(6)))
        ctk.CTkButton(
            row, text="Fav", width=sz(64), height=sz(36), font=f_ui(12),
            fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.hud_favorite,
        ).pack(side="left", padx=pad(3))
        ctk.CTkButton(
            row, text="Trim", width=sz(64), height=sz(36), font=f_ui(12),
            fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.hud_trim,
        ).pack(side="left", padx=pad(3))
        ctk.CTkButton(
            row, text="Surprise", width=sz(88), height=sz(36), font=f_ui(12),
            fg_color=C["purple"], hover_color=C["purple_h"], command=self.surprise_me,
        ).pack(side="left", padx=(pad(6), 0))

    # =====================================================================
    # Quick tab
    # =====================================================================
    def _job_card_header(self, parent, title: str, subtitle: str, accent: str = None):
        """Clear section title so jobs don't feel conjoined."""
        accent = accent or C["accent"]
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", padx=pad(14), pady=(pad(12), pad(4)))
        bar = ctk.CTkFrame(head, fg_color=accent, width=sz(4), height=sz(28), corner_radius=2)
        bar.pack(side="left", padx=(0, pad(10)))
        bar.pack_propagate(False)
        texts = ctk.CTkFrame(head, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            texts, text=title, font=f_ui(12, "bold"), text_color=C["text"], anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            texts, text=subtitle, font=f_ui(11), text_color=C["muted"], anchor="w",
        ).pack(anchor="w")


    def build_sticky_copy_bar(self):
        """Pinned green Copy — same place every workflow."""
        self.sticky_copy_bar = ctk.CTkFrame(
            self.root, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["success"],
        )
        inner = ctk.CTkFrame(self.sticky_copy_bar, fg_color="transparent")
        inner.pack(fill="x", padx=pad(12), pady=pad(8))
        ctk.CTkLabel(
            inner, text="YOUR LINE", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(side="left", padx=(0, pad(10)))
        self.quick_len = ctk.CTkLabel(
            inner, text="0 / 150", font=f_ui(13, "bold"), text_color=C["success"],
        )
        self.quick_len.pack(side="left")
        self.sticky_copy_btn = ctk.CTkButton(
            inner, text="Copy", width=sz(140), height=sz(40), font=f_ui(15, "bold"),
            fg_color=C["success"], hover_color=C["success_h"], text_color="#04120a",
            command=self.copy_quick_out,
        )
        self.sticky_copy_btn.pack(side="right")
        ctk.CTkButton(
            inner, text="★ Fav", width=sz(72), height=sz(40), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.favorite_quick_out,
        ).pack(side="right", padx=(0, pad(8)))
        ctk.CTkButton(
            inner, text="✦ Spice", width=sz(80), height=sz(40), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.spice_selected_quick,
        ).pack(side="right", padx=(0, pad(6)))

    def _show_sticky_copy_bar(self, show: bool):
        if not hasattr(self, "sticky_copy_bar"):
            return
        try:
            self.sticky_copy_bar.pack_forget()
        except Exception:
            pass
        if show and not self.hud_mode.get():
            # Pack after main_body, before status footer
            try:
                foot = None
                for w in self.root.winfo_children():
                    if w is self.main_body or w is self.header or w is self.hud_body:
                        continue
                    if w is self.sticky_copy_bar:
                        continue
                    if hasattr(self, "status_bar") and w == self.status_bar.master:
                        foot = w
                if foot is not None:
                    self.sticky_copy_bar.pack(
                        fill="x", padx=pad(14), pady=(pad(4), 0), before=foot,
                    )
                else:
                    self.sticky_copy_bar.pack(fill="x", padx=pad(14), pady=(pad(4), 0))
            except Exception:
                self.sticky_copy_bar.pack(fill="x", padx=pad(14), pady=(pad(4), 0))

    def build_generator_tab(self):
        """Single intent-driven Chat Generator (replaces Quick/Wingman/Recruit)."""
        tab = self.tabview.tab("Chat Generator")
        tab.configure(fg_color=C["surface"])

        # ---- Onboarding ----
        self.onboard_card = ctk.CTkFrame(
            tab, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["accent"],
        )
        if not self.onboarding_done:
            self.onboard_card.pack(fill="x", padx=pad(10), pady=(pad(10), pad(6)))
        self._job_card_header(
            self.onboard_card,
            "GET STARTED IN 3 STEPS",
            "The Golden Loop — no tab hunting.",
            accent=C["accent"],
        )
        steps = ctk.CTkFrame(self.onboard_card, fg_color="transparent")
        steps.pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        for line in (
            "1  Pick what you want: LFG · Activity · Reply · Recruit · Noise",
            "2  Hit Write — your line appears below",
            "3  Green Copy (always at the bottom) → paste in game",
        ):
            ctk.CTkLabel(
                steps, text=line, font=f_ui(13), text_color=C["text"], anchor="w",
            ).pack(anchor="w", pady=2)
        ctk.CTkButton(
            self.onboard_card, text="Got it — start with LFG", height=sz(36),
            font=f_ui(13, "bold"), fg_color=C["accent"], hover_color=C["accent_h"],
            command=self.dismiss_onboarding,
        ).pack(fill="x", padx=pad(14), pady=(pad(4), pad(12)))

        # ---- Intent chips ----
        intent_card = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        intent_card.pack(fill="x", padx=pad(10), pady=(pad(10) if self.onboarding_done else 0, pad(6)))
        ctk.CTkLabel(
            intent_card, text="WHAT DO YOU WANT TO SAY?", font=f_ui(10, "bold"),
            text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(10), pad(4)))
        chip_row = ctk.CTkFrame(intent_card, fg_color="transparent")
        chip_row.pack(fill="x", padx=pad(12), pady=(0, pad(10)))
        self.intent_seg = ctk.CTkSegmentedButton(
            chip_row,
            values=[INTENT_LABELS[k] for k in INTENT_OPTIONS],
            font=f_ui(13, "bold"),
            height=sz(36),
            selected_color=C["accent"],
            selected_hover_color=C["accent_h"],
            unselected_color=C["surface"],
            unselected_hover_color=C["hover"],
            command=self.on_intent_label,
        )
        self.intent_seg.set(INTENT_LABELS.get(self.generator_intent.get(), "LFG"))
        self.intent_seg.pack(fill="x")

        self.intent_host = ctk.CTkFrame(tab, fg_color="transparent")
        self.intent_host.pack(fill="x", padx=pad(10), pady=(0, pad(4)))

        self.panel_lfg = ctk.CTkFrame(
            self.intent_host, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["accent"],
        )
        self.panel_activity = ctk.CTkFrame(
            self.intent_host, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["info"],
        )
        self.panel_reply = ctk.CTkFrame(
            self.intent_host, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["purple"],
        )
        self.panel_recruit = ctk.CTkFrame(
            self.intent_host, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["line"],
        )
        self.panel_noise = ctk.CTkFrame(
            self.intent_host, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["line"],
        )
        self._build_lfg_panel(self.panel_lfg)
        self._build_activity_panel(self.panel_activity)
        self._build_reply_panel(self.panel_reply)
        self._build_recruit_panel(self.panel_recruit)
        self._build_noise_panel(self.panel_noise)

        # ---- Advanced tweaks ----
        adv_wrap = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        adv_wrap.pack(fill="x", padx=pad(10), pady=(0, pad(6)))
        self.adv_toggle_btn = ctk.CTkButton(
            adv_wrap,
            text=self._advanced_toggle_label(),
            height=sz(32), font=f_ui(12),
            fg_color="transparent", hover_color=C["hover"],
            text_color=C["muted"], anchor="w",
            command=self.toggle_advanced,
        )
        self.adv_toggle_btn.pack(fill="x", padx=pad(8), pady=pad(4))
        self.advanced_frame = ctk.CTkFrame(adv_wrap, fg_color="transparent")
        adv_row = ctk.CTkFrame(self.advanced_frame, fg_color="transparent")
        adv_row.pack(fill="x", padx=pad(12), pady=(0, pad(10)))
        self._field_label(adv_row, "Mood").pack(side="left")
        ctk.CTkOptionMenu(
            adv_row, variable=self.mood_var, values=MOOD_OPTIONS,
            width=sz(150), height=sz(32), font=f_ui(12),
            fg_color=C["surface"], button_color=C["hover"],
            command=lambda _=None: self.save_settings(),
        ).pack(side="left", padx=(pad(6), pad(12)))
        self._field_label(adv_row, "Heat").pack(side="left")
        self.heat_label = ctk.CTkLabel(
            adv_row, text=INTENSITY_LABELS.get(self.saved_intensity, "Normal"),
            width=sz(56), font=f_ui(12, "bold"), text_color=C["text"],
        )
        self.heat_label.pack(side="left", padx=(pad(6), pad(4)))
        self.heat_slider = ctk.CTkSlider(
            adv_row, from_=0, to=2, number_of_steps=2, width=sz(90),
            progress_color=C["accent"], button_color=C["text"],
            command=self.on_heat_change,
        )
        self.heat_slider.set(self.saved_intensity)
        self.heat_slider.pack(side="left", padx=(0, pad(12)))
        self._field_label(adv_row, "LFG need").pack(side="left")
        self.lfg_need_menu = ctk.CTkOptionMenu(
            adv_row, variable=self.lfg_need_var, values=LFG_NEED_OPTIONS,
            width=sz(130), height=sz(32), font=f_ui(12),
            fg_color=C["surface"], button_color=C["hover"],
            command=self.on_lfg_need_changed,
        )
        self.lfg_need_menu.pack(side="left", padx=(pad(6), 0))
        ctk.CTkCheckBox(
            self.advanced_frame, text="Grab chat: last line only",
            variable=self.ocr_prefer_last, font=f_ui(11), text_color=C["muted"],
            fg_color=C["purple"], hover_color=C["purple_h"], border_color=C["line"],
            command=self.save_settings, checkbox_width=sz(16), checkbox_height=sz(16),
        ).pack(anchor="w", padx=pad(14), pady=(0, pad(10)))

        # ---- Generated editor ----
        editor_card = ctk.CTkFrame(
            tab, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["success"],
        )
        editor_card.pack(fill="x", padx=pad(10), pady=(0, pad(6)))
        ed_head = ctk.CTkFrame(editor_card, fg_color="transparent")
        ed_head.pack(fill="x", padx=pad(14), pady=(pad(10), pad(4)))
        ctk.CTkLabel(
            ed_head, text="GENERATED LINE", font=f_ui(11, "bold"), text_color=C["faint"],
        ).pack(side="left")
        self.editor_len = ctk.CTkLabel(
            ed_head, text="0 / 150", font=f_ui(12, "bold"), text_color=C["success"],
        )
        self.editor_len.pack(side="right")

        # Text box + Copy button side-by-side (Copy lives on the editor)
        ed_body = ctk.CTkFrame(editor_card, fg_color="transparent")
        ed_body.pack(fill="x", padx=pad(12), pady=(0, pad(6)))
        self.gen_editor = ctk.CTkTextbox(
            ed_body, height=sz(88), font=f_mono(14),
            fg_color=C["surface"], text_color=C["text"],
            border_width=0, corner_radius=10, wrap="word",
        )
        self.gen_editor.pack(side="left", fill="both", expand=True, padx=(0, pad(8)))
        self.gen_editor.insert("1.0", "")
        self.gen_editor.bind("<KeyRelease>", lambda e: self._update_quick_out_meter())
        self.quick_out = self.gen_editor
        self.ai_output = self.gen_editor

        ed_side = ctk.CTkFrame(ed_body, fg_color="transparent", width=sz(120))
        ed_side.pack(side="right", fill="y")
        ed_side.pack_propagate(False)
        self.editor_copy_btn = ctk.CTkButton(
            ed_side, text="Copy", height=sz(48), font=f_ui(15, "bold"),
            fg_color=C["success"], hover_color=C["success_h"], text_color="#04120a",
            command=self.copy_quick_out,
        )
        self.editor_copy_btn.pack(fill="x", pady=(0, pad(6)))
        ctk.CTkButton(
            ed_side, text="★ Fav", height=sz(32), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.favorite_quick_out,
        ).pack(fill="x", pady=(0, pad(4)))
        ctk.CTkButton(
            ed_side, text="Trim", height=sz(32), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.trim_gen_editor,
        ).pack(fill="x")

        refine = ctk.CTkFrame(editor_card, fg_color="transparent")
        refine.pack(fill="x", padx=pad(12), pady=(0, pad(4)))
        ctk.CTkLabel(refine, text="Refine", font=f_ui(11, "bold"), text_color=C["muted"]).pack(
            side="left", padx=(0, pad(8))
        )
        for label, cmd, bg, tc in (
            ("Shorter", self.refine_shorter, C["surface"], C["text"]),
            ("Safer", self.refine_safer, C["success_dim"], C["success"]),
            ("Spicier", self.refine_spicier, "#422006", C["warn"]),
            ("Another", self.regenerate_last, C["elevated"], C["text"]),
        ):
            ctk.CTkButton(
                refine, text=label, width=sz(78), height=sz(32), font=f_ui(12, "bold"),
                fg_color=bg, hover_color=C["hover"], text_color=tc,
                border_width=1, border_color=C["line"], command=cmd,
            ).pack(side="left", padx=pad(3))
        ctk.CTkButton(
            refine, text="Clear", width=sz(64), height=sz(32), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.clear_gen_editor,
        ).pack(side="left", padx=pad(3))

        self.variant_frame = ctk.CTkFrame(editor_card, fg_color="transparent")
        self.variant_frame.pack(fill="x", padx=pad(12), pady=(0, pad(8)))
        self.variant_btns: list[ctk.CTkButton] = []
        for i in range(3):
            b = ctk.CTkButton(
                self.variant_frame, text=f"Option {i + 1}", height=sz(30), state="disabled",
                font=f_ui(11), fg_color=C["surface"], hover_color=C["hover"],
                command=lambda idx=i: self.pick_variant(idx),
            )
            b.pack(fill="x", pady=2)
            self.variant_btns.append(b)

        self.quick_scroll = ctk.CTkScrollableFrame(
            tab, label_text="Your lines", label_font=f_ui(12, "bold"),
            label_text_color=C["muted"], fg_color=C["elevated"], corner_radius=12,
        )
        self.quick_scroll.pack(fill="both", expand=True, padx=pad(10), pady=(0, pad(8)))
        self.rebuild_quick_buttons()

        self.input_seed = ctk.CTkEntry(tab)
        self.input_seed.pack_forget()

        self._apply_advanced_visibility()
        self._show_intent_panel(self.generator_intent.get())
        self._update_quick_out_meter()

    def _advanced_toggle_label(self) -> str:
        return "▾ Advanced Tweaks" if self.show_advanced.get() else "▸ Advanced Tweaks (Mood · Heat · Need)"

    def toggle_advanced(self):
        self.show_advanced.set(not self.show_advanced.get())
        self._apply_advanced_visibility()
        self.save_settings()

    def _apply_advanced_visibility(self):
        if not hasattr(self, "advanced_frame"):
            return
        if self.show_advanced.get():
            self.advanced_frame.pack(fill="x")
        else:
            self.advanced_frame.pack_forget()
        if hasattr(self, "adv_toggle_btn"):
            self.adv_toggle_btn.configure(text=self._advanced_toggle_label())

    def dismiss_onboarding(self):
        self.onboarding_done = True
        if hasattr(self, "onboard_card"):
            self.onboard_card.pack_forget()
        self.set_intent("lfg")
        self.save_settings()
        self.show_toast("You're set — write an LFG", kind="ok")

    def on_intent_label(self, label: str):
        for key, lab in INTENT_LABELS.items():
            if lab == label:
                self.set_intent(key)
                return
        self.set_intent("lfg")

    def set_intent(self, key: str):
        if key not in INTENT_OPTIONS:
            key = "lfg"
        self.generator_intent.set(key)
        if hasattr(self, "intent_seg"):
            try:
                self.intent_seg.set(INTENT_LABELS[key])
            except Exception:
                pass
        self._show_intent_panel(key)
        self.save_settings()

    def _show_intent_panel(self, key: str):
        panels = {
            "lfg": getattr(self, "panel_lfg", None),
            "activity": getattr(self, "panel_activity", None),
            "reply": getattr(self, "panel_reply", None),
            "recruit": getattr(self, "panel_recruit", None),
            "noise": getattr(self, "panel_noise", None),
        }
        for p in panels.values():
            if p is not None:
                p.pack_forget()
        panel = panels.get(key)
        if panel is not None:
            panel.pack(fill="x")

    def _build_lfg_panel(self, parent):
        self._job_card_header(
            parent, "LFG — FIND A GROUP",
            "Pick content, then Write. Need is under Advanced Tweaks.",
            accent=C["accent"],
        )
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        self._field_label(row, "Content").pack(side="left")
        self.lfg_target_menu = ctk.CTkOptionMenu(
            row, variable=self.lfg_target_var, values=self.lfg_target_names(),
            width=sz(200), height=sz(36), font=f_ui(13, "bold"),
            fg_color=C["surface"], button_color=C["hover"],
            command=self.on_lfg_target_changed,
        )
        self.lfg_target_menu.pack(side="left", padx=(pad(8), pad(12)))
        ctk.CTkButton(
            parent, text="Write LFG line", height=sz(42), font=f_ui(14, "bold"),
            fg_color=C["accent"], hover_color=C["accent_h"], command=self.generate_lfg,
        ).pack(fill="x", padx=pad(14), pady=(0, pad(12)))

    def _build_activity_panel(self, parent):
        self._job_card_header(
            parent, "ACTIVITY CHAT",
            "Presence / banter — not an LFG. Mood & Heat in Advanced Tweaks.",
            accent=C["info"],
        )
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        self._field_label(row, "Activity").pack(side="left")
        self.activity_menu = ctk.CTkOptionMenu(
            row, variable=self.activity_var, values=self.profile()["activities"],
            width=sz(180), height=sz(36), font=f_ui(12),
            fg_color=C["surface"], button_color=C["hover"],
            command=lambda _=None: self.save_settings(),
        )
        self.activity_menu.pack(side="left", padx=(pad(8), 0))
        self.ai_activity_menu = self.activity_menu
        ctk.CTkButton(
            parent, text="Write activity line", height=sz(42), font=f_ui(14, "bold"),
            fg_color=C["info"], hover_color="#0ea5e9", text_color="#041018",
            command=self.generate_activity_line,
        ).pack(fill="x", padx=pad(14), pady=(0, pad(12)))

    def _build_reply_panel(self, parent):
        self._job_card_header(
            parent, "REPLY",
            "Paste what they said — or grab chat from the game screen.",
            accent=C["purple"],
        )
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        self._field_label(row, "They said").pack(side="left")
        self.quick_they_said = ctk.CTkEntry(
            row, height=sz(36), font=f_ui(12),
            placeholder_text="paste their line…",
            fg_color=C["surface"], border_color=C["line"],
        )
        self.quick_they_said.pack(side="left", fill="x", expand=True, padx=(pad(8), 0))
        self.quick_they_said.bind("<Return>", lambda e: self.generate_response_from_quick())
        self.input_statement = self.quick_they_said
        grab = ctk.CTkFrame(parent, fg_color="transparent")
        grab.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        ctk.CTkButton(
            grab, text="Set chat box on screen", height=sz(34), width=sz(170), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.calibrate_chat_region,
        ).pack(side="left", padx=(0, pad(6)))
        ctk.CTkButton(
            grab, text="Grab chat from game", height=sz(34), width=sz(150), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=lambda: self.grab_chat_ocr(and_reply=False),
        ).pack(side="left", padx=(0, pad(6)))
        ctk.CTkButton(
            grab, text="Grab + reply", height=sz(34), width=sz(110), font=f_ui(12, "bold"),
            fg_color=C["purple"], hover_color=C["purple_h"],
            command=lambda: self.grab_chat_ocr(and_reply=True),
        ).pack(side="left")
        self.ocr_status = ctk.CTkLabel(
            parent, text=self._ocr_status_text(), font=f_ui(11), text_color=C["faint"], anchor="w",
        )
        self.ocr_status.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        act = ctk.CTkFrame(parent, fg_color="transparent")
        act.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        ctk.CTkButton(
            act, text="Write clap-back", height=sz(42), font=f_ui(14, "bold"),
            fg_color=C["purple"], hover_color=C["purple_h"],
            command=self.generate_response_from_quick,
        ).pack(side="left", fill="x", expand=True, padx=(0, pad(8)))
        ctk.CTkButton(
            act, text="3 options", height=sz(42), width=sz(110), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.generate_triple,
        ).pack(side="left")

    def _build_recruit_panel(self, parent):
        self._job_card_header(
            parent, "RECRUIT",
            "Fit a guild pitch under the character limit.",
            accent=C["line"],
        )
        ctk.CTkLabel(parent, text="Template", font=f_ui(11), text_color=C["muted"]).pack(
            anchor="w", padx=pad(14)
        )
        self.template_combo = ctk.CTkOptionMenu(
            parent, values=self.templates or DEFAULT_TEMPLATES,
            command=self.load_selected_template, height=sz(32), font=f_ui(12),
            fg_color=C["surface"], button_color=C["hover"],
        )
        self.template_combo.pack(fill="x", padx=pad(14), pady=(2, pad(6)))
        msg_head = ctk.CTkFrame(parent, fg_color="transparent")
        msg_head.pack(fill="x", padx=pad(14), pady=(0, 2))
        ctk.CTkLabel(msg_head, text="Message", font=f_ui(11), text_color=C["muted"]).pack(side="left")
        self.counter_label = ctk.CTkLabel(
            msg_head, text="0 / 150", font=f_ui(12, "bold"), text_color=C["success"],
        )
        self.counter_label.pack(side="right")

        msg_row = ctk.CTkFrame(parent, fg_color="transparent")
        msg_row.pack(fill="x", padx=pad(14), pady=(2, pad(6)))
        self.msg_textbox = ctk.CTkTextbox(
            msg_row, height=sz(90), font=f_mono(13),
            fg_color=C["surface"], text_color=C["text"], border_width=0, corner_radius=10,
        )
        self.msg_textbox.pack(side="left", fill="both", expand=True, padx=(0, pad(8)))
        if self.templates:
            self.msg_textbox.insert("1.0", self.templates[0])
        self.msg_textbox.bind("<KeyRelease>", self.update_counter)

        recruit_side = ctk.CTkFrame(msg_row, fg_color="transparent", width=sz(120))
        recruit_side.pack(side="right", fill="y")
        recruit_side.pack_propagate(False)
        self.recruit_copy_btn = ctk.CTkButton(
            recruit_side, text="Copy", height=sz(48), font=f_ui(15, "bold"),
            fg_color=C["success"], hover_color=C["success_h"], text_color="#04120a",
            command=self.copy_recruitment,
        )
        self.recruit_copy_btn.pack(fill="x", pady=(0, pad(6)))
        ctk.CTkButton(
            recruit_side, text="Use as line", height=sz(32), font=f_ui(11),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.recruit_to_editor,
        ).pack(fill="x")

        status = ctk.CTkFrame(parent, fg_color="transparent")
        status.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        self.safety_progressbar = ctk.CTkProgressBar(
            status, progress_color=C["success"], fg_color=C["surface"],
        )
        self.safety_progressbar.pack(fill="x")
        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        ctk.CTkButton(
            btns, text="Copy", height=sz(40), width=sz(100), font=f_ui(13, "bold"),
            fg_color=C["success"], hover_color=C["success_h"], text_color="#04120a",
            command=self.copy_recruitment,
        ).pack(side="left", padx=(0, pad(6)))
        ctk.CTkButton(
            btns, text="Fit to limit", height=sz(40), font=f_ui(13, "bold"),
            fg_color=C["purple"], hover_color=C["purple_h"], command=self.ai_fit_recruitment,
        ).pack(side="left", fill="x", expand=True, padx=(0, pad(6)))
        ctk.CTkButton(
            btns, text="Save preset", height=sz(40), width=sz(110), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.save_custom_template,
        ).pack(side="left")
        self.update_counter()

    def _build_noise_panel(self, parent):
        self._job_card_header(
            parent, "NOISE — NOT GAME-RELATED",
            "Calibrate from sane small talk to pure mental chaos. Any topic.",
            accent=C["warn"],
        )
        slide = ctk.CTkFrame(parent, fg_color="transparent")
        slide.pack(fill="x", padx=pad(14), pady=(pad(2), pad(6)))
        ctk.CTkLabel(slide, text="Sane", font=f_ui(11), text_color=C["muted"]).pack(side="left")
        self.noise_level_label = ctk.CTkLabel(
            slide,
            text=NOISE_LEVEL_LABELS.get(int(self.noise_level_var.get()), "Chaos"),
            width=sz(72),
            font=f_ui(12, "bold"),
            text_color=C["warn"],
        )
        self.noise_level_label.pack(side="right")
        ctk.CTkLabel(slide, text="Mental", font=f_ui(11), text_color=C["muted"]).pack(
            side="right", padx=(0, pad(8))
        )
        self.noise_slider = ctk.CTkSlider(
            parent, from_=0, to=4, number_of_steps=4,
            progress_color=C["warn"], button_color=C["text"],
            command=self.on_noise_level_change,
        )
        self.noise_slider.set(int(self.noise_level_var.get()))
        self.noise_slider.pack(fill="x", padx=pad(14), pady=(0, pad(4)))
        self.noise_hint = ctk.CTkLabel(
            parent,
            text=NOISE_LEVEL_HINTS.get(int(self.noise_level_var.get()), ""),
            font=f_ui(11), text_color=C["faint"], anchor="w", wraplength=640, justify="left",
        )
        self.noise_hint.pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        ctk.CTkButton(
            parent, text="Write chaos line", height=sz(42), font=f_ui(14, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.generate_noise,
        ).pack(fill="x", padx=pad(14), pady=(0, pad(12)))

    def _job_card_header(self, parent, title: str, subtitle: str, accent: str = None):
        accent = accent or C["accent"]
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", padx=pad(14), pady=(pad(12), pad(4)))
        bar = ctk.CTkFrame(head, fg_color=accent, width=sz(4), height=sz(28), corner_radius=2)
        bar.pack(side="left", padx=(0, pad(10)))
        bar.pack_propagate(False)
        texts = ctk.CTkFrame(head, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            texts, text=title, font=f_ui(12, "bold"), text_color=C["text"], anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            texts, text=subtitle, font=f_ui(11), text_color=C["muted"], anchor="w",
        ).pack(anchor="w")

    def _field_label(self, parent, text: str):
        return ctk.CTkLabel(parent, text=text, font=f_ui(11), text_color=C["muted"])

    def _section_label(self, parent, text: str):
        ctk.CTkLabel(
            parent, text=text, font=f_ui(11, "bold"), text_color=C["faint"], anchor="w",
        ).pack(fill="x", pady=(12, 4), padx=2)

    def _hidden_for_game(self, game: Optional[str] = None) -> list[str]:
        return list(self.hidden_lines.get(game or self.game_var.get(), []))

    def rebuild_quick_buttons(self):
        if not hasattr(self, "quick_scroll"):
            return
        for w in self.quick_scroll.winfo_children():
            w.destroy()
        game = self.game_var.get()
        hidden = set(self._hidden_for_game(game))
        stock = [p for p in self.profile()["quick"] if p not in hidden]
        for p in self.custom_quick.get(game, []):
            if p not in stock and p not in hidden:
                stock.append(p)
        favs = [f for f in self.favorites if f and f not in hidden]
        if favs:
            self._section_label(self.quick_scroll, "STARRED")
            for phrase in favs:
                self._add_phrase_row(phrase, starred=True)
        recent = []
        for h in reversed(self.history):
            if h not in favs and h not in recent and h not in hidden:
                recent.append(h)
            if len(recent) >= 5:
                break
        for text, count in sorted(self.copy_counts.items(), key=lambda kv: kv[1], reverse=True):
            if count >= 2 and text not in favs and text not in recent and text not in stock and text not in hidden:
                recent.append(text)
            if len(recent) >= 8:
                break
        if recent:
            self._section_label(self.quick_scroll, "RECENT")
            for phrase in recent[:8]:
                self._add_phrase_row(phrase, starred=phrase in self.favorites)
        visible = [p for p in stock if p not in favs]
        if visible:
            self._section_label(self.quick_scroll, f"{self.profile()['short'].upper()} STOCK")
            for phrase in visible:
                self._add_phrase_row(phrase)
        elif not favs and not recent:
            ctk.CTkLabel(
                self.quick_scroll,
                text="Empty list. Generate something, or Manage stock in Library.",
                text_color=C["faint"], font=f_ui(12),
            ).pack(pady=28)

    def _add_phrase_row(self, phrase: str, starred: bool = False):
        row = ctk.CTkFrame(self.quick_scroll, fg_color="transparent")
        row.pack(fill="x", pady=pad(3))
        over = len(phrase) > self.limit()
        ctk.CTkButton(
            row,
            text=("⚠  " if over else "") + phrase,
            anchor="w", height=sz(36), font=f_ui(12),
            fg_color=C["danger_dim"] if over else C["surface"],
            hover_color=C["hover"],
            text_color=C["danger"] if over else C["text"],
            corner_radius=8,
            command=lambda p=phrase: self.use_quick_phrase(p),
        ).pack(side="left", fill="x", expand=True, padx=(0, pad(6)))
        star = "★" if starred or phrase in self.favorites else "☆"
        self._icon_btn(row, star, lambda p=phrase: self.toggle_favorite(p)).pack(side="left", padx=pad(4))
        self._icon_btn(row, "✦", lambda p=phrase: self.spice_phrase(p)).pack(side="left", padx=pad(4))
        self._icon_btn(
            row, "⌫", lambda p=phrase: self.delete_line(p), danger=True,
        ).pack(side="left", padx=(pad(8), 0))

    def _icon_btn(self, parent, text, command, danger=False):
        side = max(40, sz(40))
        return ctk.CTkButton(
            parent, text=text, width=side, height=side, font=f_ui(14),
            fg_color=C["danger_dim"] if danger else C["surface"],
            hover_color="#7f1d1d" if danger else C["hover"],
            border_width=0 if danger else 1,
            border_color=C["line"],
            text_color=C["danger"] if danger else C["muted"],
            command=command,
        )

    def build_library_tab(self):
        tab = self.tabview.tab("Library")
        tab.configure(fg_color=C["surface"])
        head = ctk.CTkFrame(tab, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            head, text="Click to re-copy  ·  star to pin  ·  delete to forget",
            font=f_ui(12), text_color=C["muted"],
        ).pack(side="left")
        ctk.CTkButton(
            head, text="Clear history", width=110, height=sz(30), font=f_ui(11),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.clear_history,
        ).pack(side="right")
        ctk.CTkButton(
            head, text="Manage stock", width=110, height=sz(30), font=f_ui(11),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.clear_your_lines_menu,
        ).pack(side="right", padx=(0, pad(6)))
        self.history_scroll = ctk.CTkScrollableFrame(
            tab, fg_color=C["elevated"], corner_radius=12, label_text="History",
            label_font=f_ui(12, "bold"), label_text_color=C["muted"],
        )
        self.history_scroll.pack(fill="both", expand=True, padx=12, pady=(4, 12))

    def refresh_history_ui(self):
        if not hasattr(self, "history_scroll"):
            return
        for w in self.history_scroll.winfo_children():
            w.destroy()
        if not self.history:
            ctk.CTkLabel(
                self.history_scroll, text="No history yet. Your best lines will land here.",
                text_color=C["faint"], font=f_ui(12),
            ).pack(pady=24)
            return
        for item in reversed(self.history):
            row = ctk.CTkFrame(self.history_scroll, fg_color="transparent")
            row.pack(fill="x", pady=pad(4))
            count = self.copy_counts.get(item, 0)
            label = item if len(item) < 78 else item[:75] + "…"
            if count:
                label = f"{count}×  {label}"
            ctk.CTkButton(
                row, text=label, anchor="w", height=sz(40), font=f_ui(12),
                fg_color=C["surface"], hover_color=C["hover"],
                command=lambda t=item: self.recopy_history(t),
            ).pack(side="left", fill="x", expand=True, padx=(0, pad(8)))
            star = "★" if item in self.favorites else "☆"
            self._icon_btn(row, star, lambda t=item: self.toggle_favorite(t)).pack(side="left", padx=pad(4))
            self._icon_btn(row, "⌫", lambda t=item: self.delete_line(t), danger=True).pack(
                side="left", padx=(pad(8), 0)
            )

    def build_setup_tab(self):
        tab = self.tabview.tab("Setup")
        tab.configure(fg_color=C["surface"])
        a11y = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        a11y.pack(fill="x", padx=pad(12), pady=(pad(12), pad(6)))
        ctk.CTkLabel(
            a11y, text="TYPE SIZE", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(4)))
        row = ctk.CTkFrame(a11y, fg_color="transparent")
        row.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        labels = [TYPE_PRESETS[k]["label"] for k in TYPE_SCALE_ORDER]
        current_label = TYPE_PRESETS[self.font_scale_key]["label"]
        self.help_type_menu = ctk.CTkSegmentedButton(
            row, values=labels, font=f_ui(12, "bold"), height=sz(34),
            selected_color=C["accent"], selected_hover_color=C["accent_h"],
            unselected_color=C["surface"], unselected_hover_color=C["hover"],
            command=self.on_type_scale_menu,
        )
        self.help_type_menu.set(current_label)
        self.help_type_menu.pack(side="left", fill="x", expand=True)
        # ---- Steam population trends (minimal UI) ----
        steam_box = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        steam_box.pack(fill="x", padx=pad(12), pady=(0, pad(6)))
        ctk.CTkLabel(
            steam_box, text="STEAM POPULATION LOG", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(4)))
        ctk.CTkLabel(
            steam_box,
            text="Polls concurrent players while the app is open. Log file for overnight / market timing.",
            font=f_ui(12), text_color=C["muted"], anchor="w",
        ).pack(anchor="w", padx=pad(14), pady=(0, pad(6)))

        steam_row = ctk.CTkFrame(steam_box, fg_color="transparent")
        steam_row.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        ctk.CTkCheckBox(
            steam_row, text="Log to file", variable=self.steam_log_enabled,
            font=f_ui(12), text_color=C["muted"],
            fg_color=C["info"], hover_color=C["info"], border_color=C["line"],
            command=self.save_settings, checkbox_width=sz(16), checkbox_height=sz(16),
        ).pack(side="left", padx=(0, pad(12)))
        ctk.CTkLabel(steam_row, text="Every", font=f_ui(11), text_color=C["muted"]).pack(side="left")
        self.steam_interval_menu = ctk.CTkOptionMenu(
            steam_row,
            values=[f"{m} min" for m in STEAM_LOG_INTERVAL_CHOICES],
            width=sz(90), height=sz(28), font=f_ui(12),
            fg_color=C["surface"], button_color=C["hover"],
            command=self.on_steam_log_interval,
        )
        self.steam_interval_menu.set(f"{int(self.steam_log_minutes.get())} min")
        self.steam_interval_menu.pack(side="left", padx=(pad(6), pad(12)))
        ctk.CTkButton(
            steam_row, text="Refresh chart", height=sz(28), width=sz(110), font=f_ui(11),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.refresh_steam_chart,
        ).pack(side="left", padx=(0, pad(6)))
        ctk.CTkButton(
            steam_row, text="Open log", height=sz(28), width=sz(90), font=f_ui(11),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.open_steam_log_file,
        ).pack(side="left")

        self.steam_chart_meta = ctk.CTkLabel(
            steam_box, text="No data yet — leave app open to log.",
            font=f_ui(11), text_color=C["faint"], anchor="w",
        )
        self.steam_chart_meta.pack(fill="x", padx=pad(14), pady=(0, pad(4)))

        chart_wrap = ctk.CTkFrame(steam_box, fg_color=C["surface"], corner_radius=10, height=sz(140))
        chart_wrap.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        chart_wrap.pack_propagate(False)
        self.steam_chart_canvas = tk.Canvas(
            chart_wrap, bg=C["surface"], highlightthickness=0, bd=0,
        )
        self.steam_chart_canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.steam_chart_canvas.bind("<Configure>", lambda e: self.draw_steam_chart())

        tips = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        tips.pack(fill="both", expand=True, padx=pad(12), pady=(0, pad(12)))
        ctk.CTkLabel(
            tips, text="QUICK SETUP", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(6)))
        for line in (
            "• Local AI: run LM Studio and load a model (header shows ● live)",
            "• Sampling is set BY THIS APP per job — leave LM Studio defaults",
            "• Steam log: steam_players_log.txt next to the app (TSV) for Excel/analysis",
            "• Click the header Steam chip anytime to jump here and see the chart",
            "• Leave the app running overnight to capture market population trends",
            "• HUD: pin a tiny strip · Esc exits · Type size: A− / A+",
        ):
            ctk.CTkLabel(
                tips, text=line, font=f_ui(13), text_color=C["text"], anchor="w",
            ).pack(anchor="w", padx=pad(14), pady=2)
        ctk.CTkLabel(
            tips, text=f"Chat Helper v{APP_VERSION}", font=f_ui(11), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(14)))
        self.root.after(400, self.refresh_steam_chart)


    # =====================================================================
    # HUD / chrome
    # =====================================================================
    def apply_startup_geometry(self):
        if self.hud_mode.get():
            self.root.geometry(self._hud_geometry)
            self.root.minsize(*scaled_hud_minsize())
        else:
            self.root.geometry(self._full_geometry)
            self.root.minsize(*scaled_full_minsize())

    def toggle_hud(self):
        self.set_hud(self.hud_mode.get())

    def exit_hud(self):
        if self.hud_mode.get():
            self.set_hud(False)

    def _on_escape(self, event=None):
        if self.hud_mode.get():
            self.exit_hud()
            return "break"

    def set_hud(self, enabled: bool):
        self.hud_mode.set(enabled)
        try:
            geo = self.root.geometry()
            if enabled:
                self._full_geometry = geo
            else:
                self._hud_geometry = geo
        except Exception:
            pass
        self._apply_hud_visibility(enabled)
        if enabled:
            self.root.geometry(self._hud_geometry or HUD_GEOMETRY)
            self.root.minsize(*scaled_hud_minsize())
            self.refresh_hud_line()
            self.set_status("HUD on — Exit HUD or Esc to leave.")
        else:
            self.root.geometry(self._full_geometry or FULL_GEOMETRY)
            self.root.minsize(*scaled_full_minsize())
            self.set_status("Full mode.")
        self.save_settings()

    def _apply_hud_visibility(self, enabled: bool):
        if enabled:
            self.main_body.pack_forget()
            self._show_sticky_copy_bar(False)
            self.hud_body.pack(fill="both", expand=True, padx=pad(14), pady=pad(6))
        else:
            self.hud_body.pack_forget()
            self.main_body.pack(fill="both", expand=True, padx=pad(14), pady=(pad(6), 0))
            self._show_sticky_copy_bar(True)

    def refresh_hud_line(self):
        line = self._last_good_line or (self.history[-1] if self.history else "")
        if hasattr(self, "hud_line"):
            self.hud_line.delete(0, tk.END)
            if line:
                self.hud_line.insert(0, line)
            self._update_len_label(self.hud_counter, line)

    def hud_copy(self):
        self.safe_copy(self.hud_line.get().strip())

    def hud_favorite(self):
        t = self.hud_line.get().strip()
        if t:
            self.toggle_favorite(t)

    def hud_trim(self):
        trimmed = self.trim_to_limit(self.hud_line.get().strip())
        self.hud_line.delete(0, tk.END)
        self.hud_line.insert(0, trimmed)
        self._last_good_line = trimmed
        self._update_len_label(self.hud_counter, trimmed)
        self.set_status(f"Trimmed to {len(trimmed)} / {self.limit()}")

    def apply_on_top(self):
        self.root.attributes("-topmost", bool(self.always_on_top.get()))
        self.save_settings()

    def get_gen_text(self) -> str:
        """Primary generated line (from editor)."""
        if hasattr(self, "gen_editor"):
            try:
                return self.gen_editor.get("1.0", "end-1c").strip()
            except Exception:
                pass
        return ""

    def set_gen_text(self, text: str, also_ai: bool = True, also_hud: bool = True):
        """Write into the main generated-line editor (+ optional mirrors)."""
        text = (text or "").strip()
        if hasattr(self, "gen_editor"):
            try:
                self.gen_editor.delete("1.0", tk.END)
                if text:
                    self.gen_editor.insert("1.0", text)
            except Exception:
                pass
        self._update_quick_out_meter()
        if text and not self._is_err(text):
            self._last_good_line = text
        if also_ai and hasattr(self, "ai_output"):
            try:
                self.ai_output.delete("1.0", tk.END)
                if text:
                    self.ai_output.insert(tk.END, text)
                self.update_ai_counter()
            except Exception:
                pass
        if also_hud:
            self.refresh_hud_line()

    def trim_gen_editor(self):
        t = self.get_gen_text()
        if not t:
            return
        trimmed = self.trim_to_limit(t)
        self.set_gen_text(trimmed)
        self.set_status(f"Trimmed to {len(trimmed)} / {self.limit()}")

    def clear_gen_editor(self):
        self.set_gen_text("", also_ai=True, also_hud=True)
        self.set_status("Editor cleared")

    def _format_player_count(self, n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
        if n >= 10_000:
            return f"{n // 1000}k"
        if n >= 1000:
            return f"{n / 1000:.1f}k".replace(".0k", "k")
        return str(n)

    def steam_appid(self) -> Optional[int]:
        raw = self.profile().get("steam_appid")
        try:
            return int(raw) if raw else None
        except Exception:
            return None

    def _set_steam_label(self, text: str, color: str = None):
        if not hasattr(self, "steam_dot"):
            return
        try:
            self.steam_dot.configure(text=text, text_color=color or C["muted"])
        except Exception:
            pass

    def _fetch_steam_player_count(self, appid: int) -> tuple[Optional[int], str, str]:
        """Returns (count, label, color)."""
        try:
            r = requests.get(
                STEAM_PLAYERS_URL,
                params={"appid": appid},
                timeout=4,
            )
            if r.status_code != 200:
                return None, "Steam · err", C["warn"]
            data = r.json().get("response") or {}
            if int(data.get("result", 0)) == 1 and "player_count" in data:
                count = int(data["player_count"])
                return count, f"Steam · {self._format_player_count(count)}", C["info"]
            return None, "Steam · ?", C["warn"]
        except Exception:
            return None, "Steam · offline", C["faint"]

    def pulse_steam_players(self):
        """Poll Steam GetNumberOfCurrentPlayers for the selected game (no API key)."""
        self._steam_pulse_gen += 1
        gen = self._steam_pulse_gen
        appid = self.steam_appid()
        game_name = self.game_var.get() if hasattr(self, "game_var") else ""

        if not appid:
            self._steam_player_count = None
            self._set_steam_label("Steam · n/a", C["faint"])
            self._steam_history = []
            self.root.after(0, self.draw_steam_chart)
            return

        self._set_steam_label("Steam · …", C["faint"])

        def check():
            if gen != self._steam_pulse_gen:
                return
            count, label, color = self._fetch_steam_player_count(appid)

            def apply():
                if gen != self._steam_pulse_gen:
                    return
                self._steam_player_count = count
                self._set_steam_label(label, color)
                if count is not None:
                    self._maybe_log_steam_players(appid, game_name, count)
                # Live header refresh
                if gen == self._steam_pulse_gen:
                    self.root.after(
                        STEAM_LIVE_INTERVAL_S * 1000,
                        lambda g=gen: self._steam_refresh_if_current(g),
                    )

            try:
                self.root.after(0, apply)
            except Exception:
                self._steam_player_count = count
                self._set_steam_label(label, color)
                if count is not None:
                    self._maybe_log_steam_players(appid, game_name, count)

        threading.Thread(target=check, daemon=True).start()

    def _steam_refresh_if_current(self, gen: int):
        if gen == self._steam_pulse_gen:
            self.pulse_steam_players()

    def _steam_log_interval_sec(self) -> int:
        try:
            mins = int(self.steam_log_minutes.get())
        except Exception:
            mins = 15
        if mins not in STEAM_LOG_INTERVAL_CHOICES:
            mins = 15
        return mins * 60

    def on_steam_log_interval(self, choice: str):
        try:
            mins = int(str(choice).split()[0])
        except Exception:
            mins = 15
        if mins not in STEAM_LOG_INTERVAL_CHOICES:
            mins = 15
        self.steam_log_minutes.set(mins)
        self.save_settings()
        self.show_toast(f"Steam log every {mins} min", kind="info")

    def _maybe_log_steam_players(self, appid: int, game: str, count: int):
        """Append to steam_players_log.txt on cadence (default 15 min)."""
        if hasattr(self, "steam_log_enabled") and not self.steam_log_enabled.get():
            return
        now = time.time()
        interval = self._steam_log_interval_sec()
        last = self._steam_last_log_ts.get(appid, 0)
        # Always allow first sample this session quickly for chart feedback
        if last and (now - last) < interval:
            return
        self._steam_last_log_ts[appid] = now
        try:
            iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
            line = f"{iso}\t{int(now)}\t{game}\t{appid}\t{int(count)}\n"
            write_header = not os.path.isfile(STEAM_LOG_PATH) or os.path.getsize(STEAM_LOG_PATH) == 0
            with open(STEAM_LOG_PATH, "a", encoding="utf-8") as f:
                if write_header:
                    f.write(
                        "# Steam concurrent players log (tab-separated)\n"
                        "# time_local\tunix\tgame\tappid\tplayers\n"
                        "# Leave Chat Helper running to collect overnight trends.\n"
                    )
                f.write(line)
        except Exception:
            pass
        # Update in-memory series for chart (current game only)
        if appid == self.steam_appid():
            self._steam_history.append((now, int(count)))
            # Cap memory (~1 week at 15 min)
            if len(self._steam_history) > 800:
                self._steam_history = self._steam_history[-800:]
            self.root.after(0, self.draw_steam_chart)

    def load_steam_history_from_log(self, appid: Optional[int] = None, max_points: int = 200):
        """Load recent points for the chart from the TSV log."""
        appid = appid or self.steam_appid()
        self._steam_history = []
        if not appid or not os.path.isfile(STEAM_LOG_PATH):
            return
        try:
            rows: list[tuple[float, int]] = []
            with open(STEAM_LOG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) < 5:
                        continue
                    try:
                        row_app = int(parts[3])
                        if row_app != int(appid):
                            continue
                        unix = float(parts[1])
                        players = int(parts[4])
                        rows.append((unix, players))
                    except Exception:
                        continue
            self._steam_history = rows[-max_points:]
        except Exception:
            self._steam_history = []

    def refresh_steam_chart(self):
        self.load_steam_history_from_log()
        self.draw_steam_chart()

    def draw_steam_chart(self):
        """Lightweight sparkline (no matplotlib) for population trends."""
        if not hasattr(self, "steam_chart_canvas"):
            return
        c = self.steam_chart_canvas
        try:
            c.delete("all")
            w = max(c.winfo_width(), 40)
            h = max(c.winfo_height(), 40)
        except Exception:
            return

        pts = list(getattr(self, "_steam_history", []) or [])
        game = self.game_var.get() if hasattr(self, "game_var") else ""
        appid = self.steam_appid()

        if not appid:
            if hasattr(self, "steam_chart_meta"):
                self.steam_chart_meta.configure(text="No Steam AppID for this game.")
            c.create_text(w // 2, h // 2, text="n/a", fill=C["faint"], font=(FONT_UI, 12))
            return

        if len(pts) < 1:
            if hasattr(self, "steam_chart_meta"):
                self.steam_chart_meta.configure(
                    text=f"{game} · no samples yet · leave app open (log every {self.steam_log_minutes.get()} min)"
                )
            c.create_text(
                w // 2, h // 2,
                text="Waiting for first sample…",
                fill=C["faint"], font=(FONT_UI, 11),
            )
            return

        times = [p[0] for p in pts]
        vals = [p[1] for p in pts]
        vmin, vmax = min(vals), max(vals)
        if vmax <= vmin:
            vmax = vmin + 1
        pad_x, pad_y = 28, 16
        plot_w = max(w - pad_x * 2, 10)
        plot_h = max(h - pad_y * 2, 10)

        # Grid + axes
        c.create_rectangle(pad_x, pad_y, pad_x + plot_w, pad_y + plot_h, outline=C["line"], width=1)
        for i in range(1, 4):
            y = pad_y + plot_h * i / 4
            c.create_line(pad_x, y, pad_x + plot_w, y, fill=C["line"])

        coords = []
        n = len(pts)
        for i, (t, v) in enumerate(pts):
            x = pad_x + (plot_w * i / max(n - 1, 1))
            y = pad_y + plot_h - ((v - vmin) / (vmax - vmin)) * plot_h
            coords.extend([x, y])
        if len(coords) >= 4:
            c.create_line(*coords, fill=C["info"], width=2, smooth=True)
        # Last point marker
        c.create_oval(
            coords[-2] - 3, coords[-1] - 3, coords[-2] + 3, coords[-1] + 3,
            fill=C["success"], outline="",
        )
        # Labels
        c.create_text(pad_x + 2, pad_y + 2, text=str(vmax), anchor="nw", fill=C["faint"], font=(FONT_UI, 9))
        c.create_text(pad_x + 2, pad_y + plot_h - 2, text=str(vmin), anchor="sw", fill=C["faint"], font=(FONT_UI, 9))
        c.create_text(
            pad_x + plot_w - 2, pad_y + 2,
            text=self._format_player_count(vals[-1]),
            anchor="ne", fill=C["info"], font=(FONT_UI, 10, "bold"),
        )

        if hasattr(self, "steam_chart_meta"):
            t0 = time.strftime("%m/%d %H:%M", time.localtime(times[0]))
            t1 = time.strftime("%m/%d %H:%M", time.localtime(times[-1]))
            span_h = max(0.1, (times[-1] - times[0]) / 3600.0)
            self.steam_chart_meta.configure(
                text=(
                    f"{game} · {len(pts)} samples · {t0} → {t1} ({span_h:.1f}h) · "
                    f"now {vals[-1]:,} · min {vmin:,} · max {vmax:,} · "
                    f"log: steam_players_log.txt"
                )
            )

    def open_steam_trends(self):
        """Header Steam chip → Setup + chart."""
        try:
            if not self.hud_mode.get():
                self.tabview.set("Setup")
            self.refresh_steam_chart()
            self.set_status("Steam trends · leave app open to keep logging")
        except Exception:
            pass

    def open_steam_log_file(self):
        path = STEAM_LOG_PATH
        if not os.path.isfile(path):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(
                        "# Steam concurrent players log (tab-separated)\n"
                        "# time_local\tunix\tgame\tappid\tplayers\n"
                    )
            except Exception:
                pass
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            try:
                import subprocess
                subprocess.Popen(["notepad", path])
            except Exception:
                self.show_toast(path, kind="info")

    def _refresh_game_icon(self):
        if not hasattr(self, "game_icon_label"):
            return
        bs = sz(26)
        badge = self.assets.game_badge(self.game_var.get(), size=(bs, bs))
        if badge:
            self._game_badge_img = badge
            self.game_icon_label.configure(image=badge, text="")
        else:
            self.game_icon_label.configure(image=None, text="◆", font=f_ui(12), text_color=self.accent())

    def on_game_changed(self, game: str = None, persist: bool = True):
        if game is None:
            game = self.game_var.get()
        elif game in GAME_PROFILES and self.game_var.get() != game:
            self.game_var.set(game)
        prof = self.profile()
        lim = self.limit()
        self.limit_badge.configure(text=f"{lim} max")
        self.game_pill.configure(text=prof["short"], fg_color=C["elevated"], text_color=self.accent())
        self._refresh_game_icon()

        acts = prof["activities"]
        if hasattr(self, "activity_menu") and self.activity_menu is not None:
            try:
                self.activity_menu.configure(values=acts)
            except Exception:
                pass
        if self.activity_var.get() not in acts:
            self.activity_var.set(acts[0])

        # Restore this game's preferred LFG target (or profile default)
        if hasattr(self, "lfg_target_var"):
            names = self.lfg_target_names(game)
            if hasattr(self, "lfg_target_menu"):
                self.lfg_target_menu.configure(values=names)
            preferred = (self.lfg_defaults or {}).get(game)
            self.lfg_target_var.set(self._resolve_lfg_target(game, preferred))

        self.rebuild_quick_buttons()
        if hasattr(self, "msg_textbox"):
            self.update_counter()
        self._update_quick_out_meter()
        self.refresh_hud_line()
        # Refresh Steam count + chart for the new game
        self.load_steam_history_from_log()
        self.pulse_steam_players()
        self.root.after(100, self.draw_steam_chart)
        if persist:
            self.save_settings()
            self.set_status(f"{prof['short']} voice locked in.")

    def on_heat_change(self, value):
        level = int(round(float(value)))
        self.intensity_var.set(level)
        self.heat_label.configure(text=INTENSITY_LABELS.get(level, "Normal"))
        self.save_settings()

    def on_noise_level_change(self, value):
        level = int(round(float(value)))
        level = max(0, min(4, level))
        self.noise_level_var.set(level)
        if hasattr(self, "noise_level_label"):
            self.noise_level_label.configure(
                text=NOISE_LEVEL_LABELS.get(level, "Chaos"),
                text_color=C["success"] if level <= 1 else C["warn"] if level <= 3 else C["danger"],
            )
        if hasattr(self, "noise_hint"):
            self.noise_hint.configure(text=NOISE_LEVEL_HINTS.get(level, ""))
        self.save_settings()

    # =====================================================================
    # Line list ops
    # =====================================================================
    def use_quick_phrase(self, phrase: str):
        self._selected_quick = phrase
        self.set_gen_text(phrase, also_ai=True, also_hud=True)
        if self.auto_copy.get():
            self.safe_copy(phrase)
        else:
            self.push_history(phrase, count=False)
            self.set_status("Loaded — Copy when ready.")

    def copy_quick_out(self):
        self.safe_copy(self.get_gen_text())

    def favorite_quick_out(self):
        t = self.get_gen_text()
        if t:
            self.toggle_favorite(t)

    def _update_quick_out_meter(self):
        text = self.get_gen_text()
        if hasattr(self, "quick_len"):
            self._update_len_label(self.quick_len, text)
        if hasattr(self, "editor_len"):
            self._update_len_label(self.editor_len, text)

    def delete_line(self, phrase: str, confirm: bool = True):
        phrase = (phrase or "").strip()
        if not phrase:
            return
        if confirm and not messagebox.askyesno("Delete", f"Remove this line?\n\n{phrase[:120]}"):
            return

        game = self.game_var.get()
        if phrase in self.favorites:
            self.favorites.remove(phrase)
        self.history = [h for h in self.history if h != phrase]
        self.copy_counts.pop(phrase, None)
        extras = self.custom_quick.get(game, [])
        if phrase in extras:
            self.custom_quick[game] = [p for p in extras if p != phrase]

        stock = set(self.profile()["quick"])
        hidden = list(self.hidden_lines.get(game, []))
        if phrase in stock:
            if phrase not in hidden:
                hidden.append(phrase)
                self.hidden_lines[game] = hidden
        elif phrase in hidden:
            self.hidden_lines[game] = [h for h in hidden if h != phrase]

        if self._selected_quick == phrase:
            self._selected_quick = None
        if self._last_good_line == phrase:
            self._last_good_line = self.history[-1] if self.history else ""
            self.refresh_hud_line()

        self.rebuild_quick_buttons()
        self.refresh_history_ui()
        self.save_settings()
        self.show_toast("Deleted", kind="info")

    def clear_your_lines_menu(self):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Manage lines")
        dlg.geometry("400x260")
        dlg.configure(fg_color=C["bg"])
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.attributes("-topmost", True)

        ctk.CTkLabel(dlg, text="Manage lines", font=f_ui(15, "bold")).pack(pady=(18, 4))
        ctk.CTkLabel(
            dlg, text="Or use ⌫ on any row to delete one line.",
            font=f_ui(11), text_color=C["muted"],
        ).pack(pady=(0, 12))

        def close():
            dlg.grab_release()
            dlg.destroy()

        def clear_personal():
            self.history.clear()
            self.favorites.clear()
            self.copy_counts.clear()
            self.rebuild_quick_buttons()
            self.refresh_history_ui()
            self.save_settings()
            self.show_toast("Cleared stars & recent", kind="info")
            close()

        def clear_all():
            game = self.game_var.get()
            stock = list(self.profile()["quick"])
            extras = list(self.custom_quick.get(game, []))
            kill = set(stock + extras + list(self.favorites) + list(self.history))
            self.favorites = [f for f in self.favorites if f not in kill]
            self.history = [h for h in self.history if h not in kill]
            for p in list(self.copy_counts):
                if p in kill:
                    del self.copy_counts[p]
            self.custom_quick[game] = []
            self.hidden_lines[game] = list(dict.fromkeys(stock + extras))
            self.rebuild_quick_buttons()
            self.refresh_history_ui()
            self.save_settings()
            self.show_toast("All cleared for this game", kind="info")
            close()

        def restore():
            self.hidden_lines[self.game_var.get()] = []
            self.rebuild_quick_buttons()
            self.save_settings()
            self.show_toast("Stock restored", kind="ok")
            close()

        for label, cmd, danger in (
            ("Clear stars & recent", clear_personal, False),
            ("Delete all for this game", clear_all, True),
            ("Restore stock lines", restore, False),
        ):
            ctk.CTkButton(
                dlg, text=label, height=sz(36), font=f_ui(12),
                fg_color=C["danger"] if danger else C["elevated"],
                hover_color="#b91c1c" if danger else C["hover"],
                command=cmd,
            ).pack(fill="x", padx=28, pady=4)
        ctk.CTkButton(
            dlg, text="Cancel", height=sz(32), fg_color=C["surface"], hover_color=C["hover"], command=close,
        ).pack(fill="x", padx=28, pady=(10, 16))

    def push_history(self, text: str, count: bool = True):
        text = text.strip()
        if not text or text.startswith("Backend") or text.startswith("Error") or text.startswith("…"):
            return
        game = self.game_var.get()
        hidden = list(self.hidden_lines.get(game, []))
        if text in hidden:
            self.hidden_lines[game] = [h for h in hidden if h != text]
        if text in self.history:
            self.history.remove(text)
        self.history.append(text)
        self.history = self.history[-20:]
        if count:
            self.copy_counts[text] = self.copy_counts.get(text, 0) + 1
        self._last_good_line = text
        self.refresh_history_ui()
        self.rebuild_quick_buttons()
        self.refresh_hud_line()
        self.save_settings()

    def recopy_history(self, text: str):
        self.safe_copy(text)

    def clear_history(self):
        self.history.clear()
        self.refresh_history_ui()
        self.rebuild_quick_buttons()
        self.save_settings()

    def toggle_favorite(self, text: str):
        text = text.strip()
        if not text:
            return
        if text in self.favorites:
            self.favorites.remove(text)
            self.show_toast("Unstarred", kind="info")
        else:
            self.favorites.insert(0, text)
            self.favorites = self.favorites[:30]
            self.show_toast("Starred", kind="ok")
        self.rebuild_quick_buttons()
        self.refresh_history_ui()
        self.save_settings()

    # =====================================================================
    # Copy / length / toast
    # =====================================================================
    def _update_len_label(self, label: ctk.CTkLabel, text: str):
        lim = self.limit()
        n = len(text or "")
        label.configure(text=f"{n}/{lim}")
        if n > lim:
            label.configure(text_color=C["danger"])
        elif n >= lim - 15:
            label.configure(text_color=C["warn"])
        else:
            label.configure(text_color=C["success"])

    def trim_to_limit(self, text: str) -> str:
        lim = self.limit()
        text = (text or "").strip()
        if len(text) <= lim:
            return text
        trimmed = text[:lim]
        if " " in trimmed:
            trimmed = trimmed.rsplit(" ", 1)[0]
        return trimmed.rstrip("….,;:- ")

    def safe_copy(self, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            self.show_toast("Nothing to copy", kind="warn")
            self.session_streak = 0
            self.update_session_chip()
            return False
        if text.startswith("Backend") or text.startswith("Error") or text.startswith("…"):
            self.show_toast("Can't copy status text", kind="warn")
            return False

        lim = self.limit()
        if len(text) > lim:
            self.copy_badge.configure(text="blocked", text_color=C["danger"])
            self.show_toast(f"Over limit · {len(text)}/{lim}", kind="error")
            if messagebox.askyesno("Over limit", f"{len(text)} / {lim} chars.\n\nCopy trimmed version?"):
                text = self.trim_to_limit(text)
            else:
                self.session_streak = 0
                self.update_session_chip()
                return False

        try:
            pyperclip.copy(text)
        except Exception as e:
            self.show_toast(f"Clipboard failed", kind="error")
            return False

        self._last_good_line = text
        self.push_history(text, count=True)
        self.session_copies += 1
        self.session_streak += 1
        self.session_best_streak = max(self.session_best_streak, self.session_streak)
        self.update_session_chip()

        # First successful copy completes onboarding
        if not self.onboarding_done:
            self.onboarding_done = True
            if hasattr(self, "onboard_card"):
                try:
                    self.onboard_card.pack_forget()
                except Exception:
                    pass
            self.save_settings()

        self.copy_badge.configure(text=f"copied · {len(text)}", text_color=C["success"])
        hype = random.choice(HYPE_LINES) if self.session_streak >= 2 else f"Copied · {len(text)}/{lim}"
        self.show_toast(hype, kind="ok")
        self.set_status(hype)
        self.refresh_hud_line()
        # Keep main editor in sync if copy came from elsewhere
        if self.get_gen_text() != text:
            self.set_gen_text(text, also_ai=False, also_hud=False)
        else:
            self._update_quick_out_meter()
        # Flash Copy buttons (editor + sticky footer)
        for attr in ("sticky_copy_btn", "editor_copy_btn"):
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            try:
                btn.configure(text="✓ Copied")
                self.root.after(
                    900,
                    lambda b=btn: b.configure(text="Copy") if b.winfo_exists() else None,
                )
            except Exception:
                pass
        self.root.title(f"✓ copied  ·  v{APP_VERSION}")
        self.root.after(1200, lambda: self.root.title(f"Chat Helper  ·  v{APP_VERSION}"))
        return True

    def show_toast(self, message: str, kind: str = "ok"):
        if not hasattr(self, "toast"):
            return
        try:
            if not self.toast.winfo_exists():
                return
        except Exception:
            return
        styles = {
            "ok": (C["success_dim"], C["success"]),
            "error": (C["danger_dim"], C["danger"]),
            "warn": ("#422006", C["warn"]),
            "info": (C["elevated"], C["info"]),
        }
        bg, fg = styles.get(kind, styles["info"])
        try:
            self.toast.configure(text=f"  {message}  ", fg_color=bg, text_color=fg, height=sz(30))
            self.toast.pack(fill="x", padx=pad(14), pady=(0, pad(2)), after=self.header)
        except Exception:
            return
        if self._toast_job:
            try:
                self.root.after_cancel(self._toast_job)
            except Exception:
                pass
        self._toast_job = self.root.after(2000, self._hide_toast)

    def _hide_toast(self):
        try:
            if hasattr(self, "toast") and self.toast.winfo_exists():
                self.toast.pack_forget()
                self.toast.configure(height=0)
        except Exception:
            pass
        self._toast_job = None

    def set_status(self, text: str):
        if not hasattr(self, "status_bar"):
            return
        try:
            if self.status_bar.winfo_exists():
                self.status_bar.configure(text=text)
        except Exception:
            pass

    def update_session_chip(self):
        if not hasattr(self, "session_chip"):
            return
        streak = f"  ·  🔥{self.session_streak}" if self.session_streak >= 2 else ""
        self.session_chip.configure(
            text=f"{self.session_copies} copies  ·  {self.session_gens} gens{streak}"
        )

    def _tip_rotate(self):
        if not self._busy and hasattr(self, "status_bar"):
            cur = self.status_bar.cget("text")
            if cur in TIPS or cur in HYPE_LINES or not cur:
                self.status_bar.configure(text=random.choice(TIPS))
        self.root.after(16000, self._tip_rotate)

    # =====================================================================
    # Fun
    # =====================================================================
    def roll_vibe(self):
        """Random mood + heat with playful feedback."""
        mood = random.choice(MOOD_OPTIONS)
        heat = random.randint(0, 2)
        self.mood_var.set(mood)
        self.intensity_var.set(heat)
        if hasattr(self, "heat_slider"):
            self.heat_slider.set(heat)
        self.heat_label.configure(text=INTENSITY_LABELS[heat])
        self.save_settings()
        self.show_toast(f"Vibe · {mood} · {INTENSITY_LABELS[heat]}", kind="info")
        self.set_status(f"Rolled {mood} / {INTENSITY_LABELS[heat]}")

    def surprise_me(self):
        """Random activity + pure noise (no seed echo)."""
        acts = self.profile()["activities"]
        self.activity_var.set(random.choice(acts))
        if hasattr(self, "input_seed"):
            self.input_seed.delete(0, tk.END)
        self.mood_var.set(random.choice(MOOD_OPTIONS[:8]))
        self.set_status(f"Surprise · {self.activity_var.get()} · noise")
        self.generate_noise()

    def jump_clap_back(self):
        """Switch to Reply intent on Chat Generator."""
        try:
            self.tabview.set("Chat Generator")
        except Exception:
            pass
        self.set_intent("reply")
        quick = ""
        if hasattr(self, "quick_they_said"):
            quick = self.quick_they_said.get().strip()
        if quick:
            self.generate_response_from_quick()
            return
        if hasattr(self, "quick_they_said"):
            self.quick_they_said.focus_set()
        self.show_toast("Paste what they said, then Write clap-back", kind="info")

    def jump_recruit_ai(self):
        try:
            self.tabview.set("Chat Generator")
        except Exception:
            pass
        self.set_intent("recruit")
        text = ""
        if hasattr(self, "msg_textbox"):
            text = self.msg_textbox.get("1.0", "end-1c").strip()
        if text:
            self.ai_fit_recruitment()
        else:
            self.show_toast("Pick or write a pitch, then Fit to limit", kind="info")

    # =====================================================================
    # Screen capture + OCR (calibrated chat region)
    # =====================================================================
    def _ocr_status_text(self) -> str:
        if self.chat_region:
            r = self.chat_region
            w = max(0, int(r["right"]) - int(r["left"]))
            h = max(0, int(r["bottom"]) - int(r["top"]))
            engines = []
            if _HAS_TESS:
                engines.append("Tesseract")
            engines.append("local VL (LM Studio)")
            eng = " · ".join(engines)
            return f"Chat area set · {w}×{h}px @ ({r['left']},{r['top']})  ·  OCR: {eng}"
        return "Chat area not set · click Calibrate chat area, then drag over your game chat"

    def _refresh_ocr_status(self, extra: str = ""):
        if not hasattr(self, "ocr_status"):
            return
        base = self._ocr_status_text()
        if extra:
            base = f"{base}  ·  {extra}"
        try:
            self.ocr_status.configure(text=base)
        except Exception:
            pass

    def calibrate_chat_region(self):
        """Fullscreen drag-select to mark the game chat rectangle."""
        if not _HAS_PIL or ImageGrab is None:
            messagebox.showerror("Pillow required", "Install Pillow to capture the screen.")
            return

        was_top = bool(self.always_on_top.get()) if hasattr(self, "always_on_top") else False
        try:
            self.root.attributes("-topmost", False)
            self.root.iconify()
        except Exception:
            pass

        self.root.after(280, lambda: self._open_region_selector(was_top))

    def _open_region_selector(self, restore_top: bool):
        # Virtual screen size (multi-monitor aware on Windows)
        if _HAS_WIN32:
            try:
                left = int(_USER32.GetSystemMetrics(76))   # SM_XVIRTUALSCREEN
                top = int(_USER32.GetSystemMetrics(77))    # SM_YVIRTUALSCREEN
                width = int(_USER32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
                height = int(_USER32.GetSystemMetrics(79)) # SM_CYVIRTUALSCREEN
            except Exception:
                left, top, width, height = 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        else:
            left, top = 0, 0
            width = self.root.winfo_screenwidth()
            height = self.root.winfo_screenheight()

        sel = tk.Toplevel(self.root)
        sel.title("Drag to select chat area · Esc cancel")
        sel.geometry(f"{width}x{height}+{left}+{top}")
        sel.attributes("-topmost", True)
        try:
            sel.attributes("-alpha", 0.28)
        except Exception:
            pass
        sel.configure(bg="#000000")
        sel.overrideredirect(True)

        canvas = tk.Canvas(sel, cursor="cross", bg="#111111", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        canvas.create_text(
            width // 2,
            40,
            text="Drag a box over your GAME CHAT  ·  release to save  ·  Esc to cancel",
            fill="#e8eaed",
            font=(FONT_UI, 16, "bold"),
        )

        state = {"x0": 0, "y0": 0, "rect": None}

        def on_press(event):
            state["x0"], state["y0"] = event.x, event.y
            if state["rect"]:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline="#7c6cff", width=3, fill="#7c6cff", stipple="gray50",
            )

        def on_drag(event):
            if state["rect"]:
                canvas.coords(state["rect"], state["x0"], state["y0"], event.x, event.y)

        def finish(region: Optional[dict]):
            try:
                sel.destroy()
            except Exception:
                pass
            try:
                self.root.deiconify()
                self.root.lift()
                if restore_top:
                    self.root.attributes("-topmost", True)
            except Exception:
                pass
            if region:
                self.chat_region = region
                self.save_settings()
                self._refresh_ocr_status("saved")
                self.show_toast("Chat area calibrated", kind="ok")
                self.set_status(
                    f"Chat region {region['right']-region['left']}×{region['bottom']-region['top']}"
                )
            else:
                self._refresh_ocr_status("cancelled")
                self.show_toast("Calibration cancelled", kind="info")

        def on_release(event):
            x1, y1 = state["x0"], state["y0"]
            x2, y2 = event.x, event.y
            # Canvas coords → screen coords
            abs_left = left + min(x1, x2)
            abs_top = top + min(y1, y2)
            abs_right = left + max(x1, x2)
            abs_bottom = top + max(y1, y2)
            if abs_right - abs_left < 20 or abs_bottom - abs_top < 20:
                messagebox.showwarning("Too small", "Drag a larger box over the chat area.")
                return
            finish({
                "left": int(abs_left),
                "top": int(abs_top),
                "right": int(abs_right),
                "bottom": int(abs_bottom),
            })

        def on_escape(_event=None):
            finish(None)

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        sel.bind("<Escape>", on_escape)
        canvas.focus_set()

    def grab_chat_ocr(self, and_reply: bool = False):
        """Screenshot calibrated region → OCR → They said (optional clap-back)."""
        if self._ocr_busy:
            self.show_toast("OCR already running…", kind="warn")
            return
        if not self.chat_region:
            if messagebox.askyesno(
                "Calibrate first",
                "No chat area is set yet.\n\nCalibrate now? Drag a box over your game chat.",
            ):
                self.calibrate_chat_region()
            return
        if not _HAS_PIL or ImageGrab is None:
            messagebox.showerror("Pillow required", "Install Pillow to capture the screen.")
            return

        self._ocr_busy = True
        self._refresh_ocr_status("capturing…")
        self.set_status("Grabbing chat area…")
        self.copy_badge.configure(text="ocr…", text_color=C["warn"])

        # Briefly get out of the way if overlapping
        was_top = bool(self.always_on_top.get()) if hasattr(self, "always_on_top") else False
        try:
            if was_top:
                self.root.attributes("-topmost", False)
        except Exception:
            pass

        region = dict(self.chat_region)

        def work():
            err = None
            text = ""
            engine = ""
            try:
                time.sleep(0.15)  # let our window drop behind game if needed
                bbox = (
                    int(region["left"]),
                    int(region["top"]),
                    int(region["right"]),
                    int(region["bottom"]),
                )
                img = ImageGrab.grab(bbox=bbox, all_screens=True)
                try:
                    img.save(LAST_OCR_PATH)
                except Exception:
                    pass

                # Prefer Tesseract when present (fast); else local VL model
                text, engine = self._ocr_image(img)
                text = self._clean_ocr_text(text)
                if self.ocr_prefer_last.get():
                    text = self._ocr_pick_reply_line(text)
            except Exception as e:
                err = str(e)

            def done():
                self._ocr_busy = False
                try:
                    if was_top:
                        self.root.attributes("-topmost", True)
                except Exception:
                    pass

                if err:
                    self.show_toast("Capture failed", kind="error")
                    self._refresh_ocr_status(f"error: {err[:40]}")
                    self.copy_badge.configure(text="ready", text_color=C["muted"])
                    return
                if not text:
                    self.show_toast("No text found — recalibrate or install Tesseract", kind="warn")
                    self._refresh_ocr_status("empty · try VL model or Tesseract")
                    self.copy_badge.configure(text="ready", text_color=C["muted"])
                    messagebox.showinfo(
                        "OCR empty",
                        "Couldn't read chat text.\n\n"
                        "Tips:\n"
                        "• Recalibrate tighter on the chat log\n"
                        "• Load a vision model in LM Studio (e.g. Qwen2-VL / Qwen3-VL)\n"
                        "• Or install Tesseract OCR + pip install pytesseract\n\n"
                        f"Last capture saved to:\n{LAST_OCR_PATH}",
                    )
                    return

                self._last_ocr_text = text
                self._fill_they_said(text)
                self._refresh_ocr_status(f"via {engine}")
                self.show_toast(f"OCR · {engine}", kind="ok")
                self.set_status(f"OCR ({engine}): {text[:60]}{'…' if len(text) > 60 else ''}")
                self.copy_badge.configure(text="ready", text_color=C["muted"])
                if and_reply:
                    self.generate_response_from_quick()

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _fill_they_said(self, text: str):
        text = (text or "").strip()
        if hasattr(self, "quick_they_said"):
            self.quick_they_said.delete(0, tk.END)
            self.quick_they_said.insert(0, text)
        if hasattr(self, "input_statement"):
            self.input_statement.delete(0, tk.END)
            self.input_statement.insert(0, text)

    def _preprocess_for_ocr(self, img: "Image.Image") -> "Image.Image":
        """Boost contrast for dark game UIs before Tesseract."""
        try:
            g = ImageOps.grayscale(img)
            # Upscale small regions
            w, h = g.size
            if w < 600 or h < 200:
                scale = 2 if max(w, h) < 900 else 1.5
                g = g.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            g = ImageOps.autocontrast(g)
            g = ImageEnhance.Contrast(g).enhance(1.6)
            g = ImageEnhance.Sharpness(g).enhance(1.4)
            return g
        except Exception:
            return img

    def _ocr_image(self, img: "Image.Image") -> tuple[str, str]:
        """Return (text, engine_name). Tries Tesseract then local VL."""
        # 1) Tesseract
        if _HAS_TESS:
            try:
                pre = self._preprocess_for_ocr(img)
                txt = pytesseract.image_to_string(pre, config="--psm 6")
                txt = (txt or "").strip()
                if txt:
                    return txt, "Tesseract"
            except Exception:
                pass

        # 2) Local vision model via LM Studio (OpenAI-compatible image_url)
        try:
            txt = self._ocr_via_local_vl(img)
            if txt:
                return txt, "local VL"
        except Exception:
            pass

        return "", "none"

    def _ocr_via_local_vl(self, img: "Image.Image") -> str:
        if not _HAS_PIL or base64 is None or io is None:
            return ""
        # Keep payload small + fast for mid-fight OCR
        work = img.convert("RGB")
        w, h = work.size
        max_side = 960
        if max(w, h) > max_side:
            scale = max_side / float(max(w, h))
            work = work.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        work.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"

        sampling = self._sampling_payload("ocr")
        # Smaller images = faster VL; already scaled above
        payload = {
            "model": "local-model",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You read game chat screenshots. Output ONLY the chat text you see, "
                        "one message per line, oldest first / newest last. "
                        "No commentary, no labels, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Transcribe the chat messages in this screenshot. "
                                "Only the player chat lines."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            **sampling,
        }
        r = requests.post(self.api_url, json=payload, timeout=45)
        if r.status_code != 200:
            return ""
        content = r.json()["choices"][0]["message"]["content"]
        return (content or "").strip()

    def _clean_ocr_text(self, raw: str) -> str:
        if not raw:
            return ""
        lines = []
        for part in raw.replace("\r", "\n").split("\n"):
            p = part.strip()
            if not p:
                continue
            # Drop common OCR junk
            if p in {"|", "||", "•", "-", "—"}:
                continue
            if len(p) == 1 and not p.isalnum():
                continue
            lines.append(p)
        return "\n".join(lines).strip()

    def _ocr_pick_reply_line(self, text: str) -> str:
        """Prefer the last substantial chat line for clap-back."""
        if not text:
            return ""
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if not lines:
            return text
        # Walk from bottom for a line that looks like chat (not UI chrome)
        skip_bits = ("online", "friends", "guild", "channel", "say:", "party:", "settings")
        for ln in reversed(lines):
            low = ln.lower()
            if any(s in low for s in skip_bits) and len(ln) < 18:
                continue
            if len(ln) >= 2:
                # Strip leading name prefixes like "PlayerName:" if present
                if ":" in ln[:24]:
                    name, rest = ln.split(":", 1)
                    if len(name) <= 20 and rest.strip():
                        return rest.strip()
                return ln
        return lines[-1]

    # =====================================================================
    # Recruit helpers
    # =====================================================================
    def load_selected_template(self, choice: str):
        self.msg_textbox.delete("1.0", tk.END)
        self.msg_textbox.insert("1.0", choice)
        self.update_counter()

    def update_counter(self, event=None):
        text = self.msg_textbox.get("1.0", "end-1c")
        lim = self.limit()
        length = len(text)
        self.safety_progressbar.set(min(length / max(lim, 1), 1.0))
        self.counter_label.configure(text=f"{length} / {lim}")
        color = C["danger"] if length > lim else C["warn"] if length >= lim - 15 else C["success"]
        self.counter_label.configure(text_color=color)
        self.safety_progressbar.configure(progress_color=color)

    def copy_recruitment(self):
        """Copy the Recruit message box (also syncs Generated line)."""
        if not hasattr(self, "msg_textbox"):
            return
        text = self.msg_textbox.get("1.0", "end-1c").strip()
        if text:
            self.set_gen_text(text, also_ai=True, also_hud=True)
        self.safe_copy(text)

    def recruit_to_editor(self):
        """Push recruit message into Generated line without copying."""
        if not hasattr(self, "msg_textbox"):
            return
        text = self.msg_textbox.get("1.0", "end-1c").strip()
        if not text:
            self.show_toast("Recruit message is empty", kind="warn")
            return
        self.set_gen_text(text, also_ai=True, also_hud=True)
        self.show_toast("In Generated line — Copy when ready", kind="info")

    def save_custom_template(self):
        text = self.msg_textbox.get("1.0", "end-1c").strip()
        if text and text not in self.templates:
            self.templates.append(text)
            self.template_combo.configure(values=self.templates)
            self.save_settings()
            self.show_toast("Preset saved", kind="ok")

    def reset_presets(self):
        if messagebox.askyesno("Reset", "Reset templates to defaults?"):
            self.templates = list(DEFAULT_TEMPLATES)
            self.save_settings()
            self.template_combo.configure(values=self.templates)
            self.load_selected_template(self.templates[0])

    def ai_fit_recruitment(self):
        text = self.msg_textbox.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Empty", "Write or pick a message first.")
            return
        game = self.game_var.get()
        lim = self.limit()
        prompt = (
            f"JOB: guild recruitment rewrite for {game} global/trade chat.\n"
            f"Keep the SAME core offer and facts. Do not invent new benefits.\n"
            f"Sound native to {game}, scannable, not corporate.\n"
            f"HARD LIMIT: under {lim} characters.\n"
            f"Output ONLY the recruitment line.\n\n"
            f"Original:\n{text}"
        )
        self._last_gen_mode = "recruit"
        self.run_llm_async(prompt, on_done=self._apply_recruit_result, job="recruit")

    def _apply_recruit_result(self, reply: str):
        if self._is_err(reply):
            self.show_toast("AI offline", kind="error")
            return
        reply = self._dedupe_against_history(reply)

        def apply():
            if hasattr(self, "msg_textbox"):
                self.msg_textbox.delete("1.0", tk.END)
                self.msg_textbox.insert("1.0", reply)
                self.update_counter()
            self.set_gen_text(reply, also_ai=True, also_hud=True)
            if self.auto_copy.get():
                self.safe_copy(reply)
            else:
                self.push_history(reply, count=False)

        self.ui_safe(apply)

    # =====================================================================
    # LLM — job-split prompts; temp/max_tokens sent in API payload
    # =====================================================================
    def intensity_instruction(self) -> str:
        level = int(self.intensity_var.get())
        if level <= 0:
            return "Tone: friendly, low-drama, welcoming. Zero toxicity."
        if level == 1:
            return "Tone: normal gamer banter. Light edge ok; chat-safe."
        return (
            "Tone: spicy playful — cocky, teasing, meme-y. NOT reportable. "
            "Witty rogue, not abuse."
        )

    def _job_cfg(self, job: str) -> dict:
        return JOB_LLM.get(job, JOB_LLM["banter"])

    def _anti_echo_block(self) -> str:
        recent: list[str] = []
        for h in reversed(self.history[-10:]):
            if h and h not in recent:
                recent.append(h)
        for f in self.favorites[:5]:
            if f and f not in recent:
                recent.append(f)
        if not recent:
            return ""
        previews = "; ".join(r[:50] for r in recent[:8])
        return (
            f"Do NOT reuse or closely paraphrase any of these recent lines: {previews}\n"
        )

    def system_prompt(self, job: str = "banter") -> str:
        lim = self.limit()
        cfg = self._job_cfg(job)

        # Noise is intentionally NOT game-aware — intensity 0..4
        if job == "noise":
            level = int(self.noise_level_var.get()) if hasattr(self, "noise_level_var") else 3
            level = max(0, min(4, level))
            label = NOISE_LEVEL_LABELS.get(level, "Chaos")
            hint = NOISE_LEVEL_HINTS.get(level, "")
            intensity_block = {
                0: "Keep it almost normal small talk. Light wit only. Complete sentence.",
                1: "Mildly odd observation. Still coherent and friendly.",
                2: "Weird absurdist take. Unexpected topic. Still a readable sentence.",
                3: "Strong non-sequitur chaos. Random topic from anywhere. Unhinged but clear.",
                4: (
                    "PURE MENTAL CHAOS. Maximum left-field. Can be a half-thought, a sudden "
                    "one-word shout, or a surreal brain-static line. No need to make sense."
                ),
            }[level]
            base = (
                "You type into multiplayer chat with calibrated randomness.\n"
                f"CHAOS LEVEL: {level}/4 — {label}. {hint}\n"
                f"{intensity_block}\n"
                "Any non-game topic is fair: food, history, animals, objects, nonsense philosophy.\n"
                "ABSOLUTELY FORBIDDEN: game names, LFG, loot, dungeons, guilds, raids, "
                "WB, CZ, M+, ilvl, grinding, meta, or any MMO systems/slang.\n"
                "Not mean/hateful/slurs. Weird is fine; abusive is not.\n"
            )
            base += (
                "RULES:\n"
                "- Output ONLY the chat message. No quotes. No preamble.\n"
                f"- HARD CAP: {lim} characters. Prefer shorter.\n"
                "- No emojis, hashtags, markdown.\n"
                "- One message only.\n"
            )
            base += self._anti_echo_block()
            return base

        game = self.game_var.get()
        prof = self.profile()
        activity = self.activity_var.get()

        base = (
            f"You type as a real player in {game} chat — not an assistant, not a coach.\n"
            f"Game: {prof['vibe']}\n"
            f"Activity context: {activity}.\n"
            f"{prof['avoid']}\n"
        )
        if cfg.get("use_mood"):
            base += f"Personality flavor: {self.mood_var.get()}.\n{self.intensity_instruction()}\n"
        if cfg.get("use_terms"):
            terms = ", ".join(prof["terms"][:10])
            base += f"You may use native shorthand when natural: {terms}.\n"
        if job == "lfg" and hasattr(self, "lfg_target_var"):
            info = self.lfg_target_info()
            base += (
                f"Selected LFG content: {info['label']}. "
                f"The message MUST be about that content only.\n"
            )

        job_rules = {
            "lfg": (
                "JOB: LFG / party call only.\n"
                "Name the exact content the user selected. Clear need + vibe.\n"
                "No life story. No guild recruiting. No mixing unrelated maps/dungeons.\n"
            ),
            "recruit": (
                "JOB: guild/clan recruitment line only.\n"
                "Preserve facts from the user draft. Punchy and scannable.\n"
            ),
            "comeback": (
                "JOB: clap-back / reply to something another player said.\n"
                "React to THEIR line. Do not change the subject to LFG or recruiting.\n"
            ),
            "triple": (
                "JOB: three alternate chat lines as numbered options.\n"
                "Each line must be distinct in tone.\n"
            ),
            "banter": (
                "JOB: casual icebreaker or observation.\n"
                "If a hint is given, treat it as loose vibe only — never quote the hint words.\n"
            ),
            "spice": (
                "JOB: rewrite a line fresher with same intent.\n"
                "Do not copy the original wording.\n"
            ),
            "refine": (
                "JOB: refine the given line as instructed.\n"
                "Keep meaning; change length/tone only as asked.\n"
            ),
        }
        base += job_rules.get(job, job_rules["banter"])
        base += (
            "RULES:\n"
            "- Output ONLY the chat message text. No quotes. No labels. No preamble.\n"
            f"- HARD CAP: {lim} characters. Prefer shorter.\n"
            "- Sound human and typed fast. No emojis, hashtags, markdown.\n"
            "- One message only unless asked for numbered options.\n"
            "- Never start with Chat:/Message:/Reply:/As a player.\n"
        )
        base += self._anti_echo_block()
        return base

    def _sampling_payload(self, job: str) -> dict:
        """
        Full sampling suite for LM Studio / llama.cpp OpenAI-compatible API.
        These override the LM Studio UI sliders when the server accepts them.
        """
        cfg = dict(self._job_cfg(job))
        # Scale noise sampling with chaos slider
        if job == "noise" and hasattr(self, "noise_level_var"):
            level = max(0, min(4, int(self.noise_level_var.get())))
            # 0→cooler / 4→nuclear
            temps = (0.55, 0.80, 1.05, 1.25, 1.45)
            tops = (0.88, 0.92, 0.95, 0.97, 0.99)
            ks = (30, 40, 55, 70, 90)
            cfg["temperature"] = temps[level]
            cfg["top_p"] = tops[level]
            cfg["top_k"] = ks[level]
            cfg["min_p"] = max(0.01, 0.08 - level * 0.015)
            cfg["repeat_penalty"] = 1.05 + level * 0.04
            cfg["frequency_penalty"] = 0.05 + level * 0.08
            cfg["presence_penalty"] = 0.0 + level * 0.08
            cfg["max_tokens"] = 40 + level * 8
        return {
            "temperature": float(cfg.get("temperature", 0.8)),
            "top_p": float(cfg.get("top_p", 0.9)),
            "top_k": int(cfg.get("top_k", 40)),
            "min_p": float(cfg.get("min_p", 0.05)),
            "repeat_penalty": float(cfg.get("repeat_penalty", 1.1)),
            "frequency_penalty": float(cfg.get("frequency_penalty", 0.0)),
            "presence_penalty": float(cfg.get("presence_penalty", 0.0)),
            "max_tokens": int(cfg.get("max_tokens", 80)),
            "stream": False,
        }

    def call_local_llm(self, user_prompt: str, n: int = 1, job: str = "banter") -> list[str]:
        lim = self.limit()
        use_job = "triple" if n > 1 else job
        content = user_prompt
        if n > 1:
            content = (
                user_prompt
                + f"\n\nGive exactly {n} different options as:\n1. line\n2. line\n3. line\n"
                f"Each under {lim} characters. No extra commentary."
            )

        sampling = self._sampling_payload(use_job)
        payload = {
            "model": "local-model",
            "messages": [
                {"role": "system", "content": self.system_prompt(use_job)},
                {"role": "user", "content": content},
            ],
            **sampling,
        }
        try:
            r = requests.post(self.api_url, json=payload, timeout=25)
            if r.status_code != 200:
                return [f"Error: HTTP {r.status_code}"]
            raw = r.json()["choices"][0]["message"]["content"].strip()
            if n > 1:
                return self._parse_numbered(raw, n, lim)
            return [self._clean_line(raw, lim)]
        except Exception:
            return ["Backend offline. Start LM Studio on port 1234."]

    def _clean_line(self, raw: str, lim: int) -> str:
        line = raw.strip().strip('"').strip("'")
        for prefix in (
            "Chat:", "Message:", "Reply:", "Option:", "Output:",
            "As a player:", "Player:", "Line:",
        ):
            if line.lower().startswith(prefix.lower()):
                line = line[len(prefix):].strip()
        for part in line.splitlines():
            p = part.strip().lstrip("0123456789).- ").strip()
            if p:
                line = p
                break
        line = line.replace('"', "").replace("“", "").replace("”", "").replace("‘", "").replace("’", "'")
        if len(line) > lim:
            line = self.trim_to_limit(line)
        return line

    def _parse_numbered(self, raw: str, n: int, lim: int) -> list[str]:
        lines = []
        for part in raw.splitlines():
            p = part.strip()
            if not p:
                continue
            cleaned = self._clean_line(p.lstrip("0123456789").lstrip(".)-:— ").strip(), lim)
            if cleaned and cleaned not in lines and not self._is_err(cleaned):
                lines.append(cleaned)
            if len(lines) >= n:
                break
        if not lines:
            lines = [self._clean_line(raw, lim)]
        while len(lines) < n:
            lines.append(lines[-1])
        return lines[:n]

    def _is_err(self, text: str) -> bool:
        return bool(text) and (
            text.startswith("Backend") or text.startswith("Error") or text.startswith("…")
        )

    def _noise_level(self) -> int:
        try:
            return max(0, min(4, int(self.noise_level_var.get())))
        except Exception:
            return 3

    def _noise_pool(self) -> list[str]:
        """Lines available at current chaos level (weighted toward the top tier)."""
        level = self._noise_level()
        pool: list[str] = []
        for lv in range(0, level + 1):
            lines = NOISE_PACKS.get(lv, [])
            # Weight higher tiers more heavily
            weight = 1 + (lv * 2) if lv == level else 1
            pool.extend(lines * weight)
        recent = set(self.history[-20:])
        fresh = [p for p in pool if p not in recent]
        return fresh or pool or list(NOISE_PACKS.get(0, ["yo"]))

    def _pick_noise_local(self) -> str:
        lim = self.limit()
        line = random.choice(self._noise_pool())
        if len(line) > lim:
            line = self.trim_to_limit(line)
        return line

    def _noise_is_too_gamey(self, line: str) -> bool:
        """Reject model output that slipped into MMO speak."""
        if not line:
            return True
        low = line.lower()
        banned = (
            "lfg", "lfm", "loot", "dungeon", "raid", "guild", "ilvl", "mythic",
            "world boss", " wb ", "wb ", " cz ", "fractal", "black zone", "gank",
            "quinfall", "wow ", "albion", "m+", "looking for group", "need 1 more",
            "party up", "invite me", "pst ",
        )
        # pad short tokens
        padded = f" {low} "
        return any(b in padded or b in low for b in banned)

    def _dedupe_against_history(self, line: str, fallback: Optional[str] = None) -> str:
        """If model echoed a recent line, use fallback (or noise for ambient jobs)."""
        if not line or self._is_err(line):
            return line
        norm = line.strip().lower()
        for h in self.history[-12:]:
            if h and h.strip().lower() == norm:
                if fallback:
                    return fallback
                # Only ambient noise should auto-swap to the noise pack
                if getattr(self, "_last_gen_mode", "") == "noise":
                    return self._pick_noise_local()
                return line
        return line

    def _strip_hint_echo(self, line: str, hint: str) -> str:
        """If output is basically the hint list, replace with local noise."""
        if not line or not hint or self._is_err(line):
            return line
        # Whole-hint echo
        if hint.strip().lower() in line.lower() and len(hint) > 8:
            # allow partial; only reject if line is mostly the hint
            if len(line) <= len(hint) + 12:
                return self._pick_noise_local()
        # Seed list style: "a, b, c"
        if "," in hint:
            parts = [p.strip().lower() for p in hint.split(",") if p.strip()]
            hits = sum(1 for p in parts if p and p in line.lower())
            if parts and hits >= max(2, len(parts) // 2):
                return self._pick_noise_local()
        return line

    def run_llm_async(
        self,
        prompt: str,
        on_done: Optional[Callable[[str], None]] = None,
        n: int = 1,
        job: str = "banter",
    ):
        if self._busy:
            self.set_status("Already generating…")
            return
        self._busy = True
        self.set_status("Thinking…")
        self.copy_badge.configure(text="thinking", text_color=C["warn"])

        def work():
            results = self.call_local_llm(prompt, n=n, job=job)

            def finish():
                self._busy = False
                self.session_gens += 1
                self.update_session_chip()

                def apply():
                    if on_done:
                        on_done(results[0] if results else "")
                    else:
                        self._show_ai_result(results[0] if results else "")

                self.ui_safe(apply)

            self.root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def _apply_line_to_outputs(self, reply: str, also_ai: bool = True):
        """Push a good line into the generated-line editor (+ optional Wingman)."""
        if self._is_err(reply):
            self.show_toast("AI offline — try Noise for offline lines", kind="error")
            self.copy_badge.configure(text="offline", text_color=C["danger"])
            return

        def apply():
            self.set_gen_text(reply, also_ai=also_ai, also_hud=True)
            self._last_variants = [reply]
            self._set_variant_buttons([reply])
            if self.auto_copy.get():
                self.safe_copy(reply)
            else:
                self.push_history(reply, count=False)
                self.copy_badge.configure(text="ready", text_color=C["warn"])
                self.set_status("Ready — edit above, then Copy.")

        self.ui_safe(apply)

    def _show_ai_result(self, reply: str):
        if not self._is_err(reply):
            reply = self._dedupe_against_history(reply)
        self._last_variants = [reply]
        self._set_variant_buttons([reply])
        if not self._is_err(reply):
            self.set_gen_text(reply, also_ai=True, also_hud=True)
            if self.auto_copy.get():
                self.safe_copy(reply)
            else:
                self.push_history(reply, count=False)
                self.copy_badge.configure(text="ready", text_color=C["warn"])
                self.set_status("Ready — edit above, then Copy.")
        else:
            if hasattr(self, "ai_output"):
                self.ai_output.delete("1.0", tk.END)
                self.ai_output.insert(tk.END, reply)
                self.update_ai_counter()
            self.show_toast("AI offline", kind="error")
            self.copy_badge.configure(text="offline", text_color=C["danger"])

    def _show_multi_results(self, results: list[str]):
        cleaned = []
        for r in results:
            if self._is_err(r):
                cleaned.append(r)
            else:
                cleaned.append(self._dedupe_against_history(r))
        self._last_variants = cleaned
        self._set_variant_buttons(cleaned)
        if cleaned:
            self._show_ai_result(cleaned[0])

    def _set_variant_buttons(self, results: list[str]):
        if not hasattr(self, "variant_btns"):
            return
        for i, btn in enumerate(self.variant_btns):
            if i < len(results) and not self._is_err(results[i]):
                preview = results[i] if len(results[i]) < 68 else results[i][:65] + "…"
                btn.configure(text=f"{i + 1}  {preview}", state="normal")
            else:
                btn.configure(text=f"Option {i + 1}", state="disabled")

    def pick_variant(self, idx: int):
        if 0 <= idx < len(self._last_variants):
            text = self._last_variants[idx]

            def apply():
                self.set_gen_text(text, also_ai=True, also_hud=True)
                self.safe_copy(text)

            self.ui_safe(apply)

    def update_ai_counter(self, event=None):
        self._update_quick_out_meter()

    def copy_ai_output(self):
        self.copy_quick_out()

    def favorite_ai_output(self):
        self.favorite_quick_out()

    def trim_ai_output(self):
        self.trim_gen_editor()

    def _current_output_line(self) -> str:
        return self.get_gen_text()

    def refine_shorter(self):
        text = self._current_output_line()
        if not text or self._is_err(text):
            return
        self._last_gen_mode = "refine"
        lim = max(20, int(self.limit() * 0.7))
        self.run_llm_async(
            f"Rewrite MUCH shorter (under {lim} chars), same meaning:\n{text}",
            job="refine",
        )

    def refine_safer(self):
        text = self._current_output_line()
        if not text or self._is_err(text):
            return
        self._last_gen_mode = "refine"
        self.run_llm_async(
            f"Rewrite friendlier and guild-safe, still natural:\n{text}",
            job="refine",
        )

    def refine_spicier(self):
        text = self._current_output_line()
        if not text or self._is_err(text):
            return
        self._last_gen_mode = "refine"
        self.run_llm_async(
            f"Rewrite with more playful spice. Not reportable. One line:\n{text}",
            job="refine",
        )

    def generate_activity_line(self):
        """Explicit ACTIVITY CHAT job — not LFG. Presence/banter for current activity."""
        self._last_gen_mode = "banter"
        game = self.game_var.get()
        activity = self.activity_var.get()
        mood = self.mood_var.get() if hasattr(self, "mood_var") else "Casual Gamer"
        lim = self.limit()
        seed = ""
        if hasattr(self, "input_seed"):
            seed = self.input_seed.get().strip()

        prompt = (
            f"JOB: activity chat line for {game} — NOT an LFG, NOT recruiting a party.\n"
            f"Player is hanging out in: {activity}.\n"
            f"Mood flavor: {mood}.\n"
            f"Write ONE natural global/zone chat line (observation, greeting, joke, status).\n"
            f"Do NOT start with LFG/LFM. Do NOT ask for group members.\n"
            f"Do NOT pitch a guild. Sound like a player typing live.\n"
            f"Under {lim} characters. No quotes. No emoji.\n"
        )
        if seed:
            prompt += f"Loose vibe only (do NOT quote these words): {seed}\n"

        def done(reply: str):
            if self._is_err(reply):
                self._show_ai_result(reply)
                return
            reply = self._strip_hint_echo(reply, seed)
            reply = self._dedupe_against_history(reply)
            # Soft guard: if model still wrote LFG, try one local reframe via status
            low = reply.lower()
            if low.startswith("lfg") or low.startswith("lfm") or "looking for group" in low:
                reply = f"Anyone else on {activity} right now?"
                if len(reply) > lim:
                    reply = self.trim_to_limit(reply)
            self._apply_line_to_outputs(reply, also_ai=True)
            self.set_status(f"Activity · {activity} · {mood}")

        self.run_llm_async(prompt, on_done=done, job="banter")

    def generate_banter(self):
        """Wingman banter — same intent as activity line (not LFG)."""
        self.generate_activity_line()

    def random_seed_and_banter(self):
        """Dice roll: invent banter without putting seed words in the UI box."""
        if hasattr(self, "input_seed"):
            self.input_seed.delete(0, tk.END)
        pick = random.choice(self.profile()["banter_seeds"])
        self._last_gen_mode = "banter"
        game = self.game_var.get()
        activity = self.activity_var.get()
        prompt = (
            f"Write ONE short {game} chat icebreaker for {activity}.\n"
            f"Loose vibe/intent (do NOT quote or list these words): {pick}\n"
            f"Invent a natural line. Not a template."
        )
        self.run_llm_async(prompt, job="banter")

    def generate_noise(self):
        """Non-game noise scaled by chaos slider (0 sane → 4 mental)."""
        self._last_gen_mode = "noise"
        level = self._noise_level()
        label = NOISE_LEVEL_LABELS.get(level, "Chaos")
        topic_sparks = random.sample(
            [
                "tacos", "Stalin", "geese", "dentists", "the moon", "soup", "Napoleon",
                "raccoons", "floppy disks", "sharks", "balloons", "pigeons", "frogs",
                "taxes", "cereal", "ghosts", "library books", "refrigerators", "penguins",
                "wheels", "wifi", "moths", "sandwiches", "clouds", "cows", "bread",
                "spoons", "ovens", "socks", "naps", "grocery lists",
            ],
            k=4,
        )
        energy = {
            0: "Normal human chat. Mild and coherent.",
            1: "Slightly odd, still friendly.",
            2: "Weird absurdist angle.",
            3: "Strong non-sequitur. Left field.",
            4: "Maximum mental chaos. Half-thoughts and sudden shouts OK.",
        }[level]
        prompt = (
            f"Write ONE chat line at chaos level {level}/4 ({label}).\n"
            f"Energy: {energy}\n"
            "NOT about video games, LFG, loot, dungeons, or MMOs.\n"
            f"Topic sparks (invent something new, do not list them): {', '.join(topic_sparks)}.\n"
            "Short. One line. Chat-safe weird, not hateful."
        )

        def done(reply: str):
            if self._is_err(reply):
                reply = self._pick_noise_local()
                self.show_toast("Offline noise pack", kind="info")
            elif self._noise_is_too_gamey(reply):
                reply = self._pick_noise_local()
                self.show_toast("Too gamey — pack", kind="info")
            else:
                reply = self._dedupe_against_history(reply, fallback=self._pick_noise_local())
                if self._noise_is_too_gamey(reply):
                    reply = self._pick_noise_local()
            self._apply_line_to_outputs(reply, also_ai=True)
            self.set_status(f"Noise · {label} ({level}/4)")

        # Higher chaos → more local pack (true random); sane → prefer model tone
        local_chance = 0.20 + level * 0.12
        if random.random() < local_chance:
            line = self._pick_noise_local()
            self.session_gens += 1
            self.update_session_chip()
            self._apply_line_to_outputs(line, also_ai=True)
            self.set_status(f"Noise · {label} pack")
            return

        self.run_llm_async(prompt, on_done=done, job="noise")

    def generate_response(self):
        user_input = self.input_statement.get().strip()
        if not user_input and hasattr(self, "quick_they_said"):
            user_input = self.quick_they_said.get().strip()
        if not user_input:
            messagebox.showwarning("Empty", "Paste what they said first.")
            return
        self._generate_comeback(user_input)

    def generate_response_from_quick(self):
        user_input = ""
        if hasattr(self, "quick_they_said"):
            user_input = self.quick_they_said.get().strip()
        if not user_input and hasattr(self, "input_statement"):
            user_input = self.input_statement.get().strip()
        if not user_input:
            messagebox.showwarning("Empty", "Paste what they said first.")
            return
        if hasattr(self, "input_statement"):
            self.input_statement.delete(0, tk.END)
            self.input_statement.insert(0, user_input)
        self._generate_comeback(user_input)

    def _generate_comeback(self, user_input: str):
        self._last_gen_mode = "comeback"
        game = self.game_var.get()
        activity = self.activity_var.get()
        prompt = (
            f"Someone in {game} chat ({activity}) said:\n\"{user_input}\"\n\n"
            f"Write ONE natural clap-back / reply as a fellow player.\n"
            f"React to what they said. Do not LFG or recruit unless they asked."
        )
        self.run_llm_async(prompt, job="comeback")

    def generate_triple(self):
        user_input = self.input_statement.get().strip()
        if not user_input and hasattr(self, "quick_they_said"):
            user_input = self.quick_they_said.get().strip()
        seed = self.input_seed.get().strip() if hasattr(self, "input_seed") else ""
        game = self.game_var.get()
        activity = self.activity_var.get()
        self._last_gen_mode = "triple"
        if user_input:
            prompt = (
                f"Someone in {game} ({activity}) said:\n\"{user_input}\"\n\n"
                f"Three DIFFERENT replies:\n"
                f"1 = safe/helpful\n2 = funny\n3 = spicy playful\n"
                f"Each must answer them. No LFG unless they asked."
            )
            job = "triple"
        elif seed:
            prompt = (
                f"Three different original {game} icebreakers for {activity}.\n"
                f"Loose vibe only (do NOT quote): {seed}"
            )
            job = "triple"
        else:
            prompt = f"Three different original {game} icebreakers for {activity}. Invent freely."
            job = "triple"

        if self._busy:
            return
        self._busy = True
        self.set_status("Cooking 3 options…")
        self.copy_badge.configure(text="thinking", text_color=C["warn"])

        def thinking():
            if hasattr(self, "ai_output"):
                self.ai_output.delete("1.0", tk.END)
                self.ai_output.insert(tk.END, "…")

        self.ui_safe(thinking)

        def work():
            results = self.call_local_llm(prompt, n=3, job=job)

            def finish():
                self._busy = False
                self.session_gens += 1
                self.update_session_chip()
                self.ui_safe(lambda: self._show_multi_results(results))

            self.root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def regenerate_last(self):
        mode = self._last_gen_mode
        if mode == "comeback":
            self.generate_response()
        elif mode == "triple":
            self.generate_triple()
        elif mode == "recruit":
            self.ai_fit_recruitment()
        elif mode == "lfg":
            self.generate_lfg()
        elif mode == "noise":
            self.generate_noise()
        elif mode == "spice" and self._selected_quick:
            self.spice_phrase(self._selected_quick)
        elif mode == "refine":
            text = self._current_output_line()
            if text and not self._is_err(text):
                self.run_llm_async(
                    f"Different alternative, same intent:\n{text}",
                    job="refine",
                )
            else:
                self.generate_banter()
        else:
            self.generate_banter()

    def _lfg_local_line(self) -> str:
        """Offline / fallback LFG built from target samples + need."""
        info = self.lfg_target_info()
        need = self.lfg_need_var.get() if hasattr(self, "lfg_need_var") else "Anyone"
        samples = list(info.get("samples") or [f"LFG {info.get('label', 'group')}"])
        base = random.choice(samples)
        label = info.get("label", "")
        # Light need seasoning without wrecking sample quality
        if need == "Need 1 more" and "1" not in base.lower() and "need" not in base.lower():
            base = f"{base.rstrip(' .')} — need 1 more"
        elif need == "Need a couple" and "couple" not in base.lower():
            base = f"{base.rstrip(' .')} — need a couple"
        elif need == "Chill only" and "chill" not in base.lower():
            base = f"{base.rstrip(' .')} — chill only"
        elif need == "Full group" and "full" not in base.lower():
            base = f"LFG full group for {label}" if label else base
        lim = self.limit()
        if len(base) > lim:
            base = self.trim_to_limit(base)
        return base

    def _lfg_line_ok(self, line: str, info: dict) -> bool:
        """Reject nonsense / wrong-content LFG lines."""
        if not line or self._is_err(line):
            return False
        low = line.lower()
        # Must reference the target somehow
        aliases = [a.lower() for a in info.get("aliases", []) if a]
        label = (info.get("label") or "").lower()
        if label and label not in aliases:
            aliases.append(label)
        # Also accept key tokens from must_name
        must = (info.get("must_name") or "").lower()
        for token in must.replace(",", " ").replace(" or ", " ").split():
            token = token.strip()
            if len(token) >= 2 and token not in aliases:
                aliases.append(token)
        if aliases and not any(a in low for a in aliases if len(a) >= 2):
            return False
        # Must not drag in forbidden other content
        for bad in info.get("never") or []:
            b = bad.lower()
            if not b:
                continue
            # Allow if the forbidden term is part of the chosen label
            if b in label:
                continue
            if b in low:
                return False
        # Reject assistant-y garbage
        for bad_start in ("sure", "here", "of course", "as a", "i can", "try this"):
            if low.startswith(bad_start):
                return False
        return True

    def _build_lfg_prompt(self) -> str:
        game = self.game_var.get()
        lim = self.limit()
        info = self.lfg_target_info()
        need = self.lfg_need_var.get() if hasattr(self, "lfg_need_var") else "Anyone"
        need_hint = LFG_NEED_HINTS.get(need, need)
        never = ", ".join(info.get("never") or []) or "other games' content"
        samples = info.get("samples") or []
        sample_block = "\n".join(f"  - {s}" for s in samples[:3])
        return (
            f"Write ONE LFG/LFM chat line for {game}.\n"
            f"CONTENT (required): {info['label']}\n"
            f"What it is: {info.get('brief', info['label'])}\n"
            f"You MUST clearly name this content using natural player words "
            f"(e.g. related to: {info.get('must_name', info['label'])}).\n"
            f"Need / party shape: {need} — {need_hint}.\n"
            f"Shape: LFG or LFM + content name + need + optional chill vibe.\n"
            f"DO NOT mention or mix in: {never}.\n"
            f"DO NOT recruit for a guild. DO NOT write a joke that skips the content name.\n"
            f"DO NOT invent other dungeons/maps. Stay on {info['label']} only.\n"
            f"Under {lim} characters. One line. No quotes. No emoji.\n"
            f"Good shape examples (vary wording, do not copy exactly):\n{sample_block}"
        )

    def generate_lfg(self):
        self._last_gen_mode = "lfg"
        self.sync_lfg_target_if_needed()
        # Persist current selection as this game's default
        self.on_lfg_target_changed(self.lfg_target_var.get())
        info = self.lfg_target_info()
        prompt = self._build_lfg_prompt()

        def done(reply: str):
            if self._is_err(reply) or not self._lfg_line_ok(reply, info):
                # Retry once with a stricter reminder, else local sample
                if not self._is_err(reply):
                    # wrong content — use local pack rather than nonsense
                    reply = self._lfg_local_line()
                    self.show_toast(f"LFG · {info['label']} (tuned)", kind="info")
                else:
                    reply = self._lfg_local_line()
                    self.show_toast("Offline LFG pack", kind="info")
            else:
                reply = self._dedupe_against_history(reply)
                # If dedupe swapped to noise, fix it
                if not self._lfg_line_ok(reply, info):
                    reply = self._lfg_local_line()
            self._apply_line_to_outputs(reply, also_ai=True)
            self.set_status(f"LFG · {info['label']} · {self.lfg_need_var.get()}")

        self.run_llm_async(prompt, on_done=done, job="lfg")

    def spice_phrase(self, phrase: str):
        self._last_gen_mode = "spice"
        self._selected_quick = phrase
        game = self.game_var.get()
        activity = self.activity_var.get()

        def done(reply: str):
            if not self._is_err(reply):
                reply = self._dedupe_against_history(reply)
            self._apply_line_to_outputs(reply, also_ai=True)

        self.run_llm_async(
            f"Rewrite this {game} line fresher for {activity}. Same intent. One line.\n"
            f"Do not copy wording.\n\n{phrase}",
            on_done=done,
            job="spice",
        )

    def spice_selected_quick(self):
        text = self.get_gen_text() or self._selected_quick
        if not text:
            messagebox.showinfo("Pick one", "Generate or type a line in the editor first.")
            return
        self.spice_phrase(text)

    def pulse_llm_status(self):
        gen = self._llm_pulse_gen

        def check():
            if gen != self._llm_pulse_gen:
                return
            ok = False
            try:
                base = self.api_url.rsplit("/v1/", 1)[0]
                ok = requests.get(base + "/v1/models", timeout=1.5).status_code == 200
            except Exception:
                ok = False

            def apply():
                if gen != self._llm_pulse_gen:
                    return
                if not hasattr(self, "llm_dot"):
                    return
                try:
                    if not self.llm_dot.winfo_exists():
                        return
                    if ok:
                        self.llm_dot.configure(text="● live", text_color=C["success"])
                    else:
                        self.llm_dot.configure(text="● offline", text_color=C["danger"])
                except Exception:
                    return

            try:
                self.root.after(0, apply)
                if gen == self._llm_pulse_gen:
                    self.root.after(8000, lambda: threading.Thread(target=check, daemon=True).start())
            except Exception:
                pass

        threading.Thread(target=check, daemon=True).start()


if __name__ == "__main__":
    root = ctk.CTk()
    app = GamersChatHelper(root)
    root.mainloop()
