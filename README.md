# Hyperline AI

**Instant Global Chat Velocity.** Local desktop companion for MMO chat drafting, Steam concurrent-player trends, market screenshot pricing, and raid-night utilities.

**Right line · under the character limit · paste in game** — powered by optional [LM Studio](https://lmstudio.ai/) (local OpenAI-compatible API). No cloud AI key required.

> Formerly *Gamer’s Chat Helper* — same app, sharper brand.

| | |
|---|---|
| **Platform** | Windows 10/11 (Python 3.10+) |
| **UI** | CustomTkinter |
| **AI** | LM Studio local server (`127.0.0.1:1234`) |
| **Docs** | [Setup & FAQ](SETUP_AND_FAQ.md) · [Help manual](HELP_MANUAL.md) · [Features](FEATURES.md) |

---

## Features

- **Chat Generator** — Intent-driven LFG, Activity, Reply, Recruit, Noise (+ clean dad jokes)
- **Per-game profiles** — Char limits, content lists, locations (Quinfall dungeons under Location)
- **Offline packs** — Usable LFG/activity/noise lines when the local AI is offline
- **Screen OCR** — Calibrate chat region; Tesseract and/or vision model
- **Economy** — Snap market UI → VL/OCR comps + suggested list price + WTS line (no public market API)
- **Vengeance List** — Track in-game player or guild rivals; combat-log OCR suggests names
- **Steam population** — Live concurrent players, overnight TSV log, chart with peak/min, high/low trend report, **Copy for Discord**
- **Calculator** — Simple pad with thousand separators and optional keyboard capture
- **Help system** — Menu bar, full manual, F1 context help, hover tooltips
- **Hotkeys** — F6 Write · F7 Copy · F8 Market snap · F9 Re-price · F10 Oracle (when enabled)

---

## Requirements

### Required

- [Python 3.10+](https://www.python.org/downloads/) (add to `PATH` on Windows)
- Packages in [`requirements.txt`](requirements.txt)

### Strongly recommended

- [LM Studio](https://lmstudio.ai/) with **Local Server** on port **1234**
- A loaded model (vision model for Economy / best OCR)

### Optional

- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (faster chat OCR without vision)
- Internet (Steam player counts only)

See **[SETUP_AND_FAQ.md](SETUP_AND_FAQ.md)** for model picks (e.g. **Qwen3-VL 2B Q4**), VRAM guidance, and tuning.

---

## Installation

```bat
cd /d "path\to\Gaming Chat Helper"
python -m pip install -U pip
python -m pip install -r requirements.txt
```

### Launch

```bat
Start Hyperline.bat
```

For the custom Hyperline launcher icon, use **`Start Hyperline.lnk`** instead of
the raw batch file. Recreate it beside the batch file at any time with:

```powershell
powershell -ExecutionPolicy Bypass -File ".\Create Hyperline Shortcut.ps1"
```

Add `-Desktop` to place the shortcut on your Windows desktop. Windows does not
support assigning a custom icon directly to a `.bat` file.

Or:

```bat
python gamers_chat_helper.py
```

On first run the app writes `chat_helper_config.json` next to the script.

---

## Quick start

1. Start **LM Studio** → load a model → enable **Local Server** (port `1234`).
2. Run the app; header should show **AI · on**.
3. Pick a **game** (sets character limit and profile).
4. **Chat Generator** → choose intent → **Write** → green **Copy** → paste in game.
5. **Help → Full Manual** or press **F1** for context help on the current tab.

**Golden loop:** intent → Write → Copy → paste.

---

## Project layout

```text
.
├── gamers_chat_helper.py      # Main application
├── Start Hyperline.bat
├── requirements.txt
├── README.md                  # This file
├── SETUP_AND_FAQ.md           # Install, LM Studio, models, FAQ
├── HELP_MANUAL.md             # Full product manual
├── FEATURES.md                # Feature inventory
├── assets/                    # Icons, banners, game badges
└── chat_helper_config.json    # User settings (created at runtime)
```

Runtime / local data (typically **not** committed): Steam log, economy log, last OCR/market captures, personal config.

---

## Configuration

| Item | Default / notes |
|------|------------------|
| API URL | `http://127.0.0.1:1234/v1/chat/completions` (prefer IPv4 over `localhost` on Windows) |
| Sampling | Sent **per job by the app** — leave LM Studio generation sliders at defaults |
| Steam log | `steam_players_log.txt` (TSV) while the app is open |
| House style | Setup tab — per-game notes injected into AI system prompts |

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [SETUP_AND_FAQ.md](SETUP_AND_FAQ.md) | Install, LM Studio, recommended vision models, VRAM tuning, troubleshooting |
| [HELP_MANUAL.md](HELP_MANUAL.md) | Tabs, hotkeys, Economy, Steam chart, menu reference |
| [FEATURES.md](FEATURES.md) | Feature inventory and design notes |

In the app: **Help** menu · **? Help** · **F1**.

---

## Hotkeys (app window focused, Keys enabled)

| Key | Action |
|-----|--------|
| `F1` | Context help (current tab) |
| `F6` | Write current intent |
| `F7` | Copy generated line |
| `F8` | Economy market snap |
| `F9` | Re-price last market shot |
| `F10` | Oracle |
| `Ctrl+E` | Export session pack |

Calculator keyboard capture is separate (toggle on the Calculator tab).

---

## Disclaimer

- Not affiliated with game publishers, Steam, or LM Studio.
- Economy pricing is based on **screenshots** only; there is no official Quinfall market API integration.
- Use local AI and in-game chat responsibly and in line with each game’s terms of service.

---

## License

Add a `LICENSE` file if you publish this repository publicly (e.g. MIT). Until then, all rights reserved by the author unless otherwise stated.
