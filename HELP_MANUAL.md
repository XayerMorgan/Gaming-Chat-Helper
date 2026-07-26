# Hyperline AI — Help Manual

**Version 7.0** · Instant Global Chat Velocity

Local companion for MMO chat, Steam population, market snaps, timers, and a calculator.

---

## Quick start

1. Pick a **game** in the header (sets character limit and profile).
2. Open **Chat Generator**.
3. Tap an **intent icon**: LFG · Activity · Reply · Recruit · Noise.
4. Press **Write** (or **F6** if Keys is on).
5. Press green **Copy** (or **F7**) and paste in-game.

### For AI writing you need

- LM Studio running with a model loaded
- Local Server on `http://127.0.0.1:1234`
- Header shows **AI · on** (green)

If AI is off, offline packs still cover many LFG / noise / activity lines.

**Install & LM Studio tuning:** open **SETUP_AND_FAQ.md** from Help menu.

---

## Header controls

| Control | Meaning |
|--------|---------|
| **Game** | Profile: limit, LFG content, stock lines, Steam AppID |
| **Limit badge** | Hard character cap (Copy blocks if over) |
| **Players** | Steam concurrent players — click for Setup chart |
| **AI · on/off** | LM Studio server status |
| **Timer chip** | Next alarm — click opens **Time** tab |
| **F6 / F7 / F8 / F9** | Write · Copy · Market snap · Re-price |
| **⋯ menu** | Type size, HUD, Pin, Auto, Focus, Keys, Oracle, Export, Restart |

Hover almost any control for a short tooltip.

---

## 3. Tabs

### 3.1 Chat Generator

Intent chips show only the controls you need.

The generator has vertical and horizontal scrollbars, so every control remains
reachable on smaller displays or at larger type sizes. The decorative banner was
removed to keep the working controls higher on screen.

| Intent | Purpose |
|--------|---------|
| **LFG** | Content + location + Party Finder + Write |
| **Activity** | Presence / banter (not an LFG) |
| **Reply** | Paste “they said”, or grab chat via OCR |
| **Recruit** | Guild pitch templates, fit to limit, Copy |
| **Noise** | Non-game chaos (slider) + clean **Dad joke** |

For **Recruit**, the working order is **Recruit controls → Your Line → Advanced
Tweaks → Seed Directive**. With **Multiples** enabled, click a card to highlight
it, then choose **Use highlighted in Your Line**. Checking **★ Star** also
highlights that card and marks it for Favorites.

Saved-pitch controls are always visible:

- **Load** reads a saved pitch into **Your Line**.
- **+ New** starts a blank draft; enter its label in **Pitch**, write the text in
  **Your Line**, then choose **Create pitch**.
- **Update pitch** saves edits back to the loaded pitch.
- **Duplicate** creates a separately saved copy.
- **Delete** removes the loaded pitch after confirmation.

**Advanced Tweaks:** Mood, Heat (spiciness), Variety, LFG Need, “Grab chat: last line only”.

**Variety controls chat wording only:**

- **Stable** — steady sampling while still rotating high-level content angles.
- **Varied** — recommended; new angles, phrasing, and structure plus semantic retries.
- **Wild** — broadest concepts; an occasional line may need a quick edit.

OCR and Economy stay accuracy-focused. Noise uses its separate **Chaos** control.

**Generated line:** edit freely, **Copy / Fav / Trim**, refine (Shorter / Safer / Spicier / Another).

#### Chat OCR (Reply)

1. **Set chat box on screen** — drag a rectangle over game chat.  
2. **Grab chat from game** — OCR (Tesseract and/or LM Studio vision).  
3. **Grab + reply** — OCR then clap-back.

Last capture: `last_chat_capture.png` next to the app.

#### Game context screenshots

Use **File → Save game context screenshot** to briefly hide Hyperline and save the
foreground game window for later reference. Screenshots are timestamped in
`context_captures/` beside the app. Use **File → Open context screenshots** to review
them. This local folder is created when Hyperline starts and is excluded from Git.

### 3.2 Library

History and favorites: re-copy, star, delete. Manage stock lines.

### 3.3 Vengeance List

Track fictional in-game rivals:

1. Choose **Player** or **Guild**.
2. Type the target manually, or choose **Set combat log box** and drag over the game’s combat log.
3. Choose **Capture + find names**. Confirm the detected name or guild before adding it.
4. Select why they made the list and add optional context.
5. Use **Settled** to retain the history without keeping the target active.

Combat-log layouts differ between games, so manual entry always remains available.
The last combat capture is stored locally as `last_vengeance_capture.png`.

### 3.4 Boss Timers

**Boss Timers** keeps a separate event-page URL for each game. The Quinfall ships
with `https://thequinfall-codex.com/events` as its default.

- Edit the URL and choose **Save for game** to keep a different page for the
  active game.
- **Reload** refreshes the embedded compatibility view.
- **Open live page** opens the same URL in your normal browser for pages that
  require full JavaScript interaction.
- The embedded view refreshes once per minute while the tab is active.

Shipped defaults live in `boss_timer_sites.defaults.json`. Your changes live in
the private, Git-ignored `chat_helper_config.json` and can also travel in a
Hyperline profile export.

### 3.5 Calculator

Simple pad with thousand separators (`1,000,000`).

- **⌨ Keys: Off** (default) — keyboard free  
- **⌨ Keys: On** — 0–9, numpad, + − * /, Enter, Backspace, Esc  
  Only while this tab is selected.

### 3.6 Economy (market snap)

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

### 3.7 Setup

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
| `boss_timer_sites.defaults.json` | Shipped per-game boss-timer URLs |
| `steam_players_log.txt` | Player samples (TSV) |
| `economy_price_log.jsonl` | Economy snap log |
| `last_chat_capture.png` | Last chat OCR image |
| `last_market_capture.png` | Last market snap |
| `context_captures/` | Timestamped game-context screenshots (local, Git-ignored) |
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
- Chat/market images and optional context screenshots are saved only on local disk.
- No cloud accounts.  
- Steam player count is a public Steam endpoint (count only, not your account).

---

## 10. Menu reference

**File**

- Export session pack  
- Save game context screenshot
- Open context screenshots
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
