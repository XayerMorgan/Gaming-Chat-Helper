"""
Gamer's Chat Helper — local AI companion for MMO chat.
Calm companion UI: one job (right line → under limit → paste), zero clutter.
"""

from __future__ import annotations

import json
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import Counter
from tkinter import messagebox
from typing import Callable, Match, Optional

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
APP_VERSION = "6.5"

# LM Studio (OpenAI-compatible local server defaults)
LM_DEFAULT_LOCAL_HOST = "127.0.0.1:1234"
LM_DEFAULT_PORT = "1234"
LM_MODE_OPTIONS = ("Local", "Remote")

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
# Steam GetNumberOfCurrentPlayers is GLOBAL only (one AppID for Quinfall).
# NA / Europe / Asia below are prime-time slices of that global series (evening hours
# in each region’s timezone) — not separate Steam region servers.
STEAM_REGION_ORDER = ("NA", "Europe", "Asia")
STEAM_REGIONS = {
    "NA": {
        "label": "NA",
        "long": "North America",
        "tz": "America/New_York",
        "utc_offset_std": -5,  # fallback if zoneinfo unavailable
        "prime_hours": (17, 18, 19, 20, 21, 22, 23),  # local evening
        "off_hours": (3, 4, 5, 6, 7, 8, 9),
    },
    "Europe": {
        "label": "EU",
        "long": "Europe",
        "tz": "Europe/Berlin",
        "utc_offset_std": 1,
        "prime_hours": (17, 18, 19, 20, 21, 22, 23),
        "off_hours": (3, 4, 5, 6, 7, 8, 9),
    },
    "Asia": {
        "label": "Asia",
        "long": "Asia",
        "tz": "Asia/Shanghai",
        "utc_offset_std": 8,
        "prime_hours": (17, 18, 19, 20, 21, 22, 23),
        "off_hours": (3, 4, 5, 6, 7, 8, 9),
    },
}
STEAM_REGION_FOCUS_OPTIONS = ("All", "NA", "Europe", "Asia")
CONFIG_FILE = "chat_helper_config.json"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, CONFIG_FILE)
ASSETS_DIR = os.path.join(APP_DIR, "assets")
GAMES_ASSETS_DIR = os.path.join(ASSETS_DIR, "games")
LAST_OCR_PATH = os.path.join(APP_DIR, "last_chat_capture.png")
LAST_MARKET_PATH = os.path.join(APP_DIR, "last_market_capture.png")
STEAM_LOG_PATH = os.path.join(APP_DIR, "steam_players_log.txt")
ECONOMY_LOG_PATH = os.path.join(APP_DIR, "economy_price_log.jsonl")
SESSION_EXPORT_PATH = os.path.join(APP_DIR, "session_export.txt")
HELP_MANUAL_PATH = os.path.join(APP_DIR, "HELP_MANUAL.md")
FEATURES_PATH = os.path.join(APP_DIR, "FEATURES.md")
RECRUIT_TEMPLATES_PATH = os.path.join(APP_DIR, "recruit_templates.json")
RECRUIT_PLACEHOLDER = "(type a guild pitch below)"
MACROS_MAX = 3

# ---------------------------------------------------------------------------
# Context help (F1) — short per-tab blurbs; full manual is HELP_MANUAL.md
# ---------------------------------------------------------------------------
HELP_CONTEXT = {
    "Chat Generator": (
        "CHAT GENERATOR\n\n"
        "Write the right line under the game’s character limit, then Copy and paste in-game.\n\n"
        "• Intents: LFG · Activity · Reply · Recruit · Noise\n"
        "• Advanced Tweaks: Mood, Heat, LFG Need\n"
        "• Reply: Set chat box → Grab chat (OCR) → Write clap-back\n"
        "• F6 = Write current intent · F7 = Copy (if Keys is on)\n"
        "• AI · on needs LM Studio local server; offline packs still work if AI is off\n\n"
        "Open Help → Full Manual for the complete guide."
    ),
    "Library": (
        "LIBRARY\n\n"
        "Your history and favorites live here.\n\n"
        "• Click a line to re-copy\n"
        "• Star to pin favorites\n"
        "• Delete to forget\n"
        "• Manage stock for built-in game lines\n\n"
        "Open Help → Full Manual for more."
    ),
    "Calculator": (
        "CALCULATOR\n\n"
        "Simple pad with thousand separators (1,000,000).\n\n"
        "• Click pad buttons, or turn ⌨ Keys: On to use the keyboard\n"
        "• Keys mode only works while this tab is selected\n"
        "• Keys: Off leaves the keyboard free for the rest of the app\n"
        "• Enter = equals · Esc = clear · Backspace = delete\n\n"
        "Open Help → Full Manual for more."
    ),
    "Economy": (
        "ECONOMY · MARKET SNAP\n\n"
        "There is no public Quinfall market API. This tab prices from a screenshot.\n\n"
        "1. Optional: type My item + Undercut %\n"
        "2. Set market area (drag over listings)\n"
        "3. Snap + price (F8) — needs vision model for best results\n"
        "4. Re-price last shot (F9) without a new screenshot\n"
        "5. Flip profit · WTS macros · price log\n\n"
        "Advice only uses comps visible in the image.\n"
        "Open Help → Full Manual for the full Economy section."
    ),
    "Setup": (
        "SETUP\n\n"
        "• Restart app (also top-right header)\n"
        "• Type size\n"
        "• House style — per-game notes for AI prompts\n"
        "• Steam population log + chart (click Players chip anytime)\n"
        "• Peak/min markers and real time on the chart X-axis\n\n"
        "Open Help → Full Manual for troubleshooting and file list."
    ),
}

HELP_SHORTCUTS_TEXT = (
    "KEYBOARD SHORTCUTS\n\n"
    "App (header Keys checkbox on, window focused):\n"
    "  F1   Context help for current tab\n"
    "  F6   Write current Chat Generator intent\n"
    "  F7   Copy generated line\n"
    "  F8   Economy · Snap + price\n"
    "  F9   Economy · Re-price last shot\n"
    "  F10  Oracle\n"
    "  Ctrl+E   Export session pack\n"
    "  Ctrl+ / Ctrl− / Ctrl+0   Type size\n"
    "  Esc  Exit HUD\n\n"
    "Calculator tab (Keys: On only):\n"
    "  0–9 · numpad · + − * / · Enter · Backspace · Esc\n\n"
    "Menu: Help → Full Manual for everything else."
)

FULL_GEOMETRY = "900x700"
HUD_GEOMETRY = "480x248"
# Allow tall/narrow “vertical” windows without clipping the header tools
FULL_MINSIZE = (420, 560)
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
            "The Quinfall is an open-world MMO. Chat is short and practical: grinding, loot, "
            "dungeons (DG), world bosses (WB), combat zones (CZ), guild vibes, light banter. "
            "Players use heavy shorthand — always decode it correctly."
        ),
        # General chat flavor words (not the acronym map — see vocab)
        "terms": [
            "grind", "loot", "XP", "party", "LFG", "guild", "chill", "gg", "mats",
            "DG", "WB", "CZ", "TP",
        ],
        # Canonical shorthand → meaning (used by vocabulary normalizer + AI prompts)
        "vocab": {
            "DG": "Dungeon (instanced dungeon run)",
            "DGs": "Dungeons",
            "DUNG": "Dungeon",
            "WB": "World Boss",
            "CZ": "Combat Zone",
            "LFG": "Looking For Group",
            "LFM": "Looking For More (need players)",
            "LF": "Looking For",
            "WTS": "Want To Sell",
            "WTB": "Want To Buy",
            "WTT": "Want To Trade",
            "TP": "Teleport (travel cost / TP fee — not Trading Post)",
            "XP": "Experience / leveling",
            "EXP": "Experience / leveling",
            "MATS": "Crafting materials",
            "PF": "Party Finder",
            "PST": "Please Send Tell / whisper me",
            "INV": "Invite",
        },
        "avoid": (
            "Do NOT invent other MMOs' systems (mythic+, fractals, black zones, ilvl, etc.). "
            "ALWAYS understand Quinfall shorthand when reading chat: DG=Dungeon, WB=World Boss, "
            "CZ=Combat Zone, TP=Teleport cost. "
            "When YOU write an LFG: only use WB/CZ if that content was selected; DG is valid for Dungeon. "
            "Prefer natural Quinfall player language over wrong cross-game jargon."
        ),
        "activities": [
            "General Chat", "Leveling / Grind", "Dungeon", "Trading",
            "Guild Chat", "Recruiting", "Hanging Out",
        ],
        # Content = general activity type. Location = open-world spot OR dungeon name.
        # Quinfall instanced dungeons live in Location (not Content).
        "lfg_default": "EXP / Loot Grind",
        "lfg_locations_default": [
            # Open-world / grind spots
            "Cemetery",
            "Arachnid Temple",
            # Instanced dungeons (1 Content "Dungeon" → many location names)
            "Foaming Catacombs",
            "Deepest Maze",
            "Quiet Chambers",
            "Grim Point",
        ],
        "lfg_location_default": "Cemetery",
        "lfg_targets": {
            "EXP / Loot Grind": {
                "must_name": "grind, EXP, XP, leveling, or loot",
                "aliases": ["grind", "exp", "xp", "level", "loot"],
                "brief": "EXP / loot grind — use Location for the farm spot; do NOT say WB or CZ",
                "never": ["world boss", "WB", "CZ", "combat zone", "recruiting", "mythic+", "DG"],
                "samples": [
                    "LFG Loot / XP Grind @ Cemetery",
                    "LFG XP grind @ Arachnid Temple",
                    "LFG loot grind — chill pace",
                ],
            },
            "Dungeon": {
                "must_name": "dungeon, DG, or the dungeon location name",
                "aliases": ["dungeon", "dung", "dg", "dgs", "instance"],
                "brief": (
                    "dungeon clear / party — players often write DG for dungeon. "
                    "ALWAYS name the selected Location "
                    "(Foaming Catacombs, Deepest Maze, Quiet Chambers, or Grim Point). "
                    "Valid forms: LFG DG @ Grim Point · LFG Dungeon @ … · LFG Grim Point"
                ),
                "never": ["world boss", "WB", "CZ", "combat zone", "mythic+"],
                "samples": [
                    "LFG DG @ Foaming Catacombs — chill clear, need 1 more",
                    "LFG Dungeon @ Deepest Maze — looking for a couple",
                    "LFM Quiet Chambers DG, all welcome",
                    "LFG Grim Point — need 1 more",
                    "LFG DG Grim Point in Party Finder — chill only",
                ],
            },
            "World Boss": {
                "must_name": "world boss or WB",
                "aliases": ["world boss", "WB", "wb"],
                "brief": "world boss group — players almost always write WB. ONLY when user selected World Boss",
                "never": ["dungeon clear", "DG", "mythic+", "CZ", "combat zone"],
                "samples": [
                    "LFG WB when up — chill group",
                    "WB soon? need a few more",
                    "WB group forming, hop in if free",
                ],
            },
            "Combat Zone": {
                "must_name": "combat zone or CZ",
                "aliases": ["cz", "combat zone"],
                "brief": "combat zone group — players write CZ. ONLY when user selected Combat Zone",
                "never": ["world boss", "WB", "DG", "mythic+"],
                "samples": [
                    "LFG CZ — need a couple more",
                    "Anyone for CZ, chill",
                    "CZ run? looking for a few",
                ],
            },
        },
        "quick": [
            # Generic presence / activity appearance (not wrong jargon)
            "gg",
            "o/",
            "back",
            "brb",
            "chill vibes only",
            "nice one",
            "glhf",
            "anyone else grinding?",
            "loot go brrr",
            "one more pull then snack",
            "guild chat is my second home",
            "taking it slow today",
            "LFG Loot / XP Grind @ Cemetery",
            "LFG XP grind @ Arachnid Temple — chill",
            "LFG Dungeon @ Foaming Catacombs — need 1 more",
            "LFG Dungeon @ Deepest Maze — chill clear",
            "LFG Dungeon @ Quiet Chambers, looking for a couple",
            "LFG Dungeon @ Grim Point — all welcome",
            "WTS mats / craft — whisper",
            "new here, any early tips?",
            "afk 2 sec",
        ],
        "banter_seeds": [
            "the grind", "loot luck", "queue life", "guild vibes",
            "snack breaks", "late night sessions", "RNG", "hanging out",
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
        "vocab": {
            "M+": "Mythic+ dungeon key",
            "MYTHIC+": "Mythic+ dungeon key",
            "LFG": "Looking For Group",
            "LFM": "Looking For More",
            "ILVL": "Item level",
            "WQ": "World Quest",
            "WQS": "World Quests",
            "AH": "Auction House",
            "PST": "Please Send Tell / whisper",
            "BG": "Battleground",
            "WB": "World Boss",
            "INV": "Invite",
            "BIS": "Best in slot",
        },
        "avoid": "Do not invent Quinfall/Albion-specific systems. Stay WoW-native. Decode M+/ilvl/WQ correctly.",
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
        "vocab": {
            "BZ": "Black Zone (full-loot open world)",
            "RZ": "Red Zone",
            "YZ": "Yellow Zone",
            "IP": "Item Power",
            "GVG": "Guild vs Guild",
            "ZVZ": "Zerg vs Zerg",
            "LFG": "Looking For Group",
            "LFM": "Looking For More",
            "WTS": "Want To Sell",
            "WTB": "Want To Buy",
            "INV": "Invite",
        },
        "avoid": "No WoW raid/M+ talk. Stay Albion risk/reward language. Decode BZ/IP/ZvZ correctly.",
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
        "vocab": {
            "WVW": "World vs World",
            "LFG": "Looking For Group",
            "LFM": "Looking For More",
            "CM": "Challenge Mode",
            "META": "Map meta event / train",
            "TAG": "Commander tag / squad lead",
            "INV": "Invite",
            "WP": "Waypoint",
        },
        "avoid": "Avoid other-MMO systems. Use GW2 event/meta language. Decode WvW/CM/meta correctly.",
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
        "vocab": {
            "LFG": "Looking For Group",
            "LFM": "Looking For More",
            "WTS": "Want To Sell",
            "WTB": "Want To Buy",
            "GG": "Good game",
            "INV": "Invite",
        },
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

# Stock recruit presets — left empty so users write their own guild pitch.
# (Previously shipped with sample "Defiants" lines; those are no longer defaults.)
DEFAULT_TEMPLATES: list[str] = []

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
    # Fresh wording of an existing pitch (higher novelty; same facts)
    "recruit_variant": {
        "temperature": 0.88, "top_p": 0.93, "top_k": 50, "min_p": 0.04,
        "repeat_penalty": 1.14, "frequency_penalty": 0.28, "presence_penalty": 0.12,
        "max_tokens": 100, "use_mood": True, "use_terms": True,
    },
    # Replies: cooler sampling = more human, less tryhard / superlative
    "comeback": {
        "temperature": 0.58, "top_p": 0.86, "top_k": 32, "min_p": 0.08,
        "repeat_penalty": 1.08, "frequency_penalty": 0.12, "presence_penalty": 0.04,
        "max_tokens": 48, "use_mood": True, "use_terms": False,
    },
    "triple": {
        "temperature": 0.72, "top_p": 0.90, "top_k": 40, "min_p": 0.06,
        "repeat_penalty": 1.10, "frequency_penalty": 0.18, "presence_penalty": 0.08,
        "max_tokens": 140, "use_mood": True, "use_terms": False,
    },
    "banter": {
        "temperature": 0.90, "top_p": 0.92, "top_k": 50, "min_p": 0.05,
        "repeat_penalty": 1.10, "frequency_penalty": 0.20, "presence_penalty": 0.10,
        "max_tokens": 70, "use_mood": True, "use_terms": False,
    },
    "spice": {
        "temperature": 0.90, "top_p": 0.92, "top_k": 50, "min_p": 0.05,
        "repeat_penalty": 1.12, "frequency_penalty": 0.25, "presence_penalty": 0.12,
        "max_tokens": 70, "use_mood": True, "use_terms": False,
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
    # Market screen read + price advice (vision or text)
    "economy": {
        "temperature": 0.25, "top_p": 0.88, "top_k": 30, "min_p": 0.05,
        "repeat_penalty": 1.05, "frequency_penalty": 0.05, "presence_penalty": 0.0,
        "max_tokens": 420, "use_mood": False, "use_terms": False,
    },
    # Clean dad jokes — room for full setup + punchline (models were truncating)
    "dadjoke": {
        "temperature": 0.92, "top_p": 0.93, "top_k": 50, "min_p": 0.05,
        "repeat_penalty": 1.12, "frequency_penalty": 0.25, "presence_penalty": 0.12,
        "max_tokens": 160, "use_mood": False, "use_terms": False,
    },
}

# Hard cap for dad jokes (independent of game limit when tighter)
DAD_JOKE_LIMIT = 150

# Classic structures the model should imitate (rotated into the user prompt)
DAD_JOKE_PATTERNS = (
    "setup → short punchline (one beat)",
    "What do you call … ? / Why did the … ?",
    "I used to … then … (pun twist)",
    "anti-joke / underwhelming literal answer",
    "wordplay on a common object (food, job, animal)",
    "two-sentence: statement, then the groan",
    "I'm not saying … I'm just saying …",
    "dad correction / wise-guy reframe of a simple fact",
)

# Words that make replies sound like a bot / hype account — soft-reject
REPLY_HYPE_MARKERS = (
    "legendary", "absolutely", "insanely", "goated", "goat", "king", "queen",
    "slaps", "crushed it", "fire emoji", "🔥", "amazing", "incredible",
    "unbelievable", "phenomenal", "spectacular", "masterpiece", "iconic",
    "best ever", "literally perfect", "so proud of you", "main character",
    "ate and left", "no cap", "periodt", "slay", "queen energy", "huge W",
    "massive W", "absolute unit", "chef's kiss", "living legend",
)

# Clean dad jokes only — family-safe, under 150 chars (offline pack).
DAD_JOKES = [
    "I only know 25 letters of the alphabet. I don't know y.",
    "I'm reading a book on anti-gravity. It's impossible to put down.",
    "Why don't eggs tell jokes? They'd crack each other up.",
    "I used to hate facial hair… then it grew on me.",
    "Parallel lines have so much in common. It's a shame they'll never meet.",
    "I asked my dog what's two minus two. He said nothing.",
    "What do you call a fake noodle? An impasta.",
    "I would tell you a construction joke, but I'm still working on it.",
    "Why did the scarecrow win an award? He was outstanding in his field.",
    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
    "What do you call cheese that isn't yours? Nacho cheese.",
    "I used to be addicted to soap, but I'm clean now.",
    "Why can't you give Elsa a balloon? Because she will let it go.",
    "I'm terrified of elevators, so I'm taking steps to avoid them.",
    "What did the ocean say to the beach? Nothing, it just waved.",
    "I only know how to make alphabet soup… letter by letter.",
    "Why did the bicycle fall over? It was two-tired.",
    "I don't trust stairs. They're always up to something.",
    "What do you call a bear with no teeth? A gummy bear.",
    "I used to play piano by ear, but now I use my hands.",
    "Why did the golfer bring two pairs of pants? In case he got a hole in one.",
    "I told a joke about a roof. It went over everyone's head.",
    "What's brown and sticky? A stick.",
    "I know a lot of jokes about inactive volcanoes. They just don't erupt.",
    "Why don't skeletons fight each other? They don't have the guts.",
    "I named my dog Five Miles so I can say I walk Five Miles every day.",
    "What do you call a sleeping bull? A bulldozer.",
    "I asked the librarian if the library had books on paranoia. She whispered, they're right behind you.",
    "Why did the cookie go to the doctor? Because it felt crummy.",
    "I'm on a seafood diet. I see food and I eat it.",
    "What do you call a fish wearing a bowtie? Sofishticated.",
    "I used to be a banker but I lost interest.",
    "Why can't your nose be 12 inches long? Because then it would be a foot.",
    "I ordered a chicken and an egg online. I'll let you know which comes first.",
    "What did one wall say to the other? I'll meet you at the corner.",
    "I don't trust atoms. They make up everything.",
    "Why did the math book look sad? It had too many problems.",
    "I'm reading a horror story in braille. Something bad is about to happen… I can feel it.",
    "What do you call a parade of rabbits hopping backwards? A receding hare-line.",
    "I told my computer I needed a break, and it said no problem — it would go to sleep.",
    "Why do cows have hooves instead of feet? Because they lactose.",
    "I tried to catch fog yesterday. Mist.",
    "What do you call a factory that sells passable products? A satisfactory.",
    "I was going to tell a time-traveling joke, but you didn't like it.",
    "Why did the tomato turn red? Because it saw the salad dressing.",
    "I have a joke about pizza, but it's too cheesy.",
    "What do you call an alligator in a vest? An investigator.",
    "My belt holds my pants up, but the belt loops hold my belt up. I don't know who to trust.",
    "Why don't oysters donate to charity? Because they're shellfish.",
    "I used to hate facial recognition software… then it grew on me. Wait, wrong joke.",
    "How does a penguin build its house? Igloos it together.",
    "I got a job at a bakery because I kneaded dough.",
    "What's the best thing about Switzerland? I don't know, but the flag is a big plus.",
    "I would avoid the sushi if I was you. It's a little fishy.",
    "Why did the coffee file a police report? It got mugged.",
    "I only tell dad jokes on special occasions… like when people ask me to stop.",
]

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


def _valid_region_dict(raw) -> Optional[dict]:
    """Normalize a screen region dict or return None."""
    if not isinstance(raw, dict):
        return None
    try:
        if not all(k in raw for k in ("left", "top", "right", "bottom")):
            return None
        return {
            "left": int(raw["left"]),
            "top": int(raw["top"]),
            "right": int(raw["right"]),
            "bottom": int(raw["bottom"]),
        }
    except Exception:
        return None


# Keys stored per game under config["game_settings"][game_name]
GAME_SETTING_KEYS = (
    "chat_region",
    "market_region",
    "activity",
    "lfg_target",
    "lfg_location",
    "lfg_need",
    "lfg_party_finder",
    "economy_item",
    "economy_undercut",
    "flip_fee",
    "macros",
    "ocr_prefer_last_line",
    "mood",
    "intensity",
    "noise_level",
    # Optional override; None = use GAME_PROFILES steam_appid (incl. non-Steam)
    "steam_appid",
)


class HoverTip:
    """Simple delayed tooltip for CTk/Tk widgets (hover help)."""

    def __init__(self, widget, text: str, delay_ms: int = 400):
        self.widget = widget
        self.text = (text or "").strip()
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip: Optional[tk.Toplevel] = None
        self._bound = False
        self._bind()

    def set_text(self, text: str):
        """Update tooltip text without stacking more event bindings."""
        self.text = (text or "").strip()
        if self.text and not self._bound:
            self._bind()

    def _bind(self):
        if self._bound or not self.text:
            return
        try:
            self.widget.bind("<Enter>", self._schedule, add="+")
            self.widget.bind("<Leave>", self._cancel, add="+")
            self.widget.bind("<ButtonPress>", self._cancel, add="+")
            self._bound = True
        except Exception:
            pass

    def _schedule(self, _event=None):
        if not self.text:
            return
        self._cancel()
        try:
            self._after_id = self.widget.after(self.delay_ms, self._show)
        except Exception:
            pass

    def _cancel(self, _event=None):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._hide()

    def _show(self):
        self._hide()
        if not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            win = tk.Toplevel(self.widget)
            win.wm_overrideredirect(True)
            win.wm_attributes("-topmost", True)
            win.configure(bg=C["elevated"])
            frame = tk.Frame(win, bg=C["line"], bd=0)
            frame.pack(padx=1, pady=1)
            lbl = tk.Label(
                frame,
                text=self.text,
                justify="left",
                bg=C["elevated"],
                fg=C["text"],
                font=(FONT_UI, 10),
                padx=10,
                pady=7,
                wraplength=320,
            )
            lbl.pack()
            win.wm_geometry(f"+{x}+{y}")
            self._tip = win
        except Exception:
            self._tip = None

    def _hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def tip(widget, text: str) -> HoverTip:
    """Attach or update a hover tip. Reuses an existing tip on the same widget."""
    existing = getattr(widget, "_hover_tip", None)
    if isinstance(existing, HoverTip):
        existing.set_text(text)
        return existing
    ht = HoverTip(widget, text)
    try:
        widget._hover_tip = ht  # type: ignore[attr-defined]
    except Exception:
        pass
    return ht


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
        # Threads must not touch Tk after mainloop ends / window closes
        self._alive = True
        # Thread-safe UI marshal: workers put callables here; main thread drains via after()
        self._ui_queue: queue.Queue = queue.Queue()
        self._ui_pump_started = False
        self._llm_pulse_gen = 0
        self._llm_online = None  # None=unknown, True/False from probe
        self._steam_pulse_gen = 0
        self.house_styles: dict[str, str] = dict(getattr(self, "saved_house_styles", {}) or {})
        self._steam_player_count: Optional[int] = None
        self._steam_last_log_ts: dict[int, float] = {}  # appid -> unix when last written
        self._steam_history: list[tuple[float, int]] = []  # (unix, players) for current game chart
        # Recruit pitches live in recruit_templates.json (create / edit / delete)
        if not hasattr(self, "recruit_templates"):
            self.recruit_templates: list[dict] = []
        if not hasattr(self, "_recruit_selected_id"):
            self._recruit_selected_id: Optional[str] = None
        self.steam_log_enabled = tk.BooleanVar(value=bool(getattr(self, "saved_steam_log_enabled", True)))
        self.steam_log_minutes = tk.IntVar(value=int(getattr(self, "saved_steam_log_minutes", 15)))
        _reg = str(getattr(self, "saved_steam_region_focus", "All") or "All")
        if _reg not in STEAM_REGION_FOCUS_OPTIONS:
            _reg = "All"
        self.steam_region_focus = tk.StringVar(value=_reg)

        self.game_var = tk.StringVar(value=self.default_game)
        self.lm_mode_var = tk.StringVar(value=getattr(self, "lm_mode", "Local") or "Local")
        self.lm_host_var = tk.StringVar(
            value=getattr(self, "lm_host", LM_DEFAULT_LOCAL_HOST) or LM_DEFAULT_LOCAL_HOST
        )
        self.lm_api_key_var = tk.StringVar(value=getattr(self, "lm_api_key", "") or "")
        self.lm_model_var = tk.StringVar(value=getattr(self, "lm_model", "") or "")
        self.mood_var = tk.StringVar(value=self.saved_mood)
        self.activity_var = tk.StringVar(value=self.saved_activity)
        self.intensity_var = tk.IntVar(value=self.saved_intensity)
        self.noise_level_var = tk.IntVar(value=int(getattr(self, "saved_noise_level", 3)))
        self.always_on_top = tk.BooleanVar(value=self.saved_on_top)
        self.auto_copy = tk.BooleanVar(value=self.saved_auto_copy)
        self.hud_mode = tk.BooleanVar(value=self.saved_hud)
        self.font_scale_var = tk.StringVar(value=self.font_scale_key)
        self.lfg_defaults: dict[str, str] = dict(self.saved_lfg_defaults)
        self.lfg_locations: dict[str, list[str]] = dict(self.saved_lfg_locations)
        self.lfg_location_defaults: dict[str, str] = dict(self.saved_lfg_location_defaults)
        self.lfg_target_var = tk.StringVar(
            value=self._resolve_lfg_target(self.default_game, self.saved_lfg_target)
        )
        self.lfg_need_var = tk.StringVar(
            value=self.saved_lfg_need if self.saved_lfg_need in LFG_NEED_OPTIONS else "Anyone"
        )
        loc0 = self._resolve_lfg_location(self.default_game, self.saved_lfg_location)
        self.lfg_location_var = tk.StringVar(value=loc0)
        self.lfg_party_finder = tk.BooleanVar(value=bool(self.saved_lfg_party_finder))
        self.chat_region: Optional[dict] = dict(self.saved_chat_region) if self.saved_chat_region else None
        self.market_region: Optional[dict] = (
            dict(self.saved_market_region) if getattr(self, "saved_market_region", None) else None
        )
        self.ocr_prefer_last = tk.BooleanVar(value=bool(self.saved_ocr_prefer_last))
        self._last_ocr_text = ""
        self._last_market_text = ""
        self._last_economy_suggest = ""
        self._last_economy_wts = ""
        self._ocr_busy = False
        self._economy_busy = False
        self.economy_item_var = tk.StringVar(value=str(getattr(self, "saved_economy_item", "") or ""))
        self.economy_undercut_var = tk.StringVar(
            value=str(getattr(self, "saved_economy_undercut", "5") or "5")
        )
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
        self._session_steam_peak: Optional[int] = None
        self._session_steam_peak_ts: float = 0.0
        self._clip_watch_last = ""
        self._clip_watch_job = None
        self.focus_mode = tk.BooleanVar(value=bool(getattr(self, "saved_focus_mode", False)))
        self.hotkeys_enabled = tk.BooleanVar(value=bool(getattr(self, "saved_hotkeys_enabled", True)))
        self.clip_watch_enabled = tk.BooleanVar(value=bool(getattr(self, "saved_clip_watch", True)))
        self.macro_slots: list[str] = list(getattr(self, "saved_macros", ["", "", ""]) or ["", "", ""])
        while len(self.macro_slots) < MACROS_MAX:
            self.macro_slots.append("")
        self.economy_history: list[dict] = list(getattr(self, "saved_economy_history", []) or [])[-40:]
        self.flip_buy_var = tk.StringVar(value="")
        self.flip_sell_var = tk.StringVar(value="")
        self.flip_fee_var = tk.StringVar(value=str(getattr(self, "saved_flip_fee", "5") or "5"))

        self.create_ui()
        self.assets.apply_window_icon(self.root)
        self.build_menubar()
        self.apply_startup_geometry()
        self.apply_on_top()
        self.on_game_changed(self.game_var.get(), persist=False)
        self.sync_activity_if_needed()
        self.sync_lfg_target_if_needed()
        # Write migrated multi-game bags + active snapshot (no status toast)
        try:
            self._snapshot_game_settings(self.game_var.get())
            self.save_settings()
        except Exception:
            pass
        self.pulse_llm_status()
        self.pulse_steam_players()
        self.refresh_history_ui()
        self.refresh_hud_line()
        self.update_session_chip()
        self._tip_rotate()
        self._bind_surprise_hotkeys()
        self._start_clip_watch()
        self.root.after(600, self._oracle_boot_whisper)
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
        self.root.bind("<F1>", lambda e: self.open_context_help())
        self.root.bind("<KeyPress-F1>", lambda e: self.open_context_help())
        self.root.after(200, self._cache_hwnd)
        self._start_ui_queue_pump()

    # =====================================================================
    # Config
    # =====================================================================
    def load_settings(self):
        self.game_limits = {g: p["limit"] for g, p in GAME_PROFILES.items()}
        self.templates = list(DEFAULT_TEMPLATES)
        self.recruit_templates: list[dict] = []
        self._recruit_selected_id: Optional[str] = None
        # Prefer 127.0.0.1 — on Windows, "localhost" often tries IPv6 (::1) first and
        # times out the status probe even when LM Studio is healthy on IPv4.
        self.api_url = f"http://{LM_DEFAULT_LOCAL_HOST}/v1/chat/completions"
        self.lm_mode = "Local"  # Local | Remote
        self.lm_host = LM_DEFAULT_LOCAL_HOST
        self.lm_api_key = ""
        self.lm_model = ""  # empty → use first loaded model from /v1/models
        self._lm_models_cache: list[str] = []
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
        self.saved_steam_region_focus = "All"
        self.saved_lfg_target = "EXP / Loot Grind"
        self.saved_lfg_need = "Anyone"
        self.saved_lfg_defaults: dict[str, str] = {}
        self.saved_lfg_locations: dict[str, list[str]] = {}
        self.saved_lfg_location_defaults: dict[str, str] = {}
        self.saved_lfg_location = "Cemetery"
        self.saved_lfg_party_finder = True
        self.saved_chat_region: Optional[dict] = None
        self.saved_market_region: Optional[dict] = None
        self.saved_economy_item = ""
        self.saved_economy_undercut = "5"
        self.saved_ocr_prefer_last = True
        self.saved_generator_intent = "lfg"
        self.saved_show_advanced = False
        self.saved_onboarding_done = False
        self.saved_house_styles: dict[str, str] = {}
        # Per-game bags (chat/market regions, LFG, economy, macros, …)
        self.game_settings: dict[str, dict] = {}
        self._active_game_for_settings: Optional[str] = None

        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.game_limits.update(data.get("limits", {}))
                # Flat list kept in sync with recruit_templates.json (legacy config key)
                self.templates = data.get("templates", self.templates) or list(DEFAULT_TEMPLATES)
                self.api_url = self._normalize_api_url(
                    data.get("api_url", self.api_url) or self.api_url
                )
                mode_raw = str(data.get("lm_mode", "") or "").strip()
                if mode_raw.lower() == "remote":
                    self.lm_mode = "Remote"
                elif mode_raw.lower() == "local":
                    self.lm_mode = "Local"
                else:
                    # Infer from saved URL if mode not set yet
                    host_guess = self._host_from_api_url(self.api_url)
                    self.lm_mode = (
                        "Local"
                        if host_guess.startswith("127.0.0.1") or "localhost" in host_guess.lower()
                        else "Remote"
                    )
                host_saved = str(data.get("lm_host", "") or "").strip()
                self.lm_host = host_saved or self._host_from_api_url(self.api_url) or LM_DEFAULT_LOCAL_HOST
                self.lm_api_key = str(data.get("lm_api_key", "") or "")
                self.lm_model = str(data.get("lm_model", "") or "").strip()
                # Keep api_url aligned with host/mode
                self.api_url = self._api_url_from_host(self.lm_host)
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
                self.saved_lfg_locations = data.get("lfg_locations", {}) or {}
                self.saved_lfg_location_defaults = data.get("lfg_location_defaults", {}) or {}
                self.saved_lfg_location = data.get("lfg_location", self.saved_lfg_location)
                self.saved_lfg_party_finder = bool(data.get("lfg_party_finder", True))
                cr = _valid_region_dict(data.get("chat_region"))
                if cr:
                    self.saved_chat_region = cr
                mr = _valid_region_dict(data.get("market_region"))
                if mr:
                    self.saved_market_region = mr
                self.saved_economy_item = str(data.get("economy_item", "") or "")[:120]
                self.saved_economy_undercut = str(data.get("economy_undercut", "5") or "5")[:8]
                self.saved_ocr_prefer_last = bool(data.get("ocr_prefer_last_line", True))
                gi = data.get("generator_intent", "lfg")
                self.saved_generator_intent = gi if gi in INTENT_OPTIONS else "lfg"
                self.saved_show_advanced = bool(data.get("show_advanced", False))
                self.saved_onboarding_done = bool(data.get("onboarding_done", False))
                self.saved_focus_mode = bool(data.get("focus_mode", False))
                self.saved_hotkeys_enabled = bool(data.get("hotkeys_enabled", True))
                self.saved_clip_watch = bool(data.get("clip_watch", True))
                macros = data.get("macros") or []
                if isinstance(macros, list):
                    self.saved_macros = [str(m)[:200] for m in macros][:MACROS_MAX]
                    while len(self.saved_macros) < MACROS_MAX:
                        self.saved_macros.append("")
                eh = data.get("economy_history") or []
                if isinstance(eh, list):
                    self.saved_economy_history = [x for x in eh if isinstance(x, dict)][-40:]
                self.saved_flip_fee = str(data.get("flip_fee", "5") or "5")[:8]
                self.saved_steam_log_enabled = bool(data.get("steam_log_enabled", True))
                try:
                    sm = int(data.get("steam_log_minutes", 15))
                except Exception:
                    sm = 15
                if sm not in STEAM_LOG_INTERVAL_CHOICES:
                    sm = 15
                self.saved_steam_log_minutes = sm
                srf = str(data.get("steam_region_focus", "All") or "All")
                self.saved_steam_region_focus = (
                    srf if srf in STEAM_REGION_FOCUS_OPTIONS else "All"
                )
                hs = data.get("house_styles") or {}
                if isinstance(hs, dict):
                    self.saved_house_styles = {
                        str(k): str(v)[:500] for k, v in hs.items() if str(v).strip()
                    }
                # Per-game settings bags (Steam + non-Steam)
                gs = data.get("game_settings") or {}
                if isinstance(gs, dict):
                    cleaned: dict[str, dict] = {}
                    for gname, bag in gs.items():
                        if not isinstance(bag, dict):
                            continue
                        gkey = str(gname)
                        if gkey not in GAME_PROFILES:
                            # Keep unknown games so custom profiles aren't lost
                            cleaned[gkey] = dict(bag)
                        else:
                            cleaned[gkey] = dict(bag)
                    self.game_settings = cleaned
                if self.default_game not in GAME_PROFILES:
                    self.default_game = "The Quinfall"
            except Exception:
                pass

        # Fold legacy single-slot fields into per-game bags (one-time migration)
        self._migrate_legacy_into_game_settings()

        # Recruit statements: prefer local recruit_templates.json (migrate from config once)
        self._load_or_migrate_recruit_templates()

    def save_settings(self):
        try:
            geo = self.root.geometry()
            if self.hud_mode.get():
                self._hud_geometry = geo
            else:
                self._full_geometry = geo
        except Exception:
            pass

        # Keep flat list in config as a backup mirror of the local recruit file
        self._sync_templates_flat()

        # Keep api_url derived from LM host so chat/OCR use the same endpoint
        try:
            self._sync_api_url_from_ui(save=False)
        except Exception:
            pass

        data = {
            "limits": self.game_limits,
            "templates": self.templates,
            "api_url": self.api_url,
            "lm_mode": (
                self.lm_mode_var.get()
                if hasattr(self, "lm_mode_var")
                else getattr(self, "lm_mode", "Local")
            ),
            "lm_host": (
                (self.lm_host_var.get() or "").strip()
                if hasattr(self, "lm_host_var")
                else getattr(self, "lm_host", LM_DEFAULT_LOCAL_HOST)
            ),
            "lm_api_key": (
                (self.lm_api_key_var.get() or "").strip()
                if hasattr(self, "lm_api_key_var")
                else getattr(self, "lm_api_key", "")
            ),
            "lm_model": (
                (self.lm_model_var.get() or "").strip()
                if hasattr(self, "lm_model_var")
                else getattr(self, "lm_model", "")
            ),
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
            "lfg_locations": getattr(self, "lfg_locations", self.saved_lfg_locations),
            "lfg_location_defaults": getattr(
                self, "lfg_location_defaults", self.saved_lfg_location_defaults
            ),
            "lfg_location": (
                self.lfg_location_var.get()
                if hasattr(self, "lfg_location_var")
                else self.saved_lfg_location
            ),
            "lfg_party_finder": bool(
                self.lfg_party_finder.get()
                if hasattr(self, "lfg_party_finder")
                else self.saved_lfg_party_finder
            ),
            # Legacy single-slot fields stay filled from the *active* game for older builds
            "chat_region": getattr(self, "chat_region", self.saved_chat_region),
            "market_region": getattr(self, "market_region", self.saved_market_region),
            "economy_item": (
                self.economy_item_var.get().strip()[:120]
                if hasattr(self, "economy_item_var")
                else getattr(self, "saved_economy_item", "")
            ),
            "economy_undercut": (
                self.economy_undercut_var.get().strip()[:8]
                if hasattr(self, "economy_undercut_var")
                else getattr(self, "saved_economy_undercut", "5")
            ),
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
            "steam_region_focus": (
                self.steam_region_focus.get()
                if hasattr(self, "steam_region_focus")
                else getattr(self, "saved_steam_region_focus", "All")
            ),
            "house_styles": self._house_styles_for_save(),
            "focus_mode": bool(
                self.focus_mode.get() if hasattr(self, "focus_mode")
                else getattr(self, "saved_focus_mode", False)
            ),
            "hotkeys_enabled": bool(
                self.hotkeys_enabled.get() if hasattr(self, "hotkeys_enabled")
                else getattr(self, "saved_hotkeys_enabled", True)
            ),
            "clip_watch": bool(
                self.clip_watch_enabled.get() if hasattr(self, "clip_watch_enabled")
                else getattr(self, "saved_clip_watch", True)
            ),
            "macros": list(getattr(self, "macro_slots", ["", "", ""]))[:MACROS_MAX],
            "economy_history": list(getattr(self, "economy_history", []))[-40:],
            "flip_fee": (
                self.flip_fee_var.get().strip()[:8]
                if hasattr(self, "flip_fee_var")
                else getattr(self, "saved_flip_fee", "5")
            ),
            # Canonical multi-game store (Steam + non-Steam)
            "game_settings": self._game_settings_for_save(),
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _house_styles_for_save(self) -> dict[str, str]:
        styles = dict(getattr(self, "house_styles", None) or getattr(self, "saved_house_styles", {}) or {})
        # Capture current editor text for the game the box is editing
        try:
            if hasattr(self, "house_style_box"):
                game = getattr(self, "_house_style_game", None) or (
                    self.game_var.get() if hasattr(self, "game_var") else ""
                )
                if game:
                    txt = self.house_style_box.get("1.0", "end").strip()
                    if txt:
                        styles[game] = txt[:500]
                    elif game in styles:
                        del styles[game]
        except Exception:
            pass
        return {k: str(v)[:500] for k, v in styles.items() if str(v).strip()}

    def house_style_for(self, game: Optional[str] = None) -> str:
        game = game or (self.game_var.get() if hasattr(self, "game_var") else "")
        styles = getattr(self, "house_styles", None) or getattr(self, "saved_house_styles", {}) or {}
        return str(styles.get(game, "") or "").strip()[:500]

    # ------------------------------------------------------------------
    # Per-game configuration (Steam + non-Steam)
    # ------------------------------------------------------------------
    def _migrate_legacy_into_game_settings(self):
        """
        One-time fold of flat chat_region / market_region / economy / macros
        into game_settings[default_game] so multi-game switching works.
        Existing per-game bags win; legacy fills only missing keys.
        """
        if not isinstance(getattr(self, "game_settings", None), dict):
            self.game_settings = {}

        # Ensure every known profile has a bag
        for gname in GAME_PROFILES:
            self.game_settings.setdefault(gname, {})

        active = getattr(self, "default_game", None) or "The Quinfall"
        bag = dict(self.game_settings.get(active) or {})

        def _set_if_missing(key, value):
            if value is None or value == "" or value == []:
                return
            if key not in bag or bag.get(key) in (None, "", {}, []):
                bag[key] = value

        _set_if_missing("chat_region", getattr(self, "saved_chat_region", None))
        _set_if_missing("market_region", getattr(self, "saved_market_region", None))
        _set_if_missing("economy_item", getattr(self, "saved_economy_item", ""))
        _set_if_missing("economy_undercut", getattr(self, "saved_economy_undercut", "5"))
        _set_if_missing("flip_fee", getattr(self, "saved_flip_fee", "5"))
        _set_if_missing("activity", getattr(self, "saved_activity", None))
        _set_if_missing("mood", getattr(self, "saved_mood", None))
        _set_if_missing("intensity", getattr(self, "saved_intensity", None))
        _set_if_missing("noise_level", getattr(self, "saved_noise_level", None))
        _set_if_missing("lfg_need", getattr(self, "saved_lfg_need", None))
        _set_if_missing("lfg_party_finder", getattr(self, "saved_lfg_party_finder", None))
        _set_if_missing("ocr_prefer_last_line", getattr(self, "saved_ocr_prefer_last", None))
        macros = getattr(self, "saved_macros", None)
        if macros:
            _set_if_missing("macros", list(macros)[:MACROS_MAX])

        # Align with existing lfg_defaults / location_defaults maps
        ld = getattr(self, "saved_lfg_defaults", {}) or {}
        lld = getattr(self, "saved_lfg_location_defaults", {}) or {}
        for gname in GAME_PROFILES:
            gbag = dict(self.game_settings.get(gname) or {})
            if gname == active:
                gbag.update({k: v for k, v in bag.items() if v is not None})
            if gname in ld and not gbag.get("lfg_target"):
                # Only accept real content targets, not locations (legacy mistake)
                cand = str(ld.get(gname) or "")
                if cand in (GAME_PROFILES.get(gname) or {}).get("lfg_targets", {}):
                    gbag["lfg_target"] = cand
            if gname in lld and not gbag.get("lfg_location"):
                gbag["lfg_location"] = str(lld.get(gname) or "")
            # Seed steam_appid from profile if unset (None means non-Steam)
            if "steam_appid" not in gbag:
                gbag["steam_appid"] = (GAME_PROFILES.get(gname) or {}).get("steam_appid")
            self.game_settings[gname] = gbag

    def _snapshot_game_settings(self, game: Optional[str] = None) -> dict:
        """Capture live UI state into game_settings[game]."""
        game = game or (
            self.game_var.get() if hasattr(self, "game_var")
            else getattr(self, "default_game", "The Quinfall")
        )
        if not game:
            return {}
        if not isinstance(getattr(self, "game_settings", None), dict):
            self.game_settings = {}
        bag = dict(self.game_settings.get(game) or {})

        # Regions
        cr = _valid_region_dict(getattr(self, "chat_region", None))
        if cr is not None:
            bag["chat_region"] = cr
        mr = _valid_region_dict(getattr(self, "market_region", None))
        if mr is not None:
            bag["market_region"] = mr
        elif hasattr(self, "market_region") and self.market_region is None:
            bag["market_region"] = None

        if hasattr(self, "activity_var"):
            bag["activity"] = self.activity_var.get()
        if hasattr(self, "mood_var"):
            bag["mood"] = self.mood_var.get()
        if hasattr(self, "intensity_var"):
            try:
                bag["intensity"] = int(self.intensity_var.get())
            except Exception:
                pass
        if hasattr(self, "noise_level_var"):
            try:
                bag["noise_level"] = int(self.noise_level_var.get())
            except Exception:
                pass
        if hasattr(self, "lfg_target_var"):
            bag["lfg_target"] = self.lfg_target_var.get()
        if hasattr(self, "lfg_location_var"):
            bag["lfg_location"] = self.lfg_location_var.get()
        if hasattr(self, "lfg_need_var"):
            bag["lfg_need"] = self.lfg_need_var.get()
        if hasattr(self, "lfg_party_finder"):
            bag["lfg_party_finder"] = bool(self.lfg_party_finder.get())
        if hasattr(self, "economy_item_var"):
            bag["economy_item"] = self.economy_item_var.get().strip()[:120]
        if hasattr(self, "economy_undercut_var"):
            bag["economy_undercut"] = self.economy_undercut_var.get().strip()[:8]
        if hasattr(self, "flip_fee_var"):
            bag["flip_fee"] = self.flip_fee_var.get().strip()[:8]
        if hasattr(self, "ocr_prefer_last"):
            bag["ocr_prefer_last_line"] = bool(self.ocr_prefer_last.get())
        if hasattr(self, "macro_slots"):
            bag["macros"] = list(self.macro_slots)[:MACROS_MAX]

        # Keep parallel legacy maps in sync
        if bag.get("lfg_target"):
            self.lfg_defaults = getattr(self, "lfg_defaults", {}) or {}
            # Only store real targets
            if bag["lfg_target"] in self.lfg_target_names(game):
                self.lfg_defaults[game] = bag["lfg_target"]
        if bag.get("lfg_location"):
            self.lfg_location_defaults = getattr(self, "lfg_location_defaults", {}) or {}
            self.lfg_location_defaults[game] = bag["lfg_location"]

        # Preserve steam_appid override if set; else profile default
        if "steam_appid" not in bag:
            bag["steam_appid"] = (GAME_PROFILES.get(game) or {}).get("steam_appid")

        self.game_settings[game] = bag
        self._active_game_for_settings = game
        return bag

    def _apply_game_settings(self, game: Optional[str] = None):
        """Restore UI + runtime state from game_settings[game]."""
        game = game or (
            self.game_var.get() if hasattr(self, "game_var")
            else getattr(self, "default_game", "The Quinfall")
        )
        bag = dict((getattr(self, "game_settings", {}) or {}).get(game) or {})
        prof = GAME_PROFILES.get(game) or GAME_PROFILES.get("The Quinfall") or {}

        # Chat / market capture regions — per game (different UIs)
        cr = _valid_region_dict(bag.get("chat_region"))
        self.chat_region = cr
        mr = _valid_region_dict(bag.get("market_region"))
        self.market_region = mr

        # Activity
        acts = list(prof.get("activities") or ["General Chat"])
        act = str(bag.get("activity") or "")
        if hasattr(self, "activity_var"):
            if act not in acts:
                act = acts[0] if acts else "General Chat"
            self.activity_var.set(act)
            if hasattr(self, "activity_menu"):
                try:
                    self.activity_menu.configure(values=acts)
                    self.activity_menu.set(act)
                except Exception:
                    pass

        # Mood / heat / noise (remembered per game)
        if hasattr(self, "mood_var") and bag.get("mood"):
            mood = str(bag.get("mood"))
            if mood in MOOD_OPTIONS:
                self.mood_var.set(mood)
                if hasattr(self, "mood_menu"):
                    try:
                        self.mood_menu.set(mood)
                    except Exception:
                        pass
        if hasattr(self, "intensity_var") and bag.get("intensity") is not None:
            try:
                level = int(bag.get("intensity"))
                level = max(0, min(2, level))
                self.intensity_var.set(level)
                if hasattr(self, "heat_slider"):
                    self.heat_slider.set(level)
                if hasattr(self, "heat_label"):
                    self.heat_label.configure(text=INTENSITY_LABELS.get(level, "Normal"))
            except Exception:
                pass
        if hasattr(self, "noise_level_var") and bag.get("noise_level") is not None:
            try:
                level = max(0, min(4, int(bag.get("noise_level"))))
                self.noise_level_var.set(level)
                if hasattr(self, "noise_level_label"):
                    self.noise_level_label.configure(
                        text=NOISE_LEVEL_LABELS.get(level, "Chaos"),
                        text_color=(
                            C["success"] if level <= 1
                            else C["warn"] if level <= 3
                            else C["danger"]
                        ),
                    )
            except Exception:
                pass

        # LFG
        if hasattr(self, "lfg_target_var"):
            names = self.lfg_target_names(game)
            if hasattr(self, "lfg_target_menu"):
                try:
                    self.lfg_target_menu.configure(values=names)
                except Exception:
                    pass
            preferred = bag.get("lfg_target") or (getattr(self, "lfg_defaults", {}) or {}).get(game)
            self.lfg_target_var.set(self._resolve_lfg_target(game, preferred))
        if hasattr(self, "lfg_location_var"):
            loc_pref = bag.get("lfg_location") or (
                getattr(self, "lfg_location_defaults", {}) or {}
            ).get(game)
            self.lfg_location_var.set(self._resolve_lfg_location(game, loc_pref))
            try:
                self.sync_lfg_location_if_needed()
            except Exception:
                pass
        if hasattr(self, "lfg_need_var") and bag.get("lfg_need"):
            need = str(bag.get("lfg_need"))
            if need in LFG_NEED_OPTIONS:
                self.lfg_need_var.set(need)
                if hasattr(self, "lfg_need_menu"):
                    try:
                        self.lfg_need_menu.set(need)
                    except Exception:
                        pass
        if hasattr(self, "lfg_party_finder") and bag.get("lfg_party_finder") is not None:
            self.lfg_party_finder.set(bool(bag.get("lfg_party_finder")))

        # Economy
        if hasattr(self, "economy_item_var"):
            self.economy_item_var.set(str(bag.get("economy_item") or "")[:120])
        if hasattr(self, "economy_undercut_var"):
            self.economy_undercut_var.set(str(bag.get("economy_undercut") or "5")[:8])
        if hasattr(self, "flip_fee_var"):
            self.flip_fee_var.set(str(bag.get("flip_fee") or "5")[:8])

        # OCR preference
        if hasattr(self, "ocr_prefer_last") and bag.get("ocr_prefer_last_line") is not None:
            self.ocr_prefer_last.set(bool(bag.get("ocr_prefer_last_line")))

        # Macros
        if "macros" in bag and isinstance(bag.get("macros"), list):
            slots = [str(m)[:200] for m in bag["macros"]][:MACROS_MAX]
            while len(slots) < MACROS_MAX:
                slots.append("")
            self.macro_slots = slots
            self._refresh_macro_ui_if_any()

        # Status labels for OCR / market
        try:
            self._refresh_ocr_status()
        except Exception:
            pass
        try:
            self._refresh_market_status()
        except Exception:
            pass

        self._active_game_for_settings = game

    def _refresh_macro_ui_if_any(self):
        """Push macro_slots into Economy macro buttons if present."""
        if not hasattr(self, "macro_slots"):
            return
        if hasattr(self, "macro_btns") and isinstance(self.macro_btns, list):
            for i, btn in enumerate(self.macro_btns):
                try:
                    btn.configure(text=self._macro_btn_label(i))
                except Exception:
                    pass

    def _game_settings_for_save(self) -> dict[str, dict]:
        """Snapshot active game then return serializable game_settings."""
        try:
            if hasattr(self, "game_var"):
                self._snapshot_game_settings(self.game_var.get())
        except Exception:
            pass
        out: dict[str, dict] = {}
        for gname, bag in (getattr(self, "game_settings", {}) or {}).items():
            if not isinstance(bag, dict):
                continue
            clean: dict = {}
            for k, v in bag.items():
                if k == "chat_region" or k == "market_region":
                    reg = _valid_region_dict(v)
                    if reg:
                        clean[k] = reg
                    elif v is None:
                        clean[k] = None
                elif k == "macros" and isinstance(v, list):
                    clean[k] = [str(x)[:200] for x in v][:MACROS_MAX]
                elif k == "steam_appid":
                    # Keep None for non-Steam; int for Steam
                    if v is None or v == "":
                        clean[k] = None
                    else:
                        try:
                            clean[k] = int(v)
                        except Exception:
                            clean[k] = None
                elif k in GAME_SETTING_KEYS or k in (
                    "chat_region", "market_region", "macros", "steam_appid"
                ):
                    clean[k] = v
            out[str(gname)] = clean
        # Ensure all profile games present
        for gname, prof in GAME_PROFILES.items():
            if gname not in out:
                out[gname] = {"steam_appid": prof.get("steam_appid")}
            elif "steam_appid" not in out[gname]:
                out[gname]["steam_appid"] = prof.get("steam_appid")
        return out

    def _on_house_style_edited(self, _event=None, toast: bool = False):
        self._sync_house_style_from_ui()
        self.save_settings()
        if hasattr(self, "house_style_hint"):
            game = getattr(self, "_house_style_game", "") or ""
            short = (GAME_PROFILES.get(game) or {}).get("short", game) or "game"
            n = len(self.house_style_for(game))
            self.house_style_hint.configure(
                text=f"Saved for {short}" + (f" · {n} chars" if n else " · empty")
            )
        if toast:
            self.show_toast("House style saved", kind="ok")

    def _clear_house_style(self):
        game = getattr(self, "_house_style_game", None) or (
            self.game_var.get() if hasattr(self, "game_var") else ""
        )
        if hasattr(self, "house_styles") and game in self.house_styles:
            del self.house_styles[game]
        if hasattr(self, "house_style_box"):
            try:
                self.house_style_box.delete("1.0", "end")
            except Exception:
                pass
        self.save_settings()
        if hasattr(self, "house_style_hint"):
            short = (GAME_PROFILES.get(game) or {}).get("short", game) or "game"
            self.house_style_hint.configure(text=f"Cleared for {short}")

    def _sync_house_style_from_ui(self):
        if not hasattr(self, "house_style_box"):
            return
        if not hasattr(self, "house_styles"):
            self.house_styles = dict(getattr(self, "saved_house_styles", {}) or {})
        game = getattr(self, "_house_style_game", None) or (
            self.game_var.get() if hasattr(self, "game_var") else ""
        )
        if not game:
            return
        try:
            txt = self.house_style_box.get("1.0", "end").strip()[:500]
        except Exception:
            return
        if txt:
            self.house_styles[game] = txt
        elif game in self.house_styles:
            del self.house_styles[game]

    def _load_house_style_into_ui(self, game: Optional[str] = None):
        if not hasattr(self, "house_style_box"):
            return
        game = game or (self.game_var.get() if hasattr(self, "game_var") else "")
        self._house_style_game = game
        txt = self.house_style_for(game)
        try:
            self.house_style_box.delete("1.0", "end")
            if txt:
                self.house_style_box.insert("1.0", txt)
        except Exception:
            pass

    def on_close(self):
        self._alive = False
        try:
            self.save_settings()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

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

    # ------------------------------------------------------------------
    # Per-game vocabulary normalizer (DG=Dungeon, WB=World Boss, …)
    # ------------------------------------------------------------------
    def game_vocab(self, game: Optional[str] = None) -> dict[str, str]:
        """Abbreviation → meaning for the active (or given) game."""
        game = game or (self.game_var.get() if hasattr(self, "game_var") else "The Quinfall")
        prof = GAME_PROFILES.get(game) or {}
        raw = prof.get("vocab") or {}
        out: dict[str, str] = {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                key = str(k).strip()
                val = str(v).strip()
                if key and val:
                    out[key] = val
        return out

    def vocab_prompt_block(self, game: Optional[str] = None) -> str:
        """System-prompt block teaching the model this game's shorthand."""
        vocab = self.game_vocab(game)
        if not vocab:
            return ""
        # Longer keys first so display is stable
        items = sorted(vocab.items(), key=lambda kv: (-len(kv[0]), kv[0].upper()))
        lines = "\n".join(f"- {k} = {v}" for k, v in items)
        gname = game or (self.game_var.get() if hasattr(self, "game_var") else "this game")
        return (
            f"GAME SHORTHAND VOCAB for {gname} — ALWAYS decode when reading chat:\n"
            f"{lines}\n"
            "If a player writes an abbreviation above, treat it as that full meaning.\n"
            "You may reuse the same shorthand when it is natural for this game.\n"
            "Do NOT invent other games' acronyms.\n"
        )

    def vocab_hits_in_text(self, text: str, game: Optional[str] = None) -> list[tuple[str, str]]:
        """Return (abbrev, meaning) pairs found as whole tokens in text."""
        vocab = self.game_vocab(game)
        if not text or not vocab:
            return []
        # Sort longest first so multi-char keys win over short ones
        keys = sorted(vocab.keys(), key=lambda k: (-len(k), k.upper()))
        found: list[tuple[str, str]] = []
        seen_lower: set[str] = set()
        for key in keys:
            # Word boundary; M+ etc. need escaping
            pat = r"(?<![A-Za-z0-9])" + re.escape(key) + r"(?![A-Za-z0-9])"
            if re.search(pat, text, flags=re.IGNORECASE):
                low = key.lower()
                if low in seen_lower:
                    continue
                seen_lower.add(low)
                found.append((key, vocab[key]))
        return found

    def annotate_text_with_vocab(self, text: str, game: Optional[str] = None) -> str:
        """
        Keep original chat text and append a shorthand gloss for the model.
        Example: 'LFG DG Grim' → '...\\n(Shorthand: DG = Dungeon …)'
        """
        t = (text or "").strip()
        if not t:
            return t
        hits = self.vocab_hits_in_text(t, game)
        if not hits:
            return t
        gloss = "; ".join(f"{k} = {v}" for k, v in hits)
        return f"{t}\n(Shorthand in that line: {gloss})"

    def expand_game_vocab(self, text: str, game: Optional[str] = None) -> str:
        """
        Inline expand known shorthand for model context:
        'LFG DG' → 'LFG DG (Dungeon …)'
        Does not change UI-facing strings unless the caller chooses to.
        """
        t = text or ""
        vocab = self.game_vocab(game)
        if not t or not vocab:
            return t
        keys = sorted(vocab.keys(), key=lambda k: (-len(k), k.upper()))
        out = t
        for key in keys:
            meaning = vocab[key]
            pat = r"(?<![A-Za-z0-9])(" + re.escape(key) + r")(?![A-Za-z0-9(])"

            def _sub(m: Match[str], meaning: str = meaning) -> str:
                return f"{m.group(0)} ({meaning})"

            out = re.sub(pat, _sub, out, flags=re.IGNORECASE)
        return out

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
        self.sync_lfg_location_if_needed()

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

    def lfg_location_list(self, game: Optional[str] = None) -> list[str]:
        game = game or (self.game_var.get() if hasattr(self, "game_var") else "The Quinfall")
        locs = getattr(self, "lfg_locations", None) or {}
        custom = list(locs.get(game) or [])
        prof = GAME_PROFILES.get(game) or {}
        defaults = list(prof.get("lfg_locations_default") or [])
        # Merge defaults + custom, preserve order, unique
        out: list[str] = []
        for name in defaults + custom:
            n = (name or "").strip()
            if n and n not in out:
                out.append(n)
        return out or ["Open World"]

    def _resolve_lfg_location(self, game: str, preferred: Optional[str] = None) -> str:
        names = self.lfg_location_list(game)
        prefs = getattr(self, "lfg_location_defaults", None) or getattr(
            self, "saved_lfg_location_defaults", {}
        ) or {}
        prof = GAME_PROFILES.get(game) or {}
        for cand in (preferred, prefs.get(game), prof.get("lfg_location_default")):
            if cand and cand in names:
                return cand
        return names[0]

    def sync_lfg_location_if_needed(self):
        if not hasattr(self, "lfg_location_var"):
            return
        game = self.game_var.get()
        names = self.lfg_location_list(game)
        cur = self.lfg_location_var.get()
        if cur not in names:
            self.lfg_location_var.set(self._resolve_lfg_location(game))
        if hasattr(self, "lfg_location_menu"):
            self.lfg_location_menu.configure(values=names)

    def on_lfg_location_changed(self, choice: str = None):
        game = self.game_var.get()
        loc = (choice or self.lfg_location_var.get() or "").strip()
        names = self.lfg_location_list(game)
        if loc not in names:
            loc = self._resolve_lfg_location(game)
            self.lfg_location_var.set(loc)
        if not hasattr(self, "lfg_location_defaults"):
            self.lfg_location_defaults = {}
        self.lfg_location_defaults[game] = loc
        self.save_settings()

    def on_lfg_party_finder_changed(self):
        self.save_settings()

    def add_lfg_location(self):
        """Add a custom location to this game's LFG location list."""
        if not hasattr(self, "lfg_location_entry"):
            return
        name = self.lfg_location_entry.get().strip()
        if not name:
            self.show_toast("Type a location name first", kind="warn")
            return
        game = self.game_var.get()
        if not hasattr(self, "lfg_locations"):
            self.lfg_locations = {}
        locs = list(self.lfg_locations.get(game) or [])
        # Case-insensitive de-dupe against full list
        existing = {x.lower() for x in self.lfg_location_list(game)}
        if name.lower() in existing:
            self.lfg_location_var.set(
                next(x for x in self.lfg_location_list(game) if x.lower() == name.lower())
            )
            self.show_toast("Already in list", kind="info")
        else:
            locs.append(name)
            self.lfg_locations[game] = locs
            self.lfg_location_var.set(name)
            if not hasattr(self, "lfg_location_defaults"):
                self.lfg_location_defaults = {}
            self.lfg_location_defaults[game] = name
            self.show_toast(f"Location added · {name}", kind="ok")
        self.lfg_location_entry.delete(0, tk.END)
        self.sync_lfg_location_if_needed()
        self.save_settings()

    def remove_lfg_location(self):
        """Remove current location if it is a custom (non-profile-default) entry."""
        game = self.game_var.get()
        loc = self.lfg_location_var.get().strip() if hasattr(self, "lfg_location_var") else ""
        if not loc:
            return
        prof_defaults = list((GAME_PROFILES.get(game) or {}).get("lfg_locations_default") or [])
        customs = list((getattr(self, "lfg_locations", {}) or {}).get(game) or [])
        if loc in prof_defaults and loc not in customs:
            # Allow removing from effective list by tracking "hidden" defaults? Keep simple: block
            self.show_toast("Built-in default — can't remove", kind="warn")
            return
        if loc in customs:
            customs = [c for c in customs if c != loc]
            self.lfg_locations[game] = customs
            self.lfg_location_var.set(self._resolve_lfg_location(game))
            self.sync_lfg_location_if_needed()
            self.save_settings()
            self.show_toast(f"Removed · {loc}", kind="info")
        else:
            self.show_toast("Nothing to remove", kind="warn")

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
            self.schedule_ui(lambda: self._restore_foreground(prev), delay_ms=10)
            self.schedule_ui(lambda: self._restore_foreground(prev), delay_ms=50)

    def _tk_alive(self) -> bool:
        """True while the Tk app is open. Safe from any thread.

        Worker threads must NOT call winfo_exists()/widget methods — Tk is not
        thread-safe. From workers we only trust the _alive flag.
        """
        if not getattr(self, "_alive", False):
            return False
        try:
            if threading.current_thread() is not threading.main_thread():
                return True
            return bool(self.root.winfo_exists())
        except Exception:
            return False

    def _start_ui_queue_pump(self):
        """Begin draining the thread-safe UI queue on the main thread."""
        if getattr(self, "_ui_pump_started", False):
            return
        self._ui_pump_started = True
        self._pump_ui_queue()

    def _pump_ui_queue(self):
        """Main-thread only: run queued UI callbacks, then reschedule."""
        if not getattr(self, "_alive", False):
            return
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.root.after(50, self._pump_ui_queue)
        except Exception:
            self._alive = False

    def schedule_ui(self, fn: Callable, delay_ms: int = 0) -> bool:
        """Marshal fn onto the Tk main thread. Safe from worker threads and after close.

        Python 3.14 / Tk rejects root.after() from non-main threads
        ("main thread is not in main loop"). Workers therefore only enqueue;
        the main-thread pump calls after()/runs the callable.

        Returns False if the app is shutting down. Never call Tk widgets from
        the failure path — only plain Python.
        """
        if not getattr(self, "_alive", False):
            return False
        if not callable(fn):
            return False

        ms = 0
        try:
            ms = int(delay_ms) if delay_ms else 0
        except Exception:
            ms = 0

        on_main = threading.current_thread() is threading.main_thread()

        def _run_now():
            if not getattr(self, "_alive", False):
                return
            try:
                fn()
            except Exception:
                pass

        def _run_delayed():
            if not getattr(self, "_alive", False):
                return
            try:
                self.root.after(ms, _run_now)
            except Exception:
                self._alive = False

        # Main thread can use after() directly
        if on_main:
            try:
                if ms > 0:
                    self.root.after(ms, _run_now)
                else:
                    self.root.after(0, _run_now)
                return True
            except RuntimeError:
                self._alive = False
                return False
            except Exception:
                return False

        # Worker thread: never call Tk — queue for the main-thread pump
        try:
            if ms > 0:
                self._ui_queue.put(_run_delayed)
            else:
                self._ui_queue.put(_run_now)
            return True
        except Exception:
            return False

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

        for name in ("Chat Generator", "Library", "Calculator", "Economy", "Setup"):
            self.tabview.add(name)

        self.build_generator_tab()
        self.build_library_tab()
        self.build_calculator_tab()
        self.build_economy_tab()
        self.build_setup_tab()

        self.hud_body = ctk.CTkFrame(self.root, fg_color=C["surface"], corner_radius=14)
        self.build_hud_panel()

        # Sticky Copy bar + status footer (Copy always above session tips)
        self.build_sticky_copy_bar()
        self.build_footer()
        self._attach_main_tooltips()

        if self.hud_mode.get():
            self._apply_hud_visibility(True)
        else:
            self._show_sticky_copy_bar(True)

    # =====================================================================
    # Accessibility — type scale (managed, beauty-preserving)
    # =====================================================================
    # =====================================================================
    # Menu bar + comprehensive help
    # =====================================================================
    def build_menubar(self):
        """Native File / Help menus on the main window."""
        try:
            menubar = tk.Menu(self.root, tearoff=0)

            file_m = tk.Menu(menubar, tearoff=0)
            file_m.add_command(label="Export session pack\tCtrl+E", command=self.export_session_pack)
            file_m.add_command(label="Open app folder", command=self.open_app_folder)
            file_m.add_separator()
            file_m.add_command(label="Restart app", command=self.restart_app)
            file_m.add_separator()
            file_m.add_command(label="Exit", command=self.on_close)
            menubar.add_cascade(label="File", menu=file_m)

            help_m = tk.Menu(menubar, tearoff=0)
            help_m.add_command(label="Full Manual…", command=self.open_help_manual)
            help_m.add_command(label="Context help (this tab)\tF1", command=self.open_context_help)
            help_m.add_command(label="Keyboard shortcuts", command=self.open_help_shortcuts)
            help_m.add_separator()
            help_m.add_command(label="Open HELP_MANUAL.md", command=self.open_help_manual_file)
            help_m.add_command(label="Open FEATURES.md", command=self.open_features_file)
            help_m.add_separator()
            help_m.add_command(label="About Chat Helper", command=self.open_about)
            menubar.add_cascade(label="Help", menu=help_m)

            self.root.configure(menu=menubar)
            self._menubar = menubar
        except Exception:
            pass

    def _load_help_manual_text(self) -> str:
        """Prefer on-disk HELP_MANUAL.md so docs stay editable without code changes."""
        try:
            if os.path.isfile(HELP_MANUAL_PATH):
                with open(HELP_MANUAL_PATH, "r", encoding="utf-8") as f:
                    body = f.read().strip()
                if body:
                    return body
        except Exception:
            pass
        # Fallback if file missing
        parts = [HELP_CONTEXT.get(k, "") for k in (
            "Chat Generator", "Library", "Calculator", "Economy", "Setup",
        )]
        return (
            f"# Gamer’s Chat Helper v{APP_VERSION}\n\n"
            + "\n\n---\n\n".join(parts)
            + "\n\n"
            + HELP_SHORTCUTS_TEXT
            + f"\n\nManual file not found at:\n{HELP_MANUAL_PATH}"
        )

    def open_help_manual(self):
        """Scrollable full manual window (primary help surface)."""
        # Reuse existing window if open
        existing = getattr(self, "_help_win", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass

        win = ctk.CTkToplevel(self.root)
        win.title(f"Help Manual  ·  Chat Helper v{APP_VERSION}")
        win.geometry("720x640")
        win.minsize(480, 400)
        win.configure(fg_color=C["bg"])
        try:
            win.attributes("-topmost", True)
            win.after(200, lambda: win.attributes("-topmost", False))
        except Exception:
            pass
        self._help_win = win

        top = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=12)
        top.pack(fill="x", padx=pad(12), pady=(pad(12), pad(6)))
        ctk.CTkLabel(
            top, text="HELP MANUAL", font=f_ui(14, "bold"), text_color=C["text"],
        ).pack(side="left", padx=pad(14), pady=pad(12))
        ctk.CTkLabel(
            top, text="Search · jump · F1 = this tab only", font=f_ui(11), text_color=C["faint"],
        ).pack(side="left", padx=(0, pad(8)))

        search_var = tk.StringVar(value="")
        search_e = ctk.CTkEntry(
            top, textvariable=search_var, width=sz(180), height=sz(32), font=f_ui(12),
            placeholder_text="Find…",
            fg_color=C["elevated"], border_color=C["line"],
        )
        search_e.pack(side="right", padx=pad(14), pady=pad(10))

        # Jump chips
        jumps = ctk.CTkFrame(win, fg_color="transparent")
        jumps.pack(fill="x", padx=pad(12), pady=(0, pad(4)))
        for name in (
            "Quick start", "Header", "Chat Generator", "Economy", "Calculator",
            "Hotkeys", "LM Studio", "Steam", "Troubleshoot",
        ):
            ctk.CTkButton(
                jumps, text=name, height=sz(26), width=sz(100), font=f_ui(10, "bold"),
                fg_color=C["elevated"], hover_color=C["hover"],
                command=lambda n=name: self._help_jump(n),
            ).pack(side="left", padx=(0, pad(4)), pady=pad(2))

        body = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=12)
        body.pack(fill="both", expand=True, padx=pad(12), pady=(pad(4), pad(12)))
        self._help_textbox = ctk.CTkTextbox(
            body, font=f_ui(13),
            fg_color=C["elevated"], text_color=C["text"],
            wrap="word", border_width=0, corner_radius=10,
        )
        self._help_textbox.pack(fill="both", expand=True, padx=pad(10), pady=pad(10))
        manual = self._load_help_manual_text()
        self._help_manual_cache = manual
        self._help_textbox.insert("1.0", manual)
        self._help_textbox.configure(state="disabled")

        def do_search(*_a):
            q = search_var.get().strip()
            self._help_find(q)

        search_e.bind("<Return>", do_search)
        ctk.CTkButton(
            top, text="Find", width=sz(56), height=sz(32), font=f_ui(12, "bold"),
            fg_color=C["accent"], hover_color=C["accent_h"], command=do_search,
        ).pack(side="right", padx=(0, pad(6)), pady=pad(10))

        foot = ctk.CTkFrame(win, fg_color="transparent")
        foot.pack(fill="x", padx=pad(12), pady=(0, pad(12)))
        ctk.CTkButton(
            foot, text="Context (this tab)", height=sz(34), font=f_ui(12, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.open_context_help,
        ).pack(side="left")
        ctk.CTkButton(
            foot, text="Shortcuts", height=sz(34), width=sz(100), font=f_ui(12, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.open_help_shortcuts,
        ).pack(side="left", padx=pad(6))
        ctk.CTkButton(
            foot, text="Open .md on disk", height=sz(34), width=sz(130), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.open_help_manual_file,
        ).pack(side="left")
        ctk.CTkButton(
            foot, text="Close", height=sz(34), width=sz(90), font=f_ui(12, "bold"),
            fg_color=C["accent"], hover_color=C["accent_h"], command=win.destroy,
        ).pack(side="right")

    def _help_find(self, query: str):
        tb = getattr(self, "_help_textbox", None)
        if tb is None or not query:
            return
        try:
            tb.configure(state="normal")
            tb.tag_remove("search", "1.0", "end")
            start = "1.0"
            first = None
            while True:
                pos = tb.search(query, start, stopindex="end", nocase=True)
                if not pos:
                    break
                end = f"{pos}+{len(query)}c"
                tb.tag_add("search", pos, end)
                if first is None:
                    first = pos
                start = end
            tb.tag_config("search", background=C["accent"], foreground="#ffffff")
            if first:
                tb.see(first)
            tb.configure(state="disabled")
        except Exception:
            try:
                tb.configure(state="disabled")
            except Exception:
                pass

    def _help_jump(self, keyword: str):
        """Scroll manual to first occurrence of a section keyword."""
        tb = getattr(self, "_help_textbox", None)
        if tb is None:
            return
        # Map friendly names to search strings in HELP_MANUAL.md
        mapping = {
            "Quick start": "Quick start",
            "Header": "Header controls",
            "Chat Generator": "Chat Generator",
            "Economy": "Economy",
            "Calculator": "Calculator",
            "Hotkeys": "Hotkeys",
            "LM Studio": "Local AI",
            "Steam": "Steam population",
            "Troubleshoot": "Troubleshooting",
        }
        q = mapping.get(keyword, keyword)
        self._help_find(q)

    def open_context_help(self, _event=None):
        """F1 — help for the currently selected main tab."""
        tab_name = "Chat Generator"
        try:
            if hasattr(self, "tabview"):
                tab_name = self.tabview.get() or tab_name
        except Exception:
            pass
        body = HELP_CONTEXT.get(
            tab_name,
            f"No specific help for “{tab_name}”.\n\nOpen Help → Full Manual for everything.",
        )
        self._show_help_dialog(f"Help · {tab_name}", body)
        return "break"

    def open_help_shortcuts(self):
        self._show_help_dialog("Keyboard shortcuts", HELP_SHORTCUTS_TEXT)

    def open_about(self):
        about = (
            f"Gamer’s Chat Helper  ·  v{APP_VERSION}\n\n"
            "Local companion for MMO chat lines, Steam population,\n"
            "market screenshot pricing, calculator, and session tools.\n\n"
            "AI: LM Studio (OpenAI-compatible local server)\n"
            "Default API: http://127.0.0.1:1234\n\n"
            f"App folder:\n{APP_DIR}\n\n"
            "Not affiliated with game publishers.\n"
            "Help → Full Manual for the complete guide."
        )
        self._show_help_dialog("About Chat Helper", about)

    def _show_help_dialog(self, title: str, body: str):
        win = ctk.CTkToplevel(self.root)
        win.title(title)
        win.geometry("520x420")
        win.minsize(400, 300)
        win.configure(fg_color=C["bg"])
        try:
            win.attributes("-topmost", True)
            win.after(150, lambda: win.attributes("-topmost", False))
        except Exception:
            pass
        ctk.CTkLabel(
            win, text=title, font=f_ui(14, "bold"), text_color=C["text"],
        ).pack(anchor="w", padx=pad(16), pady=(pad(14), pad(6)))
        box = ctk.CTkTextbox(
            win, font=f_ui(13), fg_color=C["surface"], text_color=C["text"],
            wrap="word", border_width=0, corner_radius=10,
        )
        box.pack(fill="both", expand=True, padx=pad(14), pady=(0, pad(8)))
        box.insert("1.0", body)
        box.configure(state="disabled")
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(fill="x", padx=pad(14), pady=(0, pad(14)))
        ctk.CTkButton(
            row, text="Full Manual", height=sz(34), font=f_ui(12, "bold"),
            fg_color=C["accent"], hover_color=C["accent_h"],
            command=lambda: (win.destroy(), self.open_help_manual()),
        ).pack(side="left")
        ctk.CTkButton(
            row, text="Close", height=sz(34), width=sz(90), font=f_ui(12, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=win.destroy,
        ).pack(side="right")

    def open_help_manual_file(self):
        path = HELP_MANUAL_PATH
        if not os.path.isfile(path):
            # Write fallback so user always has a file
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._load_help_manual_text())
            except Exception:
                self.show_toast("Could not write HELP_MANUAL.md", kind="error")
                return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            self.show_toast(path, kind="info")

    def open_features_file(self):
        path = FEATURES_PATH
        if not os.path.isfile(path):
            self.show_toast("FEATURES.md not found", kind="warn")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            self.show_toast(path, kind="info")

    def open_app_folder(self):
        try:
            os.startfile(APP_DIR)  # type: ignore[attr-defined]
        except Exception:
            self.show_toast(APP_DIR, kind="info")

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
        self.build_menubar()
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
        """
        Slim daily-path header: Game · limit · AI · status.
        Power tools (type size, HUD/Pin/Auto/Focus/Keys, Oracle, Export, Restart) live in ⋯
        """
        self.header = ctk.CTkFrame(self.root, fg_color=C["surface"], corner_radius=14)
        self.header.pack(fill="x", padx=pad(14), pady=(pad(14), pad(4)))

        row1 = ctk.CTkFrame(self.header, fg_color="transparent")
        row1.pack(fill="x", padx=pad(12), pady=(pad(10), pad(8)))

        # Right: overflow + help (always visible, low noise)
        self.header_more_btn = ctk.CTkButton(
            row1, text="⋯", width=sz(40), height=sz(30), font=f_ui(16, "bold"),
            fg_color=C["elevated"], hover_color=C["hover"],
            command=self._open_header_overflow,
        )
        self.header_more_btn.pack(side="right", padx=(pad(6), 0))
        tip(
            self.header_more_btn,
            "More: type size, HUD / Pin / Auto / Focus / Keys,\n"
            "Oracle, Export, Restart, Setup.",
        )
        # Keep references so Setup / restarts still work if code looks them up
        self.header_restart_btn = self.header_more_btn
        self.header_help_btn = ctk.CTkButton(
            row1, text="?", width=sz(36), height=sz(30), font=f_ui(14, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.open_help_manual,
        )
        self.header_help_btn.pack(side="right", padx=(pad(4), 0))
        tip(self.header_help_btn, "Help manual · F1 = this tab")

        logo_s = sz(28)
        self.logo_label = ctk.CTkLabel(row1, text="", width=logo_s, height=logo_s)
        logo_img = self.assets.logo(size=(logo_s, logo_s))
        if logo_img:
            self.logo_label.configure(image=logo_img, text="")
            self._logo_img = logo_img
        else:
            self.logo_label.configure(text="◎", font=f_ui(18, "bold"), text_color=C["accent"])
        self.logo_label.pack(side="left", padx=(0, pad(8)))

        ctk.CTkLabel(row1, text="Chat Helper", font=f_ui(16, "bold"), text_color=C["text"]).pack(
            side="left"
        )

        icon_s = sz(26)
        self.game_icon_label = ctk.CTkLabel(row1, text="", width=icon_s, height=icon_s)
        self.game_icon_label.pack(side="left", padx=(pad(10), pad(4)))

        self.game_pill = ctk.CTkLabel(
            row1, text="Quinfall", font=f_ui(11, "bold"),
            text_color=C["text"], fg_color=C["elevated"], corner_radius=8,
            padx=pad(10), pady=pad(4),
        )
        self.game_pill.pack(side="left", padx=(2, pad(6)))

        self.game_combo = ctk.CTkOptionMenu(
            row1, variable=self.game_var, values=list(GAME_PROFILES.keys()),
            command=self.on_game_changed, width=sz(140), height=sz(28),
            fg_color=C["elevated"], button_color=C["hover"], button_hover_color=C["line"],
            dropdown_fg_color=C["elevated"], font=f_ui(12),
        )
        self.game_combo.pack(side="left", padx=pad(4))
        tip(
            self.game_combo,
            "Active game profile — limit, LFG content, vocab, Steam AppID.",
        )

        self.limit_badge = ctk.CTkLabel(
            row1, text="150", font=f_ui(11, "bold"), text_color=C["success"],
            fg_color=C["success_dim"], corner_radius=8, padx=pad(8), pady=pad(3),
        )
        self.limit_badge.pack(side="left", padx=pad(6))
        tip(self.limit_badge, "Hard character limit. Copy blocks if Generated line is over.")

        # Status chips (AI + ready) — still daily-path critical
        self.llm_dot = ctk.CTkLabel(
            row1,
            text="AI · off",
            font=f_ui(12, "bold"),
            text_color=C["danger"],
            fg_color=C["elevated"],
            corner_radius=8,
            padx=pad(10),
            pady=pad(5),
            cursor="hand2",
        )
        self.llm_dot.pack(side="left", padx=(pad(10), pad(6)))
        self.llm_dot.bind("<Button-1>", lambda e: self.open_lm_setup())
        tip(
            self.llm_dot,
            "LM Studio · click Setup.\n"
            "AI · on = server reachable for Write / OCR / Economy.",
        )

        self.copy_badge = ctk.CTkLabel(
            row1, text="ready", font=f_ui(11), text_color=C["muted"],
        )
        self.copy_badge.pack(side="left", padx=(0, pad(4)))
        tip(self.copy_badge, "ready · thinking · copied · offline · over limit")

        # Steam on a quiet second chip row (optional glance, not tools clutter)
        row2 = ctk.CTkFrame(self.header, fg_color="transparent")
        row2.pack(fill="x", padx=pad(12), pady=(0, pad(10)))
        self.steam_dot = ctk.CTkLabel(
            row2,
            text="Players · …",
            font=f_ui(12, "bold"),
            text_color=C["faint"],
            cursor="hand2",
            fg_color=C["elevated"],
            corner_radius=8,
            padx=pad(10),
            pady=pad(5),
        )
        self.steam_dot.pack(side="left")
        self.steam_dot.bind("<Button-1>", lambda e: self.open_steam_trends())
        tip(
            self.steam_dot,
            "Steam concurrent players (not AI). Click → Setup chart.\n"
            "Non-Steam games show n/a.",
        )
        self.type_scale_label = ctk.CTkLabel(
            row2, text=TYPE_PRESETS[self.font_scale_key]["label"],
            font=f_ui(11), text_color=C["faint"],
        )
        # Hidden label kept for type-scale code that updates it; shown in overflow menu
        self.type_scale_label.pack_forget()
        ctk.CTkLabel(
            row2, text="  ·  F6 Write · F7 Copy · hover for tips",
            font=f_ui(10), text_color=C["faint"],
        ).pack(side="left", padx=(pad(8), 0))

    def _open_header_overflow(self):
        """Native menu for power controls — keeps the daily header calm."""
        try:
            menu = tk.Menu(
                self.root, tearoff=0,
                bg=C["elevated"], fg=C["text"],
                activebackground=C["hover"], activeforeground=C["text"],
                bd=0, font=(FONT_UI, 10),
            )
        except Exception:
            menu = tk.Menu(self.root, tearoff=0)

        menu.add_command(label="Type size  A−", command=lambda: self.nudge_type_scale(-1))
        menu.add_command(label="Type size  A+", command=lambda: self.nudge_type_scale(1))
        menu.add_command(label="Type size  reset (M)", command=lambda: self.apply_type_scale("M"))
        menu.add_separator()

        def _toggle(var, after=None):
            def go():
                try:
                    var.set(not bool(var.get()))
                    if after:
                        after()
                    else:
                        self.save_settings()
                except Exception:
                    pass
            return go

        def _check(label, var, after=None):
            try:
                on = bool(var.get())
            except Exception:
                on = False
            mark = "✓  " if on else "    "
            menu.add_command(label=f"{mark}{label}", command=_toggle(var, after))

        _check("HUD mode", self.hud_mode, self.toggle_hud)
        _check("Pin on top", self.always_on_top, self.apply_on_top)
        _check("Auto-copy", self.auto_copy, self.save_settings)
        _check("Focus mode", self.focus_mode, self.toggle_focus_mode)
        _check("Hotkeys (F6–F10)", self.hotkeys_enabled, self.save_settings)
        menu.add_separator()
        menu.add_command(label="Oracle (F10)", command=self.run_oracle)
        menu.add_command(label="Export session (Ctrl+E)", command=self.export_session_pack)
        menu.add_command(label="Open Setup tab", command=self.open_lm_setup)
        menu.add_separator()
        menu.add_command(label="Restart app", command=self.restart_app)
        menu.add_command(label="Help manual", command=self.open_help_manual)

        try:
            # Post near the ⋯ button
            bx = self.header_more_btn.winfo_rootx()
            by = self.header_more_btn.winfo_rooty() + self.header_more_btn.winfo_height()
            menu.tk_popup(bx, by)
        except Exception:
            try:
                menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
            except Exception:
                pass
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def build_footer(self):
        foot = ctk.CTkFrame(self.root, fg_color="transparent", height=sz(36))
        foot.pack(fill="x", padx=pad(16), pady=(pad(6), pad(10)))

        self.status_bar = ctk.CTkLabel(
            foot, text=random.choice(TIPS), font=f_ui(11),
            text_color=C["faint"], anchor="w",
        )
        self.status_bar.pack(side="left", fill="x", expand=True)

        help_foot = ctk.CTkButton(
            foot, text="F1 Help", width=sz(72), height=sz(28), font=f_ui(11, "bold"),
            fg_color=C["elevated"], hover_color=C["hover"],
            command=self.open_context_help,
        )
        help_foot.pack(side="right", padx=(pad(6), pad(6)))
        tip(help_foot, "Context help for the current tab (F1). Full manual: Help menu or ? Help.")

        self.session_chip = ctk.CTkLabel(
            foot, text="session  ·  0 copies", font=f_ui(11, "bold"),
            text_color=C["muted"], fg_color=C["elevated"], corner_radius=8,
            padx=pad(10), pady=pad(4),
        )
        self.session_chip.pack(side="right")
        tip(self.session_chip, "This session only: copies, AI generations, streak. Resets when you close the app.")

    def _attach_main_tooltips(self):
        """Hover help for main configurable controls (safe if widgets missing)."""
        pairs = [
            (getattr(self, "sticky_copy_btn", None),
             "Copy the Generated line to the clipboard.\nBlocked if over this game’s character limit."),
            (getattr(self, "editor_copy_btn", None),
             "Copy the Generated line (same as the green sticky Copy bar at the bottom)."),
            (getattr(self, "intent_seg", None),
             "What you want to say: LFG · Activity · Reply · Recruit · Noise.\n"
             "Only that intent’s panel shows below."),
            (getattr(self, "lfg_target_menu", None),
             "General content type: EXP grind, Dungeon, World Boss, Combat Zone.\n"
             "Dungeon names are under Location — not here."),
            (getattr(self, "lfg_location_menu", None),
             "Where / which dungeon.\n"
             "Open-world: Cemetery, Arachnid Temple…\n"
             "Dungeons: Foaming Catacombs, Deepest Maze, Quiet Chambers, Grim Point.\n"
             "Add custom names below."),
            (getattr(self, "lfg_location_entry", None),
             "Type a custom location name, then Add. Saved for this game profile."),
            (getattr(self, "lfg_party_finder_cb", None),
             "When checked, generated LFG lines mention Party Finder."),
            (getattr(self, "noise_slider", None),
             "Chaos intensity for Noise only: Sane → Mental.\nDoes not affect Dad jokes (always clean)."),
            (getattr(self, "adv_toggle_btn", None),
             "Show or hide Mood, Heat (spiciness), LFG Need, and Grab-chat options."),
            (getattr(self, "heat_slider", None),
             "How spicy / pushy the AI wording can get (Safe → Normal → Spicy)."),
            (getattr(self, "lfg_need_menu", None),
             "What role or need to emphasize in LFG (tank, heals, DPS, any, etc.)."),
            (getattr(self, "gen_editor", None),
             "Your chat line. Edit freely, then Copy.\nCounter (top-right) shows length vs limit."),
            (getattr(self, "activity_menu", None),
             "What you’re doing in-world (for banter / presence lines — not an LFG)."),
            (getattr(self, "quick_they_said", None),
             "Paste the line you’re replying to, or fill it via Grab chat."),
            (getattr(self, "template_combo", None),
             "Pick a recruit / guild pitch template, then Fit to limit or Write."),
            (getattr(self, "setup_restart_btn", None),
             "Save settings and relaunch via Start Gamers Chat Helper.bat."),
            (getattr(self, "header_restart_btn", None),
             "Same as Setup → Restart app. Use after code updates."),
            (getattr(self, "header_help_btn", None),
             "Open the full Help Manual. F1 = context help for the current tab."),
            (getattr(self, "steam_log_cb", None),
             "Append Steam player samples to steam_players_log.txt while the app is open."),
            (getattr(self, "steam_interval_menu", None),
             "How often to write player-count samples (15 / 30 / 60 minutes)."),
            (getattr(self, "help_type_menu", None),
             "UI text size (same as A− / A+ in the header)."),
            (getattr(self, "economy_item_entry", None),
             "Item name for market pricing (optional). Helps the vision model focus."),
            (getattr(self, "economy_undercut_entry", None),
             "How far under the lowest clear listing to suggest (percent)."),
            (getattr(self, "house_style_box", None),
             "Per-game flavor for AI: guild name, slang, never-say list. Saved per game."),
        ]
        for w, text in pairs:
            if w is not None and text:
                try:
                    # Skip non-widgets (e.g. BooleanVar)
                    if not hasattr(w, "bind"):
                        continue
                    tip(w, text)
                except Exception:
                    pass

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
        """
        Bottom sticky bar disabled — Copy lives next to Generated line.
        Keep a lightweight frame object so HUD/show code does not crash.
        """
        self.sticky_copy_bar = ctk.CTkFrame(self.root, fg_color="transparent", height=0)
        # sticky_copy_btn is reassigned to editor_copy_btn after generator tab builds

    def _show_sticky_copy_bar(self, show: bool):
        # No bottom bar; Copy is on the Generated line card
        if not hasattr(self, "sticky_copy_bar"):
            return
        try:
            self.sticky_copy_bar.pack_forget()
        except Exception:
            pass

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
        self.mood_menu = ctk.CTkOptionMenu(
            adv_row, variable=self.mood_var, values=MOOD_OPTIONS,
            width=sz(150), height=sz(32), font=f_ui(12),
            fg_color=C["surface"], button_color=C["hover"],
            command=lambda _=None: self.save_settings(),
        )
        self.mood_menu.pack(side="left", padx=(pad(6), pad(12)))
        tip(self.mood_menu, "Tone for AI-written lines (friendly, sarcastic, hype, etc.).")
        self._field_label(adv_row, "Heat").pack(side="left")
        self.heat_label = ctk.CTkLabel(
            adv_row, text=INTENSITY_LABELS.get(self.saved_intensity, "Normal"),
            width=sz(56), font=f_ui(12, "bold"), text_color=C["text"],
        )
        self.heat_label.pack(side="left", padx=(pad(6), pad(4)))
        tip(self.heat_label, "Current Heat level (Safe / Normal / Spicy). Drag the slider to change.")
        self.heat_slider = ctk.CTkSlider(
            adv_row, from_=0, to=2, number_of_steps=2, width=sz(90),
            progress_color=C["accent"], button_color=C["text"],
            command=self.on_heat_change,
        )
        self.heat_slider.set(self.saved_intensity)
        self.heat_slider.pack(side="left", padx=(0, pad(12)))
        tip(self.heat_slider, "How spicy / pushy AI wording can get: Safe → Normal → Spicy.")
        self._field_label(adv_row, "LFG need").pack(side="left")
        self.lfg_need_menu = ctk.CTkOptionMenu(
            adv_row, variable=self.lfg_need_var, values=LFG_NEED_OPTIONS,
            width=sz(130), height=sz(32), font=f_ui(12),
            fg_color=C["surface"], button_color=C["hover"],
            command=self.on_lfg_need_changed,
        )
        self.lfg_need_menu.pack(side="left", padx=(pad(6), 0))
        tip(self.lfg_need_menu, "What you’re looking for in LFG (any / tank / heals / DPS…).")
        self.ocr_last_cb = ctk.CTkCheckBox(
            self.advanced_frame, text="Grab chat: last line only",
            variable=self.ocr_prefer_last, font=f_ui(11), text_color=C["muted"],
            fg_color=C["purple"], hover_color=C["purple_h"], border_color=C["line"],
            command=self.save_settings, checkbox_width=sz(16), checkbox_height=sz(16),
        )
        self.ocr_last_cb.pack(anchor="w", padx=pad(14), pady=(0, pad(10)))
        tip(
            self.ocr_last_cb,
            "When grabbing chat from the screen, prefer only the last readable line\n"
            "instead of a bigger block of chat history.",
        )

        # ---- Generated editor + Copy right next to it (not buried at window bottom) ----
        editor_card = ctk.CTkFrame(
            tab, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["success"],
        )
        editor_card.pack(fill="x", padx=pad(10), pady=(0, pad(6)))
        ed_head = ctk.CTkFrame(editor_card, fg_color="transparent")
        ed_head.pack(fill="x", padx=pad(14), pady=(pad(10), pad(4)))
        ctk.CTkLabel(
            ed_head, text="GENERATED LINE",
            font=f_ui(11, "bold"), text_color=C["faint"],
        ).pack(side="left")
        self.editor_len = ctk.CTkLabel(
            ed_head, text="0 / 150", font=f_ui(12, "bold"), text_color=C["success"],
        )
        self.editor_len.pack(side="right")
        # Mirror for sticky bar meter if present
        self.quick_len = self.editor_len

        ed_body = ctk.CTkFrame(editor_card, fg_color="transparent")
        ed_body.pack(fill="x", padx=pad(12), pady=(0, pad(6)))
        self.gen_editor = ctk.CTkTextbox(
            ed_body, height=sz(96), font=f_mono(14),
            fg_color=C["surface"], text_color=C["text"],
            border_width=0, corner_radius=10, wrap="word",
        )
        self.gen_editor.pack(side="left", fill="both", expand=True, padx=(0, pad(8)))
        self.gen_editor.insert("1.0", "")
        self.gen_editor.bind("<KeyRelease>", lambda e: self._update_quick_out_meter())
        self.quick_out = self.gen_editor
        self.ai_output = self.gen_editor

        ed_side = ctk.CTkFrame(ed_body, fg_color="transparent", width=sz(128))
        ed_side.pack(side="right", fill="y")
        ed_side.pack_propagate(False)
        self.editor_copy_btn = ctk.CTkButton(
            ed_side, text="Copy", height=sz(56), font=f_ui(16, "bold"),
            fg_color=C["success"], hover_color=C["success_h"], text_color="#04120a",
            command=self.copy_quick_out,
        )
        self.editor_copy_btn.pack(fill="x", pady=(0, pad(6)))
        tip(self.editor_copy_btn, "Copy Generated line · F7")
        # sticky_copy_btn aliases to this so flash/tooltips keep working
        self.sticky_copy_btn = self.editor_copy_btn
        ctk.CTkButton(
            ed_side, text="★ Fav", height=sz(32), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.favorite_quick_out,
        ).pack(fill="x")

        refine = ctk.CTkFrame(editor_card, fg_color="transparent")
        refine.pack(fill="x", padx=pad(12), pady=(0, pad(4)))
        for label, cmd in (
            ("Shorter", self.refine_shorter),
            ("Another", self.regenerate_last),
            ("Trim", self.trim_gen_editor),
            ("Clear", self.clear_gen_editor),
        ):
            ctk.CTkButton(
                refine, text=label, width=sz(72), height=sz(30), font=f_ui(12),
                fg_color=C["surface"], hover_color=C["hover"], text_color=C["text"],
                border_width=1, border_color=C["line"], command=cmd,
            ).pack(side="left", padx=(0, pad(4)))
        ctk.CTkButton(
            refine, text="Safer", width=sz(64), height=sz(30), font=f_ui(11),
            fg_color="transparent", hover_color=C["hover"], text_color=C["muted"],
            command=self.refine_safer,
        ).pack(side="left", padx=(pad(4), 0))
        ctk.CTkButton(
            refine, text="Spicier", width=sz(64), height=sz(30), font=f_ui(11),
            fg_color="transparent", hover_color=C["hover"], text_color=C["muted"],
            command=self.refine_spicier,
        ).pack(side="left")

        self.variant_frame = ctk.CTkFrame(editor_card, fg_color="transparent")
        self.variant_frame.pack(fill="x", padx=pad(12), pady=(0, pad(8)))
        self.variant_btns: list[ctk.CTkButton] = []
        for i in range(3):
            b = ctk.CTkButton(
                self.variant_frame, text=f"Option {i + 1}", height=sz(28), state="disabled",
                font=f_ui(11), fg_color=C["surface"], hover_color=C["hover"],
                command=lambda idx=i: self.pick_variant(idx),
            )
            b.pack(fill="x", pady=1)
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
            parent, "LFG",
            "Content + location. Need is under Advanced Tweaks.",
            accent=C["accent"],
        )
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        self._field_label(row, "Content").pack(side="left")
        self.lfg_target_menu = ctk.CTkOptionMenu(
            row, variable=self.lfg_target_var, values=self.lfg_target_names(),
            width=sz(200), height=sz(36), font=f_ui(13, "bold"),
            fg_color=C["surface"], button_color=C["hover"],
            command=self.on_lfg_target_changed,
        )
        self.lfg_target_menu.pack(side="left", padx=(pad(8), pad(12)))

        self._field_label(row, "Location").pack(side="left")
        self.lfg_location_menu = ctk.CTkOptionMenu(
            row, variable=self.lfg_location_var, values=self.lfg_location_list(),
            width=sz(160), height=sz(36), font=f_ui(13, "bold"),
            fg_color=C["surface"], button_color=C["hover"],
            command=self.on_lfg_location_changed,
        )
        self.lfg_location_menu.pack(side="left", padx=(pad(8), 0))

        pf_row = ctk.CTkFrame(parent, fg_color="transparent")
        pf_row.pack(fill="x", padx=pad(14), pady=(0, pad(4)))
        self.lfg_party_finder_cb = ctk.CTkCheckBox(
            pf_row, text="Party Finder",
            variable=self.lfg_party_finder,
            font=f_ui(12), text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_h"], border_color=C["line"],
            command=self.on_lfg_party_finder_changed,
            checkbox_width=sz(18), checkbox_height=sz(18),
        )
        self.lfg_party_finder_cb.pack(side="left")
        tip(self.lfg_party_finder_cb, "Include “in Party Finder” in the LFG line.")

        self.write_lfg_btn = self._pack_primary_cta(
            parent, "Write LFG  ·  F6", self.generate_lfg,
            tip_text="Primary action — Content + Location → Generated line → Copy below.",
        )

        def _lfg_more(fr):
            loc_row = ctk.CTkFrame(fr, fg_color="transparent")
            loc_row.pack(fill="x", padx=pad(10), pady=pad(8))
            self.lfg_location_entry = ctk.CTkEntry(
                loc_row, height=sz(30), font=f_ui(12),
                placeholder_text="Add custom location…",
                fg_color=C["elevated"], border_color=C["line"],
            )
            self.lfg_location_entry.pack(side="left", fill="x", expand=True, padx=(0, pad(6)))
            self.lfg_location_entry.bind("<Return>", lambda e: self.add_lfg_location())
            ctk.CTkButton(
                loc_row, text="Add", width=sz(56), height=sz(30), font=f_ui(12),
                fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
                command=self.add_lfg_location,
            ).pack(side="left", padx=(0, pad(4)))
            ctk.CTkButton(
                loc_row, text="Remove", width=sz(68), height=sz(30), font=f_ui(12),
                fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
                command=self.remove_lfg_location,
            ).pack(side="left")

        self._pack_more_block(parent, "lfg", _lfg_more)

    def _build_activity_panel(self, parent):
        self._job_card_header(
            parent, "ACTIVITY",
            "Presence / banter — not an LFG.",
            accent=C["info"],
        )
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=pad(14), pady=(0, pad(4)))
        self._field_label(row, "Activity").pack(side="left")
        self.activity_menu = ctk.CTkOptionMenu(
            row, variable=self.activity_var, values=self.profile()["activities"],
            width=sz(180), height=sz(36), font=f_ui(12),
            fg_color=C["surface"], button_color=C["hover"],
            command=lambda _=None: self.save_settings(),
        )
        self.activity_menu.pack(side="left", padx=(pad(8), 0))
        self.ai_activity_menu = self.activity_menu
        self._pack_primary_cta(
            parent, "Write activity  ·  F6", self.generate_activity_line,
            color=C["info"], hover="#0ea5e9", text_color="#041018",
            tip_text="Casual presence line → Generated line → Copy below.",
        )

    def _build_reply_panel(self, parent):
        self._job_card_header(
            parent, "REPLY",
            "Paste their line — or grab from game chat.",
            accent=C["purple"],
        )
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=pad(14), pady=(0, pad(4)))
        self._field_label(row, "They said").pack(side="left")
        self.quick_they_said = ctk.CTkEntry(
            row, height=sz(36), font=f_ui(12),
            placeholder_text="paste their line…",
            fg_color=C["surface"], border_color=C["line"],
        )
        self.quick_they_said.pack(side="left", fill="x", expand=True, padx=(pad(8), 0))
        self.quick_they_said.bind("<Return>", lambda e: self.generate_response_from_quick())
        self.input_statement = self.quick_they_said
        self.ocr_status = ctk.CTkLabel(
            parent, text=self._ocr_status_text(), font=f_ui(11), text_color=C["faint"], anchor="w",
        )
        self.ocr_status.pack(fill="x", padx=pad(14), pady=(0, pad(2)))

        self._pack_primary_cta(
            parent, "Write reply  ·  F6", self.generate_response_from_quick,
            color=C["purple"], hover=C["purple_h"],
            tip_text="Understated reply from “They said” → Generated line → Copy.",
        )

        # Secondary: grab path (common but secondary to write-when-pasted)
        grab = ctk.CTkFrame(parent, fg_color="transparent")
        grab.pack(fill="x", padx=pad(14), pady=(0, pad(4)))
        ctk.CTkButton(
            grab, text="Grab + reply", height=sz(34), font=f_ui(12, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["purple"],
            command=lambda: self.grab_chat_ocr(and_reply=True),
        ).pack(side="left", fill="x", expand=True, padx=(0, pad(6)))
        ctk.CTkButton(
            grab, text="Grab only", height=sz(34), width=sz(100), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=lambda: self.grab_chat_ocr(and_reply=False),
        ).pack(side="left")

        def _reply_more(fr):
            r = ctk.CTkFrame(fr, fg_color="transparent")
            r.pack(fill="x", padx=pad(10), pady=pad(8))
            ctk.CTkButton(
                r, text="Set chat box", height=sz(30), font=f_ui(12),
                fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
                command=self.calibrate_chat_region,
            ).pack(side="left", padx=(0, pad(6)))
            ctk.CTkButton(
                r, text="Open last grab", height=sz(30), font=f_ui(12),
                fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
                command=self.open_last_chat_capture,
            ).pack(side="left", padx=(0, pad(6)))
            ctk.CTkButton(
                r, text="3 options", height=sz(30), font=f_ui(12),
                fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
                command=self.generate_triple,
            ).pack(side="left")

        self._pack_more_block(parent, "reply", _reply_more)

    def _build_recruit_panel(self, parent):
        self._job_card_header(
            parent, "RECRUIT",
            "Manage pitches (CRUD) · AI rewrite does not auto-save.",
            accent=C["line"],
        )

        # ---- CRUD: always visible, labeled ----
        ctk.CTkLabel(
            parent, text="SAVED PITCHES  ·  CREATE · READ · UPDATE · DELETE",
            font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(0, pad(2)))

        pick_row = ctk.CTkFrame(parent, fg_color="transparent")
        pick_row.pack(fill="x", padx=pad(14), pady=(0, pad(4)))
        self._field_label(pick_row, "Load").pack(side="left")
        combo_vals, _ = self._recruit_combo_data()
        self.template_combo = ctk.CTkOptionMenu(
            pick_row,
            values=combo_vals,
            command=self.load_selected_template,
            height=sz(32),
            font=f_ui(12),
            fg_color=C["surface"],
            button_color=C["hover"],
        )
        self.template_combo.pack(side="left", fill="x", expand=True, padx=(pad(8), pad(8)))
        tip(self.template_combo, "READ — load a saved pitch into the seed editor.")
        self.recruit_crud_status = ctk.CTkLabel(
            pick_row, text="", font=f_ui(11), text_color=C["faint"], anchor="e",
        )
        self.recruit_crud_status.pack(side="right")

        name_row = ctk.CTkFrame(parent, fg_color="transparent")
        name_row.pack(fill="x", padx=pad(14), pady=(0, pad(4)))
        ctk.CTkLabel(name_row, text="Name", font=f_ui(11), text_color=C["muted"], width=sz(48)).pack(
            side="left"
        )
        self.recruit_name_var = tk.StringVar(value="")
        self.recruit_name_entry = ctk.CTkEntry(
            name_row,
            textvariable=self.recruit_name_var,
            placeholder_text="Pitch name (used on Save / Save as new)",
            height=sz(30),
            font=f_ui(12),
            fg_color=C["surface"],
            border_width=1,
            border_color=C["line"],
        )
        self.recruit_name_entry.pack(side="left", fill="x", expand=True, padx=(pad(6), 0))

        crud = ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=10)
        crud.pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        crud_inner = ctk.CTkFrame(crud, fg_color="transparent")
        crud_inner.pack(fill="x", padx=pad(8), pady=pad(8))
        # Row of clear CRUD actions
        for label, cmd, fg, hover, tc, help_txt in (
            ("+ New", self.recruit_new, C["elevated"], C["hover"], C["text"],
             "CREATE — blank draft (not saved until you Save)."),
            ("Save", self.recruit_save, C["accent"], C["accent_h"], C["text"],
             "UPDATE — overwrite the loaded pitch (or create if new draft)."),
            ("Save as new", self.recruit_save_as_new, C["elevated"], C["hover"], C["text"],
             "CREATE — always add a new pitch; keeps the original."),
            ("Duplicate", self.recruit_duplicate, C["elevated"], C["hover"], C["text"],
             "CREATE — copy current text as another saved pitch."),
            ("Delete", self.recruit_delete, C["danger_dim"], "#7f1d1d", C["danger"],
             "DELETE — remove the loaded pitch from the list."),
        ):
            b = ctk.CTkButton(
                crud_inner, text=label, height=sz(32), font=f_ui(12, "bold" if label == "Save" else "normal"),
                fg_color=fg, hover_color=hover, text_color=tc,
                border_width=0 if label == "Save" else 1, border_color=C["line"],
                command=cmd,
            )
            b.pack(side="left", padx=(0, pad(4)), fill="x" if label == "Save" else None, expand=(label == "Save"))
            tip(b, help_txt)

        msg_head = ctk.CTkFrame(parent, fg_color="transparent")
        msg_head.pack(fill="x", padx=pad(14), pady=(0, 2))
        ctk.CTkLabel(msg_head, text="Pitch text (seed)", font=f_ui(11), text_color=C["muted"]).pack(side="left")
        self.counter_label = ctk.CTkLabel(
            msg_head, text="0 / 150", font=f_ui(12, "bold"), text_color=C["success"],
        )
        self.counter_label.pack(side="right")
        self.msg_textbox = ctk.CTkTextbox(
            parent, height=sz(72), font=f_mono(13),
            fg_color=C["surface"], text_color=C["text"], border_width=0, corner_radius=10,
        )
        self.msg_textbox.pack(fill="x", padx=pad(14), pady=(2, pad(4)))
        self.msg_textbox.bind("<KeyRelease>", self.update_counter)
        tip(
            self.msg_textbox,
            "Pitch text you edit and save.\n"
            "AI variant rewrites this into Generated line — does NOT auto-save.",
        )

        self.safety_progressbar = ctk.CTkProgressBar(
            parent, progress_color=C["success"], fg_color=C["surface"], height=sz(6),
        )
        self.safety_progressbar.pack(fill="x", padx=pad(14), pady=(0, pad(4)))

        seed_row = ctk.CTkFrame(parent, fg_color="transparent")
        seed_row.pack(fill="x", padx=pad(14), pady=(0, pad(4)))
        self.recruit_variant_seed_var = tk.StringVar(value="")
        self.recruit_variant_seed_entry = ctk.CTkEntry(
            seed_row,
            textvariable=self.recruit_variant_seed_var,
            height=sz(30),
            font=f_ui(12),
            fg_color=C["surface"],
            border_width=1,
            border_color=C["line"],
            placeholder_text="Optional AI direction: shorter · chill · punchier…",
        )
        self.recruit_variant_seed_entry.pack(fill="x")

        # Primary AI — NO auto-save
        self._pack_primary_cta(
            parent,
            "AI variant  ·  F6",
            lambda: self.generate_recruit_variant(n=1, save_as_new=False),
            tip_text="Rewrite into Generated line only. Use Save / Save as new when you like it.",
        )
        self.recruit_copy_btn = None

        def _recruit_more(fr):
            r = ctk.CTkFrame(fr, fg_color="transparent")
            r.pack(fill="x", padx=pad(10), pady=pad(8))
            ctk.CTkButton(
                r, text="3 variants", height=sz(30), font=f_ui(12),
                fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
                command=lambda: self.generate_recruit_variant(n=3, save_as_new=False),
            ).pack(side="left", padx=(0, pad(4)))
            ctk.CTkButton(
                r, text="Fit to limit", height=sz(30), font=f_ui(12),
                fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
                command=self.ai_fit_recruitment,
            ).pack(side="left", padx=(0, pad(4)))
            ctk.CTkButton(
                r, text="Open file", height=sz(30), font=f_ui(12),
                fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
                command=self.recruit_open_file,
            ).pack(side="left")

        self._pack_more_block(parent, "recruit", _recruit_more)
        self._refresh_recruit_ui(load_editor=True)
        self.update_counter()

    def _build_noise_panel(self, parent):
        self._job_card_header(
            parent, "NOISE",
            "Non-game chatter. Or a clean dad joke.",
            accent=C["warn"],
        )
        slide = ctk.CTkFrame(parent, fg_color="transparent")
        slide.pack(fill="x", padx=pad(14), pady=(pad(2), pad(4)))
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
        self.noise_slider.pack(fill="x", padx=pad(14), pady=(0, pad(2)))
        self.noise_hint = ctk.CTkLabel(
            parent,
            text=NOISE_LEVEL_HINTS.get(int(self.noise_level_var.get()), ""),
            font=f_ui(11), text_color=C["faint"], anchor="w", wraplength=640, justify="left",
        )
        self.noise_hint.pack(fill="x", padx=pad(14), pady=(0, pad(4)))

        self._pack_primary_cta(
            parent, "Write chaos  ·  F6", self.generate_noise,
            color=C["surface"], hover=C["hover"],
            tip_text="Non-game noise at the slider level → Generated line → Copy.",
        )
        # Dad joke as clear second primary (not buried)
        dad = ctk.CTkButton(
            parent, text="Dad joke", height=sz(36), font=f_ui(13, "bold"),
            fg_color=C["info"], hover_color="#0ea5e9", text_color="#041018",
            command=self.generate_dad_joke,
        )
        dad.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        tip(dad, "Always clean · max 150 chars · ignores chaos slider.")

    def _pack_primary_cta(
        self,
        parent,
        text: str,
        command,
        *,
        color: str = None,
        hover: str = None,
        tip_text: str = "",
        text_color: str = None,
    ):
        """Single full-width primary action for an intent panel."""
        color = color or C["accent"]
        hover = hover or C["accent_h"]
        kw = dict(
            text=text,
            height=sz(44),
            font=f_ui(15, "bold"),
            fg_color=color,
            hover_color=hover,
            command=command,
        )
        if text_color:
            kw["text_color"] = text_color
        btn = ctk.CTkButton(parent, **kw)
        btn.pack(fill="x", padx=pad(14), pady=(pad(4), pad(8)))
        if tip_text:
            tip(btn, tip_text)
        return btn

    def _pack_more_block(self, parent, key: str, build_extras):
        """
        Collapsed 'More tools' section — secondary actions hidden by default.
        build_extras(frame) packs widgets into the expandable frame.
        """
        if not hasattr(self, "_more_open"):
            self._more_open: dict[str, bool] = {}
        self._more_open.setdefault(key, False)

        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", padx=pad(14), pady=(0, pad(10)))

        toggle = ctk.CTkButton(
            wrap,
            text="▸ More tools",
            height=sz(28),
            font=f_ui(12),
            fg_color="transparent",
            hover_color=C["hover"],
            text_color=C["muted"],
            anchor="w",
        )
        toggle.pack(fill="x")

        extras = ctk.CTkFrame(wrap, fg_color=C["surface"], corner_radius=10)
        # built but not packed until open
        try:
            build_extras(extras)
        except Exception:
            pass

        def _apply():
            open_ = bool(self._more_open.get(key))
            toggle.configure(text="▾ More tools" if open_ else "▸ More tools")
            try:
                extras.pack_forget()
            except Exception:
                pass
            if open_:
                extras.pack(fill="x", pady=(pad(4), 0))

        def _toggle():
            self._more_open[key] = not bool(self._more_open.get(key))
            _apply()

        toggle.configure(command=_toggle)
        tip(toggle, "Secondary actions — keep the main button for daily use.")
        _apply()
        return wrap

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

    def build_calculator_tab(self):
        """Simple four-function calculator with optional keyboard capture mode."""
        tab = self.tabview.tab("Calculator")
        tab.configure(fg_color=C["surface"])

        self._calc_expr = ""
        self._calc_just_eval = False
        if not hasattr(self, "calc_keys_mode"):
            self.calc_keys_mode = tk.BooleanVar(value=False)

        wrap = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=14)
        wrap.pack(fill="both", expand=True, padx=pad(12), pady=pad(12))

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", padx=pad(16), pady=(pad(14), pad(6)))
        ctk.CTkLabel(
            head, text="CALCULATOR", font=f_ui(11, "bold"), text_color=C["faint"],
        ).pack(side="left")

        self.calc_keys_btn = ctk.CTkButton(
            head, text="⌨ Keys: Off", width=sz(120), height=sz(30), font=f_ui(12, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            text_color=C["muted"], command=self.toggle_calc_keys_mode,
        )
        self.calc_keys_btn.pack(side="right")
        tip(
            self.calc_keys_btn,
            "Toggle keyboard capture for this calculator.\n"
            "ON  = number keys, numpad, + − × ÷, Enter, Backspace, Esc drive the pad.\n"
            "OFF = keyboard is free for the rest of the app.\n"
            "Only active while the Calculator tab is selected.",
        )

        self.calc_keys_hint = ctk.CTkLabel(
            wrap, text="Keyboard free · click Keys to capture 0–9 + − × ÷ Enter",
            font=f_ui(11), text_color=C["faint"], anchor="w",
        )
        self.calc_keys_hint.pack(fill="x", padx=pad(16), pady=(0, pad(6)))

        self.calc_display = ctk.CTkEntry(
            wrap, height=sz(52), font=f_mono(22), justify="right",
            fg_color=C["surface"], border_color=C["line"], text_color=C["text"],
        )
        self.calc_display.pack(fill="x", padx=pad(16), pady=(0, pad(12)))
        self.calc_display.insert(0, "0")
        tip(
            self.calc_display,
            "Result display. Prefer the pad or Keys mode — typing here is optional.\n"
            "When Keys is On, typed characters are handled by the calculator.",
        )

        grid = ctk.CTkFrame(wrap, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=pad(12), pady=(0, pad(16)))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1, uniform="calc")
        for r in range(5):
            grid.grid_rowconfigure(r, weight=1)

        rows = [
            [("C", "fn"), ("⌫", "fn"), ("%", "op"), ("÷", "op")],
            [("7", "digit"), ("8", "digit"), ("9", "digit"), ("×", "op")],
            [("4", "digit"), ("5", "digit"), ("6", "digit"), ("−", "op")],
            [("1", "digit"), ("2", "digit"), ("3", "digit"), ("+", "op")],
            [("±", "fn"), ("0", "digit"), (".", "digit"), ("=", "eq")],
        ]
        for r, row in enumerate(rows):
            for c, (label, kind) in enumerate(row):
                if kind == "eq":
                    fg, hov, tc = C["accent"], C["accent_h"], C["text"]
                elif kind == "op":
                    fg, hov, tc = C["hover"], C["line"], C["info"]
                elif kind == "fn":
                    fg, hov, tc = C["surface"], C["hover"], C["muted"]
                else:
                    fg, hov, tc = C["surface"], C["hover"], C["text"]
                btn = ctk.CTkButton(
                    grid, text=label, font=f_ui(18, "bold"), height=sz(52),
                    fg_color=fg, hover_color=hov, text_color=tc,
                    border_width=0 if kind == "eq" else 1, border_color=C["line"],
                    command=lambda L=label: self._calc_press(L),
                )
                btn.grid(row=r, column=c, sticky="nsew", padx=pad(4), pady=pad(4))

        # Bind once per app lifetime (UI rebuilds must not stack handlers)
        if not getattr(self, "_calc_key_bound", False):
            try:
                self.root.bind_all("<KeyPress>", self._calc_on_key, add="+")
            except Exception:
                self.root.bind("<KeyPress>", self._calc_on_key, add="+")
            self._calc_key_bound = True
        self._update_calc_keys_ui()

    def toggle_calc_keys_mode(self):
        on = not bool(self.calc_keys_mode.get())
        self.calc_keys_mode.set(on)
        self._update_calc_keys_ui()
        if on:
            self.show_toast("Calculator keys On", kind="ok")
            try:
                self.root.focus_set()
            except Exception:
                pass
        else:
            self.show_toast("Calculator keys Off", kind="info")

    def _update_calc_keys_ui(self):
        on = bool(self.calc_keys_mode.get()) if hasattr(self, "calc_keys_mode") else False
        if hasattr(self, "calc_keys_btn"):
            if on:
                self.calc_keys_btn.configure(
                    text="⌨ Keys: On",
                    fg_color=C["accent"],
                    hover_color=C["accent_h"],
                    text_color=C["text"],
                    border_width=0,
                )
            else:
                self.calc_keys_btn.configure(
                    text="⌨ Keys: Off",
                    fg_color=C["surface"],
                    hover_color=C["hover"],
                    text_color=C["muted"],
                    border_width=1,
                    border_color=C["line"],
                )
        if hasattr(self, "calc_keys_hint"):
            self.calc_keys_hint.configure(
                text=(
                    "Keys On · 0–9  + − * /  Enter=  Backspace  Esc=C  numpad OK"
                    if on
                    else "Keyboard free · click Keys to capture 0–9 + − × ÷ Enter"
                ),
                text_color=C["success"] if on else C["faint"],
            )
        # Readonly display while capturing keys so digits don't double-type into the entry
        if hasattr(self, "calc_display"):
            try:
                self.calc_display.configure(state="readonly" if on else "normal")
            except Exception:
                pass

    def _calc_map_key(self, event) -> Optional[str]:
        """Map a Tk key event to a calculator pad key, or None."""
        key = event.keysym or ""
        ch = event.char or ""
        # Numpad digits
        if key.startswith("KP_") and len(key) == 4 and key[3].isdigit():
            return key[3]
        mapping = {
            "Return": "=",
            "KP_Enter": "=",
            "equal": "=",
            "Escape": "C",
            "BackSpace": "⌫",
            "Delete": "C",
            "plus": "+",
            "KP_Add": "+",
            "minus": "−",
            "KP_Subtract": "−",
            "asterisk": "×",
            "KP_Multiply": "×",
            "slash": "÷",
            "KP_Divide": "÷",
            "percent": "%",
            "period": ".",
            "KP_Decimal": ".",
            "c": "C",
            "C": "C",
        }
        if key in mapping:
            return mapping[key]
        if key in "0123456789":
            return key
        if ch in "0123456789":
            return ch
        if ch == "+":
            return "+"
        if ch == "-":
            return "−"
        if ch == "*":
            return "×"
        if ch == "/":
            return "÷"
        if ch == ".":
            return "."
        if ch == "=":
            return "="
        if ch == "%":
            return "%"
        return None

    def _calc_on_key(self, event):
        """
        When Keys mode is On and Calculator tab is selected, map hardware keys
        to the pad and stop the event from typing elsewhere.
        """
        try:
            if not hasattr(self, "calc_keys_mode") or not self.calc_keys_mode.get():
                return
            if not hasattr(self, "tabview") or self.tabview.get() != "Calculator":
                return
            # Ignore pure modifiers
            if (event.keysym or "") in (
                "Shift_L", "Shift_R", "Control_L", "Control_R",
                "Alt_L", "Alt_R", "Caps_Lock", "Num_Lock", "Win_L", "Win_R",
            ):
                return
            mapped = self._calc_map_key(event)
            if mapped is None:
                return
            self._calc_press(mapped)
            return "break"
        except Exception:
            pass

    def _calc_get_display(self) -> str:
        try:
            return (self.calc_display.get() or "").strip()
        except Exception:
            return "0"

    def _calc_raw(self, text: str) -> str:
        """Strip thousand separators for math / typing buffer."""
        return (text or "").replace(",", "").strip()

    def _calc_pretty_input(self, raw: str) -> str:
        """Format a typed number with commas (keeps trailing '.' and fractional digits)."""
        s = (raw or "").strip()
        if s in ("", "Error", "∞"):
            return s or "0"
        neg = s.startswith("-")
        body = s[1:] if neg else s
        if body == "" or body == ".":
            return ("-" if neg else "") + (body or "0")
        if "." in body:
            whole, frac = body.split(".", 1)
            whole = whole or "0"
            # allow incomplete whole while typing
            if whole.isdigit():
                whole_fmt = f"{int(whole):,}"
            else:
                whole_fmt = whole
            return ("-" if neg else "") + whole_fmt + "." + frac
        if body.isdigit():
            return ("-" if neg else "") + f"{int(body):,}"
        return s

    def _calc_set_display(self, text: str):
        try:
            # readonly/disabled still needs a brief unlock on some CTk builds
            was = None
            try:
                was = str(self.calc_display.cget("state"))
            except Exception:
                pass
            if was and was != "normal":
                self.calc_display.configure(state="normal")
            self.calc_display.delete(0, "end")
            self.calc_display.insert(0, text)
            if was and was != "normal":
                self.calc_display.configure(state=was)
        except Exception:
            pass

    def _calc_press(self, key: str):
        expr = getattr(self, "_calc_expr", "") or ""
        just = getattr(self, "_calc_just_eval", False)
        disp = self._calc_get_display()
        raw_disp = self._calc_raw(disp)

        if key == "C":
            self._calc_expr = ""
            self._calc_just_eval = False
            self._calc_set_display("0")
            return
        if key == "⌫":
            if just:
                self._calc_expr = ""
                self._calc_just_eval = False
                self._calc_set_display("0")
                return
            if len(raw_disp) <= 1 or raw_disp in ("-", "-0"):
                self._calc_set_display("0")
            else:
                self._calc_set_display(self._calc_pretty_input(raw_disp[:-1]))
            return
        if key == "±":
            try:
                v = float(raw_disp)
                if v == 0:
                    return
                self._calc_set_display(self._calc_fmt_num(-v))
                self._calc_just_eval = False
            except Exception:
                pass
            return
        if key == "=":
            if expr and expr[-1] in "+-*/" and not just:
                raw = expr + raw_disp
            elif expr:
                raw = expr + ("" if just else raw_disp)
            else:
                raw = raw_disp
            result = self._calc_eval(raw if raw else raw_disp)
            self._calc_set_display(result)
            self._calc_expr = ""
            self._calc_just_eval = True
            return

        op_map = {"+": "+", "−": "-", "-": "-", "×": "*", "*": "*", "÷": "/", "/": "/", "%": "%"}
        if key in op_map:
            op = op_map[key]
            if op == "%":
                try:
                    v = float(raw_disp)
                    self._calc_set_display(self._calc_fmt_num(v / 100.0))
                    self._calc_just_eval = True
                except Exception:
                    pass
                return
            if expr and expr[-1] in "+-*/" and not just:
                mid = self._calc_eval(expr + raw_disp)
                self._calc_set_display(mid)
                try:
                    float(self._calc_raw(mid))
                    self._calc_expr = self._calc_raw(mid) + op
                except Exception:
                    self._calc_expr = ""
                self._calc_just_eval = True
                return
            left = raw_disp if raw_disp else "0"
            self._calc_expr = left + op
            self._calc_just_eval = True
            return

        if key == "." or (len(key) == 1 and key.isdigit()):
            if just or disp in ("0", "Error", "∞") or raw_disp in ("0", "Error", "∞"):
                nxt = "0." if key == "." else key
                self._calc_set_display(self._calc_pretty_input(nxt))
                self._calc_just_eval = False
                return
            if key == "." and "." in raw_disp:
                return
            if raw_disp == "0" and key != ".":
                nxt = key
            else:
                nxt = raw_disp + key
            self._calc_set_display(self._calc_pretty_input(nxt))
            self._calc_just_eval = False

    def _calc_eval(self, expression: str) -> str:
        """Safely evaluate a simple arithmetic expression."""
        s = self._calc_raw(expression or "")
        s = s.replace("×", "*").replace("÷", "/").replace("−", "-")
        allowed = set("0123456789+-*/.()eE ")
        if not s or any(ch not in allowed for ch in s):
            return "Error"
        if "__" in s:
            return "Error"
        try:
            val = eval(s, {"__builtins__": {}}, {})  # noqa: S307 — char-filtered only
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                return "Error"
            if val != val:  # NaN
                return "Error"
            if abs(val) == float("inf"):
                return "∞"
            return self._calc_fmt_num(float(val))
        except ZeroDivisionError:
            return "∞"
        except Exception:
            return "Error"

    def _calc_fmt_num(self, n: float) -> str:
        """Format results with thousand separators, e.g. 1,000,000."""
        try:
            n = float(n)
        except Exception:
            return "Error"
        # Integers (or near-integers)
        if abs(n - round(n)) < 1e-12 and abs(n) < 1e15:
            return f"{int(round(n)):,}"
        # Decimals: comma the whole part, keep fractional digits
        sign = "-" if n < 0 else ""
        n = abs(n)
        s = f"{n:.10f}".rstrip("0").rstrip(".")
        if "e" in s.lower() or len(s) > 18:
            # scientific / very long — still try to prettify if possible
            s = f"{n:.8g}"
            if "e" in s.lower():
                return sign + s
        if "." in s:
            whole, frac = s.split(".", 1)
            try:
                whole_fmt = f"{int(whole):,}"
            except Exception:
                whole_fmt = whole
            return f"{sign}{whole_fmt}.{frac}"
        try:
            return sign + f"{int(s):,}"
        except Exception:
            return sign + s

    def build_economy_tab(self):
        """Market screenshot → LM Studio vision/OCR → price suggestion (no official API)."""
        tab = self.tabview.tab("Economy")
        tab.configure(fg_color=C["surface"])

        # ---- Intro ----
        head = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        head.pack(fill="x", padx=pad(12), pady=(pad(12), pad(6)))
        ctk.CTkLabel(
            head, text="ECONOMY · MARKET SNAP", font=f_ui(11, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(2)))
        ctk.CTkLabel(
            head,
            text="No public Quinfall market API yet. Snap the in-game listings; local AI reads comps and suggests a price.",
            font=f_ui(12), text_color=C["muted"], anchor="w", wraplength=720, justify="left",
        ).pack(fill="x", padx=pad(14), pady=(0, pad(12)))

        # ---- Item + undercut ----
        card = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        card.pack(fill="x", padx=pad(12), pady=(0, pad(6)))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=pad(14), pady=(pad(12), pad(4)))
        ctk.CTkLabel(
            row1, text="My item", font=f_ui(12, "bold"), text_color=C["muted"], width=sz(90), anchor="w",
        ).pack(side="left")
        self.economy_item_entry = ctk.CTkEntry(
            row1, textvariable=self.economy_item_var, height=sz(36), font=f_ui(13),
            placeholder_text="Item name (optional — helps the model focus)",
            fg_color=C["surface"], border_color=C["line"],
        )
        self.economy_item_entry.pack(side="left", fill="x", expand=True, padx=(pad(8), 0))
        tip(
            self.economy_item_entry,
            "What you’re pricing. Leave blank to price the main item visible in the screenshot.",
        )

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=pad(14), pady=(pad(4), pad(12)))
        ctk.CTkLabel(
            row2, text="Undercut %", font=f_ui(12, "bold"), text_color=C["muted"], width=sz(90), anchor="w",
        ).pack(side="left")
        self.economy_undercut_entry = ctk.CTkEntry(
            row2, textvariable=self.economy_undercut_var, height=sz(36), font=f_mono(13),
            width=sz(72), fg_color=C["surface"], border_color=C["line"],
        )
        self.economy_undercut_entry.pack(side="left", padx=(pad(8), pad(8)))
        tip(
            self.economy_undercut_entry,
            "How aggressively to undercut the lowest clear listing (e.g. 5 = list ~5% under low).",
        )
        ctk.CTkLabel(
            row2, text="% under lowest clear comp (default 5)", font=f_ui(11), text_color=C["faint"],
        ).pack(side="left")

        # ---- Capture controls ----
        act = ctk.CTkFrame(card, fg_color="transparent")
        act.pack(fill="x", padx=pad(14), pady=(0, pad(14)))
        cal_btn = ctk.CTkButton(
            act, text="Set market area", height=sz(40), width=sz(140), font=f_ui(13, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.calibrate_market_region,
        )
        cal_btn.pack(side="left", padx=(0, pad(6)))
        tip(cal_btn, "Drag a box over the market / auction list in your game (same idea as chat OCR).")
        snap_btn = ctk.CTkButton(
            act, text="Snap + price", height=sz(40), font=f_ui(14, "bold"),
            fg_color=C["accent"], hover_color=C["accent_h"],
            command=self.grab_market_price,
        )
        snap_btn.pack(side="left", fill="x", expand=True, padx=(0, pad(6)))
        tip(
            snap_btn,
            "Screenshot the calibrated market area → LM Studio vision (or OCR) → comps + suggested price.\n"
            "Needs LM Studio running with a vision model for best results.",
        )
        open_btn = ctk.CTkButton(
            act, text="Last shot", height=sz(40), width=sz(100), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.open_last_market_capture,
        )
        open_btn.pack(side="left")
        tip(open_btn, f"Open last capture:\n{LAST_MARKET_PATH}")

        self.economy_status = ctk.CTkLabel(
            card, text=self._market_status_text(), font=f_ui(11), text_color=C["faint"], anchor="w",
        )
        self.economy_status.pack(fill="x", padx=pad(14), pady=(0, pad(12)))

        # ---- Results ----
        out = ctk.CTkFrame(
            tab, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["info"],
        )
        out.pack(fill="both", expand=True, padx=pad(12), pady=(0, pad(12)))
        ctk.CTkLabel(
            out, text="READ FROM SCREEN", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(4)))

        self.economy_comps = ctk.CTkTextbox(
            out, height=sz(120), font=f_mono(12),
            fg_color=C["surface"], text_color=C["text"],
            border_width=0, corner_radius=10, wrap="word",
        )
        self.economy_comps.pack(fill="both", expand=True, padx=pad(14), pady=(0, pad(8)))
        self.economy_comps.insert("1.0", "Snap a market list to see comps here…")

        self.economy_suggest = ctk.CTkLabel(
            out, text="Suggested · —", font=f_ui(18, "bold"), text_color=C["success"], anchor="w",
        )
        self.economy_suggest.pack(fill="x", padx=pad(14), pady=(0, pad(4)))

        self.economy_wts = ctk.CTkLabel(
            out, text="", font=f_mono(13), text_color=C["text"],
            fg_color=C["surface"], corner_radius=8, anchor="w",
            padx=pad(10), pady=pad(8),
        )
        self.economy_wts.pack(fill="x", padx=pad(14), pady=(0, pad(8)))

        copy_row = ctk.CTkFrame(out, fg_color="transparent")
        copy_row.pack(fill="x", padx=pad(14), pady=(0, pad(14)))
        ctk.CTkButton(
            copy_row, text="Copy suggest", height=sz(36), width=sz(120), font=f_ui(12, "bold"),
            fg_color=C["success"], hover_color=C["success_h"], text_color="#04120a",
            command=self.copy_economy_suggest,
        ).pack(side="left", padx=(0, pad(6)))
        ctk.CTkButton(
            copy_row, text="Copy WTS line", height=sz(36), width=sz(130), font=f_ui(12, "bold"),
            fg_color=C["info"], hover_color="#0ea5e9", text_color="#041018",
            command=self.copy_economy_wts,
        ).pack(side="left", padx=(0, pad(6)))
        ctk.CTkButton(
            copy_row, text="Copy comps", height=sz(36), width=sz(110), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.copy_economy_comps,
        ).pack(side="left")


        # ---- Surprise tools: reprice / flip / macros / history ----
        tools = ctk.CTkFrame(out, fg_color="transparent")
        tools.pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        ctk.CTkButton(
            tools, text="↻ Re-price last shot", height=sz(34), font=f_ui(12, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.reprice_last_market,
        ).pack(side="left", padx=(0, pad(6)))
        tip(tools.winfo_children()[-1], "Re-run vision/OCR on last_market_capture.png without a new screenshot. F9")
        ctk.CTkButton(
            tools, text="Δ vs previous", height=sz(34), width=sz(120), font=f_ui(12, "bold"),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.economy_compare_previous,
        ).pack(side="left", padx=(0, pad(6)))
        tip(tools.winfo_children()[-1], "Compare this suggestion to the previous economy log entry.")
        ctk.CTkButton(
            tools, text="Save → Macro", height=sz(34), width=sz(120), font=f_ui(12, "bold"),
            fg_color=C["purple"], hover_color=C["purple_h"],
            command=self.save_wts_to_macro,
        ).pack(side="left")
        tip(tools.winfo_children()[-1], "Store the current WTS line into the next empty macro slot (1–3).")

        flip = ctk.CTkFrame(out, fg_color=C["surface"], corner_radius=10)
        flip.pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        ctk.CTkLabel(
            flip, text="FLIP PROFIT", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(10), pady=(pad(8), pad(2)))
        fr = ctk.CTkFrame(flip, fg_color="transparent")
        fr.pack(fill="x", padx=pad(10), pady=(0, pad(4)))
        for lab, var, w in (
            ("Buy", self.flip_buy_var, 100),
            ("Sell", self.flip_sell_var, 100),
            ("Fee %", self.flip_fee_var, 64),
        ):
            ctk.CTkLabel(fr, text=lab, font=f_ui(11), text_color=C["muted"]).pack(side="left")
            e = ctk.CTkEntry(
                fr, textvariable=var, width=sz(w), height=sz(30), font=f_mono(12),
                fg_color=C["elevated"], border_color=C["line"],
            )
            e.pack(side="left", padx=(pad(4), pad(10)))
            e.bind("<KeyRelease>", lambda _e: self.recalc_flip())
        self.flip_result = ctk.CTkLabel(
            flip, text="Profit · —", font=f_ui(14, "bold"), text_color=C["info"], anchor="w",
        )
        self.flip_result.pack(fill="x", padx=pad(10), pady=(0, pad(8)))
        tip(self.flip_result, "Sell − Buy − fees. Clipboard watcher can fill Buy/Sell when you copy a number.")

        macros = ctk.CTkFrame(out, fg_color=C["surface"], corner_radius=10)
        macros.pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        ctk.CTkLabel(
            macros, text="WTS MACROS · one-tap paste", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(10), pady=(pad(8), pad(4)))
        mrow = ctk.CTkFrame(macros, fg_color="transparent")
        mrow.pack(fill="x", padx=pad(10), pady=(0, pad(8)))
        self.macro_btns = []
        for i in range(MACROS_MAX):
            b = ctk.CTkButton(
                mrow, text=self._macro_btn_label(i), height=sz(34), font=f_ui(11, "bold"),
                fg_color=C["elevated"], hover_color=C["hover"], border_width=1, border_color=C["line"],
                command=lambda idx=i: self.fire_macro(idx),
            )
            b.pack(side="left", fill="x", expand=True, padx=(0, pad(4) if i < MACROS_MAX - 1 else 0))
            tip(
                b,
                f"Macro {i + 1}: click to copy into chat.\n"
                "Save WTS with Save → Macro. Shift+click a slot to clear it.",
            )
            self.macro_btns.append(b)
            b.bind("<Shift-Button-1>", lambda e, idx=i: self._clear_macro(idx))

        hist_box = ctk.CTkFrame(out, fg_color=C["surface"], corner_radius=10)
        hist_box.pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        ctk.CTkLabel(
            hist_box, text="PRICE LOG", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(10), pady=(pad(8), pad(2)))
        self.economy_hist_label = ctk.CTkLabel(
            hist_box, text=self._economy_hist_summary(), font=f_ui(11), text_color=C["muted"],
            anchor="w", justify="left",
        )
        self.economy_hist_label.pack(fill="x", padx=pad(10), pady=(0, pad(8)))

        note = ctk.CTkLabel(
            out,
            text="Advice is only as good as the listings in the screenshot — not a live server-wide market feed.  F8 snap · F9 reprice",
            font=f_ui(11), text_color=C["faint"], anchor="w",
        )
        note.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        self.recalc_flip()

    def build_setup_tab(self):
        tab = self.tabview.tab("Setup")
        tab.configure(fg_color=C["surface"])

        # Restart — full-width so it can't hide off-screen in narrow layouts
        restart_bar = ctk.CTkFrame(
            tab, fg_color=C["elevated"], corner_radius=12,
            border_width=1, border_color=C["accent"],
        )
        restart_bar.pack(fill="x", padx=pad(12), pady=(pad(12), pad(6)))
        ctk.CTkLabel(
            restart_bar, text="APP · RESTART", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(10), pad(2)))
        ctk.CTkLabel(
            restart_bar,
            text="Saves settings, then runs Start Gamers Chat Helper.bat from this folder.",
            font=f_ui(12), text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=pad(14), pady=(0, pad(8)))
        self.setup_restart_btn = ctk.CTkButton(
            restart_bar, text="↻  Restart app", height=sz(42), font=f_ui(14, "bold"),
            fg_color=C["accent"], hover_color=C["accent_h"],
            command=self.restart_app,
        )
        self.setup_restart_btn.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        tip(
            self.setup_restart_btn,
            "Relaunch from the app directory (same as double-clicking the .bat).\n"
            "Keeps config; reloads code. Also available in the header (right side).",
        )

        # ---- LM Studio (local or remote OpenAI-compatible server) ----
        self._build_lm_setup_panel(tab)

        a11y = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        a11y.pack(fill="x", padx=pad(12), pady=(0, pad(6)))
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

        # ---- Per-game house style (feeds AI system prompt) ----
        style_box = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        style_box.pack(fill="x", padx=pad(12), pady=(0, pad(6)))
        ctk.CTkLabel(
            style_box, text="HOUSE STYLE · PER GAME", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(2)))
        ctk.CTkLabel(
            style_box,
            text="Optional flavor for AI lines (guild name, slang, things never to say). Saved per game.",
            font=f_ui(12), text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        self.house_style_box = ctk.CTkTextbox(
            style_box, height=sz(72), font=f_ui(12),
            fg_color=C["surface"], text_color=C["text"],
            border_width=0, corner_radius=10, wrap="word",
        )
        self.house_style_box.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        self.house_style_box.bind(
            "<FocusOut>", lambda e: (self._sync_house_style_from_ui(), self.save_settings())
        )
        tip(
            self.house_style_box,
            "Examples:\n"
            "• Guild: [your name] · chill PvE · Discord required\n"
            "• Never say mythic+ or CZ unless I pick that content\n"
            "• Prefer “LFG” over “looking for group”\n"
            "Injected into AI prompts for this game (not dad jokes / pure noise).",
        )
        style_row = ctk.CTkFrame(style_box, fg_color="transparent")
        style_row.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        ctk.CTkButton(
            style_row, text="Save style", height=sz(30), width=sz(100), font=f_ui(12, "bold"),
            fg_color=C["accent"], hover_color=C["accent_h"],
            command=lambda: self._on_house_style_edited(toast=True),
        ).pack(side="left")
        ctk.CTkButton(
            style_row, text="Clear", height=sz(30), width=sz(72), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self._clear_house_style,
        ).pack(side="left", padx=(pad(6), 0))
        self.house_style_hint = ctk.CTkLabel(
            style_row, text="", font=f_ui(11), text_color=C["faint"],
        )
        self.house_style_hint.pack(side="left", padx=(pad(10), 0))
        self._load_house_style_into_ui()

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
        self.steam_log_cb = ctk.CTkCheckBox(
            steam_row, text="Log to file", variable=self.steam_log_enabled,
            font=f_ui(12), text_color=C["muted"],
            fg_color=C["info"], hover_color=C["info"], border_color=C["line"],
            command=self.save_settings, checkbox_width=sz(16), checkbox_height=sz(16),
        )
        self.steam_log_cb.pack(side="left", padx=(0, pad(12)))
        tip(
            self.steam_log_cb,
            "When on, appends concurrent player samples to steam_players_log.txt\n"
            "on the interval below (while this app is open).",
        )
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
        tip(
            self.steam_interval_menu,
            "How often to write a player-count sample to the log file (15 / 30 / 60 min).",
        )
        self.steam_refresh_btn = ctk.CTkButton(
            steam_row, text="Refresh chart", height=sz(28), width=sz(110), font=f_ui(11),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.refresh_steam_chart,
        )
        self.steam_refresh_btn.pack(side="left", padx=(0, pad(6)))
        tip(self.steam_refresh_btn, "Reload samples from steam_players_log.txt and redraw the chart.")
        self.steam_open_log_btn = ctk.CTkButton(
            steam_row, text="Open log", height=sz(28), width=sz(90), font=f_ui(11),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.open_steam_log_file,
        )
        self.steam_open_log_btn.pack(side="left")
        tip(self.steam_open_log_btn, "Open steam_players_log.txt in your default text editor.")

        self.steam_chart_meta = ctk.CTkLabel(
            steam_box, text="No data yet — leave app open to log.",
            font=f_ui(11), text_color=C["faint"], anchor="w",
        )
        self.steam_chart_meta.pack(fill="x", padx=pad(14), pady=(0, pad(4)))

        chart_wrap = ctk.CTkFrame(steam_box, fg_color=C["surface"], corner_radius=10, height=sz(200))
        chart_wrap.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        chart_wrap.pack_propagate(False)
        self.steam_chart_canvas = tk.Canvas(
            chart_wrap, bg=C["surface"], highlightthickness=0, bd=0,
        )
        self.steam_chart_canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.steam_chart_canvas.bind("<Configure>", lambda e: self.draw_steam_chart())
        tip(
            self.steam_chart_canvas,
            "Steam concurrent players over real time (X = clock time).\n"
            "Steam API is GLOBAL only (one world total for Quinfall).\n"
            "NA / Europe / Asia below = prime-time slices of that global total.",
        )

        # Region focus: All / NA / Europe / Asia (prime-time analysis of global series)
        reg_row = ctk.CTkFrame(steam_box, fg_color="transparent")
        reg_row.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        ctk.CTkLabel(
            reg_row, text="Region lens", font=f_ui(11, "bold"), text_color=C["muted"],
        ).pack(side="left", padx=(0, pad(8)))
        self.steam_region_seg = ctk.CTkSegmentedButton(
            reg_row,
            values=list(STEAM_REGION_FOCUS_OPTIONS),
            font=f_ui(12, "bold"),
            height=sz(30),
            selected_color=C["info"],
            selected_hover_color="#0ea5e9",
            unselected_color=C["surface"],
            unselected_hover_color=C["hover"],
            command=self.on_steam_region_focus,
        )
        self.steam_region_seg.set(self.steam_region_focus.get())
        self.steam_region_seg.pack(side="left", fill="x", expand=True)
        tip(
            self.steam_region_seg,
            "Steam does NOT publish separate NA/EU/Asia player counts for Quinfall.\n"
            "This lens compares the GLOBAL concurrent total during each region’s\n"
            "local evening (prime) vs late night (off-peak).\n"
            "Pick a region to emphasize that window in the report + Discord copy.",
        )
        self.steam_region_now = ctk.CTkLabel(
            reg_row, text="", font=f_ui(11), text_color=C["faint"],
        )
        self.steam_region_now.pack(side="left", padx=(pad(10), 0))

        # High / low population report + trend analysis (full log, not just chart window)
        report_box = ctk.CTkFrame(steam_box, fg_color=C["surface"], corner_radius=10)
        report_box.pack(fill="x", padx=pad(14), pady=(0, pad(12)))
        report_head = ctk.CTkFrame(report_box, fg_color="transparent")
        report_head.pack(fill="x", padx=pad(12), pady=(pad(10), pad(2)))
        ctk.CTkLabel(
            report_head, text="POPULATION REPORT · HIGH / LOW + TRENDS + REGIONS",
            font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(side="left")
        self.steam_pop_copy_btn = ctk.CTkButton(
            report_head, text="Copy for Discord", height=sz(28), width=sz(130),
            font=f_ui(11, "bold"),
            fg_color=C["success"], hover_color=C["success_h"], text_color="#04120a",
            command=self.copy_steam_pop_report,
        )
        self.steam_pop_copy_btn.pack(side="right")
        tip(
            self.steam_pop_copy_btn,
            "Copy the full population report (including NA/EU/Asia prime slices)\n"
            "as a Discord-friendly code block.",
        )
        self.steam_pop_report = ctk.CTkLabel(
            report_box,
            text="Leave the app open to log samples — report fills from steam_players_log.txt.",
            font=f_ui(12), text_color=C["muted"],
            anchor="w", justify="left",
        )
        self.steam_pop_report.pack(fill="x", padx=pad(12), pady=(0, pad(10)))
        tip(
            self.steam_pop_report,
            "Full-log high/low + trends.\n"
            "NA / Europe / Asia = evening vs off-peak averages of the GLOBAL Steam total\n"
            "(not separate regional servers — Steam doesn’t expose those).",
        )
        self._steam_pop_report_text = ""

        tips = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        tips.pack(fill="both", expand=True, padx=pad(12), pady=(0, pad(12)))
        ctk.CTkLabel(
            tips, text="QUICK SETUP", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(6)))
        for line in (
            "• LM Studio (above): Local or Remote host · Test (green/red) · model dropdown",
            "• Default model = currently loaded model in LM Studio (first in /v1/models)",
            "• Per-game settings: chat/market boxes, LFG, economy, macros, mood — saved separately",
            "• Steam games show Players · count; non-Steam (e.g. WoW) show Players · n/a",
            "• AI off? Write still works — offline packs for LFG, activity, noise, replies",
            "• House style (above): per-game guild/slang notes fed into AI prompts",
            "• Sampling is set BY THIS APP per job — leave LM Studio defaults alone",
            "• Steam log: steam_players_log.txt next to the app (TSV) for Excel/analysis",
            "• Restart (top-right) reloads after code updates · hover controls for tips",
            "• Help menu · ? Help · F1 context · Full Manual in HELP_MANUAL.md",
            "• Hotkeys: F6 Write · F7 Copy · F8 Market snap · F9 Re-price · F10 Oracle",
            "• Economy: flip profit, WTS macros, price log, re-price last shot",
            "• Export session pack (header ⇪ or Ctrl+E) → session_export.txt",
        ):
            ctk.CTkLabel(
                tips, text=line, font=f_ui(13), text_color=C["text"], anchor="w",
            ).pack(anchor="w", padx=pad(14), pady=2)
        ctk.CTkLabel(
            tips, text=f"Chat Helper v{APP_VERSION}", font=f_ui(11), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(14)))
        self.root.after(400, self.refresh_steam_chart)

    def _build_lm_setup_panel(self, tab):
        """Setup → LM Studio: Local/Remote host, green/red test, model dropdown."""
        lm = ctk.CTkFrame(tab, fg_color=C["elevated"], corner_radius=12)
        lm.pack(fill="x", padx=pad(12), pady=(0, pad(6)))
        self.lm_setup_frame = lm

        ctk.CTkLabel(
            lm, text="LM STUDIO · LOCAL AI", font=f_ui(10, "bold"), text_color=C["faint"],
        ).pack(anchor="w", padx=pad(14), pady=(pad(12), pad(2)))
        ctk.CTkLabel(
            lm,
            text="OpenAI-compatible server. Local = this PC · Remote = another machine’s IP/hostname.",
            font=f_ui(12), text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=pad(14), pady=(0, pad(8)))

        mode_row = ctk.CTkFrame(lm, fg_color="transparent")
        mode_row.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        ctk.CTkLabel(
            mode_row, text="Mode", font=f_ui(11, "bold"), text_color=C["muted"], width=sz(72),
            anchor="w",
        ).pack(side="left")
        self.lm_mode_seg = ctk.CTkSegmentedButton(
            mode_row,
            values=list(LM_MODE_OPTIONS),
            font=f_ui(12, "bold"),
            height=sz(30),
            selected_color=C["accent"],
            selected_hover_color=C["accent_h"],
            unselected_color=C["surface"],
            unselected_hover_color=C["hover"],
            command=self.on_lm_mode_change,
            variable=self.lm_mode_var,
        )
        self.lm_mode_seg.set(self.lm_mode_var.get() if self.lm_mode_var.get() in LM_MODE_OPTIONS else "Local")
        self.lm_mode_seg.pack(side="left", fill="x", expand=True)
        tip(
            self.lm_mode_seg,
            "Local — LM Studio on this PC (127.0.0.1:1234).\n"
            "Remote — LM Studio on another PC; enter that host:port below.\n"
            "Remote needs LM Studio server listening on the LAN (and firewall open).",
        )

        host_row = ctk.CTkFrame(lm, fg_color="transparent")
        host_row.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        ctk.CTkLabel(
            host_row, text="Host", font=f_ui(11, "bold"), text_color=C["muted"], width=sz(72),
            anchor="w",
        ).pack(side="left")
        self.lm_host_entry = ctk.CTkEntry(
            host_row,
            textvariable=self.lm_host_var,
            height=sz(32),
            font=f_ui(13),
            fg_color=C["surface"],
            border_width=1,
            border_color=C["line"],
            placeholder_text="127.0.0.1:1234  or  192.168.1.50:1234",
        )
        self.lm_host_entry.pack(side="left", fill="x", expand=True)
        self.lm_host_entry.bind("<Return>", lambda e: self.test_lm_connection())
        self.lm_host_entry.bind("<FocusOut>", lambda e: self._sync_api_url_from_ui(save=True))
        tip(
            self.lm_host_entry,
            "Examples:\n"
            "• 127.0.0.1:1234  (local default)\n"
            "• 192.168.1.42:1234  (LAN remote)\n"
            "• http://my-pc:1234  (also OK)\n"
            "Port is usually 1234 in LM Studio → Developer / Local Server.",
        )

        key_row = ctk.CTkFrame(lm, fg_color="transparent")
        key_row.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        ctk.CTkLabel(
            key_row, text="API key", font=f_ui(11, "bold"), text_color=C["muted"], width=sz(72),
            anchor="w",
        ).pack(side="left")
        self.lm_api_key_entry = ctk.CTkEntry(
            key_row,
            textvariable=self.lm_api_key_var,
            height=sz(32),
            font=f_ui(13),
            fg_color=C["surface"],
            border_width=1,
            border_color=C["line"],
            placeholder_text="Optional (if LM Studio server requires one)",
            show="•",
        )
        self.lm_api_key_entry.pack(side="left", fill="x", expand=True)
        tip(
            self.lm_api_key_entry,
            "Usually blank for local LM Studio.\n"
            "If you set an API key in LM Studio server settings, paste it here.",
        )

        model_row = ctk.CTkFrame(lm, fg_color="transparent")
        model_row.pack(fill="x", padx=pad(14), pady=(0, pad(6)))
        ctk.CTkLabel(
            model_row, text="Model", font=f_ui(11, "bold"), text_color=C["muted"], width=sz(72),
            anchor="w",
        ).pack(side="left")
        initial_models = [self.lm_model_var.get()] if (self.lm_model_var.get() or "").strip() else ["(connect to list)"]
        self.lm_model_menu = ctk.CTkOptionMenu(
            model_row,
            values=initial_models,
            variable=self.lm_model_var,
            height=sz(32),
            font=f_ui(12),
            fg_color=C["surface"],
            button_color=C["hover"],
            button_hover_color=C["line"],
            dropdown_fg_color=C["elevated"],
            command=self.on_lm_model_change,
        )
        if (self.lm_model_var.get() or "").strip():
            self.lm_model_menu.set(self.lm_model_var.get())
        else:
            self.lm_model_menu.set(initial_models[0])
        self.lm_model_menu.pack(side="left", fill="x", expand=True, padx=(0, pad(8)))
        tip(
            self.lm_model_menu,
            "Models reported by LM Studio /v1/models.\n"
            "Defaults to the currently loaded model (first in the list).\n"
            "Use Test connection or Refresh to reload the list.",
        )
        self.lm_refresh_models_btn = ctk.CTkButton(
            model_row, text="Refresh", height=sz(32), width=sz(84), font=f_ui(12),
            fg_color=C["surface"], hover_color=C["hover"], border_width=1, border_color=C["line"],
            command=self.refresh_lm_models,
        )
        self.lm_refresh_models_btn.pack(side="left")
        tip(self.lm_refresh_models_btn, "Re-query LM Studio for loaded models.")

        action_row = ctk.CTkFrame(lm, fg_color="transparent")
        action_row.pack(fill="x", padx=pad(14), pady=(0, pad(10)))
        self.lm_test_btn = ctk.CTkButton(
            action_row, text="Test connection", height=sz(34), width=sz(140),
            font=f_ui(13, "bold"),
            fg_color=C["accent"], hover_color=C["accent_h"],
            command=self.test_lm_connection,
        )
        self.lm_test_btn.pack(side="left")
        tip(
            self.lm_test_btn,
            "Hits GET /v1/models on the host above.\n"
            "Green = reachable · Red = offline / error.\n"
            "Also fills the model dropdown (default = loaded model).",
        )

        status_box = ctk.CTkFrame(action_row, fg_color=C["surface"], corner_radius=10)
        status_box.pack(side="left", fill="x", expand=True, padx=(pad(10), 0))
        status_inner = ctk.CTkFrame(status_box, fg_color="transparent")
        status_inner.pack(fill="x", padx=pad(10), pady=pad(6))
        self.lm_status_dot = ctk.CTkLabel(
            status_inner, text="●", font=f_ui(16, "bold"), text_color=C["faint"], width=sz(22),
        )
        self.lm_status_dot.pack(side="left")
        self.lm_status_label = ctk.CTkLabel(
            status_inner,
            text="Not tested yet — click Test connection",
            font=f_ui(12),
            text_color=C["muted"],
            anchor="w",
        )
        self.lm_status_label.pack(side="left", fill="x", expand=True, padx=(pad(4), 0))
        tip(
            status_box,
            "Green = LM Studio server online.\n"
            "Red = cannot reach host (server off, wrong IP, firewall, or no model loaded).",
        )

        # Seed status from last known pulse if available
        if getattr(self, "_llm_online", None) is True:
            model = (self.lm_model_var.get() or "").strip() or "ready"
            self._set_lm_conn_status(True, f"Online · {model}")
        elif getattr(self, "_llm_online", None) is False:
            self._set_lm_conn_status(False, "Offline — start LM Studio Local Server")

    def open_lm_setup(self):
        """Jump to Setup tab and focus LM Studio panel (header AI chip)."""
        try:
            self.tabview.set("Setup")
        except Exception:
            pass
        try:
            if hasattr(self, "lm_host_entry"):
                self.lm_host_entry.focus_set()
        except Exception:
            pass

    def on_lm_mode_change(self, value: str = ""):
        mode = (value or self.lm_mode_var.get() or "Local").strip()
        if mode not in LM_MODE_OPTIONS:
            mode = "Local"
        self.lm_mode_var.set(mode)
        self.lm_mode = mode
        host = (self.lm_host_var.get() or "").strip()
        if mode == "Local":
            # Prefer local default when switching back unless already local-looking
            if not host or not (
                host.startswith("127.0.0.1")
                or "localhost" in host.lower()
                or host.startswith("http://127.0.0.1")
            ):
                if not host or self._host_looks_remote(host):
                    self.lm_host_var.set(LM_DEFAULT_LOCAL_HOST)
        self._sync_api_url_from_ui(save=True)
        self._set_lm_conn_status(None, "Mode changed — test connection")

    def on_lm_model_change(self, value: str = ""):
        model = (value or self.lm_model_var.get() or "").strip()
        if model.startswith("("):
            return
        self.lm_model = model
        self.lm_model_var.set(model)
        self.save_settings()
        if getattr(self, "_llm_online", None):
            self._set_lm_conn_status(True, f"Online · {model}")

    def _host_looks_remote(self, host: str) -> bool:
        h = (host or "").strip().lower()
        if not h:
            return False
        if "127.0.0.1" in h or "localhost" in h or "[::1]" in h:
            return False
        return True

    def _sync_api_url_from_ui(self, save: bool = False):
        if hasattr(self, "lm_mode_var"):
            self.lm_mode = self.lm_mode_var.get() if self.lm_mode_var.get() in LM_MODE_OPTIONS else "Local"
        if hasattr(self, "lm_host_var"):
            host = (self.lm_host_var.get() or "").strip() or (
                LM_DEFAULT_LOCAL_HOST if self.lm_mode == "Local" else ""
            )
            if host:
                self.lm_host = host
                self.api_url = self._api_url_from_host(host)
        if hasattr(self, "lm_api_key_var"):
            self.lm_api_key = (self.lm_api_key_var.get() or "").strip()
        if hasattr(self, "lm_model_var"):
            m = (self.lm_model_var.get() or "").strip()
            if m and not m.startswith("("):
                self.lm_model = m
        if save:
            # save_settings calls us again with save=False — no recursion loop
            try:
                self.save_settings()
            except Exception:
                pass

    def _set_lm_conn_status(self, ok: Optional[bool], message: str):
        """Green / red connectivity indicator on Setup panel."""
        if not hasattr(self, "lm_status_dot"):
            return
        try:
            if ok is True:
                color = C["success"]
                prefix = "Connected"
            elif ok is False:
                color = C["danger"]
                prefix = "Offline"
            else:
                color = C["faint"]
                prefix = "Unknown"
            msg = (message or "").strip()
            if msg and not msg.lower().startswith(prefix.lower()):
                text = f"{prefix} · {msg}" if ok is not None else msg
            else:
                text = msg or prefix
            self.lm_status_dot.configure(text_color=color)
            self.lm_status_label.configure(text=text[:120], text_color=color if ok is not None else C["muted"])
        except Exception:
            pass

    def _populate_lm_model_menu(
        self, models: list[str], preferred: str = "", *, online: Optional[bool] = None
    ):
        """Fill model dropdown; default to preferred or first loaded model."""
        models = [m for m in (models or []) if m and not str(m).startswith("(")]
        self._lm_models_cache = list(models)
        if not hasattr(self, "lm_model_menu"):
            if models:
                if preferred and preferred in models:
                    self.lm_model = preferred
                elif not (getattr(self, "lm_model", "") or "").strip():
                    self.lm_model = models[0]
                if hasattr(self, "lm_model_var"):
                    self.lm_model_var.set(self.lm_model)
            return

        if not models:
            if online is False:
                placeholder = "(not connected)"
            elif online is True:
                placeholder = "(no model loaded)"
            else:
                placeholder = "(connect to list)"
            try:
                self.lm_model_menu.configure(values=[placeholder])
                self.lm_model_menu.set(placeholder)
                self.lm_model_var.set(placeholder)
            except Exception:
                pass
            return

        pick = (preferred or getattr(self, "lm_model", "") or "").strip()
        if pick.startswith("("):
            pick = ""
        if pick not in models:
            # Start with the default loaded model (first from LM Studio /v1/models)
            pick = models[0]
        self.lm_model = pick
        try:
            self.lm_model_menu.configure(values=models)
            self.lm_model_menu.set(pick)
            self.lm_model_var.set(pick)
        except Exception:
            pass

    def test_lm_connection(self):
        """Manual connectivity test → green/red + model list."""
        self._sync_api_url_from_ui(save=False)
        self._set_lm_conn_status(None, "Testing…")
        if hasattr(self, "lm_test_btn"):
            try:
                self.lm_test_btn.configure(state="disabled", text="Testing…")
            except Exception:
                pass
        gen = getattr(self, "_llm_pulse_gen", 0)

        def work():
            ok, detail, models = self._probe_llm_server(full=True)

            def apply():
                if hasattr(self, "lm_test_btn"):
                    try:
                        self.lm_test_btn.configure(state="normal", text="Test connection")
                    except Exception:
                        pass
                if ok:
                    preferred = (self.lm_model_var.get() if hasattr(self, "lm_model_var") else "") or ""
                    if preferred.startswith("("):
                        preferred = ""
                    self._populate_lm_model_menu(models, preferred=preferred, online=True)
                    model = (self.lm_model_var.get() if hasattr(self, "lm_model_var") else "") or detail
                    if model.startswith("("):
                        model = detail or "ready"
                    self._set_lm_conn_status(True, str(model))
                    self._llm_online = True
                    # Update header chip immediately
                    if hasattr(self, "llm_dot"):
                        try:
                            self.llm_dot.configure(text="AI · on", text_color=C["success"])
                            tip(
                                self.llm_dot,
                                "LM STUDIO AI SERVER — online\n"
                                f"Model: {model}\n"
                                f"Mode: {getattr(self, 'lm_mode', 'Local')}\n"
                                f"API: {self._normalize_api_url(self.api_url)}\n"
                                "Click → Setup to change host / model.",
                            )
                        except Exception:
                            pass
                    self.save_settings()
                    self.show_toast(f"LM Studio · {model}", kind="ok")
                else:
                    self._llm_online = False
                    self._populate_lm_model_menu([], online=False)
                    self._set_lm_conn_status(False, detail or "unreachable")
                    if hasattr(self, "llm_dot"):
                        try:
                            self.llm_dot.configure(text="AI · off", text_color=C["danger"])
                        except Exception:
                            pass
                    self.show_toast(f"LM Studio offline · {detail}", kind="error")
                # Keep periodic pulse in sync
                _ = gen

            self.schedule_ui(apply)

        threading.Thread(target=work, daemon=True).start()

    def refresh_lm_models(self):
        """Re-fetch model list without full toast spam if already online."""
        self._sync_api_url_from_ui(save=False)
        self._set_lm_conn_status(None, "Refreshing models…")

        def work():
            ok, detail, models = self._probe_llm_server(full=True)

            def apply():
                if ok:
                    preferred = (self.lm_model_var.get() if hasattr(self, "lm_model_var") else "") or ""
                    if preferred.startswith("("):
                        preferred = ""
                    self._populate_lm_model_menu(models, preferred=preferred, online=True)
                    model = self.lm_model_var.get() if hasattr(self, "lm_model_var") else detail
                    self._set_lm_conn_status(True, str(model))
                    self._llm_online = True
                    self.save_settings()
                else:
                    self._populate_lm_model_menu([], online=False)
                    self._set_lm_conn_status(False, detail or "unreachable")
                    self._llm_online = False

            self.schedule_ui(apply)

        threading.Thread(target=work, daemon=True).start()


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

    def restart_app(self):
        """
        Save settings, re-launch Start Gamers Chat Helper.bat from APP_DIR
        (bat does cd /d \"%~dp0\"), then quit this process.
        """
        try:
            self.save_settings()
        except Exception:
            pass

        bat = os.path.join(APP_DIR, "Start Gamers Chat Helper.bat")
        py_script = os.path.join(APP_DIR, "gamers_chat_helper.py")

        try:
            if os.path.isfile(bat):
                # start opens a new console window; bat sets cwd to its folder
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "", bat],
                    cwd=APP_DIR,
                    close_fds=True,
                )
            elif os.path.isfile(py_script):
                flags = 0
                if sys.platform == "win32":
                    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                    )
                subprocess.Popen(
                    [sys.executable, py_script],
                    cwd=APP_DIR,
                    close_fds=True,
                    creationflags=flags,
                )
            else:
                messagebox.showerror(
                    "Restart failed",
                    f"Could not find launcher in:\n{APP_DIR}",
                )
                return
        except Exception as e:
            messagebox.showerror("Restart failed", str(e))
            return

        self.show_toast("Restarting…", kind="info")
        self.root.after(250, self._quit_for_restart)

    def _quit_for_restart(self):
        self._alive = False
        try:
            self.root.destroy()
        except Exception:
            pass
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)

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

    def steam_appid(self, game: Optional[str] = None) -> Optional[int]:
        """
        Steam AppID for concurrent-player polling.
        Per-game override in game_settings wins; None = non-Steam (WoW, Custom, …).
        """
        game = game or (self.game_var.get() if hasattr(self, "game_var") else None)
        bag = (getattr(self, "game_settings", {}) or {}).get(game or "", {}) or {}
        if "steam_appid" in bag:
            raw = bag.get("steam_appid")
        else:
            prof = GAME_PROFILES.get(game or "") or self.profile()
            raw = prof.get("steam_appid")
        try:
            return int(raw) if raw not in (None, "", 0, "0") else None
        except Exception:
            return None

    def is_steam_game(self, game: Optional[str] = None) -> bool:
        return self.steam_appid(game) is not None

    def _set_steam_label(self, text: str, color: str = None):
        if not self._tk_alive() or not hasattr(self, "steam_dot"):
            return
        try:
            self.steam_dot.configure(text=text, text_color=color or C["muted"])
        except Exception:
            pass

    def _steam_region_local_hour(self, unix: float, region_key: str) -> int:
        """Local hour (0–23) for a region timezone at unix time."""
        meta = STEAM_REGIONS.get(region_key) or {}
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime

            tz = ZoneInfo(str(meta.get("tz") or "UTC"))
            return int(datetime.fromtimestamp(float(unix), tz=tz).hour)
        except Exception:
            # Fixed offset fallback (ignores DST)
            off = int(meta.get("utc_offset_std", 0))
            utc_h = int(time.gmtime(float(unix)).tm_hour)
            return (utc_h + off) % 24

    def _steam_region_is_prime(self, unix: float, region_key: str) -> bool:
        meta = STEAM_REGIONS.get(region_key) or {}
        hours = meta.get("prime_hours") or ()
        return self._steam_region_local_hour(unix, region_key) in hours

    def _steam_region_is_off(self, unix: float, region_key: str) -> bool:
        meta = STEAM_REGIONS.get(region_key) or {}
        hours = meta.get("off_hours") or ()
        return self._steam_region_local_hour(unix, region_key) in hours

    def _steam_regions_in_prime_now(self, now: Optional[float] = None) -> list[str]:
        now = now if now is not None else time.time()
        out = []
        for key in STEAM_REGION_ORDER:
            if self._steam_region_is_prime(now, key):
                out.append(STEAM_REGIONS[key]["label"])
        return out

    def _steam_format_header_label(self, count: Optional[int], status: str = "ok") -> tuple[str, str]:
        """Header chip text + color. Always global count; annotate which regions are in prime."""
        if status == "err":
            return "Players · err", C["warn"]
        if status == "offline":
            return "Players · offline", C["faint"]
        if status == "na":
            return "Players · n/a", C["faint"]
        if status == "loading":
            return "Players · …", C["faint"]
        if count is None:
            return "Players · ?", C["warn"]
        primes = self._steam_regions_in_prime_now()
        base = f"Players · {self._format_player_count(count)}"
        if primes:
            return f"{base} · {'/'.join(primes)} prime", C["info"]
        return f"{base} · global", C["info"]

    def on_steam_region_focus(self, choice: str = None):
        if choice is None and hasattr(self, "steam_region_focus"):
            choice = self.steam_region_focus.get()
        choice = str(choice or "All")
        if choice not in STEAM_REGION_FOCUS_OPTIONS:
            choice = "All"
        if hasattr(self, "steam_region_focus"):
            self.steam_region_focus.set(choice)
        if hasattr(self, "steam_region_seg"):
            try:
                self.steam_region_seg.set(choice)
            except Exception:
                pass
        self.save_settings()
        self.update_steam_pop_report()
        self._update_steam_region_now_label()
        self.show_toast(f"Steam region lens · {choice}", kind="info")

    def _update_steam_region_now_label(self):
        if not hasattr(self, "steam_region_now"):
            return
        primes = self._steam_regions_in_prime_now()
        if primes:
            txt = f"Now in prime: {', '.join(primes)}"
        else:
            txt = "Now: no major region in evening prime"
        try:
            self.steam_region_now.configure(text=txt)
        except Exception:
            pass

    def _fetch_steam_player_count(self, appid: int) -> tuple[Optional[int], str, str]:
        """Returns (count, label, color). Global concurrent Steam players for this app."""
        try:
            r = requests.get(
                STEAM_PLAYERS_URL,
                params={"appid": appid},
                timeout=4,
            )
            if r.status_code != 200:
                return None, "Players · err", C["warn"]
            data = r.json().get("response") or {}
            if int(data.get("result", 0)) == 1 and "player_count" in data:
                count = int(data["player_count"])
                label, color = self._steam_format_header_label(count, "ok")
                return count, label, color
            return None, "Players · ?", C["warn"]
        except Exception:
            return None, "Players · offline", C["faint"]

    def pulse_steam_players(self):
        """Poll Steam GetNumberOfCurrentPlayers for the selected game (no API key)."""
        if not self._tk_alive():
            return
        self._steam_pulse_gen += 1
        gen = self._steam_pulse_gen
        appid = self.steam_appid()
        try:
            game_name = self.game_var.get() if hasattr(self, "game_var") else ""
        except Exception:
            game_name = ""

        if not appid:
            self._steam_player_count = None
            self._set_steam_label("Players · n/a", C["faint"])
            self._steam_history = []
            self.schedule_ui(self.draw_steam_chart)
            self.schedule_ui(self._update_steam_region_now_label)
            return

        self._set_steam_label("Players · …", C["faint"])

        def check():
            # Worker thread: network only — never touch Tk/widgets/vars here
            if gen != self._steam_pulse_gen or not getattr(self, "_alive", False):
                return
            count, label, color = self._fetch_steam_player_count(appid)

            def apply():
                if gen != self._steam_pulse_gen or not self._tk_alive():
                    return
                self._steam_player_count = count
                self._set_steam_label(label, color)
                self._update_steam_region_now_label()
                if count is not None:
                    self._note_steam_session_peak(count)
                    self._maybe_log_steam_players(appid, game_name, count)
                # Live header refresh (main thread only)
                if gen == self._steam_pulse_gen and self._tk_alive():
                    self.schedule_ui(
                        lambda g=gen: self._steam_refresh_if_current(g),
                        delay_ms=STEAM_LIVE_INTERVAL_S * 1000,
                    )

            # If schedule fails (app closed), drop the result — do not fall back to Tk from this thread
            self.schedule_ui(apply)

        threading.Thread(target=check, daemon=True).start()

    def _steam_refresh_if_current(self, gen: int):
        if not self._tk_alive():
            return
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
        """Append to steam_players_log.txt on cadence (default 15 min). Main-thread only."""
        if not self._tk_alive():
            return
        try:
            if hasattr(self, "steam_log_enabled") and not self.steam_log_enabled.get():
                return
        except Exception:
            return
        now = time.time()
        try:
            interval = self._steam_log_interval_sec()
        except Exception:
            interval = 15 * 60
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
        try:
            current_app = self.steam_appid()
        except Exception:
            current_app = None
        if appid == current_app:
            self._steam_history.append((now, int(count)))
            # Cap memory (~1 week at 15 min)
            if len(self._steam_history) > 800:
                self._steam_history = self._steam_history[-800:]
            self.schedule_ui(self.draw_steam_chart)

    def _read_steam_log_rows(self, appid: Optional[int] = None) -> list[tuple[float, int]]:
        """All log samples for an appid: (unix, players), sorted by time."""
        appid = appid or self.steam_appid()
        if not appid or not os.path.isfile(STEAM_LOG_PATH):
            return []
        rows: list[tuple[float, int]] = []
        try:
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
        except Exception:
            return []
        rows.sort(key=lambda r: r[0])
        return rows

    def load_steam_history_from_log(self, appid: Optional[int] = None, max_points: int = 400):
        """Load recent points for the chart from the TSV log."""
        appid = appid or self.steam_appid()
        rows = self._read_steam_log_rows(appid)
        self._steam_history = rows[-max_points:] if rows else []
        # Keep full series for the population report
        self._steam_history_full = rows

    def refresh_steam_chart(self):
        self.load_steam_history_from_log()
        self.draw_steam_chart()
        self.update_steam_pop_report()

    def _steam_mean(self, vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def _steam_median(self, vals: list[float]) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        n = len(s)
        mid = n // 2
        if n % 2:
            return float(s[mid])
        return (s[mid - 1] + s[mid]) / 2.0

    def _steam_stdev(self, vals: list[float]) -> float:
        n = len(vals)
        if n < 2:
            return 0.0
        m = self._steam_mean(vals)
        var = sum((v - m) ** 2 for v in vals) / (n - 1)
        return var ** 0.5

    def _steam_slope_per_hour(self, rows: list[tuple[float, int]]) -> float:
        """Linear regression: players per hour change (using real time as X)."""
        if len(rows) < 2:
            return 0.0
        t0 = rows[0][0]
        xs = [(r[0] - t0) / 3600.0 for r in rows]  # hours from start
        ys = [float(r[1]) for r in rows]
        n = len(xs)
        mx = self._steam_mean(xs)
        my = self._steam_mean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = sum((x - mx) ** 2 for x in xs)
        if den <= 1e-12:
            return 0.0
        return num / den  # Δplayers per hour

    def _steam_window(
        self, rows: list[tuple[float, int]], hours: float
    ) -> list[tuple[float, int]]:
        if not rows:
            return []
        cutoff = rows[-1][0] - hours * 3600.0
        return [r for r in rows if r[0] >= cutoff]

    def _steam_hour_of_day_stats(
        self, rows: list[tuple[float, int]]
    ) -> tuple[Optional[int], float, Optional[int], float]:
        """Return (best_hour, best_avg, worst_hour, worst_avg) local time."""
        buckets: dict[int, list[int]] = {}
        for t, v in rows:
            h = int(time.localtime(t).tm_hour)
            buckets.setdefault(h, []).append(int(v))
        if not buckets:
            return None, 0.0, None, 0.0
        avgs = {h: self._steam_mean(vs) for h, vs in buckets.items()}
        best_h = max(avgs, key=lambda k: avgs[k])
        worst_h = min(avgs, key=lambda k: avgs[k])
        return best_h, avgs[best_h], worst_h, avgs[worst_h]

    def _steam_trend_label(self, slope_per_h: float, mean_v: float) -> str:
        """Classify trend relative to mean population."""
        if mean_v <= 0:
            return "stable"
        # ~0.5% of mean per hour is noise
        thr = max(2.0, mean_v * 0.005)
        if slope_per_h > thr:
            return "rising"
        if slope_per_h < -thr:
            return "falling"
        return "stable"

    def compute_steam_pop_report(self, appid: Optional[int] = None) -> str:
        """
        High/low report + statistical trend analysis from the full log
        for the selected game AppID.
        """
        appid = appid or self.steam_appid()
        game = self.game_var.get() if hasattr(self, "game_var") else "Game"
        if not appid:
            return "No Steam AppID for this game — population log N/A."

        rows = getattr(self, "_steam_history_full", None)
        if not rows:
            rows = self._read_steam_log_rows(appid)
            self._steam_history_full = rows

        if not rows:
            return (
                f"{game} · no log samples yet.\n"
                "Enable “Log to file”, leave the app open, then Refresh chart."
            )

        vals = [int(r[1]) for r in rows]
        times = [float(r[0]) for r in rows]
        n = len(vals)
        now_v = vals[-1]
        now_t = times[-1]
        vmin, vmax = min(vals), max(vals)
        i_min = vals.index(vmin)
        i_max = vals.index(vmax)
        t_min, t_max = times[i_min], times[i_max]
        mean_v = self._steam_mean(vals)
        med_v = self._steam_median(vals)
        std_v = self._steam_stdev(vals)
        span_h = max(0.01, (times[-1] - times[0]) / 3600.0)

        # Full-log slope
        slope_all = self._steam_slope_per_hour(rows)
        trend_all = self._steam_trend_label(slope_all, mean_v)

        # Recent windows
        last_6 = self._steam_window(rows, 6.0)
        last_24 = self._steam_window(rows, 24.0)
        # Earlier 6h window (before last 6h) for comparison
        earlier_6: list[tuple[float, int]] = []
        if last_6:
            cut = last_6[0][0]
            earlier_6 = [r for r in rows if cut - 6 * 3600 <= r[0] < cut]

        def avg_rows(rs):
            return self._steam_mean([r[1] for r in rs]) if rs else None

        a6 = avg_rows(last_6)
        a24 = avg_rows(last_24)
        a_prev6 = avg_rows(earlier_6)
        slope_6 = self._steam_slope_per_hour(last_6) if len(last_6) >= 3 else 0.0
        slope_24 = self._steam_slope_per_hour(last_24) if len(last_24) >= 3 else 0.0
        trend_6 = self._steam_trend_label(slope_6, a6 or mean_v)
        trend_24 = self._steam_trend_label(slope_24, a24 or mean_v)

        best_h, best_avg, worst_h, worst_avg = self._steam_hour_of_day_stats(rows)

        # vs mean
        vs_mean_pct = ((now_v - mean_v) / mean_v * 100.0) if mean_v else 0.0
        if now_v >= vmax * 0.98 and n > 1:
            regime = "near all-time HIGH in your log"
        elif now_v <= vmin * 1.02 + 1 and n > 1:
            regime = "near all-time LOW in your log"
        elif vs_mean_pct >= 8:
            regime = "above typical (good list/LFG window)"
        elif vs_mean_pct <= -8:
            regime = "below typical (quieter / farm in peace)"
        else:
            regime = "around typical population"

        def fmt_t(ts: float) -> str:
            return time.strftime("%a %m/%d %H:%M", time.localtime(ts))

        def fmt_n(v: float) -> str:
            try:
                return f"{int(round(v)):,}"
            except Exception:
                return str(v)

        def fmt_slope(s: float) -> str:
            sign = "+" if s >= 0 else ""
            return f"{sign}{s:.1f}/hr"

        def fmt_hour(h: Optional[int]) -> str:
            if h is None:
                return "—"
            return f"{h:02d}:00–{h:02d}:59"

        # Percentile rough: current rank
        below = sum(1 for v in vals if v < now_v)
        pctile = (below / max(n - 1, 1)) * 100.0

        lines = [
            f"{game} · full log · {n} samples · {span_h:.1f}h coverage · now {fmt_n(now_v)} ({fmt_t(now_t)})",
            f"HIGH  {fmt_n(vmax)} @ {fmt_t(t_max)}     LOW  {fmt_n(vmin)} @ {fmt_t(t_min)}",
            (
                f"Avg {fmt_n(mean_v)} · median {fmt_n(med_v)} · σ {fmt_n(std_v)} · "
                f"now {vs_mean_pct:+.1f}% vs avg · ~{pctile:.0f}th pctile · {regime}"
            ),
            (
                f"Trend (all log): {trend_all} ({fmt_slope(slope_all)})   ·   "
                f"last 24h: {trend_24} ({fmt_slope(slope_24)})   ·   "
                f"last 6h: {trend_6} ({fmt_slope(slope_6)})"
            ),
        ]

        win_bits = []
        if a24 is not None:
            win_bits.append(f"24h avg {fmt_n(a24)}")
        if a6 is not None:
            win_bits.append(f"6h avg {fmt_n(a6)}")
        if a6 is not None and a_prev6 is not None and a_prev6 > 0:
            d = (a6 - a_prev6) / a_prev6 * 100.0
            win_bits.append(f"6h vs prior 6h {d:+.1f}%")
        if win_bits:
            lines.append("Windows: " + " · ".join(win_bits))

        if best_h is not None and worst_h is not None:
            lines.append(
                f"By hour of day (local PC): busiest {fmt_hour(best_h)} (avg {fmt_n(best_avg)}) · "
                f"quietest {fmt_hour(worst_h)} (avg {fmt_n(worst_avg)})"
            )

        # ---- NA / Europe / Asia prime-time slices of GLOBAL Steam total ----
        # Steam does not publish separate regional concurrent counts for Quinfall.
        lines.append(
            "REGIONS (Steam global total only — sliced by each region’s local evening):"
        )
        focus = "All"
        if hasattr(self, "steam_region_focus"):
            try:
                focus = self.steam_region_focus.get() or "All"
            except Exception:
                focus = "All"
        region_stats: dict[str, dict] = {}
        for key in STEAM_REGION_ORDER:
            meta = STEAM_REGIONS[key]
            prime_rows = [r for r in rows if self._steam_region_is_prime(r[0], key)]
            off_rows = [r for r in rows if self._steam_region_is_off(r[0], key)]
            p_avg = avg_rows(prime_rows)
            o_avg = avg_rows(off_rows)
            p_hi = max((r[1] for r in prime_rows), default=None)
            p_lo = min((r[1] for r in prime_rows), default=None)
            in_prime = self._steam_region_is_prime(now_t, key)
            lift = None
            if p_avg is not None and o_avg is not None and o_avg > 0:
                lift = (p_avg - o_avg) / o_avg * 100.0
            region_stats[key] = {
                "prime_n": len(prime_rows),
                "off_n": len(off_rows),
                "p_avg": p_avg,
                "o_avg": o_avg,
                "p_hi": p_hi,
                "p_lo": p_lo,
                "in_prime": in_prime,
                "lift": lift,
            }
            p_txt = fmt_n(p_avg) if p_avg is not None else "—"
            o_txt = fmt_n(o_avg) if o_avg is not None else "—"
            hi_lo = ""
            if p_hi is not None and p_lo is not None:
                hi_lo = f" · prime high {fmt_n(p_hi)} / low {fmt_n(p_lo)}"
            lift_txt = f" · evening +{lift:.0f}% vs late-night" if lift is not None else ""
            now_tag = " · NOW IN PRIME" if in_prime else ""
            mark = "► " if focus == key else "  "
            lines.append(
                f"{mark}{meta['label']:4} ({meta['long']}): "
                f"evening avg {p_txt} (n={len(prime_rows)}) · "
                f"off-peak avg {o_txt} (n={len(off_rows)})"
                f"{hi_lo}{lift_txt}{now_tag}"
            )

        primes_now = self._steam_regions_in_prime_now(now_t)
        if primes_now:
            lines.append(f"Right now (clock): {', '.join(primes_now)} evening prime · global pop {fmt_n(now_v)}")
        else:
            lines.append(f"Right now (clock): between major region primes · global pop {fmt_n(now_v)}")

        # Focused region: trend using only that region’s prime samples
        if focus in STEAM_REGIONS:
            meta = STEAM_REGIONS[focus]
            focus_rows = [r for r in rows if self._steam_region_is_prime(r[0], focus)]
            if len(focus_rows) >= 3:
                f_slope = self._steam_slope_per_hour(focus_rows)
                f_vals = [r[1] for r in focus_rows]
                f_mean = self._steam_mean(f_vals)
                f_trend = self._steam_trend_label(f_slope, f_mean)
                f_hi, f_lo = max(f_vals), min(f_vals)
                lines.append(
                    f"Focus {meta['label']} evening only: trend {f_trend} ({fmt_slope(f_slope)}) · "
                    f"avg {fmt_n(f_mean)} · high {fmt_n(f_hi)} · low {fmt_n(f_lo)} · n={len(focus_rows)}"
                )
            else:
                lines.append(
                    f"Focus {meta['label']}: need more evening samples (have {len(focus_rows)}) "
                    "— leave app open across more nights."
                )

        # Simple advice (prefer focused region if set)
        if trend_6 == "rising" and vs_mean_pct > 0:
            advice = "Advice: global pop climbing and above avg — good window for LFG / listings."
        elif trend_6 == "falling" and vs_mean_pct < 0:
            advice = "Advice: cooling off and below avg — quieter grind / undercut less urgently."
        elif primes_now:
            advice = (
                f"Advice: {', '.join(primes_now)} in evening prime now — "
                "expect more social/market activity if those regions play Quinfall."
            )
        elif best_h is not None and int(time.localtime(now_t).tm_hour) == best_h:
            advice = "Advice: historically busy hour on your PC clock — market/LFG may move faster."
        else:
            advice = (
                "Advice: more overnight samples → stronger NA/EU/Asia prime signals. "
                "Steam only publishes one global concurrent total."
            )
        lines.append(advice)
        lines.append(
            "Note: NA/EU/Asia are NOT separate Steam player counts — "
            "they are time-of-day lenses on the same global total."
        )

        return "\n".join(lines)

    def update_steam_pop_report(self):
        if not hasattr(self, "steam_pop_report"):
            return
        try:
            text = self.compute_steam_pop_report()
            self._steam_pop_report_text = text
            self.steam_pop_report.configure(text=text)
        except Exception as e:
            self._steam_pop_report_text = f"Report error: {e}"
            try:
                self.steam_pop_report.configure(text=self._steam_pop_report_text)
            except Exception:
                pass

    def copy_steam_pop_report(self):
        """Copy population high/low + trend summary for Discord paste."""
        text = (getattr(self, "_steam_pop_report_text", "") or "").strip()
        if not text:
            # Fresh compute if UI never refreshed
            try:
                text = self.compute_steam_pop_report().strip()
                self._steam_pop_report_text = text
            except Exception:
                text = ""
        if not text or text.startswith("No Steam") or "no log samples" in text.lower():
            self.show_toast("Nothing to copy yet — need log samples", kind="warn")
            return
        game = self.game_var.get() if hasattr(self, "game_var") else "Game"
        focus = "All"
        if hasattr(self, "steam_region_focus"):
            try:
                focus = self.steam_region_focus.get() or "All"
            except Exception:
                pass
        # Discord mono block reads cleanly in channels
        payload = (
            f"**Steam pop · {game}** · lens: {focus} (global Steam total)\n"
            f"```\n{text}\n```"
        )
        try:
            # Bypass char-limit block used for in-game chat lines
            pyperclip.copy(payload)
            self.show_toast("Population report copied", kind="ok")
            self.set_status("Steam pop report → clipboard (Discord-ready)")
            if hasattr(self, "steam_pop_copy_btn"):
                try:
                    self.steam_pop_copy_btn.configure(text="✓ Copied")
                    self.root.after(
                        900,
                        lambda: self.steam_pop_copy_btn.configure(text="Copy for Discord")
                        if hasattr(self, "steam_pop_copy_btn") and self.steam_pop_copy_btn.winfo_exists()
                        else None,
                    )
                except Exception:
                    pass
        except Exception as e:
            self.show_toast(f"Copy failed: {e}", kind="error")

    def _steam_time_tick_step(self, span_s: float, max_ticks: int = 6) -> float:
        """Pick a readable tick interval (seconds) for the X axis."""
        span_s = max(float(span_s), 60.0)
        # Prefer “wall clock” friendly steps
        candidates = (
            5 * 60, 10 * 60, 15 * 60, 30 * 60,
            60 * 60, 2 * 3600, 3 * 3600, 4 * 3600, 6 * 3600,
            12 * 3600, 24 * 3600, 2 * 86400, 7 * 86400,
        )
        for step in candidates:
            if span_s / step <= max_ticks:
                return float(step)
        return max(span_s / max(max_ticks, 1), 60.0)

    def _steam_align_tick(self, t: float, step_s: float) -> float:
        """Align unix time to a local-time multiple of step_s (approx for day/hour steps)."""
        try:
            lt = time.localtime(t)
            # Build local midnight for day alignment when step is multi-hour/day
            if step_s >= 86400:
                midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
                day_step = int(round(step_s / 86400.0)) or 1
                # day-of-year-ish: step from epoch days in local offset is hard; use midnight ceil
                if t <= midnight:
                    return midnight
                days_ahead = int((t - midnight) // 86400)
                aligned_days = ((days_ahead + day_step - 1) // day_step) * day_step
                return midnight + aligned_days * 86400
            if step_s >= 3600:
                # Align to local hour boundaries
                hour0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, 0, 0, 0, 0, -1))
                hours = int(round(step_s / 3600.0)) or 1
                # snap hour0 up to next multiple of `hours` from midnight
                mid = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
                h_from_mid = int((hour0 - mid) // 3600)
                h_aligned = ((h_from_mid + hours - 1) // hours) * hours
                cand = mid + h_aligned * 3600
                if cand < t - 1:
                    cand = mid + (h_aligned + hours) * 3600
                return cand
            # Minute-scale: align from local minute
            minute0 = time.mktime(
                (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min, 0, 0, 0, -1)
            )
            mins = int(round(step_s / 60.0)) or 1
            m = lt.tm_min
            m_aligned = ((m + mins - 1) // mins) * mins
            if m_aligned >= 60:
                return minute0 + (60 - m) * 60  # next hour
            cand = time.mktime(
                (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, m_aligned, 0, 0, 0, -1)
            )
            if cand < t - 1:
                cand += mins * 60
            return cand
        except Exception:
            # Fallback: epoch step
            return (int(t // step_s) + 1) * step_s

    def _steam_format_axis_time(self, t: float, span_s: float, prev_t: Optional[float] = None) -> str:
        """Human X-axis label; adds date when the day changes or span is multi-day."""
        lt = time.localtime(t)
        multi_day = span_s >= 20 * 3600
        day_changed = False
        if prev_t is not None:
            day_changed = time.localtime(prev_t).tm_yday != lt.tm_yday or time.localtime(prev_t).tm_year != lt.tm_year
        if multi_day or day_changed:
            if span_s >= 3 * 86400:
                return time.strftime("%m/%d", lt)
            return time.strftime("%m/%d %H:%M", lt)
        if span_s < 3 * 3600:
            return time.strftime("%H:%M", lt)
        return time.strftime("%H:%M", lt)

    def _steam_x_ticks(self, t0: float, t1: float, max_ticks: int = 6) -> list[float]:
        if t1 < t0:
            t0, t1 = t1, t0
        span = max(t1 - t0, 1.0)
        # Single sample or tiny span: just endpoints
        if span < 90:
            return [t0] if abs(t1 - t0) < 1 else [t0, t1]
        step = self._steam_time_tick_step(span, max_ticks=max_ticks)
        ticks: list[float] = []
        # Always include start
        ticks.append(t0)
        cur = self._steam_align_tick(t0 + 1, step)
        # If first aligned tick is almost t0, skip ahead one step
        if cur - t0 < step * 0.25:
            cur = self._steam_align_tick(t0 + step * 0.5, step)
        guard = 0
        while cur < t1 - step * 0.15 and guard < 40:
            if cur > t0 + 30:
                ticks.append(cur)
            cur += step
            guard += 1
        if t1 - ticks[-1] > 45:
            ticks.append(t1)
        elif abs(ticks[-1] - t1) > 1:
            ticks[-1] = t1
        # Dedup near-duplicates
        cleaned: list[float] = []
        for t in ticks:
            if not cleaned or abs(t - cleaned[-1]) > max(span * 0.04, 45):
                cleaned.append(t)
        if cleaned and abs(cleaned[-1] - t1) > 1:
            if abs(t1 - cleaned[-1]) < max(span * 0.08, 90) and len(cleaned) > 1:
                cleaned[-1] = t1
            else:
                cleaned.append(t1)
        return cleaned[: max_ticks + 2]

    def draw_steam_chart(self):
        """Population trend: X = real sample time, Y = concurrent players."""
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
            self.update_steam_pop_report()
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
            self.update_steam_pop_report()
            return

        # Sort by time; plot on real timeline (not evenly spaced sample index)
        pts = sorted(pts, key=lambda p: p[0])
        times = [float(p[0]) for p in pts]
        vals = [int(p[1]) for p in pts]
        t0, t1 = times[0], times[-1]
        span = max(t1 - t0, 1.0)
        vmin, vmax = min(vals), max(vals)
        if vmax <= vmin:
            vmax = vmin + 1
            vmin = max(0, vmin - 1)

        # Margins: left for Y labels, bottom for X time labels
        pad_l, pad_r = 44, 12
        pad_t, pad_b = 14, 36
        plot_w = max(w - pad_l - pad_r, 20)
        plot_h = max(h - pad_t - pad_b, 20)
        x0, y0 = pad_l, pad_t
        x1, y1 = pad_l + plot_w, pad_t + plot_h

        def x_at(t: float) -> float:
            if len(times) == 1 or span <= 1:
                return x0 + plot_w * 0.5
            return x0 + ((t - t0) / span) * plot_w

        def y_at(v: float) -> float:
            return y1 - ((v - vmin) / (vmax - vmin)) * plot_h

        # Plot background + frame
        c.create_rectangle(x0, y0, x1, y1, outline=C["line"], width=1, fill=C["bg"])

        # Horizontal grid + Y labels
        for i in range(0, 5):
            frac = i / 4.0
            y = y0 + plot_h * frac
            v = vmax - (vmax - vmin) * frac
            c.create_line(x0, y, x1, y, fill=C["line"])
            if i in (0, 2, 4):
                c.create_text(
                    x0 - 4, y,
                    text=self._format_player_count(int(round(v))),
                    anchor="e", fill=C["faint"], font=(FONT_UI, 9),
                )

        # Vertical grid + X time labels (real clock)
        max_x_ticks = 7 if plot_w > 420 else (5 if plot_w > 280 else 4)
        xticks = self._steam_x_ticks(t0, t1, max_ticks=max_x_ticks)
        prev_tick: Optional[float] = None
        for ti in xticks:
            x = x_at(ti)
            c.create_line(x, y0, x, y1, fill=C["line"])
            # tick mark below axis
            c.create_line(x, y1, x, y1 + 5, fill=C["muted"])
            label = self._steam_format_axis_time(ti, span, prev_tick)
            # Slightly rotate feel via two-line day/time when multi-day already in format
            c.create_text(
                x, y1 + 8,
                text=label,
                anchor="n",
                fill=C["muted"],
                font=(FONT_UI, 9),
            )
            prev_tick = ti

        # Axis captions
        c.create_text(
            x0 + plot_w / 2, h - 3,
            text="Time (local)",
            anchor="s",
            fill=C["faint"],
            font=(FONT_UI, 8),
        )

        # Line + markers (time-scaled X)
        coords: list[float] = []
        for t, v in zip(times, vals):
            coords.extend([x_at(t), y_at(v)])
        if len(coords) >= 4:
            c.create_line(*coords, fill=C["info"], width=2, smooth=False)
        elif len(coords) == 2:
            c.create_oval(
                coords[0] - 4, coords[1] - 4, coords[0] + 4, coords[1] + 4,
                fill=C["info"], outline="",
            )
        # Peak / min (first occurrence of max / min)
        i_max = max(range(len(vals)), key=lambda i: (vals[i], -times[i]))
        i_min = min(range(len(vals)), key=lambda i: (vals[i], times[i]))
        t_peak, v_peak = times[i_max], vals[i_max]
        t_low, v_low = times[i_min], vals[i_min]
        peak_same = (i_max == i_min) or (v_peak == v_low)

        def _clock(ts: float) -> str:
            return time.strftime("%H:%M", time.localtime(ts))

        # Sample dots (cap count so dense logs stay readable)
        mark_every = max(1, len(pts) // 40)
        for i, (t, v) in enumerate(zip(times, vals)):
            if i % mark_every != 0 and i not in (0, len(pts) - 1, i_max, i_min):
                continue
            px, py = x_at(t), y_at(v)
            r = 2.5 if i != len(pts) - 1 else 4
            fill = C["success"] if i == len(pts) - 1 else C["info"]
            c.create_oval(px - r, py - r, px + r, py + r, fill=fill, outline="")

        def _mark_extremum(t: float, v: int, kind: str):
            """Diamond + callout for peak (amber) or min (muted)."""
            px, py = x_at(t), y_at(v)
            color = C["warn"] if kind == "peak" else C["muted"]
            d = 6
            c.create_polygon(
                px, py - d, px + d, py, px, py + d, px - d, py,
                fill=color, outline=C["text"], width=1,
            )
            label = f"{'peak' if kind == 'peak' else 'min'} {self._format_player_count(v)} @ {_clock(t)}"
            above = kind == "peak" or py > (y0 + y1) / 2
            ly = py - 14 if above else py + 14
            lx = min(max(px, x0 + 40), x1 - 40)
            c.create_line(px, py, lx, ly, fill=color, width=1)
            c.create_text(
                lx, ly,
                text=label,
                anchor="s" if above else "n",
                fill=color,
                font=(FONT_UI, 9, "bold"),
            )

        if len(pts) >= 1:
            _mark_extremum(t_peak, v_peak, "peak")
            if not peak_same:
                _mark_extremum(t_low, v_low, "min")

        # Latest value callout
        c.create_text(
            x1 - 2, y0 + 2,
            text=f"now {self._format_player_count(vals[-1])}",
            anchor="ne", fill=C["info"], font=(FONT_UI, 10, "bold"),
        )

        if hasattr(self, "steam_chart_meta"):
            t0s = time.strftime("%a %m/%d %H:%M", time.localtime(t0))
            t1s = time.strftime("%a %m/%d %H:%M", time.localtime(t1))
            span_h = span / 3600.0
            if span_h < 1:
                span_txt = f"{span / 60.0:.0f}m"
            elif span_h < 48:
                span_txt = f"{span_h:.1f}h"
            else:
                span_txt = f"{span_h / 24.0:.1f}d"
            peak_txt = f"peak {v_peak:,} @ {_clock(t_peak)}"
            min_txt = f"min {v_low:,} @ {_clock(t_low)}"
            ext_txt = peak_txt if peak_same else f"{peak_txt} · {min_txt}"
            self.steam_chart_meta.configure(
                text=(
                    f"{game} · {len(pts)} samples · {t0s}  →  {t1s}  ({span_txt}) · "
                    f"now {vals[-1]:,} · {ext_txt}"
                )
            )
        self.update_steam_pop_report()

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
        """
        Switch active game and restore that game's settings bag.
        OptionMenu already sets game_var before calling us — track previous via
        _active_game_for_settings so we don't lose the game we're leaving.
        """
        if game is None:
            game = self.game_var.get() if hasattr(self, "game_var") else self.default_game
        if game not in GAME_PROFILES:
            game = self.default_game if self.default_game in GAME_PROFILES else "The Quinfall"

        prev = getattr(self, "_active_game_for_settings", None)

        # Snapshot the game we're leaving (regions, LFG, economy, macros, …)
        if prev and prev != game:
            try:
                # Ensure game_var still points at prev for snapshot of UI... 
                # OptionMenu already flipped game_var to *new* game, so snapshot
                # using stored prev key but LIVE widgets currently show prev game's
                # values until we apply. Actually after OptionMenu change, widgets
                # still hold previous game's LFG/regions until we apply — game_var
                # is new. Snapshot must write under *prev* key from current widgets.
                self._snapshot_game_settings(prev)
            except Exception:
                pass

        if hasattr(self, "game_var") and self.game_var.get() != game:
            self.game_var.set(game)

        prof = self.profile()
        lim = self.limit()
        if hasattr(self, "limit_badge"):
            self.limit_badge.configure(text=f"{lim} max")
        if hasattr(self, "game_pill"):
            self.game_pill.configure(text=prof["short"], fg_color=C["elevated"], text_color=self.accent())
        self._refresh_game_icon()

        # Restore full per-game bag (regions, LFG, economy, macros, mood, …)
        try:
            self._apply_game_settings(game)
        except Exception:
            # Fallback: at least swap activity list + LFG targets
            acts = prof["activities"]
            if hasattr(self, "activity_menu") and self.activity_menu is not None:
                try:
                    self.activity_menu.configure(values=acts)
                except Exception:
                    pass
            if hasattr(self, "activity_var") and self.activity_var.get() not in acts:
                self.activity_var.set(acts[0])
            if hasattr(self, "lfg_target_var"):
                names = self.lfg_target_names(game)
                if hasattr(self, "lfg_target_menu"):
                    self.lfg_target_menu.configure(values=names)
                preferred = (self.lfg_defaults or {}).get(game)
                self.lfg_target_var.set(self._resolve_lfg_target(game, preferred))
            if hasattr(self, "lfg_location_var"):
                loc_pref = (getattr(self, "lfg_location_defaults", {}) or {}).get(game)
                self.lfg_location_var.set(self._resolve_lfg_location(game, loc_pref))
                self.sync_lfg_location_if_needed()
            self._active_game_for_settings = game

        self.rebuild_quick_buttons()
        if hasattr(self, "msg_textbox"):
            self.update_counter()
        self._update_quick_out_meter()
        self.refresh_hud_line()
        # Persist previous game's house style, then load this game's
        # House style sync uses _house_style_game (previous editor target)
        try:
            if prev:
                self._house_style_game = prev
            self._sync_house_style_from_ui()
        except Exception:
            pass
        self._load_house_style_into_ui(game)
        if hasattr(self, "house_style_hint"):
            try:
                short = (GAME_PROFILES.get(game) or {}).get("short", game)
                steam = self.steam_appid(game)
                steam_bit = f" · Steam {steam}" if steam else " · non-Steam"
                self.house_style_hint.configure(text=f"Editing style for {short}{steam_bit}")
            except Exception:
                pass
        # Refresh Steam count + chart for the new game (n/a for non-Steam)
        self.load_steam_history_from_log()
        self.pulse_steam_players()
        self.root.after(100, self.draw_steam_chart)
        if persist:
            self.save_settings()
            steam = self.steam_appid(game)
            tag = f"Steam {steam}" if steam else "non-Steam"
            self.set_status(f"{prof['short']} · {tag} · settings restored")

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
        # Flash sticky Copy (the only paste path)
        btn = getattr(self, "sticky_copy_btn", None)
        if btn is not None:
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
        if not self._tk_alive() or not hasattr(self, "toast"):
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
            self._toast_job = None
        # schedule_ui returns bool; keep job id via root.after only when alive
        if self._tk_alive():
            try:
                self._toast_job = self.root.after(2000, self._hide_toast)
            except Exception:
                self._toast_job = None

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
        if not self._tk_alive():
            return
        try:
            if not self._busy and hasattr(self, "status_bar"):
                cur = self.status_bar.cget("text")
                if cur in TIPS or cur in HYPE_LINES or not cur:
                    self.status_bar.configure(text=random.choice(TIPS))
        except Exception:
            pass
        self.schedule_ui(self._tip_rotate, delay_ms=16000)

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
        self.show_toast("Paste what they said, then Write reply", kind="info")

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
            model = self._selected_lm_model() if hasattr(self, "_selected_lm_model") else "LM Studio"
            engines.append(f"VL ({model})")
            eng = " · ".join(engines)
            mode = getattr(self, "lm_mode", "Local")
            if hasattr(self, "lm_mode_var"):
                try:
                    mode = self.lm_mode_var.get() or mode
                except Exception:
                    pass
            return (
                f"Chat area set · {w}×{h}px @ ({r['left']},{r['top']})  ·  "
                f"OCR: {eng}  ·  {mode}"
            )
        return "Chat area not set · click Set chat box on screen, then drag over your game chat"

    def open_last_chat_capture(self):
        path = LAST_OCR_PATH
        if not os.path.isfile(path):
            self.show_toast("No chat grab yet — use Grab chat first", kind="warn")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            try:
                subprocess.Popen(["explorer", "/select,", path])
            except Exception:
                self.show_toast(path, kind="info")

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
        self._start_region_calibrate(
            prompt="Drag a box over your GAME CHAT  ·  release to save  ·  Esc to cancel",
            on_saved=self._on_chat_region_saved,
            on_cancel=lambda: (
                self._refresh_ocr_status("cancelled"),
                self.show_toast("Calibration cancelled", kind="info"),
            ),
        )

    def calibrate_market_region(self):
        """Fullscreen drag-select for market / auction listings."""
        self._start_region_calibrate(
            prompt="Drag a box over MARKET / LISTINGS  ·  release to save  ·  Esc to cancel",
            on_saved=self._on_market_region_saved,
            on_cancel=lambda: (
                self._refresh_market_status("cancelled"),
                self.show_toast("Market calibration cancelled", kind="info"),
            ),
        )

    def _on_chat_region_saved(self, region: dict):
        self.chat_region = region
        # Bind region to the active game (each game keeps its own OCR box)
        try:
            g = self.game_var.get() if hasattr(self, "game_var") else None
            self._snapshot_game_settings(g)
        except Exception:
            pass
        self.save_settings()
        self._refresh_ocr_status("saved")
        short = (self.profile() or {}).get("short", "game")
        self.show_toast(f"Chat area saved · {short}", kind="ok")
        self.set_status(
            f"Chat region {region['right'] - region['left']}×{region['bottom'] - region['top']} · {short}"
        )

    def _on_market_region_saved(self, region: dict):
        self.market_region = region
        try:
            g = self.game_var.get() if hasattr(self, "game_var") else None
            self._snapshot_game_settings(g)
        except Exception:
            pass
        self.save_settings()
        self._refresh_market_status("saved")
        short = (self.profile() or {}).get("short", "game")
        self.show_toast(f"Market area saved · {short}", kind="ok")
        self.set_status(
            f"Market region {region['right'] - region['left']}×{region['bottom'] - region['top']} · {short}"
        )

    def _start_region_calibrate(
        self,
        prompt: str,
        on_saved: Callable,
        on_cancel: Optional[Callable] = None,
    ):
        if not _HAS_PIL or ImageGrab is None:
            messagebox.showerror("Pillow required", "Install Pillow to capture the screen.")
            return

        was_top = bool(self.always_on_top.get()) if hasattr(self, "always_on_top") else False
        try:
            self.root.attributes("-topmost", False)
            self.root.iconify()
        except Exception:
            pass

        self.root.after(
            280,
            lambda: self._open_region_selector(was_top, prompt, on_saved, on_cancel),
        )

    def _open_region_selector(
        self,
        restore_top: bool,
        prompt: str,
        on_saved: Callable,
        on_cancel: Optional[Callable] = None,
    ):
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
        sel.title("Drag to select area · Esc cancel")
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
            text=prompt,
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
                try:
                    on_saved(region)
                except Exception:
                    pass
            elif on_cancel:
                try:
                    on_cancel()
                except Exception:
                    pass

        def on_release(event):
            x1, y1 = state["x0"], state["y0"]
            x2, y2 = event.x, event.y
            abs_left = left + min(x1, x2)
            abs_top = top + min(y1, y2)
            abs_right = left + max(x1, x2)
            abs_bottom = top + max(y1, y2)
            if abs_right - abs_left < 20 or abs_bottom - abs_top < 20:
                messagebox.showwarning("Too small", "Drag a larger box over the target UI.")
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

        # Grab buttons live on Reply panel — keep user on that intent
        try:
            if hasattr(self, "generator_intent"):
                self.generator_intent.set("reply")
                if hasattr(self, "set_intent"):
                    self.set_intent("reply")
                elif hasattr(self, "on_intent_change"):
                    self.on_intent_change("reply")
        except Exception:
            pass

        self._ocr_busy = True
        self._last_ocr_error = ""
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
        model = self._selected_lm_model()
        host = getattr(self, "lm_host", "") or self._host_from_api_url(self.api_url)

        def work():
            err = None
            text = ""
            engine = ""
            try:
                time.sleep(0.18)  # let our window drop behind game if needed
                bbox = (
                    int(region["left"]),
                    int(region["top"]),
                    int(region["right"]),
                    int(region["bottom"]),
                )
                if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    raise ValueError(f"invalid chat region bbox {bbox}")
                img = ImageGrab.grab(bbox=bbox, all_screens=True)
                try:
                    img.save(LAST_OCR_PATH)
                except Exception:
                    pass

                # Prefer vision model when configured (remote Qwen-VL etc.); Tesseract as fallback
                text, engine = self._ocr_image(img)
                text = self._clean_ocr_text(text)
                # Always pick a single reply line for Grab+reply / clap-back entry field
                if self.ocr_prefer_last.get() or and_reply:
                    text = self._ocr_pick_reply_line(text)
            except Exception as e:
                err = str(e)
                self._last_ocr_error = err

            def done():
                self._ocr_busy = False
                try:
                    if was_top:
                        self.root.attributes("-topmost", True)
                except Exception:
                    pass

                if err:
                    self.show_toast("Capture failed", kind="error")
                    self._refresh_ocr_status(f"error: {err[:48]}")
                    self.copy_badge.configure(text="ready", text_color=C["muted"])
                    messagebox.showerror(
                        "Grab failed",
                        f"Could not capture or read chat.\n\n{err}\n\n"
                        f"Last capture (if any):\n{LAST_OCR_PATH}",
                    )
                    return
                if not text:
                    detail = (getattr(self, "_last_ocr_error", "") or "").strip()
                    self.show_toast("No text found — see OCR details", kind="warn")
                    self._refresh_ocr_status(
                        f"empty · {detail[:40]}" if detail else "empty · VL/Tesseract failed"
                    )
                    self.copy_badge.configure(text="ready", text_color=C["muted"])
                    messagebox.showinfo(
                        "OCR empty",
                        "Couldn't read chat text from the grab.\n\n"
                        f"Model: {model}\n"
                        f"Host: {host}\n"
                        f"Engine tried: {engine or 'none'}\n"
                        f"Detail: {detail or '(no error body — empty model reply)'}\n\n"
                        "Checklist:\n"
                        "• Setup → Test connection is green\n"
                        "• Model dropdown = a VL / vision model (e.g. qwen3-vl-8b)\n"
                        "• In LM Studio that model is loaded + Server running\n"
                        "• Open last grab — confirm chat text is visible in the PNG\n"
                        "• Recalibrate tighter on the chat log if the PNG is wrong\n"
                        "• Remote: GPU busy or cold start can time out — try again\n\n"
                        f"Last capture:\n{LAST_OCR_PATH}",
                    )
                    return

                self._last_ocr_text = text
                self._fill_they_said(text)
                self._refresh_ocr_status(f"via {engine}")
                self.show_toast(f"OCR · {engine}", kind="ok")
                self.set_status(f"OCR ({engine}): {text[:60]}{'…' if len(text) > 60 else ''}")
                self.copy_badge.configure(text="ready", text_color=C["muted"])
                if and_reply:
                    # Entry is updated; generate clap-back against that line
                    self.root.after(50, self.generate_response_from_quick)

            self.schedule_ui(done)

        threading.Thread(target=work, daemon=True).start()

    # =====================================================================
    # Economy · market snap + price advice
    # =====================================================================
    def _market_status_text(self) -> str:
        if self.market_region:
            r = self.market_region
            w = max(0, int(r["right"]) - int(r["left"]))
            h = max(0, int(r["bottom"]) - int(r["top"]))
            engines = []
            if _HAS_TESS:
                engines.append("Tesseract")
            engines.append("local VL (LM Studio)")
            return f"Market area set · {w}×{h}px @ ({r['left']},{r['top']})  ·  engines: {' · '.join(engines)}"
        return "Market area not set · click Set market area, then drag over the listings UI"

    def _refresh_market_status(self, extra: str = ""):
        if not hasattr(self, "economy_status"):
            return
        base = self._market_status_text()
        if extra:
            base = f"{base}  ·  {extra}"
        try:
            self.economy_status.configure(text=base)
        except Exception:
            pass

    def open_last_market_capture(self):
        path = LAST_MARKET_PATH
        if not os.path.isfile(path):
            self.show_toast("No market capture yet", kind="warn")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            try:
                subprocess.Popen(["notepad", path])
            except Exception:
                self.show_toast(path, kind="info")

    def grab_market_price(self):
        """Screenshot market region → VL/OCR → price recommendation."""
        if self._economy_busy:
            self.show_toast("Already analyzing market…", kind="warn")
            return
        if not self.market_region:
            if messagebox.askyesno(
                "Calibrate first",
                "No market area is set yet.\n\n"
                "Calibrate now? Drag a box over the in-game market / auction listings.",
            ):
                self.calibrate_market_region()
            return
        if not _HAS_PIL or ImageGrab is None:
            messagebox.showerror("Pillow required", "Install Pillow to capture the screen.")
            return

        self.save_settings()
        item = (self.economy_item_var.get() if hasattr(self, "economy_item_var") else "").strip()
        try:
            undercut = float(
                (self.economy_undercut_var.get() if hasattr(self, "economy_undercut_var") else "5")
                .replace("%", "")
                .strip()
                or "5"
            )
        except Exception:
            undercut = 5.0
        undercut = max(0.0, min(50.0, undercut))

        self._economy_busy = True
        self._refresh_market_status("capturing…")
        self.set_status("Snapping market area…")
        self.copy_badge.configure(text="market…", text_color=C["warn"])

        was_top = bool(self.always_on_top.get()) if hasattr(self, "always_on_top") else False
        try:
            if was_top:
                self.root.attributes("-topmost", False)
        except Exception:
            pass

        region = dict(self.market_region)
        game = self.game_var.get() if hasattr(self, "game_var") else ""

        def work():
            err = None
            raw_out = ""
            engine = ""
            try:
                time.sleep(0.18)
                bbox = (
                    int(region["left"]),
                    int(region["top"]),
                    int(region["right"]),
                    int(region["bottom"]),
                )
                img = ImageGrab.grab(bbox=bbox, all_screens=True)
                try:
                    img.save(LAST_MARKET_PATH)
                except Exception:
                    pass
                raw_out, engine = self._economy_analyze_image(img, item, undercut, game)
            except Exception as e:
                err = str(e)

            def done():
                self._economy_busy = False
                try:
                    if was_top:
                        self.root.attributes("-topmost", True)
                except Exception:
                    pass
                if err:
                    self.show_toast("Market capture failed", kind="error")
                    self._refresh_market_status(f"error: {err[:48]}")
                    self.copy_badge.configure(text="ready", text_color=C["muted"])
                    return
                if not raw_out or self._is_err(raw_out):
                    self.show_toast("Could not read market — need VL model?", kind="warn")
                    self._refresh_market_status("empty · load vision model in LM Studio")
                    self.copy_badge.configure(text="ready", text_color=C["muted"])
                    messagebox.showinfo(
                        "Economy empty",
                        "Couldn't read market listings.\n\n"
                        "Tips:\n"
                        "• Recalibrate tighter on the price list\n"
                        "• Load a vision model in LM Studio (Qwen2-VL / Qwen3-VL)\n"
                        "• Or install Tesseract for text OCR fallback\n"
                        "• Ensure Local Server is on (AI · on)\n\n"
                        f"Last capture:\n{LAST_MARKET_PATH}",
                    )
                    return

                parsed = self._parse_economy_result(raw_out, item)
                self._apply_economy_result(parsed, engine)
                self.session_gens += 1
                self.update_session_chip()
                self.show_toast(f"Economy · {engine}", kind="ok")
                self.set_status(f"Economy ({engine}): {parsed.get('suggest') or 'see comps'}")
                self.copy_badge.configure(text="ready", text_color=C["muted"])
                if self.auto_copy.get() and parsed.get("wts"):
                    try:
                        self.safe_copy(parsed["wts"])
                    except Exception:
                        pass

            self.schedule_ui(done)

        threading.Thread(target=work, daemon=True).start()

    def _economy_analyze_image(
        self,
        img: "Image.Image",
        item: str,
        undercut: float,
        game: str,
    ) -> tuple[str, str]:
        """Prefer vision model for market UI; fall back to OCR + text LLM."""
        # 1) Vision one-shot
        try:
            vl = self._economy_via_local_vl(img, item, undercut, game)
            if vl and not self._is_err(vl):
                return vl, "local VL"
        except Exception:
            pass

        # 2) OCR text → text model
        text, eng = "", ""
        try:
            text, eng = self._ocr_image(img)
            text = self._clean_ocr_text(text)
        except Exception:
            text, eng = "", "none"
        if not text:
            return "", eng or "none"

        prompt = self._economy_text_prompt(text, item, undercut, game)
        lines = self.call_local_llm(prompt, n=1, job="economy")
        out = lines[0] if lines else ""
        return out, f"{eng}+LLM" if eng else "LLM"

    def _economy_via_local_vl(
        self,
        img: "Image.Image",
        item: str,
        undercut: float,
        game: str,
    ) -> str:
        if not _HAS_PIL or base64 is None or io is None:
            return ""
        self.api_url = self._normalize_api_url(self.api_url)
        data_url = self._image_to_data_url(img, max_side=1280, jpeg=True)

        item_bit = item if item else "the main item shown in the listings"
        game_bit = game or "this game"
        sampling = self._sampling_payload("economy")
        sampling = {
            "temperature": float(sampling.get("temperature", 0.25)),
            "top_p": float(sampling.get("top_p", 0.88)),
            "max_tokens": int(sampling.get("max_tokens", 420)),
            "stream": False,
        }
        payload = {
            "model": self._selected_lm_model(),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You read MMO market / auction house screenshots.\n"
                        "Extract comparable listing prices for the player's item.\n"
                        "Be conservative: only use prices you can actually see.\n"
                        "If text is unclear, say so. No fake APIs or invented server averages.\n"
                        "Output EXACTLY this structure (plain text, no markdown):\n"
                        "ITEM: <name>\n"
                        "COMPS: <comma-separated prices you read, or NONE>\n"
                        "LOW: <lowest clear price or ?>\n"
                        "HIGH: <highest clear price or ?>\n"
                        "MEDIAN: <approx median or ?>\n"
                        "SUGGEST: <recommended list price only>\n"
                        "WTS: <one short in-game chat line to sell at that price>\n"
                        "NOTES: <one short line on confidence / caveats>\n"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Game: {game_bit}.\n"
                                f"Item to price: {item_bit}.\n"
                                f"Undercut target: about {undercut:g}% under the lowest clear listing "
                                f"(if comps exist).\n"
                                "Read the market screenshot and fill the output structure."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            **sampling,
        }
        timeout = self._vl_request_timeout()
        # Economy can take longer on remote 8B VL
        timeout = (timeout[0], max(timeout[1], 150.0))
        r = requests.post(
            self.api_url, json=payload, headers=self._llm_headers(), timeout=timeout
        )
        if r.status_code != 200:
            return ""
        return self._extract_chat_message_text(r.json()).strip()

    def _economy_text_prompt(self, ocr_text: str, item: str, undercut: float, game: str) -> str:
        item_bit = item if item else "the item in the listings"
        return (
            f"You are helping a {game or 'MMO'} player price an item from OCR of market UI.\n"
            f"Item: {item_bit}\n"
            f"Undercut ~{undercut:g}% under lowest clear comp if possible.\n"
            "Only use prices present in the text. Do not invent a server average.\n"
            "OCR text:\n"
            f"{ocr_text[:3500]}\n\n"
            "Output EXACTLY:\n"
            "ITEM: ...\nCOMPS: ...\nLOW: ...\nHIGH: ...\nMEDIAN: ...\n"
            "SUGGEST: ...\nWTS: ...\nNOTES: ...\n"
        )

    def _parse_economy_result(self, raw: str, fallback_item: str = "") -> dict:
        data = {
            "item": fallback_item or "",
            "comps": "",
            "low": "",
            "high": "",
            "median": "",
            "suggest": "",
            "wts": "",
            "notes": "",
            "raw": (raw or "").strip(),
        }
        for line in (raw or "").replace("\r", "\n").split("\n"):
            ln = line.strip()
            if not ln or ":" not in ln:
                continue
            key, val = ln.split(":", 1)
            key = key.strip().upper()
            val = val.strip()
            if key == "ITEM":
                data["item"] = val
            elif key == "COMPS":
                data["comps"] = val
            elif key == "LOW":
                data["low"] = val
            elif key == "HIGH":
                data["high"] = val
            elif key == "MEDIAN":
                data["median"] = val
            elif key == "SUGGEST":
                data["suggest"] = val
            elif key == "WTS":
                data["wts"] = val
            elif key == "NOTES":
                data["notes"] = val
        # Fallback: whole raw if structure missing
        if not data["comps"] and not data["suggest"]:
            data["comps"] = data["raw"][:800]
        if not data["wts"] and data["suggest"]:
            name = data["item"] or fallback_item or "item"
            data["wts"] = f"WTS {name} {data['suggest']}"
        return data

    def _apply_economy_result(self, parsed: dict, engine: str = ""):
        comps_bits = []
        if parsed.get("item"):
            comps_bits.append(f"Item: {parsed['item']}")
        if parsed.get("comps"):
            comps_bits.append(f"Comps: {parsed['comps']}")
        rng = []
        if parsed.get("low"):
            rng.append(f"low {parsed['low']}")
        if parsed.get("median"):
            rng.append(f"med {parsed['median']}")
        if parsed.get("high"):
            rng.append(f"high {parsed['high']}")
        if rng:
            comps_bits.append(" · ".join(rng))
        if parsed.get("notes"):
            comps_bits.append(f"Notes: {parsed['notes']}")
        if engine:
            comps_bits.append(f"via {engine}")
        body = "\n".join(comps_bits) if comps_bits else (parsed.get("raw") or "—")

        self._last_market_text = body
        self._last_economy_suggest = parsed.get("suggest") or ""
        self._last_economy_wts = parsed.get("wts") or ""

        if hasattr(self, "economy_comps"):
            try:
                self.economy_comps.delete("1.0", "end")
                self.economy_comps.insert("1.0", body)
            except Exception:
                pass
        if hasattr(self, "economy_suggest"):
            sug = self._last_economy_suggest or "—"
            self.economy_suggest.configure(text=f"Suggested · {sug}")
        if hasattr(self, "economy_wts"):
            self.economy_wts.configure(
                text=self._last_economy_wts or "(no WTS line)"
            )
        self._refresh_market_status("done")
        try:
            self._log_economy_entry(parsed, engine)
        except Exception:
            pass

    def copy_economy_suggest(self):
        t = getattr(self, "_last_economy_suggest", "") or ""
        if not t:
            self.show_toast("No suggestion yet", kind="warn")
            return
        try:
            self.safe_copy(t)
        except Exception:
            pyperclip.copy(t)
            self.show_toast("Copied suggest", kind="ok")

    def copy_economy_wts(self):
        t = getattr(self, "_last_economy_wts", "") or ""
        if not t:
            self.show_toast("No WTS line yet", kind="warn")
            return
        try:
            self.safe_copy(t)
        except Exception:
            pyperclip.copy(t)
            self.show_toast("Copied WTS", kind="ok")

    def copy_economy_comps(self):
        t = getattr(self, "_last_market_text", "") or ""
        if not t:
            try:
                t = self.economy_comps.get("1.0", "end").strip()
            except Exception:
                t = ""
        if not t:
            self.show_toast("No comps yet", kind="warn")
            return
        try:
            self.safe_copy(t)
        except Exception:
            pyperclip.copy(t)
            self.show_toast("Copied comps", kind="ok")

    def _fill_they_said(self, text: str):
        # CTkEntry is single-line — collapse newlines so clap-back sees one usable string
        text = (text or "").replace("\r", "\n").strip()
        if "\n" in text:
            text = self._ocr_pick_reply_line(text) or " ".join(
                ln.strip() for ln in text.split("\n") if ln.strip()
            )
        text = (text or "").strip()
        if hasattr(self, "quick_they_said"):
            self.quick_they_said.delete(0, tk.END)
            self.quick_they_said.insert(0, text)
        if hasattr(self, "input_statement") and self.input_statement is not getattr(
            self, "quick_they_said", None
        ):
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

    def _model_looks_vision(self, model: Optional[str] = None) -> bool:
        m = (model if model is not None else self._selected_lm_model()).lower()
        if not m or m.startswith("("):
            return False
        keys = ("-vl", "vl-", "vision", "llava", "pixtral", "gemini", "qwen2-vl", "qwen3-vl", "qwen3.5")
        # qwen3.5-9b-vlm etc.
        return any(k in m for k in keys) or "vlm" in m

    def _vl_request_timeout(self) -> tuple[float, float]:
        """(connect, read) timeouts — remote 8B VL needs more headroom."""
        mode = getattr(self, "lm_mode", "Local")
        if hasattr(self, "lm_mode_var"):
            try:
                mode = self.lm_mode_var.get() or mode
            except Exception:
                pass
        if str(mode).lower().startswith("remote"):
            return (8.0, 120.0)
        return (3.0, 60.0)

    def _image_to_data_url(self, img: "Image.Image", *, max_side: int = 960, jpeg: bool = True) -> str:
        """Encode screenshot for multimodal chat completions (JPEG smaller for remote LAN)."""
        work = img.convert("RGB")
        w, h = work.size
        if max(w, h) > max_side:
            scale = max_side / float(max(w, h))
            work = work.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        if jpeg:
            work.save(buf, format="JPEG", quality=85, optimize=True)
            mime = "image/jpeg"
        else:
            work.save(buf, format="PNG", optimize=True)
            mime = "image/png"
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def _extract_chat_message_text(self, data: dict) -> str:
        """Pull assistant text from OpenAI-compatible (and Qwen reasoning) responses."""
        try:
            choice = (data.get("choices") or [None])[0] or {}
            msg = choice.get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") in (None, "text") and part.get("text"):
                            parts.append(str(part.get("text") or ""))
                        elif isinstance(part.get("content"), str):
                            parts.append(part["content"])
                    elif isinstance(part, str):
                        parts.append(part)
                content = "\n".join(p for p in parts if p).strip()
            if content is None:
                content = ""
            content = str(content).strip()
            if content:
                return content
            # Some reasoning builds put visible answer only in reasoning_content
            reasoning = str(msg.get("reasoning_content") or msg.get("reasoning") or "").strip()
            if reasoning:
                return reasoning
            # Older delta-style
            text = choice.get("text")
            if text:
                return str(text).strip()
        except Exception:
            pass
        return ""

    def _ocr_image(self, img: "Image.Image") -> tuple[str, str]:
        """Return (text, engine_name). Prefer VL when a vision model is selected."""
        self._last_ocr_error = ""
        prefer_vl = self._model_looks_vision() or getattr(self, "lm_mode", "Local") == "Remote"

        def try_tess() -> tuple[str, str]:
            if not _HAS_TESS:
                return "", ""
            try:
                pre = self._preprocess_for_ocr(img)
                txt = pytesseract.image_to_string(pre, config="--psm 6")
                txt = (txt or "").strip()
                if txt:
                    return txt, "Tesseract"
            except Exception as e:
                self._last_ocr_error = f"Tesseract: {e}"
            return "", ""

        def try_vl() -> tuple[str, str]:
            try:
                txt = self._ocr_via_local_vl(img)
                if txt:
                    return txt, "LM Studio VL"
            except Exception as e:
                self._last_ocr_error = str(e)
            return "", ""

        order = (try_vl, try_tess) if prefer_vl else (try_tess, try_vl)
        for fn in order:
            txt, eng = fn()
            if txt:
                return txt, eng
        return "", "none"

    def _ocr_via_local_vl(self, img: "Image.Image") -> str:
        if not _HAS_PIL or base64 is None or io is None:
            self._last_ocr_error = "Pillow / base64 unavailable"
            return ""
        self.api_url = self._normalize_api_url(self.api_url)
        model = self._selected_lm_model()
        data_url = self._image_to_data_url(img, max_side=960, jpeg=True)

        sampling = self._sampling_payload("ocr")
        # Vision OCR: keep sampling light; drop exotic fields some servers mishandle
        sampling = {
            "temperature": float(sampling.get("temperature", 0.05)),
            "top_p": float(sampling.get("top_p", 0.85)),
            "max_tokens": int(sampling.get("max_tokens", 280)),
            "stream": False,
        }
        payload = {
            "model": model,
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
                                "Transcribe the player chat messages in this screenshot. "
                                "Only chat lines (names + messages). Ignore UI chrome."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            **sampling,
        }
        timeout = self._vl_request_timeout()
        try:
            r = requests.post(
                self.api_url, json=payload, headers=self._llm_headers(), timeout=timeout
            )
        except requests.exceptions.Timeout:
            self._last_ocr_error = (
                f"timeout after {timeout[1]:.0f}s · {model} @ {self._host_from_api_url(self.api_url)}"
            )
            raise TimeoutError(self._last_ocr_error)
        except requests.exceptions.ConnectionError as e:
            self._last_ocr_error = f"connection failed · {self._host_from_api_url(self.api_url)} · {e}"
            raise ConnectionError(self._last_ocr_error) from e

        if r.status_code != 200:
            body = (r.text or "")[:240].replace("\n", " ")
            self._last_ocr_error = f"HTTP {r.status_code} · {body}"
            return ""
        try:
            data = r.json()
        except Exception:
            self._last_ocr_error = f"non-JSON response · {(r.text or '')[:160]}"
            return ""
        content = self._extract_chat_message_text(data)
        if not content:
            self._last_ocr_error = "model returned empty content (is a VL model loaded?)"
            return ""
        return content.strip()

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
            # Drop repeated-char garbage (e.g. "xadddddddddd")
            if len(p) >= 6:
                c = Counter(p.lower())
                if c.most_common(1)[0][1] >= max(6, int(len(p) * 0.55)):
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
            # skip garbage runs
            if len(ln) >= 6:
                if Counter(ln.lower()).most_common(1)[0][1] >= max(6, int(len(ln) * 0.55)):
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
    # Recruit helpers · local file CRUD (recruit_templates.json)
    # =====================================================================
    def _new_recruit_id(self) -> str:
        return f"r{int(time.time() * 1000):x}{random.randint(0, 9999):04d}"

    def _auto_recruit_name(self, text: str) -> str:
        t = " ".join((text or "").split())
        if not t:
            return "Untitled"
        return (t[:40] + "…") if len(t) > 40 else t

    def _sync_templates_flat(self):
        """Mirror recruit_templates → flat text list (config backup + offline pack)."""
        items = getattr(self, "recruit_templates", None) or []
        self.templates = [str(t.get("text") or "").strip() for t in items if str(t.get("text") or "").strip()]

    def _load_or_migrate_recruit_templates(self):
        """Load recruit_templates.json; migrate once from config templates if missing."""
        items: list[dict] = []
        selected: Optional[str] = None
        path = RECRUIT_TEMPLATES_PATH
        loaded_file = False

        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                loaded_file = True
                if isinstance(data, list):
                    raw = data
                elif isinstance(data, dict):
                    raw = data.get("templates") or []
                    selected = data.get("selected_id")
                else:
                    raw = []
                for t in raw:
                    if isinstance(t, str):
                        text = t.strip()
                        if text:
                            items.append(
                                {
                                    "id": self._new_recruit_id(),
                                    "name": self._auto_recruit_name(text),
                                    "text": text,
                                }
                            )
                    elif isinstance(t, dict):
                        text = str(t.get("text") or "").strip()
                        if not text:
                            continue
                        rid = str(t.get("id") or "").strip() or self._new_recruit_id()
                        name = str(t.get("name") or "").strip()[:80]
                        items.append(
                            {
                                "id": rid,
                                "name": name or self._auto_recruit_name(text),
                                "text": text,
                            }
                        )
            except Exception:
                items = []
                loaded_file = False

        if not items and not loaded_file:
            # First run / no file: migrate any non-empty strings left in config
            for t in (self.templates or []):
                text = str(t).strip()
                if not text:
                    continue
                # Skip any leftover branded defaults if they somehow remain
                if "defiant" in text.lower():
                    continue
                items.append(
                    {
                        "id": self._new_recruit_id(),
                        "name": self._auto_recruit_name(text),
                        "text": text,
                    }
                )
            self.recruit_templates = items
            self._recruit_selected_id = items[0]["id"] if items else None
            self._sync_templates_flat()
            if items:
                self._save_recruit_file()
            return

        self.recruit_templates = items
        if selected and any(x.get("id") == selected for x in items):
            self._recruit_selected_id = selected
        else:
            self._recruit_selected_id = items[0]["id"] if items else None
        self._sync_templates_flat()

    def _save_recruit_file(self) -> bool:
        """Persist recruit pitches to recruit_templates.json."""
        self._sync_templates_flat()
        payload = {
            "version": 1,
            "selected_id": getattr(self, "_recruit_selected_id", None),
            "templates": [
                {
                    "id": str(t.get("id") or self._new_recruit_id()),
                    "name": str(t.get("name") or "")[:80],
                    "text": str(t.get("text") or "").strip(),
                }
                for t in (self.recruit_templates or [])
                if str(t.get("text") or "").strip()
            ],
        }
        try:
            with open(RECRUIT_TEMPLATES_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.write("\n")
            return True
        except Exception as e:
            try:
                messagebox.showerror("Recruit save failed", str(e))
            except Exception:
                pass
            return False

    def _find_recruit(self, rid: Optional[str]) -> Optional[dict]:
        if not rid:
            return None
        for t in self.recruit_templates or []:
            if t.get("id") == rid:
                return t
        return None

    def _recruit_combo_data(self) -> tuple[list[str], dict[str, str]]:
        """Return (combo labels, label→id). Labels are unique."""
        labels: list[str] = []
        label_to_id: dict[str, str] = {}
        used: set[str] = set()
        for t in self.recruit_templates or []:
            rid = str(t.get("id") or "")
            name = str(t.get("name") or "").strip()
            text = str(t.get("text") or "").strip()
            base = name or self._auto_recruit_name(text)
            label = base
            n = 2
            while label in used:
                label = f"{base} ({n})"
                n += 1
            used.add(label)
            labels.append(label)
            label_to_id[label] = rid
        if not labels:
            labels = [RECRUIT_PLACEHOLDER]
        self._recruit_label_to_id = label_to_id
        return labels, label_to_id

    def _refresh_recruit_ui(self, load_editor: bool = False):
        """Refresh combo + optional editor from current selection."""
        labels, label_to_id = self._recruit_combo_data()
        if hasattr(self, "template_combo"):
            try:
                self.template_combo.configure(values=labels)
            except Exception:
                pass

        sel = getattr(self, "_recruit_selected_id", None)
        item = self._find_recruit(sel)
        # Pick combo display for selection
        display = RECRUIT_PLACEHOLDER
        if item:
            for lab, rid in label_to_id.items():
                if rid == item.get("id"):
                    display = lab
                    break
            if hasattr(self, "template_combo"):
                try:
                    self.template_combo.set(display)
                except Exception:
                    pass
        else:
            if hasattr(self, "template_combo"):
                try:
                    self.template_combo.set(labels[0])
                except Exception:
                    pass

        if load_editor and hasattr(self, "msg_textbox"):
            try:
                self.msg_textbox.delete("1.0", tk.END)
                if item:
                    self.msg_textbox.insert("1.0", item.get("text") or "")
                    if hasattr(self, "recruit_name_var"):
                        self.recruit_name_var.set(str(item.get("name") or ""))
                else:
                    if hasattr(self, "recruit_name_var"):
                        self.recruit_name_var.set("")
            except Exception:
                pass
            self.update_counter()
        self._update_recruit_crud_status()

    def _update_recruit_crud_status(self):
        """Show Create vs Update state next to the pitch picker."""
        if not hasattr(self, "recruit_crud_status"):
            return
        n = len(getattr(self, "recruit_templates", None) or [])
        item = self._find_recruit(getattr(self, "_recruit_selected_id", None))
        try:
            if item:
                name = str(item.get("name") or "pitch")[:28]
                self.recruit_crud_status.configure(
                    text=f"Editing · {name}  ({n})",
                    text_color=C["info"],
                )
            else:
                self.recruit_crud_status.configure(
                    text=f"New draft  ({n} saved)",
                    text_color=C["faint"],
                )
        except Exception:
            pass

    def load_selected_template(self, choice: str):
        """Read — load a saved pitch into the editor (combo callback)."""
        if not choice or choice == RECRUIT_PLACEHOLDER:
            return
        rid = (getattr(self, "_recruit_label_to_id", {}) or {}).get(choice)
        if not rid:
            # Fallback: match by label rebuild
            labels, mapping = self._recruit_combo_data()
            rid = mapping.get(choice)
        item = self._find_recruit(rid)
        if not item:
            return
        self._recruit_selected_id = item.get("id")
        if hasattr(self, "msg_textbox"):
            self.msg_textbox.delete("1.0", tk.END)
            self.msg_textbox.insert("1.0", item.get("text") or "")
        if hasattr(self, "recruit_name_var"):
            self.recruit_name_var.set(str(item.get("name") or ""))
        self.update_counter()
        self._update_recruit_crud_status()
        # Remember selection in file (light write)
        self._save_recruit_file()
        self.show_toast(f"Loaded · {item.get('name') or 'pitch'}", kind="info")

    def recruit_new(self):
        """Create — blank draft (does not delete anything until you Update/Save)."""
        self._recruit_selected_id = None
        if hasattr(self, "recruit_name_var"):
            self.recruit_name_var.set("")
        if hasattr(self, "msg_textbox"):
            self.msg_textbox.delete("1.0", tk.END)
        self._refresh_recruit_ui(load_editor=False)
        if hasattr(self, "template_combo"):
            try:
                labels, _ = self._recruit_combo_data()
                # Show placeholder-ish first label when empty list
                self.template_combo.set(labels[0] if labels else RECRUIT_PLACEHOLDER)
            except Exception:
                pass
        self.update_counter()
        self._update_recruit_crud_status()
        self.show_toast("New draft — type a pitch, then Update", kind="info")

    def recruit_save(self):
        """Update selected pitch, or Create if no selection → recruit_templates.json."""
        if not hasattr(self, "msg_textbox"):
            return
        text = self.msg_textbox.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Empty", "Write a recruiting message first.")
            return
        name = ""
        if hasattr(self, "recruit_name_var"):
            name = (self.recruit_name_var.get() or "").strip()[:80]
        if not name:
            name = self._auto_recruit_name(text)

        item = self._find_recruit(getattr(self, "_recruit_selected_id", None))
        if item:
            item["name"] = name
            item["text"] = text
            self.show_toast(f"Updated · {name}", kind="ok")
            self.set_status(f"Recruit updated · {name}")
        else:
            rid = self._new_recruit_id()
            self.recruit_templates.append({"id": rid, "name": name, "text": text})
            self._recruit_selected_id = rid
            self.show_toast(f"Created · {name}", kind="ok")
            self.set_status(f"Recruit created · {name}")

        if self._save_recruit_file():
            self.save_settings()
            self._refresh_recruit_ui(load_editor=True)

    def recruit_save_as_new(self):
        """Always create a new pitch from the current editor (keeps the old one)."""
        self._recruit_selected_id = None
        self.recruit_save()

    def recruit_duplicate(self):
        """Duplicate — save a copy of the current pitch as a new named entry."""
        if not hasattr(self, "msg_textbox"):
            return
        text = self.msg_textbox.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Empty", "Nothing to duplicate — load or type a pitch first.")
            return
        seed_name = ""
        if hasattr(self, "recruit_name_var"):
            seed_name = (self.recruit_name_var.get() or "").strip()
        if not seed_name:
            item = self._find_recruit(getattr(self, "_recruit_selected_id", None))
            if item:
                seed_name = str(item.get("name") or "")
        if not seed_name:
            seed_name = self._auto_recruit_name(text)
        # Unique copy name
        base = re.sub(r"\s*[·•]\s*(copy|variant|v\d+)\s*$", "", seed_name, flags=re.IGNORECASE).strip()
        base = (base or "Pitch")[:50]
        existing = {
            str(t.get("name") or "").strip().lower()
            for t in (getattr(self, "recruit_templates", None) or [])
        }
        name = f"{base} · copy"
        if name.lower() in existing:
            for i in range(2, 50):
                cand = f"{base} · copy {i}"
                if cand.lower() not in existing:
                    name = cand
                    break
        rid = self._new_recruit_id()
        self.recruit_templates = list(getattr(self, "recruit_templates", None) or [])
        self.recruit_templates.append({"id": rid, "name": name, "text": text})
        self._recruit_selected_id = rid
        if hasattr(self, "recruit_name_var"):
            self.recruit_name_var.set(name)
        if self._save_recruit_file():
            self.save_settings()
            self._refresh_recruit_ui(load_editor=True)
            self.show_toast(f"Duplicated · {name}", kind="ok")
            self.set_status(f"Recruit duplicated · {name}")
        else:
            self.show_toast("Duplicate failed", kind="error")

    def recruit_delete(self):
        """Delete the selected recruiting statement from the local file."""
        item = self._find_recruit(getattr(self, "_recruit_selected_id", None))
        if not item:
            # Try match editor text to a saved item
            text = ""
            if hasattr(self, "msg_textbox"):
                text = self.msg_textbox.get("1.0", "end-1c").strip()
            for t in self.recruit_templates or []:
                if (t.get("text") or "").strip() == text and text:
                    item = t
                    break
        if not item:
            self.show_toast("Nothing selected to delete", kind="warn")
            return
        label = item.get("name") or self._auto_recruit_name(item.get("text") or "")
        if not messagebox.askyesno(
            "Delete pitch?",
            f"Delete this recruiting statement?\n\n{label}\n\nThis updates recruit_templates.json.",
        ):
            return
        rid = item.get("id")
        self.recruit_templates = [t for t in self.recruit_templates if t.get("id") != rid]
        self._recruit_selected_id = (
            self.recruit_templates[0]["id"] if self.recruit_templates else None
        )
        self._save_recruit_file()
        self.save_settings()
        self._refresh_recruit_ui(load_editor=True)
        self.show_toast(f"Deleted · {label}", kind="info")
        self.set_status(f"Recruit deleted · {label}")

    def recruit_open_file(self):
        """Open recruit_templates.json in Explorer / default editor."""
        path = RECRUIT_TEMPLATES_PATH
        if not os.path.isfile(path):
            # Create empty file so user can see it
            self._save_recruit_file()
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
            self.show_toast("Opened recruit_templates.json", kind="info")
        except Exception:
            try:
                os.startfile(APP_DIR)  # type: ignore[attr-defined]
            except Exception:
                messagebox.showinfo("Recruit file", path)

    def save_custom_template(self):
        """Back-compat alias for older UI hooks."""
        self.recruit_save()

    def reset_presets(self):
        if messagebox.askyesno(
            "Clear all pitches?",
            "Delete ALL recruiting statements from recruit_templates.json?",
        ):
            self.recruit_templates = []
            self._recruit_selected_id = None
            self._save_recruit_file()
            self.save_settings()
            self._refresh_recruit_ui(load_editor=True)
            self.show_toast("All recruit pitches cleared", kind="info")

    def update_counter(self, event=None):
        if not hasattr(self, "msg_textbox") or not hasattr(self, "counter_label"):
            return
        text = self.msg_textbox.get("1.0", "end-1c")
        lim = self.limit()
        length = len(text)
        if hasattr(self, "safety_progressbar"):
            self.safety_progressbar.set(min(length / max(lim, 1), 1.0))
        self.counter_label.configure(text=f"{length} / {lim}")
        color = C["danger"] if length > lim else C["warn"] if length >= lim - 15 else C["success"]
        self.counter_label.configure(text_color=color)
        if hasattr(self, "safety_progressbar"):
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

    def _recruit_seed_text(self) -> str:
        """Current pitch used as the variation seed."""
        if not hasattr(self, "msg_textbox"):
            return ""
        return self.msg_textbox.get("1.0", "end-1c").strip()

    def _recruit_variant_direction(self) -> str:
        if hasattr(self, "recruit_variant_seed_var"):
            return (self.recruit_variant_seed_var.get() or "").strip()[:160]
        return ""

    def generate_recruit_variant(self, n: int = 1, save_as_new: bool = False):
        """
        AI variation of the current recruit message (seed).
        Optional Variant seed steers tone/length (shorter, chill, mention X…).
        n=3 fills the option buttons under Generated line.
        save_as_new=True → after a good result, write a NEW pitch to recruit_templates.json.
        """
        text = self._recruit_seed_text()
        if not text:
            messagebox.showwarning(
                "Need a seed",
                "Load a saved pitch or type a recruiting message first.\n"
                "That text is the seed AI will rewrite.",
            )
            return
        n = 1 if n < 1 else (3 if n > 3 else int(n))
        # Multi-option mode does not auto-save all three; user picks then Save as new
        if n > 1:
            save_as_new = False
        game = self.game_var.get()
        lim = self.limit()
        direction = self._recruit_variant_direction()
        house = self.house_style_for(game)
        house_bit = f"\nHouse style notes: {house}\n" if house else ""
        # Remember seed name for the new pitch title
        seed_name = ""
        if hasattr(self, "recruit_name_var"):
            seed_name = (self.recruit_name_var.get() or "").strip()[:60]
        if not seed_name:
            item = self._find_recruit(getattr(self, "_recruit_selected_id", None))
            if item:
                seed_name = str(item.get("name") or "").strip()[:60]
        if not seed_name:
            seed_name = self._auto_recruit_name(text)
        self._recruit_variant_seed_name = seed_name
        self._recruit_variant_save_as_new = bool(save_as_new)

        if n == 1:
            dir_bit = (
                f"Variant direction (honor if possible, do not invent facts): {direction}\n"
                if direction
                else "Make it feel fresh — different hooks/rhythm, same offer.\n"
            )
            prompt = (
                f"Write ONE new guild recruiting chat line for {game}.\n"
                f"This is a VARIANT of the seed below — same facts, new wording.\n"
                f"{dir_bit}"
                f"Keep guild/clan name, core benefits, and how to apply if present.\n"
                f"Do NOT invent Discord requirements, buffs, or content the seed never said.\n"
                f"Do NOT copy phrases from the seed word-for-word.\n"
                f"Sound like a real player in global chat, not an ad agency.\n"
                f"{house_bit}"
                f"HARD LIMIT: under {lim} characters.\n"
                f"Output ONLY the recruitment line.\n\n"
                f"SEED PITCH:\n{text}"
            )
            self._last_gen_mode = "recruit_variant"
            self.set_status(
                "Recruit variant + save…" if save_as_new else "Recruit variant…"
            )

            def on_done(reply: str):
                self._apply_recruit_result(reply, save_as_new=save_as_new)

            self.run_llm_async(
                prompt,
                on_done=on_done,
                job="recruit_variant",
                seed_text=text,
            )
            return

        # Three distinct variants
        dir_bit = (
            f"Shared direction for all three: {direction}\n" if direction else ""
        )
        prompt = (
            f"Write THREE different guild recruiting chat lines for {game}.\n"
            f"Each is a VARIANT of the same seed pitch — same facts, different wording.\n"
            f"{dir_bit}"
            f"1 = tighter / shorter\n"
            f"2 = friendlier / chill\n"
            f"3 = punchier / more hype (still chat-safe)\n"
            f"Keep guild name + core offer + apply path from the seed.\n"
            f"Do NOT invent benefits the seed never said.\n"
            f"Do NOT copy seed phrasing.\n"
            f"{house_bit}"
            f"Each under {lim} characters.\n"
            f"Output exactly:\n1. line\n2. line\n3. line\n\n"
            f"SEED PITCH:\n{text}"
        )
        self._last_gen_mode = "recruit_variant"
        self.set_status("Recruit ×3 variants…")
        self.copy_badge.configure(text="thinking", text_color=C["warn"])

        if self._busy:
            self.set_status("Already generating…")
            return
        self._busy = True

        def work():
            used_offline = False
            if getattr(self, "_llm_online", None) is False:
                results = [self._pick_recruit_local() for _ in range(3)]
                used_offline = True
            else:
                results = self.call_local_llm(prompt, n=3, job="recruit_variant")
                if results and all(self._is_err(r) for r in results):
                    results = [self._pick_recruit_local() for _ in range(3)]
                    used_offline = True
                    self._llm_online = False
                elif results and not all(self._is_err(r) for r in results):
                    self._llm_online = True

            def finish():
                self._busy = False
                self.session_gens += 1
                self.update_session_chip()
                cleaned = []
                for r in results or []:
                    if self._is_err(r):
                        continue
                    line = self._clean_line(r, lim)
                    if line and line not in cleaned:
                        # Prefer not identical to seed
                        if line.strip().lower() == text.strip().lower():
                            continue
                        cleaned.append(line)
                while len(cleaned) < 3:
                    # Soft offline padding
                    pad_line = self._pick_recruit_local()
                    if pad_line and pad_line not in cleaned:
                        cleaned.append(pad_line)
                    else:
                        cleaned.append(text[:lim] if text else pad_line)
                    if len(cleaned) >= 3:
                        break
                cleaned = cleaned[:3]

                def apply():
                    if used_offline:
                        self.show_toast("Offline pack (AI off)", kind="info")
                    self._last_variants = cleaned
                    self._set_variant_buttons(cleaned)
                    if cleaned:
                        self._apply_recruit_result(cleaned[0], save_as_new=False)
                        self.show_toast(
                            "3 variants ready — pick 1–3, then Save as new",
                            kind="ok",
                        )
                    self.copy_badge.configure(text="ready", text_color=C["muted"])
                    self.set_status("Recruit variants ready")

                self.ui_safe(apply)

            self.schedule_ui(finish)

        threading.Thread(target=work, daemon=True).start()

    def _next_recruit_variant_name(self, seed_name: str = "") -> str:
        """Build a unique name like 'KFQ1 · v2' for a saved AI variant."""
        base = (seed_name or "Pitch").strip() or "Pitch"
        # Strip existing · vN suffix so we don't stack v2 · v3
        base = re.sub(r"\s*[·•]\s*v\d+\s*$", "", base, flags=re.IGNORECASE).strip() or "Pitch"
        base = base[:50]
        existing = {
            str(t.get("name") or "").strip().lower()
            for t in (getattr(self, "recruit_templates", None) or [])
        }
        # Prefer "Name · variant", then "Name · v2", …
        candidates = [f"{base} · variant"]
        for i in range(2, 50):
            candidates.append(f"{base} · v{i}")
        for name in candidates:
            if name.lower() not in existing:
                return name
        return f"{base} · v{int(time.time()) % 10000}"

    def _save_recruit_variant_as_new(self, text: str, seed_name: str = "") -> bool:
        """
        Append AI variant as a brand-new pitch (does not overwrite seed).
        Updates recruit_templates.json + Saved pitch dropdown.
        """
        text = (text or "").strip()
        if not text:
            return False
        name = self._next_recruit_variant_name(seed_name)
        rid = self._new_recruit_id()
        self.recruit_templates = list(getattr(self, "recruit_templates", None) or [])
        self.recruit_templates.append({"id": rid, "name": name, "text": text})
        self._recruit_selected_id = rid
        if hasattr(self, "recruit_name_var"):
            self.recruit_name_var.set(name)
        if hasattr(self, "msg_textbox"):
            self.msg_textbox.delete("1.0", tk.END)
            self.msg_textbox.insert("1.0", text)
            self.update_counter()
        ok = self._save_recruit_file()
        if ok:
            self.save_settings()
            self._refresh_recruit_ui(load_editor=True)
        return ok

    def _apply_recruit_result(self, reply: str, save_as_new: bool = False):
        if self._is_err(reply):
            self.show_toast("AI offline", kind="error")
            self._recruit_variant_save_as_new = False
            return
        lim = self.limit()
        reply = self._clean_line(reply, lim)
        reply = self._dedupe_against_history(reply, fallback=reply)
        # Honor one-shot flag from generate_recruit_variant(save_as_new=True)
        if not save_as_new:
            save_as_new = bool(getattr(self, "_recruit_variant_save_as_new", False))
        self._recruit_variant_save_as_new = False
        seed_name = str(getattr(self, "_recruit_variant_seed_name", "") or "")

        def apply():
            if save_as_new and reply:
                ok = self._save_recruit_variant_as_new(reply, seed_name=seed_name)
                self.set_gen_text(reply, also_ai=True, also_hud=True)
                if self.auto_copy.get():
                    self.safe_copy(reply)
                else:
                    self.push_history(reply, count=False)
                if ok:
                    name = ""
                    if hasattr(self, "recruit_name_var"):
                        name = (self.recruit_name_var.get() or "").strip()
                    self.show_toast(
                        f"Saved new pitch · {name or 'variant'}",
                        kind="ok",
                    )
                    self.set_status(f"Recruit variant saved · {name or 'variant'}")
                else:
                    self.show_toast("Variant ready — save failed", kind="warn")
                return

            if hasattr(self, "msg_textbox"):
                self.msg_textbox.delete("1.0", tk.END)
                self.msg_textbox.insert("1.0", reply)
                self.update_counter()
            self.set_gen_text(reply, also_ai=True, also_hud=True)
            if self.auto_copy.get():
                self.safe_copy(reply)
            else:
                self.push_history(reply, count=False)
            mode = getattr(self, "_last_gen_mode", "") or ""
            if mode == "recruit_variant":
                self.show_toast("Recruit variant ready — Save as new to keep", kind="ok")

        self.ui_safe(apply)

    # =====================================================================
    # LLM — job-split prompts; temp/max_tokens sent in API payload
    # =====================================================================
    def intensity_instruction(self, job: str = "") -> str:
        level = int(self.intensity_var.get()) if hasattr(self, "intensity_var") else 1
        # Replies: heat only nudges dryness vs light tease — never hype/chaos
        if job in ("comeback", "triple"):
            if level <= 0:
                return (
                    "Tone: chill and understated. Short. Almost dry. "
                    "No hype, no superlatives, no performance comedy."
                )
            if level == 1:
                return (
                    "Tone: normal in-game chat. Casual, human, lightly funny at most. "
                    "Never tryhard-clever or cheerleader-y."
                )
            return (
                "Tone: slightly sharper tease or dry sarcasm — still low-key. "
                "One jab max. No superlatives, no roast essay, not mean."
            )
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

        # Economy text fallback (OCR → price advice)
        if job == "economy":
            return (
                "You price MMO market items from OCR text of auction/market UI.\n"
                "Only use prices present in the text. Never invent server averages.\n"
                "Output EXACTLY the labeled lines requested (ITEM, COMPS, LOW, HIGH, "
                "MEDIAN, SUGGEST, WTS, NOTES). No markdown. No preamble."
            )

        # Clean dad jokes — always family-safe; MUST finish the punchline
        if job == "dadjoke":
            cap = min(lim, DAD_JOKE_LIMIT)
            base = (
                "You write classic clean dad jokes for multiplayer game chat.\n"
                "ALWAYS family-friendly. G-rated. No innuendo, no swearing, no insults, "
                "no dark humor, no politics, no adult topics, no game jargon.\n"
                "Voice: wholesome dad energy — punny, slightly proud of a bad joke.\n"
                "CRITICAL: every joke must be COMPLETE — setup AND punchline. "
                "Never stop after the question. Never leave the answer unfinished.\n"
                "Good example: What do you call a bread that's always late? A loaf-er.\n"
                "Bad example: What do you call a bread that's always late?  (missing punchline)\n"
                "Structures: setup then punchline · What do you call…? · Why did the…? · "
                "I used to… · object wordplay (food, animals, jobs, school, sports).\n"
                "Make it ORIGINAL — not a famous stock joke word-for-word.\n"
            )
            base += (
                "RULES:\n"
                "- Output ONLY the full joke text. No 'Here's a joke' / 'Dad joke:' preamble.\n"
                f"- HARD CAP: {cap} characters. Use enough of the budget to finish the punchline.\n"
                "- One complete joke only. Setup + payoff. No trailing ellipsis mid-thought.\n"
                "- No emojis, hashtags, markdown.\n"
                "- Groan-worthy is good; random nonsense is not a dad joke.\n"
            )
            base += self._anti_echo_block()
            return base

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
        # Per-game vocabulary normalizer (DG=Dungeon, WB=World Boss, …)
        vocab_block = self.vocab_prompt_block(game)
        if vocab_block:
            base += vocab_block
        house = self.house_style_for(game)
        if house:
            base += (
                f"PLAYER HOUSE STYLE (honor this — guild/slang/constraints):\n"
                f"{house}\n"
            )
        if cfg.get("use_mood"):
            mood = self.mood_var.get() if hasattr(self, "mood_var") else "Casual Gamer"
            # For replies, mood is a light tint only — never a character monologue
            if job in ("comeback", "triple"):
                base += (
                    f"Light personality tint only: {mood}. Stay understated.\n"
                    f"{self.intensity_instruction(job)}\n"
                )
            else:
                base += f"Personality flavor: {mood}.\n{self.intensity_instruction(job)}\n"
        # Only inject specialty terms for LFG/recruit — not for idle presence chat
        if job == "lfg" and hasattr(self, "lfg_target_var"):
            info = self.lfg_target_info()
            label = (info.get("label") or "").lower()
            base += (
                f"Selected LFG content: {info['label']}. "
                f"The message MUST be about that content only.\n"
            )
            # Content-specific allow list (Quinfall etc.)
            if "world boss" in label:
                base += "WB / world boss language is REQUIRED/allowed for this LFG.\n"
            elif "combat zone" in label:
                base += "CZ / combat zone language is REQUIRED/allowed for this LFG.\n"
            elif "dungeon" in label:
                base += (
                    "Dungeon language is required. Players often write DG for dungeon — "
                    "DG is valid and preferred short form.\n"
                )
            else:
                base += (
                    "Do NOT mention WB/world boss, CZ/combat zone, or DG/dungeon "
                    "unless they appear in the selected content or location name.\n"
                )
        elif cfg.get("use_terms") and job in ("recruit",):
            terms = ", ".join(prof.get("terms", [])[:8])
            if terms:
                base += f"Light native shorthand only when natural: {terms}.\n"
        elif job in ("banter", "spice", "refine"):
            base += (
                "For presence/idle chat: use GENERIC gamer platitudes "
                "(grind, loot, chill, gg, brb, hanging out). "
                "Do NOT force content acronyms (WB/CZ/DG) unless the activity is that content.\n"
            )
        elif job in ("comeback", "triple"):
            base += (
                "REPLY VOICE: real player typing fast in global/party chat.\n"
                "Understated > clever. Dry or casual > witty monologue.\n"
                "Match their energy: short in → short out.\n"
                "If THEY used game shorthand (DG, WB, CZ, …), decode it correctly and "
                "you may reply using the same shorthand.\n"
                "Do NOT force content jargon they did not use.\n"
            )

        job_rules = {
            "lfg": (
                "JOB: LFG / party call only.\n"
                "Name the exact content the user selected. Clear need + vibe.\n"
                "No life story. No guild recruiting. No mixing unrelated content.\n"
                "Use this game's natural shorthand when it fits the selected content "
                "(e.g. DG for Dungeon, WB for World Boss, CZ for Combat Zone).\n"
            ),
            "recruit": (
                "JOB: guild/clan recruitment line only.\n"
                "Preserve facts from the user draft. Punchy and scannable.\n"
                "Avoid stuffing fake system acronyms.\n"
            ),
            "recruit_variant": (
                "JOB: rewrite an existing guild recruit pitch as a fresh VARIANT.\n"
                "Keep the SAME guild/clan name, core benefits, rules, and how-to-apply.\n"
                "Change wording, rhythm, and hooks — do NOT copy the seed phrasing.\n"
                "Do not invent new rewards, Discord rules, or content the seed never said.\n"
                "Punchy, scannable chat line — not a paragraph essay.\n"
            ),
            "comeback": (
                "JOB: reply to another player's line in chat.\n"
                "React to THEIR words. Answer a question if they asked one.\n"
                "Sound like a human, not a coach, wingman, or hype bot.\n"
                "Prefer short understated lines (fair / lol / true / one dry beat).\n"
                "FORBIDDEN: superlatives, cheerleading, 'as a fellow player', essay replies,\n"
                "forced jokes, LFG/recruit pivots unless they asked, invented drama.\n"
                "Do not invent WB/CZ unless they mentioned it.\n"
            ),
            "triple": (
                "JOB: three alternate REPLY lines as numbered options.\n"
                "1 = dry/minimal · 2 = friendly · 3 = light tease.\n"
                "All three understated and human — no hype, no superlatives.\n"
                "Each must still respond to what they said.\n"
            ),
            "banter": (
                "JOB: casual presence line — maintain activity appearance in chat.\n"
                "Generic gamer platitude / observation / half-thought.\n"
                "NOT an LFG. NOT a system callout. NOT WB/CZ unless activity requires it.\n"
                "If a hint is given, treat it as loose vibe only — never quote the hint words.\n"
            ),
            "spice": (
                "JOB: rewrite a line fresher with same intent.\n"
                "Do not copy the original wording. Do not inject WB/CZ jargon.\n"
            ),
            "refine": (
                "JOB: refine the given line as instructed.\n"
                "Keep meaning; change length/tone only as asked. Do not add fake jargon.\n"
            ),
        }
        base += job_rules.get(job, job_rules["banter"])
        prefer_short = max(24, min(lim, 90 if job in ("comeback", "triple") else lim))
        base += (
            "RULES:\n"
            "- Output ONLY the chat message text. No quotes. No labels. No preamble.\n"
            f"- HARD CAP: {lim} characters. Prefer shorter"
            + (f" (aim under {prefer_short}).\n" if job in ("comeback", "triple") else ".\n")
            + "- Sound human and typed fast. No emojis, hashtags, markdown.\n"
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
        # Keep specialized multi-output jobs (recruit_variant, etc.); only fall back
        # to "triple" system prompt for generic multi when the job has no multi rules.
        if n > 1 and job in ("banter", "comeback", "spice", "refine", "lfg", "noise"):
            use_job = "triple"
        else:
            use_job = job
        content = user_prompt
        if n > 1 and "1." not in user_prompt and "1)" not in user_prompt:
            content = (
                user_prompt
                + f"\n\nGive exactly {n} different options as:\n1. line\n2. line\n3. line\n"
                f"Each under {lim} characters. No extra commentary."
            )

        sampling = self._sampling_payload(use_job)
        # Prefer recruit_variant sampling even when n>1
        if job == "recruit_variant":
            sampling = self._sampling_payload("recruit_variant")
        self.api_url = self._normalize_api_url(self.api_url)
        payload = {
            "model": self._selected_lm_model(),
            "messages": [
                {"role": "system", "content": self.system_prompt(use_job)},
                {"role": "user", "content": content},
            ],
            **sampling,
        }
        try:
            r = requests.post(
                self.api_url, json=payload, headers=self._llm_headers(), timeout=25
            )
            if r.status_code != 200:
                return [f"Error: HTTP {r.status_code}"]
            raw = r.json()["choices"][0]["message"]["content"].strip()
            if n > 1:
                return self._parse_numbered(raw, n, lim)
            return [self._clean_line(raw, lim)]
        except Exception:
            host = getattr(self, "lm_host", "") or LM_DEFAULT_LOCAL_HOST
            return [f"Backend offline. Start LM Studio server on {host}."]

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

    def _pick_activity_local(self) -> str:
        """Offline presence / activity line from stock + light templates."""
        lim = self.limit()
        activity = self.activity_var.get() if hasattr(self, "activity_var") else "General Chat"
        hidden = set(self.hidden_lines.get(self.game_var.get(), []) if hasattr(self, "hidden_lines") else [])
        stock = [p for p in (self.profile().get("quick") or []) if p not in hidden]
        # Prefer non-LFG stock for activity
        ambient = [
            p for p in stock
            if not p.lower().startswith("lfg") and not p.lower().startswith("lfm")
            and "looking for" not in p.lower()
        ]
        templates = [
            "just grinding, say hi",
            "chill vibes tonight",
            "loot go brrr",
            "taking it slow",
            "o/",
            "back on the grind",
            "gg",
            "anyone else hanging?",
            f"on {activity} for a bit",
            f"{activity} mode",
            "brb snack",
            "nice one",
        ]
        pool = ambient + templates + stock[:6]
        recent = set(self.history[-12:])
        fresh = [p for p in pool if p and p not in recent]
        line = random.choice(fresh or pool or ["o/"])
        if len(line) > lim:
            line = self.trim_to_limit(line)
        return line

    def _pick_comeback_local(self, they_said: str = "") -> str:
        """Offline reply pack — short/human, not AI."""
        lim = self.limit()
        low = (they_said or "").lower()
        if any(w in low for w in ("lfg", "lfm", "looking for", "need ")):
            pool = [
                "i can hop if still need",
                "invite if spots",
                "might be down — what content?",
                "same, forming too",
            ]
        elif re.search(r"(?<![a-z0-9])dg(?![a-z0-9])", low) or "dungeon" in low:
            pool = [
                "which dg?",
                "i can hop if still need",
                "what dungeon?",
                "might be down for that dg",
            ]
        elif re.search(r"(?<![a-z0-9])wb(?![a-z0-9])", low) or "world boss" in low:
            pool = [
                "wb when?",
                "might hop if still up",
                "same, waiting on wb",
                "invite if spots for wb",
            ]
        elif re.search(r"(?<![a-z0-9])cz(?![a-z0-9])", low) or "combat zone" in low:
            pool = [
                "cz? might hop",
                "which cz / need?",
                "same, looking at cz",
                "invite if still need for cz",
            ]
        elif any(w in low for w in ("howdy", "hello", "hi ", "hey", "o/")):
            pool = ["hey", "o/", "yo", "howdy"]
        elif any(w in low for w in ("lol", "haha", "lmao", "xd")):
            pool = ["lol true", "same", "real", "fair"]
        elif any(w in low for w in ("price", "sell", "buy", "gold", "cost", "tp ")):
            pool = [
                "yeah prices are weird",
                "felt that",
                "market's a mess rn",
                "true, not paying that",
            ]
        elif "?" in (they_said or ""):
            pool = [
                "not sure tbh",
                "idk — maybe",
                "could be",
                "no idea, just vibing",
            ]
        else:
            pool = [
                "fair",
                "true",
                "heard",
                "same tbh",
                "lol real",
                "respect",
                "gg",
                "facts",
                "mood",
                "oof",
                "yeah",
            ]
        recent = set(self.history[-10:])
        fresh = [p for p in pool if p not in recent]
        line = random.choice(fresh or pool)
        if len(line) > lim:
            line = self.trim_to_limit(line)
        return line

    def _reply_too_hype(self, text: str) -> bool:
        """True if the model wrote superlative / bot-cheerleader energy."""
        low = f" {(text or '').lower()} "
        hits = sum(1 for m in REPLY_HYPE_MARKERS if m in low)
        if hits >= 1 and len((text or "").split()) >= 8:
            return True
        if hits >= 2:
            return True
        # Long performative replies feel fake in game chat
        if len(text or "") > min(self.limit(), 110) and hits >= 1:
            return True
        # Exclamation spam
        if (text or "").count("!") >= 2:
            return True
        return False

    def _soften_reply_line(self, text: str, they_said: str = "") -> str:
        """If AI went tryhard, fall back to a short human offline line."""
        t = (text or "").strip()
        if not t or self._is_err(t) or self._reply_too_hype(t):
            return self._pick_comeback_local(they_said)
        return t

    def _pick_recruit_local(self) -> str:
        """Offline: use current recruit draft or first template, fit to limit."""
        lim = self.limit()
        text = ""
        try:
            if hasattr(self, "msg_textbox"):
                text = self.msg_textbox.get("1.0", "end").strip()
        except Exception:
            pass
        if not text:
            items = getattr(self, "recruit_templates", None) or []
            if items:
                text = str(items[0].get("text") or "").strip()
            elif self.templates:
                text = self.templates[0]
            else:
                text = "Chill guild recruiting — whisper me"
        if len(text) > lim:
            text = self.trim_to_limit(text)
        return text

    def _offline_line(self, job: str, *, they_said: str = "", seed_text: str = "") -> str:
        """Best offline pack for a job when LM Studio is unreachable."""
        j = (job or "banter").lower()
        if j == "lfg":
            return self._lfg_local_line()
        if j == "noise":
            return self._pick_noise_local()
        if j == "dadjoke":
            return self._pick_dad_joke_local()
        if j == "comeback":
            return self._pick_comeback_local(they_said)
        if j in ("recruit", "recruit_variant"):
            return self._pick_recruit_local()
        if j in ("refine", "spice"):
            base = (seed_text or "").strip()
            if not base and hasattr(self, "get_gen_text"):
                try:
                    base = (self.get_gen_text() or "").strip()
                except Exception:
                    base = ""
            if not base or self._is_err(base):
                return self._pick_activity_local()
            lim = self.limit()
            if j == "refine" and len(base) > int(lim * 0.75):
                return self.trim_to_limit(base)
            return base[:lim] if len(base) > lim else base
        # banter / triple / activity / default
        return self._pick_activity_local()

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
        *,
        they_said: str = "",
        seed_text: str = "",
        offline_ok: bool = True,
    ):
        if self._busy:
            self.set_status("Already generating…")
            return
        self._busy = True
        self.set_status("Thinking…")
        self.copy_badge.configure(text="thinking", text_color=C["warn"])

        def work():
            # Fast path only when probe already proved offline (None = try network)
            if offline_ok and getattr(self, "_llm_online", None) is False:
                pack = [
                    self._offline_line(job, they_said=they_said, seed_text=seed_text)
                    for _ in range(max(1, n))
                ]
                results = pack
                used_offline = True
            else:
                results = self.call_local_llm(prompt, n=n, job=job)
                used_offline = False
                if offline_ok and results and all(self._is_err(r) for r in results):
                    results = [
                        self._offline_line(job, they_said=they_said, seed_text=seed_text)
                        for _ in range(max(1, n))
                    ]
                    used_offline = True
                    self._llm_online = False
                elif results and not all(self._is_err(r) for r in results):
                    self._llm_online = True

            def finish():
                self._busy = False
                self.session_gens += 1
                self.update_session_chip()

                def apply():
                    if used_offline:
                        self.show_toast("Offline pack (AI off)", kind="info")
                        self.copy_badge.configure(text="offline pack", text_color=C["warn"])
                    if on_done:
                        on_done(results[0] if results else "")
                    else:
                        self._show_ai_result(results[0] if results else "")

                self.ui_safe(apply)

            self.schedule_ui(finish)

        threading.Thread(target=work, daemon=True).start()

    def _apply_line_to_outputs(self, reply: str, also_ai: bool = True):
        """Push a good line into the generated-line editor (+ optional Wingman)."""
        if self._is_err(reply):
            # Last resort offline pack from last job
            job = getattr(self, "_last_gen_mode", "banter") or "banter"
            reply = self._offline_line(job)
            self.show_toast("Offline pack (AI off)", kind="info")
            self.copy_badge.configure(text="offline pack", text_color=C["warn"])

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

        def done(reply: str):
            if self._is_err(reply):
                reply = self.trim_to_limit(text) if len(text) > lim else text
                if len(reply) > lim:
                    reply = reply[:lim]
                self.show_toast("Offline trim", kind="info")
            self._apply_line_to_outputs(reply, also_ai=True)

        self.run_llm_async(
            f"Rewrite MUCH shorter (under {lim} chars), same meaning:\n{text}",
            on_done=done, job="refine", seed_text=text,
        )

    def refine_safer(self):
        text = self._current_output_line()
        if not text or self._is_err(text):
            return
        self._last_gen_mode = "refine"

        def done(reply: str):
            if self._is_err(reply):
                reply = text  # keep original offline
                self.show_toast("Offline — kept line", kind="info")
            self._apply_line_to_outputs(reply, also_ai=True)

        self.run_llm_async(
            f"Rewrite friendlier and guild-safe, still natural:\n{text}",
            on_done=done, job="refine", seed_text=text,
        )

    def refine_spicier(self):
        text = self._current_output_line()
        if not text or self._is_err(text):
            return
        self._last_gen_mode = "refine"

        def done(reply: str):
            if self._is_err(reply):
                reply = text
                self.show_toast("Offline — kept line", kind="info")
            self._apply_line_to_outputs(reply, also_ai=True)

        self.run_llm_async(
            f"Rewrite with more playful spice. Not reportable. One line:\n{text}",
            on_done=done, job="refine", seed_text=text,
        )

    def generate_activity_line(self):
        """Activity chat = generic gamer presence / activity appearance. Not jargon spam."""
        self._last_gen_mode = "banter"
        game = self.game_var.get()
        activity = self.activity_var.get()
        mood = self.mood_var.get() if hasattr(self, "mood_var") else "Casual Gamer"
        lim = self.limit()
        seed = ""
        if hasattr(self, "input_seed"):
            seed = self.input_seed.get().strip()

        prompt = (
            f"JOB: idle presence chat while playing {game}.\n"
            f"Purpose: look active in chat — generic gamer platitude, not a systems lecture.\n"
            f"Loose setting: {activity}. Mood: {mood}.\n"
            f"Write ONE short line: greeting, status, light joke, grind/loot vibe, or chill banter.\n"
            f"FORBIDDEN unless the player already said them: WB, world boss, CZ, combat zone, "
            f"and any invented acronyms/systems.\n"
            f"NOT an LFG. NOT recruiting. NOT party calls.\n"
            f"Under {lim} characters. No quotes. No emoji.\n"
        )
        if seed:
            prompt += f"Loose vibe only (do NOT quote these words): {seed}\n"

        def done(reply: str):
            if self._is_err(reply):
                reply = self._pick_activity_local()
                self.show_toast("Offline activity pack", kind="info")
            else:
                # Strip accidental forced jargon
                low = (reply or "").lower()
                if any(x in low for x in (" world boss", "combat zone", " wb", " cz", "wb ", "cz ")):
                    if "world boss" not in activity.lower() and "combat zone" not in activity.lower():
                        reply = self._pick_activity_local()
                reply = self._strip_hint_echo(reply, seed)
                reply = self._dedupe_against_history(reply, fallback=self._pick_activity_local())
                # Soft guard: if model still wrote LFG, local ambient
                low = (reply or "").lower()
                if low.startswith("lfg") or low.startswith("lfm") or "looking for group" in low:
                    reply = self._pick_activity_local()
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

    def _dad_joke_cap(self) -> int:
        return min(int(self.limit()), DAD_JOKE_LIMIT)

    def _pick_dad_joke_local(self) -> str:
        cap = self._dad_joke_cap()
        recent = set(self.history[-15:])
        pool = [j for j in DAD_JOKES if j not in recent and len(j) <= cap]
        if not pool:
            pool = [j for j in DAD_JOKES if len(j) <= cap] or list(DAD_JOKES)
        line = random.choice(pool)
        if len(line) > cap:
            line = self.trim_to_limit(line) if len(line) > self.limit() else line[:cap]
        return line

    def _dad_joke_looks_ok(self, joke: str, cap: int) -> bool:
        """Quality gate: clean, complete setup+punchline (not truncated)."""
        j = (joke or "").strip()
        if not j or self._is_err(j):
            return False
        if len(j) > cap + 20:
            return False
        low = f" {j.lower()} "
        dirty_bits = (
            " damn", " hell", " crap", "sexy", "nude", "kill", "drug",
            "nsfw", "****", " fuck", " shit", " ass ", " porn",
        )
        if any(b in low for b in dirty_bits):
            return False
        if len(j) < 18:
            return False
        if low.strip().startswith("lfg") or "looking for group" in low:
            return False
        # Incomplete: ends with bare ? (setup only) or trailing "…" mid-thought
        stripped = j.rstrip()
        if stripped.endswith("?") and stripped.count("?") == 1 and len(stripped) < 55:
            # Single question with no answer after it
            # Allow short anti-jokes that ARE the punchline if very short? No — need payoff
            # If nothing after the last ?, it's incomplete
            return False
        if stripped.endswith("?") or stripped.endswith("…") or stripped.endswith("..."):
            # Question-only or ellipsis cut-off
            q = stripped.rfind("?")
            if q >= 0 and len(stripped[q + 1 :].strip()) < 2:
                return False
            if stripped.endswith("…") or stripped.endswith("..."):
                return False
        # "What do you call" / "Why did" must have text after the ?
        for lead in ("what do you call", "why did", "why don't", "why can't", "how do you"):
            if lead in j.lower():
                if "?" not in j:
                    return False
                after = j.split("?", 1)[-1].strip(" -–—:")
                if len(after) < 2:
                    return False
        return True

    def _clean_dad_joke(self, raw: str, cap: int) -> str:
        """Light clean that keeps full setup+punchline (not first-line only)."""
        line = (raw or "").strip().strip('"').strip("'")
        for prefix in (
            "Dad joke:", "Joke:", "Here's a joke:", "Here is a joke:",
            "Output:", "Answer:",
        ):
            if line.lower().startswith(prefix.lower()):
                line = line[len(prefix):].strip()
        # Join multi-line into one chat-friendly string
        line = " ".join(p.strip() for p in line.replace("\r", "\n").split("\n") if p.strip())
        line = line.replace('"', "").replace("“", "").replace("”", "")
        if len(line) > cap:
            # Prefer keep punchline: cut from the start of setup if needed, else hard cap
            line = line[:cap].rstrip()
            # If we cut mid-word, drop the fragment
            if " " in line:
                line = line.rsplit(" ", 1)[0]
        return line.strip()

    def generate_dad_joke(self):
        """AI-first clean dad joke (classic patterns). Offline pack only if AI fails."""
        self._last_gen_mode = "dadjoke"
        cap = self._dad_joke_cap()
        pattern = random.choice(DAD_JOKE_PATTERNS)
        spark = random.choice(
            [
                "coffee", "socks", "bread", "dogs", "math", "elevator", "stairs",
                "cheese", "birds", "clocks", "shoes", "soup", "plants", "parking",
                "library", "weather", "batteries", "mirrors", "pencils", "traffic",
            ]
        )
        prompt = (
            f"Write ONE original clean dad joke. Max {cap} characters.\n"
            f"Structure: {pattern}.\n"
            f"Topic spark (optional): {spark}.\n"
            "MUST include BOTH the setup AND the full punchline — never stop after the question.\n"
            "Example of COMPLETE: What do you call a bread that's always late? A loaf-er.\n"
            "Example of BAD (incomplete): What do you call a bread that's always late?\n"
            "Family-friendly only. Groan-worthy pun.\n"
            "Output only the finished joke text."
        )

        def done(reply: str):
            cleaned = self._clean_dad_joke(reply, cap)
            if not self._dad_joke_looks_ok(cleaned, cap):
                cleaned = self._pick_dad_joke_local()
                self.show_toast(
                    "Dad joke pack"
                    if getattr(self, "_llm_online", None) is False
                    else "Dad joke · finished from pack",
                    kind="info",
                )
            else:
                cleaned = self._dedupe_against_history(
                    cleaned, fallback=self._pick_dad_joke_local()
                )
            self._apply_line_to_outputs(cleaned, also_ai=True)
            self.set_status(f"Dad joke · {len(cleaned)}/{cap}")

        self.run_llm_async(prompt, on_done=done, job="dadjoke")

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
        lim = self.limit()
        aim = max(20, min(lim, 72))
        annotated = self.annotate_text_with_vocab(user_input, game)
        # Few-shot style anchors without forcing copy
        examples = (
            "Examples of good energy (style only, do NOT copy):\n"
            "- fair\n"
            "- lol yeah\n"
            "- true, market's weird rn\n"
            "- i can hop if still need\n"
            "- oof that tax\n"
            "- wb tax is rough\n"
            "- dg? which one\n"
        )
        prompt = (
            f"In {game} chat ({activity}), another player said:\n"
            f"\"{annotated}\"\n\n"
            f"Write ONE short reply you would actually type.\n"
            f"Decode any game shorthand correctly (see gloss if present).\n"
            f"Understated and human. React to their words.\n"
            f"Prefer under {aim} characters (hard max {lim}).\n"
            f"No superlatives, no hype, no essay, no 'as a player'.\n"
            f"No LFG/recruit unless they asked for a group.\n"
            f"{examples}"
            f"Output only the reply."
        )

        def done(reply: str):
            if self._is_err(reply):
                reply = self._pick_comeback_local(user_input)
                self.show_toast("Offline reply pack", kind="info")
            else:
                cleaned = self._clean_line(reply, lim)
                if self._reply_too_hype(cleaned):
                    # One soft retry path: use offline short line rather than bad hype
                    reply = self._pick_comeback_local(user_input)
                    self.show_toast("Kept reply low-key", kind="info")
                else:
                    reply = self._dedupe_against_history(
                        cleaned, fallback=self._pick_comeback_local(user_input)
                    )
            self._apply_line_to_outputs(reply, also_ai=True)
            self.set_status("Reply ready")

        self.run_llm_async(
            prompt, on_done=done, job="comeback", they_said=user_input,
        )

    def generate_triple(self):
        user_input = self.input_statement.get().strip()
        if not user_input and hasattr(self, "quick_they_said"):
            user_input = self.quick_they_said.get().strip()
        seed = self.input_seed.get().strip() if hasattr(self, "input_seed") else ""
        game = self.game_var.get()
        activity = self.activity_var.get()
        self._last_gen_mode = "triple"
        if user_input:
            lim = self.limit()
            aim = max(20, min(lim, 72))
            annotated = self.annotate_text_with_vocab(user_input, game)
            prompt = (
                f"In {game} chat ({activity}), they said:\n\"{annotated}\"\n\n"
                f"Decode any game shorthand correctly (see gloss if present).\n"
                f"Three DIFFERENT short replies a real player might type:\n"
                f"1 = dry / minimal\n"
                f"2 = friendly / helpful\n"
                f"3 = light tease (still low-key)\n"
                f"Each under ~{aim} chars. No superlatives, no hype, no essays.\n"
                f"Each must respond to what they said. No LFG unless they asked.\n"
                f"Number them 1. 2. 3. only."
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
            offline = False
            if getattr(self, "_llm_online", None) is False:
                if user_input:
                    results = [self._pick_comeback_local(user_input) for _ in range(3)]
                else:
                    results = [self._pick_activity_local() for _ in range(3)]
                offline = True
            else:
                results = self.call_local_llm(prompt, n=3, job=job)
                if results and all(self._is_err(r) for r in results):
                    if user_input:
                        results = [self._pick_comeback_local(user_input) for _ in range(3)]
                    else:
                        results = [self._pick_activity_local() for _ in range(3)]
                    offline = True
                    self._llm_online = False
                elif results and not all(self._is_err(r) for r in results):
                    self._llm_online = True

            def finish():
                self._busy = False
                self.session_gens += 1
                self.update_session_chip()
                if offline:
                    self.show_toast("Offline pack ×3", kind="info")
                self.ui_safe(lambda: self._show_multi_results(results))

            self.schedule_ui(finish)

        threading.Thread(target=work, daemon=True).start()

    def regenerate_last(self):
        mode = self._last_gen_mode
        if mode == "comeback":
            self.generate_response()
        elif mode == "triple":
            self.generate_triple()
        elif mode in ("recruit", "recruit_variant"):
            if hasattr(self, "generate_recruit_variant"):
                self.generate_recruit_variant(n=1)
            else:
                self.ai_fit_recruitment()
        elif mode == "lfg":
            self.generate_lfg()
        elif mode == "noise":
            self.generate_noise()
        elif mode == "dadjoke":
            self.generate_dad_joke()
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

    def _lfg_location(self) -> str:
        if hasattr(self, "lfg_location_var"):
            return (self.lfg_location_var.get() or "").strip()
        return ""

    def _lfg_party_finder_on(self) -> bool:
        if hasattr(self, "lfg_party_finder"):
            return bool(self.lfg_party_finder.get())
        return False

    def _lfg_local_line(self) -> str:
        """Offline / fallback LFG: Content @ Location [in Party Finder] + need."""
        info = self.lfg_target_info()
        label = info.get("label", "group")
        loc = self._lfg_location()
        pf = self._lfg_party_finder_on()
        need = self.lfg_need_var.get() if hasattr(self, "lfg_need_var") else "Anyone"

        # Preferred shape: Content @ Location (Location may be a dungeon name)
        low_label = label.lower()
        if "loot" in low_label or "exp" in low_label or "grind" in low_label:
            content_phrase = "Loot / XP Grind" if ("loot" in low_label or "exp" in low_label) else label
        else:
            content_phrase = label

        base = f"LFG {content_phrase}"
        if loc:
            # Dungeon content + dungeon location: "LFG Dungeon @ Foaming Catacombs"
            # Grind + farm spot: "LFG Loot / XP Grind @ Cemetery"
            base += f" @ {loc}"
        if pf:
            base += " in Party Finder"

        if need == "Need 1 more":
            base += " — need 1 more"
        elif need == "Need a couple":
            base += " — need a couple"
        elif need == "Chill only":
            base += " — chill only"
        elif need == "Full group":
            base += " — full group"

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
        # Loot/XP grind: accept "loot" OR "xp" OR "exp" OR "grind"
        if aliases and not any(a in low for a in aliases if len(a) >= 2):
            return False
        loc = self._lfg_location().lower()
        if loc and loc not in low and not any(
            t in low for t in loc.replace("/", " ").split() if len(t) > 2
        ):
            # Soft: prefer location but don't hard-fail if content is clear
            pass
        if self._lfg_party_finder_on() and "party finder" not in low and "pf" not in low:
            pass  # soft preference; local pack enforces
        # Must not drag in forbidden other content (but allow current location)
        for bad in info.get("never") or []:
            b = bad.lower()
            if not b:
                continue
            if b in label or (loc and b in loc):
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
        loc = self._lfg_location()
        pf = self._lfg_party_finder_on()
        never = ", ".join(info.get("never") or []) or "other games' content"
        example = self._lfg_local_line()
        is_dungeon = (info.get("label") or "").lower() == "dungeon"
        loc_rule = ""
        if loc:
            if is_dungeon:
                loc_rule = (
                    f"LOCATION is the DUNGEON NAME: {loc}. You MUST include it "
                    f"(e.g. LFG Dungeon @ {loc} or LFG {loc}). Do not invent another dungeon."
                )
            else:
                loc_rule = f"You MUST include the location: {loc} (e.g. @ {loc})."
        # Content-specific shorthand hint for this LFG
        shorthand = ""
        lab = (info.get("label") or "").lower()
        if "dungeon" in lab:
            shorthand = "Players often write DG for Dungeon — DG is valid and natural."
        elif "world boss" in lab:
            shorthand = "Players almost always write WB for World Boss — prefer WB."
        elif "combat zone" in lab:
            shorthand = "Players write CZ for Combat Zone — prefer CZ."
        vocab_hits = ""
        vb = self.vocab_prompt_block(game)
        if vb:
            vocab_hits = "Use only shorthand that matches the selected content.\n"

        return (
            f"Write ONE LFG/LFM chat line for {game}.\n"
            f"CONTENT (general type): {info['label']}\n"
            f"What it is: {info.get('brief', info['label'])}\n"
            f"{shorthand}\n"
            f"LOCATION (spot or dungeon name): {loc or 'none'}\n"
            f"PARTY FINDER: {'YES — include the phrase Party Finder' if pf else 'NO — do not mention Party Finder'}.\n"
            f"You MUST clearly name the content using natural player words "
            f"(e.g. related to: {info.get('must_name', info['label'])}).\n"
            f"{loc_rule}\n"
            f"Need / party shape: {need} — {need_hint}.\n"
            f"Preferred shape: LFG + content + @ location + optional 'in Party Finder' + need.\n"
            f"{vocab_hits}"
            f"Good example shape: {example}\n"
            f"Do NOT invent other locations/dungeons. Stay on {loc or 'the selected content'}.\n"
            f"Do NOT mention: {never}.\n"
            f"Do NOT say WB/world boss or CZ/combat zone unless CONTENT is World Boss or Combat Zone.\n"
            f"DO NOT recruit for a guild. DO NOT write a joke that skips the content name.\n"
            f"Under {lim} characters. One line. No quotes. No emoji.\n"
        )

    def generate_lfg(self):
        self._last_gen_mode = "lfg"
        self.sync_lfg_target_if_needed()
        # Persist current selection as this game's default
        self.on_lfg_target_changed(self.lfg_target_var.get())
        self.on_lfg_location_changed(self.lfg_location_var.get() if hasattr(self, "lfg_location_var") else None)
        info = self.lfg_target_info()
        loc = self._lfg_location()
        prompt = self._build_lfg_prompt()

        def done(reply: str):
            if self._is_err(reply) or not self._lfg_line_ok(reply, info):
                reply = self._lfg_local_line()
                if self._is_err(reply):
                    self.show_toast("Offline LFG pack", kind="info")
                else:
                    self.show_toast(f"LFG · {info['label']} (tuned)", kind="info")
            else:
                reply = self._dedupe_against_history(reply, fallback=self._lfg_local_line())
                if not self._lfg_line_ok(reply, info):
                    reply = self._lfg_local_line()
            self._apply_line_to_outputs(reply, also_ai=True)
            self.set_status(
                f"LFG · {info['label']}"
                + (f" @ {loc}" if loc else "")
                + (" · PF" if self._lfg_party_finder_on() else "")
            )

        self.run_llm_async(prompt, on_done=done, job="lfg")

    def spice_phrase(self, phrase: str):
        self._last_gen_mode = "spice"
        self._selected_quick = phrase
        game = self.game_var.get()
        activity = self.activity_var.get()

        def done(reply: str):
            if self._is_err(reply):
                # Offline: use a different stock/activity line with same vibe, not error text
                reply = self._pick_activity_local()
                self.show_toast("Offline spice pack", kind="info")
            else:
                reply = self._dedupe_against_history(reply, fallback=self._pick_activity_local())
            self._apply_line_to_outputs(reply, also_ai=True)

        self.run_llm_async(
            f"Rewrite this {game} line fresher for {activity}. Same intent. One line.\n"
            f"Do not copy wording.\n\n{phrase}",
            on_done=done,
            job="spice",
            seed_text=phrase,
        )

    def spice_selected_quick(self):
        text = self.get_gen_text() or self._selected_quick
        if not text:
            messagebox.showinfo("Pick one", "Generate or type a line in the editor first.")
            return
        self.spice_phrase(text)

    def _host_from_api_url(self, url: str) -> str:
        """Extract host:port (no scheme/path) from a chat completions URL."""
        u = (url or "").strip()
        if not u:
            return LM_DEFAULT_LOCAL_HOST
        for prefix in ("https://", "http://"):
            if u.lower().startswith(prefix):
                u = u[len(prefix):]
                break
        # strip path
        u = u.split("/", 1)[0].strip()
        return u or LM_DEFAULT_LOCAL_HOST

    def _api_url_from_host(self, host: str) -> str:
        """Build chat completions URL from host, host:port, or full URL."""
        h = (host or "").strip()
        if not h:
            h = LM_DEFAULT_LOCAL_HOST
        # Already a full chat completions URL
        if "/v1/chat/completions" in h:
            return self._normalize_api_url(h)
        # Full base like http://ip:1234 or http://ip:1234/v1
        if h.lower().startswith("http://") or h.lower().startswith("https://"):
            base = h.rstrip("/")
            if base.lower().endswith("/v1"):
                base = base[:-3].rstrip("/")
            return self._normalize_api_url(base + "/v1/chat/completions")
        # bare host or host:port
        if "://" not in h:
            if ":" not in h:
                h = f"{h}:{LM_DEFAULT_PORT}"
            return self._normalize_api_url(f"http://{h}/v1/chat/completions")
        return self._normalize_api_url(h)

    def _normalize_api_url(self, url: str) -> str:
        """Rewrite localhost → 127.0.0.1 so Windows IPv6 lag does not fake offline."""
        u = (url or "").strip() or f"http://{LM_DEFAULT_LOCAL_HOST}/v1/chat/completions"
        # Common LM Studio defaults
        for bad, good in (
            ("http://localhost:", "http://127.0.0.1:"),
            ("https://localhost:", "https://127.0.0.1:"),
            ("http://[::1]:", "http://127.0.0.1:"),
            ("https://[::1]:", "https://127.0.0.1:"),
        ):
            if u.lower().startswith(bad):
                u = good + u[len(bad):]
                break
        if not u.endswith("/v1/chat/completions") and "/v1/" not in u:
            u = u.rstrip("/") + "/v1/chat/completions"
        return u

    def _api_base(self, url: Optional[str] = None) -> str:
        u = self._normalize_api_url(url or getattr(self, "api_url", "") or "")
        if "/v1/" in u:
            return u.rsplit("/v1/", 1)[0].rstrip("/")
        return u.rstrip("/")

    def _llm_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        key = ""
        if hasattr(self, "lm_api_key_var"):
            try:
                key = (self.lm_api_key_var.get() or "").strip()
            except Exception:
                key = ""
        if not key:
            key = (getattr(self, "lm_api_key", "") or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _selected_lm_model(self) -> str:
        """Model id for chat/completions — prefer UI selection, else first cached loaded model."""
        for candidate in (
            (self.lm_model_var.get() if hasattr(self, "lm_model_var") else "") or "",
            getattr(self, "lm_model", "") or "",
        ):
            m = str(candidate).strip()
            if m and not m.startswith("("):
                return m
        cache = getattr(self, "_lm_models_cache", None) or []
        if cache:
            return str(cache[0])
        # LM Studio accepts this alias when a model is loaded
        return "local-model"

    def _llm_probe_urls(self) -> list[str]:
        """Candidate /v1/models URLs — configured host first; local fallback only in Local mode."""
        # Prefer live UI host if present
        try:
            if hasattr(self, "lm_host_var"):
                host = (self.lm_host_var.get() or "").strip()
                if host:
                    primary = self._api_url_from_host(host)
                else:
                    primary = self._normalize_api_url(getattr(self, "api_url", "") or "")
            else:
                primary = self._normalize_api_url(getattr(self, "api_url", "") or "")
        except Exception:
            primary = self._normalize_api_url(getattr(self, "api_url", "") or "")

        bases = [self._api_base(primary)]
        mode = getattr(self, "lm_mode", "Local")
        if hasattr(self, "lm_mode_var"):
            try:
                mode = self.lm_mode_var.get() or mode
            except Exception:
                pass
        # Local only: also try classic LM Studio port if user typed something odd
        if str(mode).lower().startswith("local"):
            if "127.0.0.1:1234" not in " ".join(bases):
                bases.append(f"http://{LM_DEFAULT_LOCAL_HOST}")
        seen = set()
        out = []
        for b in bases:
            if not b or b in seen:
                continue
            seen.add(b)
            out.append(b.rstrip("/") + "/v1/models")
        return out

    def _probe_llm_server(self, full: bool = False):
        """
        Probe LM Studio OpenAI-compatible /v1/models.
        Returns (online, detail, model_ids) when full=True,
        else (online, detail) for the status pulse.
        detail = first loaded model id, or error reason.
        """
        last_err = "unreachable"
        headers = self._llm_headers()
        # Drop Content-Type on GET (harmless but cleaner)
        get_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
        mode = getattr(self, "lm_mode", "Local")
        if hasattr(self, "lm_mode_var"):
            try:
                mode = self.lm_mode_var.get() or mode
            except Exception:
                pass
        # Remote may be slower on LAN
        timeout = (3.5, 6.0) if str(mode).lower().startswith("remote") else (2.0, 4.0)

        for models_url in self._llm_probe_urls():
            try:
                r = requests.get(models_url, headers=get_headers or None, timeout=timeout)
                if 200 <= r.status_code < 300:
                    model_ids: list[str] = []
                    try:
                        data = r.json()
                        items = data.get("data") or []
                        if items and isinstance(items, list):
                            for it in items:
                                if not isinstance(it, dict):
                                    continue
                                mid = str(it.get("id") or "").strip()
                                if mid and mid not in model_ids:
                                    model_ids.append(mid)
                    except Exception:
                        model_ids = []
                    model_id = model_ids[0] if model_ids else "ready"
                    self._lm_models_cache = list(model_ids)
                    # Pin api_url to the base we actually reached
                    try:
                        base = models_url.rsplit("/v1/", 1)[0]
                        want = base.rstrip("/") + "/v1/chat/completions"
                        if self._normalize_api_url(self.api_url) != want:
                            self.api_url = want
                        # Keep host field in sync with successful probe
                        host_disp = self._host_from_api_url(want)
                        self.lm_host = host_disp
                    except Exception:
                        pass
                    if full:
                        return True, model_id, model_ids
                    return True, model_id
                last_err = f"HTTP {r.status_code}"
            except requests.exceptions.Timeout:
                last_err = "timeout"
            except requests.exceptions.ConnectionError:
                last_err = "no server"
            except Exception as e:
                last_err = type(e).__name__
        if full:
            return False, last_err, []
        return False, last_err

    def pulse_llm_status(self):
        if not self._tk_alive():
            return
        gen = self._llm_pulse_gen

        def check():
            # Worker thread: network only
            if gen != self._llm_pulse_gen or not getattr(self, "_alive", False):
                return
            ok, detail, models = self._probe_llm_server(full=True)

            def apply():
                if gen != self._llm_pulse_gen or not self._tk_alive():
                    return
                if not hasattr(self, "llm_dot"):
                    return
                try:
                    if not self.llm_dot.winfo_exists():
                        return
                    self._llm_online = bool(ok)
                    if ok:
                        # Prefer saved selection if still present; else default loaded model
                        preferred = ""
                        if hasattr(self, "lm_model_var"):
                            preferred = (self.lm_model_var.get() or "").strip()
                            if preferred.startswith("("):
                                preferred = ""
                        preferred = preferred or (getattr(self, "lm_model", "") or "")
                        if models:
                            self._populate_lm_model_menu(models, preferred=preferred, online=True)
                        model_show = self._selected_lm_model()
                        if model_show == "local-model":
                            model_show = detail
                        # Keep chip short; full model id is in the hover tip
                        self.llm_dot.configure(text="AI · on", text_color=C["success"])
                        mode = getattr(self, "lm_mode", "Local")
                        if hasattr(self, "lm_mode_var"):
                            try:
                                mode = self.lm_mode_var.get() or mode
                            except Exception:
                                pass
                        tip(
                            self.llm_dot,
                            "LM STUDIO AI SERVER — online\n"
                            f"Model: {model_show}\n"
                            f"Mode: {mode}\n"
                            f"API: {self._normalize_api_url(self.api_url)}\n"
                            "Click → Setup to change host / model.\n"
                            "Used for Write / dad jokes / vision OCR.",
                        )
                        self._set_lm_conn_status(True, str(model_show))
                    else:
                        self.llm_dot.configure(text="AI · off", text_color=C["danger"])
                        host = getattr(self, "lm_host", "") or LM_DEFAULT_LOCAL_HOST
                        if hasattr(self, "lm_host_var"):
                            try:
                                host = (self.lm_host_var.get() or host).strip() or host
                            except Exception:
                                pass
                        tip(
                            self.llm_dot,
                            "LM STUDIO AI SERVER — offline\n"
                            f"Last check: {detail}\n"
                            f"Host: {host}\n"
                            "Write still works via offline packs (LFG/activity/noise/etc).\n"
                            "1) Open LM Studio  2) Load a model  3) Start Server\n"
                            "Click → Setup for Local/Remote + Test connection.",
                        )
                        self._set_lm_conn_status(False, detail or "unreachable")
                except Exception:
                    return

            if not self.schedule_ui(apply):
                return
            if gen == self._llm_pulse_gen and getattr(self, "_alive", False):
                self.schedule_ui(
                    lambda: threading.Thread(target=check, daemon=True).start(),
                    delay_ms=8000,
                )

        threading.Thread(target=check, daemon=True).start()


    # =====================================================================
    # Surprise pack · hotkeys / focus / oracle / economy extras
    # =====================================================================
    def _bind_surprise_hotkeys(self):
        if getattr(self, "_surprise_hotkeys_bound", False):
            return
        binds = {
            "<F6>": lambda e: self.hotkey_write(),
            "<F7>": lambda e: self.hotkey_copy(),
            "<F8>": lambda e: self.hotkey_market_snap(),
            "<F9>": lambda e: self.hotkey_reprice(),
            "<F10>": lambda e: self.hotkey_oracle(),
            "<Control-e>": lambda e: self.export_session_pack(),
            "<Control-E>": lambda e: self.export_session_pack(),
        }
        for seq, fn in binds.items():
            try:
                self.root.bind(seq, fn, add="+")
            except Exception:
                pass
        self._surprise_hotkeys_bound = True

    def _hotkeys_ok(self) -> bool:
        return bool(getattr(self, "hotkeys_enabled", None) and self.hotkeys_enabled.get())

    def hotkey_write(self):
        if not self._hotkeys_ok():
            return
        try:
            self.tabview.set("Chat Generator")
        except Exception:
            pass
        key = self.generator_intent.get() if hasattr(self, "generator_intent") else "lfg"
        dispatch = {
            "lfg": self.generate_lfg,
            "activity": self.generate_activity_line,
            "reply": self.generate_response_from_quick,
            "recruit": (
                (lambda: self.generate_recruit_variant(n=1, save_as_new=False))
                if hasattr(self, "generate_recruit_variant")
                else self.ai_fit_recruitment
            ),
            "noise": self.generate_noise,
        }
        fn = dispatch.get(key, self.generate_lfg)
        try:
            fn()
            self.show_toast(f"F6 · Write {key}", kind="info")
        except Exception:
            self.show_toast("F6 write failed", kind="error")

    def hotkey_copy(self):
        if not self._hotkeys_ok():
            return
        try:
            self.copy_quick_out()
            self.show_toast("F7 · Copy", kind="ok")
        except Exception:
            self.show_toast("F7 copy failed", kind="error")

    def hotkey_market_snap(self):
        if not self._hotkeys_ok():
            return
        try:
            self.tabview.set("Economy")
        except Exception:
            pass
        self.grab_market_price()

    def hotkey_reprice(self):
        if not self._hotkeys_ok():
            return
        try:
            self.tabview.set("Economy")
        except Exception:
            pass
        self.reprice_last_market()

    def hotkey_oracle(self):
        if not self._hotkeys_ok():
            return
        self.run_oracle()

    def toggle_focus_mode(self):
        on = bool(self.focus_mode.get())
        if on:
            try:
                self.always_on_top.set(True)
                self.apply_on_top()
            except Exception:
                pass
            try:
                self.auto_copy.set(True)
            except Exception:
                pass
            self.show_toast("Focus mode · F6 write · F7 copy · F8 market", kind="ok")
            if hasattr(self, "status_bar"):
                self.set_status("FOCUS · F6 Write · F7 Copy · F8 Market · F9 Reprice · F10 Oracle")
        else:
            self.show_toast("Focus mode off", kind="info")
        self.save_settings()

    def export_session_pack(self):
        """Write a human-readable session dump next to the app."""
        try:
            elapsed = max(1, int(time.time() - getattr(self, "session_started", time.time())))
            mins = elapsed // 60
            lines = [
                f"Chat Helper session export · v{APP_VERSION}",
                f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Game: {self.game_var.get() if hasattr(self, 'game_var') else '?'}",
                f"Session: {mins}m · copies {self.session_copies} · gens {self.session_gens} · streak {self.session_streak}",
                f"Steam peak this session: {self._session_steam_peak or 'n/a'}",
                "",
                "=== Recent history ===",
            ]
            for h in list(getattr(self, "history", []) or [])[-15:]:
                lines.append(f"  • {h}")
            lines.append("")
            lines.append("=== Favorites ===")
            for f in list(getattr(self, "favorites", []) or [])[:15]:
                lines.append(f"  ★ {f}")
            lines.append("")
            lines.append("=== Economy log (recent) ===")
            for e in list(getattr(self, "economy_history", []) or [])[-10:]:
                lines.append(
                    f"  {e.get('when', '?')} · {e.get('item', '?')} · suggest {e.get('suggest', '?')} · {e.get('wts', '')}"
                )
            lines.append("")
            lines.append("=== Macros ===")
            for i, m in enumerate(getattr(self, "macro_slots", []) or []):
                if m:
                    lines.append(f"  M{i + 1}: {m}")
            lines.append("")
            lines.append(f"Files: {STEAM_LOG_PATH}")
            lines.append(f"       {ECONOMY_LOG_PATH}")
            lines.append(f"       {LAST_MARKET_PATH}")
            body = "\n".join(lines)
            with open(SESSION_EXPORT_PATH, "w", encoding="utf-8") as f:
                f.write(body)
            try:
                os.startfile(SESSION_EXPORT_PATH)  # type: ignore
            except Exception:
                pass
            self.show_toast("Session exported", kind="ok")
            self.set_status(f"Exported → {SESSION_EXPORT_PATH}")
        except Exception as e:
            self.show_toast(f"Export failed: {e}", kind="error")

    def run_oracle(self):
        """Daily surprise: fortune + pop advice + random location."""
        game = self.game_var.get() if hasattr(self, "game_var") else "MMO"
        day = time.strftime("%Y-%m-%d")
        seed = sum(ord(c) for c in day + game) + int(time.time()) // 86400
        rng = random.Random(seed)
        fortunes = [
            "The loot gods are watching. Tip them with one clean LFG.",
            "Low drama, high mats. Sell the boring stuff first.",
            "Your next whisper is luckier if the line is under the char limit.",
            "Population is a tide — farm during the swell, list during the calm.",
            "A short chat line travels farther than a paragraph.",
            "If the market looks empty, your price is a lighthouse.",
            "Party Finder is a billboard. Make it readable at a glance.",
            "Today's RNG is mid. Skill issue is optional; vibe is not.",
            "Double-check the stack size before you undercut your own listing.",
            "Someone out there needs exactly what you're carrying.",
        ]
        pop = getattr(self, "_steam_player_count", None)
        peak = getattr(self, "_session_steam_peak", None)
        if pop and peak and pop >= peak * 0.95:
            pop_advice = f"Steam looks hot right now (~{pop:,}). Good window to list or LFG."
        elif pop and peak and pop < peak * 0.7:
            pop_advice = f"Quieter than session peak ({peak:,} → {pop:,}). Flip crafts or farm in peace."
        elif pop:
            pop_advice = f"About {pop:,} concurrent on Steam for this title. Solid mid-session energy."
        else:
            pop_advice = "No Steam pop for this game — trust the vibe, not the graph."
        locs = self.lfg_location_list() if hasattr(self, "lfg_location_list") else []
        loc = rng.choice(locs) if locs else "the usual spot"
        fortune = fortunes[seed % len(fortunes)]
        line = f"Oracle · {fortune} · {pop_advice} · Try LFG @ {loc}"
        if hasattr(self, "lfg_location_var") and locs:
            try:
                self.lfg_location_var.set(loc)
            except Exception:
                pass
        self.set_status(line)
        self.show_toast(f"Oracle · @{loc}", kind="info")
        # Also drop a tiny note into Generated if empty
        try:
            if not self.get_gen_text().strip():
                self.set_gen_text(f"LFG chill @ {loc}", also_ai=True, also_hud=True)
        except Exception:
            pass
        messagebox.showinfo("✦ Oracle", f"{fortune}\n\n{pop_advice}\n\nSuggested hangout: {loc}")

    def _oracle_boot_whisper(self):
        """Quiet status-line oracle on launch (no popup)."""
        try:
            if getattr(self, "onboarding_done", True):
                game = self.game_var.get() if hasattr(self, "game_var") else "game"
                day = time.strftime("%Y-%m-%d")
                seed = sum(ord(c) for c in day + game)
                whispers = [
                    "Oracle whispers: short lines hit harder tonight.",
                    "Oracle whispers: check Economy if you're listing.",
                    "Oracle whispers: F8 snaps the market. F10 for a full reading.",
                    "Oracle whispers: pin the app and forget alt-tab stress.",
                ]
                self.set_status(whispers[seed % len(whispers)])
        except Exception:
            pass

    def _start_clip_watch(self):
        if getattr(self, "_clip_watch_started", False):
            return
        self._clip_watch_started = True
        self.root.after(1500, self._clip_watch_tick)

    def _clip_watch_tick(self):
        if not self._tk_alive():
            return
        try:
            if hasattr(self, "clip_watch_enabled") and self.clip_watch_enabled.get():
                self._clip_watch_once()
        except Exception:
            pass
        self.schedule_ui(self._clip_watch_tick, delay_ms=2000)

    def _clip_watch_once(self):
        """If clipboard is a pure number, offer it to flip Buy/Sell fields."""
        try:
            clip = pyperclip.paste()
        except Exception:
            return
        if not clip or clip == getattr(self, "_clip_watch_last", None):
            return
        s = str(clip).strip().replace(",", "").replace(" ", "")
        # plain number / k / m
        low = s.lower()
        mult = 1.0
        if low.endswith("k"):
            mult = 1000.0
            low = low[:-1]
        elif low.endswith("m"):
            mult = 1_000_000.0
            low = low[:-1]
        try:
            val = float(low) * mult
        except Exception:
            self._clip_watch_last = clip
            return
        if val <= 0 or val > 1e15:
            self._clip_watch_last = clip
            return
        self._clip_watch_last = clip
        # Only nudge when Economy tab is active (less spam)
        try:
            if hasattr(self, "tabview") and self.tabview.get() != "Economy":
                return
        except Exception:
            return
        pretty = f"{int(val):,}" if abs(val - round(val)) < 0.01 else f"{val:g}"
        # Fill empty buy first, else sell
        buy = (self.flip_buy_var.get() if hasattr(self, "flip_buy_var") else "").strip()
        sell = (self.flip_sell_var.get() if hasattr(self, "flip_sell_var") else "").strip()
        if not buy:
            self.flip_buy_var.set(pretty)
            self.recalc_flip()
            self.show_toast(f"Clip → Buy {pretty}", kind="info")
        elif not sell:
            self.flip_sell_var.set(pretty)
            self.recalc_flip()
            self.show_toast(f"Clip → Sell {pretty}", kind="info")
        else:
            # rotate: push sell into buy? just update sell
            self.flip_sell_var.set(pretty)
            self.recalc_flip()
            self.show_toast(f"Clip → Sell {pretty}", kind="info")

    def recalc_flip(self):
        if not hasattr(self, "flip_result"):
            return
        def parse(raw):
            s = (raw or "").strip().lower().replace(",", "").replace(" ", "")
            if not s:
                return None
            mult = 1.0
            if s.endswith("k"):
                mult = 1000.0
                s = s[:-1]
            elif s.endswith("m"):
                mult = 1_000_000.0
                s = s[:-1]
            try:
                return float(s) * mult
            except Exception:
                return None
        buy = parse(self.flip_buy_var.get() if hasattr(self, "flip_buy_var") else "")
        sell = parse(self.flip_sell_var.get() if hasattr(self, "flip_sell_var") else "")
        fee = parse(self.flip_fee_var.get() if hasattr(self, "flip_fee_var") else "5") or 0.0
        if buy is None or sell is None:
            self.flip_result.configure(text="Profit · enter buy + sell", text_color=C["faint"])
            return
        fee_amt = sell * (fee / 100.0)
        profit = sell - buy - fee_amt
        pct = (profit / buy * 100.0) if buy else 0.0
        color = C["success"] if profit > 0 else C["danger"] if profit < 0 else C["muted"]
        p_txt = f"{profit:,.0f}" if abs(profit) >= 100 else f"{profit:,.2f}"
        self.flip_result.configure(
            text=f"Profit · {p_txt}  ({pct:+.1f}%)  ·  fees {fee_amt:,.0f}",
            text_color=color,
        )

    def _macro_btn_label(self, idx: int) -> str:
        slots = getattr(self, "macro_slots", ["", "", ""])
        raw = slots[idx] if idx < len(slots) else ""
        if not raw:
            return f"M{idx + 1} · empty"
        prev = raw if len(raw) < 18 else raw[:15] + "…"
        return f"M{idx + 1} · {prev}"

    def _refresh_macro_btns(self):
        if not hasattr(self, "macro_btns"):
            return
        for i, b in enumerate(self.macro_btns):
            try:
                b.configure(text=self._macro_btn_label(i))
            except Exception:
                pass

    def _clear_macro(self, idx: int):
        try:
            self.macro_slots[idx] = ""
            self._refresh_macro_btns()
            self.save_settings()
            self.show_toast(f"Macro {idx + 1} cleared", kind="info")
        except Exception:
            pass
        return "break"

    def fire_macro(self, idx: int):
        slots = getattr(self, "macro_slots", [])
        if idx < 0 or idx >= len(slots) or not slots[idx]:
            self.show_toast(f"Macro {idx + 1} empty — Save → Macro from WTS", kind="warn")
            return
        line = slots[idx]
        try:
            self.safe_copy(line)
            self.set_gen_text(line, also_ai=True, also_hud=True)
        except Exception:
            pyperclip.copy(line)
            self.show_toast(f"Macro {idx + 1} copied", kind="ok")

    def save_wts_to_macro(self):
        line = (getattr(self, "_last_economy_wts", "") or "").strip()
        if not line:
            line = (self.get_gen_text() or "").strip()
        if not line:
            self.show_toast("Nothing to save — snap a price first", kind="warn")
            return
        slots = getattr(self, "macro_slots", ["", "", ""])
        # fill empty first, else overwrite last
        placed = None
        for i, s in enumerate(slots):
            if not s:
                slots[i] = line[:200]
                placed = i
                break
        if placed is None:
            slots[-1] = line[:200]
            placed = len(slots) - 1
        self.macro_slots = slots
        self._refresh_macro_btns()
        self.save_settings()
        self.show_toast(f"Saved → Macro {placed + 1}", kind="ok")

    def _economy_hist_summary(self) -> str:
        hist = list(getattr(self, "economy_history", []) or [])
        if not hist:
            return "No snaps logged yet — each Snap + price stores item + suggest here."
        lines = []
        for e in reversed(hist[-6:]):
            lines.append(
                f"{e.get('when', '?')}  ·  {e.get('item') or 'item'}  ·  {e.get('suggest') or '?'}"
            )
        return "\n".join(lines)

    def _refresh_economy_hist_ui(self):
        if hasattr(self, "economy_hist_label"):
            try:
                self.economy_hist_label.configure(text=self._economy_hist_summary())
            except Exception:
                pass

    def _log_economy_entry(self, parsed: dict, engine: str = ""):
        entry = {
            "when": time.strftime("%m/%d %H:%M"),
            "ts": time.time(),
            "game": self.game_var.get() if hasattr(self, "game_var") else "",
            "item": parsed.get("item") or (self.economy_item_var.get() if hasattr(self, "economy_item_var") else ""),
            "suggest": parsed.get("suggest") or "",
            "wts": parsed.get("wts") or "",
            "comps": parsed.get("comps") or "",
            "low": parsed.get("low") or "",
            "high": parsed.get("high") or "",
            "engine": engine,
        }
        hist = list(getattr(self, "economy_history", []) or [])
        hist.append(entry)
        self.economy_history = hist[-40:]
        try:
            with open(ECONOMY_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
        self._refresh_economy_hist_ui()
        try:
            self.save_settings()
        except Exception:
            pass

    def reprice_last_market(self):
        """Re-run analysis on last_market_capture.png without a new screenshot."""
        if self._economy_busy:
            self.show_toast("Already analyzing…", kind="warn")
            return
        if not _HAS_PIL:
            messagebox.showerror("Pillow required", "Install Pillow.")
            return
        if not os.path.isfile(LAST_MARKET_PATH):
            self.show_toast("No last shot — Snap first", kind="warn")
            return
        self._economy_busy = True
        self._refresh_market_status("re-pricing last shot…")
        item = (self.economy_item_var.get() if hasattr(self, "economy_item_var") else "").strip()
        try:
            undercut = float(
                (self.economy_undercut_var.get() if hasattr(self, "economy_undercut_var") else "5")
                .replace("%", "").strip() or "5"
            )
        except Exception:
            undercut = 5.0
        game = self.game_var.get() if hasattr(self, "game_var") else ""

        def work():
            err = None
            raw_out = ""
            engine = ""
            try:
                img = Image.open(LAST_MARKET_PATH)
                raw_out, engine = self._economy_analyze_image(img, item, undercut, game)
            except Exception as e:
                err = str(e)

            def done():
                self._economy_busy = False
                if err or not raw_out or self._is_err(raw_out):
                    self.show_toast("Re-price failed", kind="error")
                    self._refresh_market_status("re-price failed")
                    return
                parsed = self._parse_economy_result(raw_out, item)
                self._apply_economy_result(parsed, engine + "·reprice")
                self.show_toast("Re-priced last shot", kind="ok")

            self.schedule_ui(done)

        threading.Thread(target=work, daemon=True).start()

    def economy_compare_previous(self):
        hist = list(getattr(self, "economy_history", []) or [])
        if len(hist) < 2:
            self.show_toast("Need 2+ snaps in the price log", kind="warn")
            return
        a, b = hist[-2], hist[-1]
        def num(s):
            s = (s or "").replace(",", "").strip()
            # pull first number
            import re as _re
            m = _re.search(r"[\d.]+", s.replace("k", "000").replace("K", "000"))
            if not m:
                return None
            try:
                return float(m.group(0))
            except Exception:
                return None
        na, nb = num(a.get("suggest")), num(b.get("suggest"))
        msg = (
            f"Previous: {a.get('item') or '?'} · {a.get('suggest') or '?'}\n"
            f"Latest:     {b.get('item') or '?'} · {b.get('suggest') or '?'}\n"
        )
        if na is not None and nb is not None and na > 0:
            delta = nb - na
            pct = delta / na * 100.0
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            msg += f"\n{arrow} {delta:+,.0f} ({pct:+.1f}%)"
        messagebox.showinfo("Δ Economy compare", msg)
        self.show_toast("Compared last two snaps", kind="info")

    def _note_steam_session_peak(self, count: Optional[int]):
        if count is None:
            return
        peak = getattr(self, "_session_steam_peak", None)
        if peak is None or count > peak:
            prev = peak
            self._session_steam_peak = count
            self._session_steam_peak_ts = time.time()
            if prev is not None and count >= int(prev * 1.05) and count - prev >= 20:
                self.show_toast(f"Steam session peak · {count:,}", kind="ok")
                self.set_status(f"New Steam session peak: {count:,}")



if __name__ == "__main__":
    root = ctk.CTk()
    app = GamersChatHelper(root)
    root.mainloop()
