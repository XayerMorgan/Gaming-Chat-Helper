# Gamer’s Chat Helper — Feature Document

**Product:** Local desktop companion for MMO chat drafting, Steam population trends, market screenshot pricing, calculator, and session tools.  
**Stack:** Python · CustomTkinter · LM Studio (OpenAI-compatible API) · optional Tesseract · Steam public player count API  
**Current version:** 6.2  

---

## Product pillars

1. **Right line, under limit, paste** — intent-driven Chat Generator (LFG / Activity / Reply / Recruit / Noise).  
2. **Local AI first** — LM Studio per-job sampling; offline packs when the server is down.  
3. **Live context** — Steam concurrent players + overnight log/chart; market snap pricing without a vendor API.  
4. **Raid-night UX** — multi-row header, focus mode, hotkeys, hover tips, help menu + full manual.  

---

## Feature inventory (by area)

### Chat Generator
- Intent chips with progressive disclosure  
- LFG: content types, locations (custom), Party Finder, need/mood/heat in Advanced  
- Activity presence lines (anti-jargon guards)  
- Reply: paste + screen OCR (region calibrate, Tesseract / VL)  
- Recruit templates, fit-to-limit, dual Copy  
- Noise chaos slider + always-clean dad jokes  
- Generated editor: Copy / Fav / Trim / refine / variants  
- Sticky green Copy bar; auto-copy option  
- House style (per-game notes → system prompt)  
- Offline fallback packs for major jobs  

### Library
- History + favorites + stock management  

### Calculator
- Four-function pad, comma formatting  
- Optional keyboard capture mode (toggle)  

### Economy
- Calibrate market region; snap + VL/OCR price advice  
- Undercut %; suggested price + WTS line  
- Re-price last shot; compare last two snaps  
- Flip profit (buy/sell/fee); clipboard number sniffer on Economy tab  
- WTS macro slots (3); price log + `economy_price_log.jsonl`  
- No official market API — comps from screenshot only  

### Setup / Steam
- Restart (header + Setup)  
- Type scale; house style editor  
- Steam population log intervals; chart with real time X-axis, peak/min markers  
- Session Steam peak toasts  

### Session / fun / power user
- Oracle (daily vibe + pop advice + location)  
- Focus mode; hotkeys F6–F10; Ctrl+E export  
- Session export pack (`session_export.txt`)  
- HUD mode; pin; session stats  

### Help system (v6.2)
- **Menu bar:** File + Help  
- **Full Manual** window (searchable sections, mirrors `HELP_MANUAL.md`)  
- **F1** context help for current tab  
- **Shortcuts** and **About** dialogs  
- Hover tooltips on configurable controls  
- Open manual file on disk  

---

## Files of note

| Path | Role |
|------|------|
| `gamers_chat_helper.py` | Main application |
| `Start Gamers Chat Helper.bat` | Windows launcher |
| `chat_helper_config.json` | User settings |
| `HELP_MANUAL.md` | End-user manual |
| `FEATURES.md` | This document |
| `requirements.txt` | Python deps |
| `assets/` | Brand + game badges |

---

## Design constraints

- Prefer **local** LM Studio over cloud AI.  
- Prefer **127.0.0.1** for local API (Windows `localhost` IPv6 lag).  
- Sampling overrides sent in request body per job.  
- Quinfall WB/CZ jargon only when user selects that LFG content.  
- Economy never invents server-wide averages outside the screenshot.  

---

## GitHub commit narrative

### Title

```
feat: Economy snaps, help system, and raid-night companion suite (v6.2)
```

### Description

```markdown
## Summary
Ships Gamer’s Chat Helper as a full local companion: intent-driven chat generation with offline packs, Steam population trends (time-axis chart + peak/min), market screenshot pricing via LM Studio vision, simple calculator with keyboard mode, and a comprehensive Help menu + manual.

## Highlights
- **Chat Generator** — LFG/Activity/Reply/Recruit/Noise, house style, OCR grab, sticky Copy
- **Economy** — market region snap, VL/OCR price advice, re-price last shot, flip profit, WTS macros, price log
- **Steam** — concurrent players header, overnight TSV log, chart with real timestamps and extrema
- **Calculator** — basic pad, comma formatting, optional key capture
- **Power tools** — F6–F10 hotkeys, Focus mode, Oracle, session export
- **Help** — File/Help menu, full in-app manual, F1 context help, hover tooltips, HELP_MANUAL.md + FEATURES.md

## Notes
- No official Quinfall market API; Economy is screenshot-grounded only
- Default LM Studio URL uses 127.0.0.1 to avoid false “AI off” on Windows
- Config and logs live next to the app for easy backup

## How to run
1. Install deps from `requirements.txt`
2. Start LM Studio + local server (optional for offline packs)
3. Double-click `Start Gamers Chat Helper.bat`
4. Help → Full Manual for the full walkthrough
```

---

*Last updated for app version 6.2.*
