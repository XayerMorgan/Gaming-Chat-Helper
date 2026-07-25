# Hyperline AI — Help Manual

**Version:** 7.0  
**App:** Hyperline — Instant Global Chat Velocity. Local desktop companion for MMO chat lines, Steam population, market snaps, and a simple calculator.

**Your Line telemetry** (engagement / readability) is a local heuristic estimate, not live game CTR.

This manual is available from the app menu: **Help → Full Manual** (also **F1** for context help on the current tab).

**Install, LM Studio, vision models, and PC tuning:** see **[SETUP_AND_FAQ.md](SETUP_AND_FAQ.md)**  
(also **Help → Setup & FAQ (LM Studio)** in the app).

---

## 0. Requirements at a glance

| Need | Details |
|------|---------|
| Python 3.10+ | `pip install -r requirements.txt` |
| LM Studio | https://lmstudio.ai/ — model loaded + **Local Server** on port **1234** |
| Recommended model | **Qwen3-VL 2B Instruct Q4** (chat + Economy + OCR on modest VRAM) |
| Stronger vision | Qwen2-VL / Qwen3-VL 7B–8B Q4 |
| Optional OCR | [Tesseract for Windows](https://github.com/UB-Mannheim/tesseract/wiki) + `pytesseract` |
| API URL | `http://127.0.0.1:1234` (prefer IPv4, not `localhost`) |

Full install steps, VRAM guide, and FAQ → **SETUP_AND_FAQ.md**.

---

## 1. Quick start (Golden Loop)

1. Pick a **game** in the header (sets character limit and profile).
2. Open **Chat Generator**.
3. Choose an intent: **LFG · Activity · Reply · Recruit · Noise**.
4. Press **Write** (or **F6** if hotkeys are on).
5. Press green **Copy** (or **F7**) and paste in-game.

Requirements for AI writing:

- [LM Studio](https://lmstudio.ai/) running  
- A model loaded  
- **Local Server** enabled (default `http://127.0.0.1:1234`)  
- Header shows **AI · on** (green)

If AI is off, many jobs still work via **offline packs** (stock LFG, noise, dad jokes, activity lines).

---

## 2. Header controls

| Control | Meaning |
|--------|---------|
| **Game dropdown** | Profile: char limit, LFG content, stock lines, Steam AppID |
| **Limit badge** | Hard character cap (Copy blocks if over) |
| **A− / A+** | UI text size (also Ctrl+ / Ctrl− / Ctrl+0) |
| **Players · …** | Steam **concurrent players** for this game (not AI). Click → Setup chart |
| **AI · on/off** | LM Studio local server reachable? Hover for model name |
| **ready / thinking** | Clipboard / generate status |
| **HUD** | Compact always-on-top strip |
| **Pin** | Keep window above the game |
| **Auto** | Auto-copy when generation finishes |
| **Focus** | Pin + auto-copy + quieter “raid night” status |
| **Keys** | Enable app hotkeys (F6–F10) |
| **↻ Restart** | Save settings and relaunch the `.bat` |
| **✦ Oracle** | Daily vibe + Steam advice + random LFG location |
| **⇪ Export** | Write `session_export.txt` (or **Ctrl+E**) |

**Hover** almost any control for a short tooltip.  
Status line (footer) rotates tips; session chip counts copies / gens / streak.

---

## 3. Tabs

### 3.1 Chat Generator

Intent chips show only the controls you need.

| Intent | Purpose |
|--------|---------|
| **LFG** | Content + location + Party Finder + Write |
| **Activity** | Presence / banter (not an LFG) |
| **Reply** | Paste “they said”, or grab chat via OCR |
| **Recruit** | Guild pitch templates, fit to limit, Copy |
| **Noise** | Non-game chaos (slider) + clean **Dad joke** |

**Advanced Tweaks:** Mood, Heat (spiciness), LFG Need, “Grab chat: last line only”.  
**Generated line:** edit freely, **Copy / Fav / Trim**, refine (Shorter / Safer / Spicier / Another).

#### Chat OCR (Reply)

1. **Set chat box on screen** — drag a rectangle over game chat.  
2. **Grab chat from game** — OCR (Tesseract and/or LM Studio vision).  
3. **Grab + reply** — OCR then clap-back.

Last capture: `last_chat_capture.png` next to the app.

### 3.2 Library

History and favorites: re-copy, star, delete. Manage stock lines.

### 3.3 Calculator

Simple pad with thousand separators (`1,000,000`).

- **⌨ Keys: Off** (default) — keyboard free  
- **⌨ Keys: On** — 0–9, numpad, + − * /, Enter, Backspace, Esc  
  Only while this tab is selected.

### 3.4 Economy (market snap)

There is **no public Quinfall market API**. Economy reads **what is on screen**.

1. Optional: type **My item** + **Undercut %**.  
2. **Set market area** — drag over listings.  
3. Open market in-game → **Snap + price** (**F8**).  
4. Read comps, **Suggested**, **WTS** line.  
5. **↻ Re-price last shot** (**F9**) reuses `last_market_capture.png`.  
6. **Δ vs previous** — compare last two logged snaps.  
7. **Flip profit** — Buy / Sell / Fee % (clipboard numbers auto-fill on Economy tab).  
8. **WTS Macros** M1–M3 — save WTS; click to paste; Shift+click to clear.  
9. **Price log** — recent snaps + `economy_price_log.jsonl`.

**Best results:** vision model in LM Studio (e.g. Qwen3-VL), tight crop on the price list.

### 3.5 Setup

- Full-width **Restart app**  
- **Type size**  
- **House style** (per-game notes injected into AI prompts — not noise/dad jokes)  
- **Steam population log** + chart (peak/min + time axis)  
- Quick setup bullets  

Steam log file: `steam_players_log.txt` (TSV).

---

## 4. Hotkeys

Enable with header **Keys** checkbox (when the app window is focused).

| Key | Action |
|-----|--------|
| **F1** | Context help for current tab |
| **F6** | Write current Chat Generator intent |
| **F7** | Copy generated line |
| **F8** | Economy market snap |
| **F9** | Re-price last market shot |
| **F10** | Oracle |
| **Ctrl+E** | Export session pack |
| **Ctrl+ / Ctrl− / Ctrl+0** | Type size |
| **Esc** | Exit HUD (if active) |

Calculator Keys mode is separate (on the Calculator tab).

---

## 5. Local AI (LM Studio)

**Deep dive (install, models, VRAM, tuning):** [SETUP_AND_FAQ.md](SETUP_AND_FAQ.md)

### Short version

1. Install LM Studio → download a model → **Load** it.  
2. **Developer / Local Server** → start server on port **1234**.  
3. App uses `http://127.0.0.1:1234` (not `localhost` — avoids Windows IPv6 lag).  
4. Header **AI · on** = good.  
5. **Sampling is sent per job by this app** — leave LM Studio generation sliders at defaults.

### Recommended models

| Goal | Model |
|------|--------|
| Default (chat + market + OCR) | **Qwen3-VL 2B Instruct Q4** |
| Better market reading | Qwen2-VL / Qwen3-VL 7B–8B Q4 |
| Chat-only, max quality | Qwen2.5 Instruct 7B–14B Q4/Q5 |

### Jobs vs vision

| Job | Notes |
|-----|--------|
| LFG / Activity / Reply / Recruit | Text; house style applies |
| Noise / Dad joke | Often local packs; always-clean dad jokes |
| Economy / chat grab | **Vision model** strongly preferred; Tesseract optional fallback |

**Offline packs:** if the server is down, LFG, activity, noise, replies, etc. still produce usable lines.

---

## 6. Steam population

- Header **Players · N** = concurrent players (Steam Web API, no key).  
- Setup chart: real time on X, peak/min diamonds.  
- Optional file log every 15 / 30 / 60 minutes while the app is open.  
- Session peak toasts when population hits a new high this session.

---

## 7. Files next to the app

| File | Purpose |
|------|---------|
| `chat_helper_config.json` | Settings, history, regions, macros |
| `steam_players_log.txt` | Player samples (TSV) |
| `economy_price_log.jsonl` | Economy snap log |
| `last_chat_capture.png` | Last chat OCR image |
| `last_market_capture.png` | Last market snap |
| `session_export.txt` | Session dump (Export) |
| `HELP_MANUAL.md` | This manual |
| `SETUP_AND_FAQ.md` | Install, LM Studio, models, tuning, FAQ |
| `FEATURES.md` | Feature overview / release notes |
| `requirements.txt` | Python packages |
| `Start Hyperline.bat` | Launcher |

---

## 8. Troubleshooting

| Problem | Try |
|---------|-----|
| AI · off but LM Studio runs | Use Local Server; app uses `127.0.0.1:1234`; restart app |
| OCR empty | Recalibrate tighter; load vision model; install Tesseract |
| Economy nonsense prices | Tighter market crop; name the item; vision model |
| Restart missing | Update to latest; top-right **↻ Restart** or Setup full-width button |
| Narrow window clips UI | Header is multi-row; widen slightly or use Focus mode |
| Calculator steals keys | Turn **Keys: Off** on Calculator tab |
| Copy blocked | Line over game char limit — Trim or Shorter |

---

## 9. Privacy

- Runs **locally**.  
- Chat/market images saved only as last-capture PNGs on disk.  
- No cloud accounts.  
- Steam player count is a public Steam endpoint (count only, not your account).

---

## 10. Menu reference

**File**

- Export session pack  
- Open app folder  
- Restart app  
- Exit  

**Help**

- Full Manual (this document, in-app)  
- **Setup & FAQ (LM Studio)** — install, models, tuning  
- Context help (current tab)  
- Keyboard shortcuts  
- About  
- Open HELP_MANUAL.md / SETUP_AND_FAQ.md / FEATURES.md on disk  

---

*Hyperline AI — local companion, not affiliated with game publishers or LM Studio.*
