# Hyperline AI — Setup & FAQ

**Version:** 7.0  
**For:** first-time install, LM Studio, vision models, and tuning your PC  

Also in the app: **Help → Setup & FAQ (LM Studio)** · **Help → Full Manual** · **F1** (current tab).

---

## 1. What you need

| Piece | Required? | Why |
|--------|-----------|-----|
| **Windows 10/11** (or similar with Python GUI) | Yes | Desktop app |
| **Python 3.10+** | Yes | Runs `gamers_chat_helper.py` |
| **Python packages** (`requirements.txt`) | Yes | UI, clipboard, HTTP, images |
| **LM Studio** | Strongly recommended | Local AI for Write / OCR / Economy |
| **Vision-capable model** in LM Studio | For Economy + best OCR | Reads screenshots |
| **Tesseract OCR** | Optional | Faster text OCR without vision |
| **Internet** | Optional | Steam player counts only (public API) |

You can still use offline packs (LFG templates, noise, dad jokes) with **AI · off**, but generation quality and market snaps need LM Studio.

---

## 2. Install the app (one-time)

### 2.1 Python

1. Install Python 3.10+ from [python.org](https://www.python.org/downloads/) (check **Add Python to PATH**).  
2. Open a terminal in this folder:

```bat
cd /d "D:\Vibe Code Repo\Gaming Chat Helper"
python -m pip install -U pip
python -m pip install -r requirements.txt
```

### 2.2 App packages (`requirements.txt`)

| Package | Role |
|---------|------|
| `customtkinter` | Modern UI |
| `pyperclip` | Clipboard copy/paste |
| `requests` | LM Studio API + Steam player count |
| `Pillow` | Screenshots / image prep for OCR & vision |
| `pytesseract` | Optional bridge to Tesseract OCR |

### 2.3 Launch

Double-click:

```text
Start Hyperline.bat
```

Or:

```bat
python gamers_chat_helper.py
```

Config is created next to the app as `chat_helper_config.json`.

---

## 3. LM Studio — install and enable the local server

### 3.1 Install

1. Download **LM Studio**: https://lmstudio.ai/  
2. Install and open it.  
3. Go to the **Discover / Models** tab and download a model (see recommendations below).

### 3.2 Load a model

1. **My Models** → select a model → **Load**.  
2. Wait until it shows as loaded (not “loading…”).  
3. For chat-only machines, a small text model is fine.  
4. For **Economy** and best **chat grab**, load a **vision (VL)** model.

### 3.3 Start the Local Server (critical)

1. Open **Developer** (or **Local Server** / server panel — name varies by LM Studio version).  
2. Enable **Start server** / **Local Inference Server**.  
3. Default port: **1234**.  
4. Keep **OpenAI-compatible** API enabled.  
5. Leave context length reasonable (e.g. 4k–8k for small models).  

Hyperline expects:

```text
http://127.0.0.1:1234/v1/chat/completions
http://127.0.0.1:1234/v1/models
```

The app prefers **`127.0.0.1`**, not `localhost`, because Windows often tries IPv6 first and can show **AI · off** even when the server is up.

### 3.4 Confirm the app sees AI

1. Launch Hyperline.  
2. Header should show **AI · on** (green) within a few seconds.  
3. Hover **AI · on** — tooltip may show the loaded model id.  
4. If **AI · off**: see [§7 Troubleshooting](#7-troubleshooting).

---

## 4. Recommended models (local)

Pick by **VRAM** and what you need. Names below are examples; exact hub names may vary slightly in LM Studio’s catalog.

### 4.1 Best all-rounder for *this app* (chat + OCR + Economy)

| Priority | Model family | Notes |
|----------|--------------|--------|
| **Recommended** | **Qwen3-VL 2B** (Q4 / Q4_K quant) | Small VRAM, vision for market + chat grab, usable chat |
| **Stronger vision** | **Qwen2-VL / Qwen3-VL 7B–8B** (Q4) | Better reading of dense market UIs; more VRAM |
| **Chat quality** (no vision) | **Qwen2.5 7B / 14B Instruct** (Q4/Q5) | Better LFG/reply prose; Economy falls back to Tesseract + text |

**Practical default for most gaming PCs (8–12 GB VRAM):**  
→ **Qwen3-VL 2B Instruct Q4** (or similar 2B VL quant in LM Studio).

**If you only care about chat lines (no Economy snaps):**  
→ Any solid instruct model 3B–7B Q4 is fine.

### 4.2 VRAM rough guide

| VRAM | Suggestion |
|------|------------|
| **4–6 GB** | VL **2B Q4** only; lower context (2k–4k); close other GPU apps |
| **8–12 GB** | VL **2B–7B Q4**; comfortable dual-use chat + snaps |
| **16 GB+** | VL **7B–8B Q4/Q5** or separate chat 14B + switch models as needed |

Always prefer **GGUF / quant** builds (Q4_K_M, Q5_K_M) over full precision on consumer cards.

### 4.3 What this app uses the model *for*

| Feature | Needs vision? | Notes |
|---------|---------------|--------|
| LFG / Activity / Reply / Recruit | No | Text chat completions |
| Noise / Dad joke | No | Often uses local packs anyway |
| Grab chat (OCR) | Optional | Tesseract first if installed; else VL |
| Economy Snap + price | **Yes (best)** | VL reads listings; else OCR + text model |
| Steam Players chip | No model | Public Steam API only |

### 4.4 Switching models mid-session

1. In LM Studio, unload old model → load new one.  
2. Keep **Local Server** running.  
3. In Hyperline, wait for **AI · on** (or Restart app).  
4. No need to change code if the server stays on port **1234**.

---

## 5. Get tuned properly for *your* machine

### 5.1 Golden rules (read this)

1. **This app sends sampling settings per job** (temperature, top_p, max_tokens, etc.).  
   → In LM Studio, leave generation presets at **defaults**. Do not “fight” the app with extreme server-side sliders.  
2. **One model loaded** on the local server is enough.  
3. **Vision models** must actually support **image** inputs in LM Studio (VL / vision tags).  
4. **Close GPU-heavy games/overlays** while loading large models if VRAM is tight.  
5. Prefer **127.0.0.1** (already the app default).

### 5.2 LM Studio server settings (recommended baseline)

| Setting | Suggested |
|---------|-----------|
| Port | `1234` |
| CORS / OpenAI compat | On |
| GPU offload | As many layers as fit in VRAM (full offload if possible) |
| Context length | 4096 for 2B VL; 4096–8192 for 7B if VRAM allows |
| Parallel requests | 1 (this app is sequential) |

If the model thrashing/disk-swaps: lower context, use a smaller quant, or fewer GPU layers.

### 5.3 Hyperline side (no LM Studio knobs needed)

| Area | How to tune |
|------|-------------|
| **Tone** | Advanced Tweaks → Mood + Heat |
| **LFG content** | Content / Location / Party Finder / Need |
| **House style** | Setup → per-game notes (guild name, never-say list) |
| **Noise chaos** | Noise slider (Sane → Mental) |
| **Economy undercut** | Economy tab % under lowest clear comp |
| **Type size** | A− / A+ or Setup type scale |

### 5.4 Economy / OCR quality checklist

1. Load a **VL** model.  
2. Economy → **Set market area** → tight crop on the **price list**, not the whole UI.  
3. Type **My item** if the list is busy.  
4. **Snap + price**; if wrong, **Re-price last shot** after adjusting crop/name.  
5. Optional: install **Tesseract** for faster text OCR when VL is busy:

   - Windows installer: https://github.com/UB-Mannheim/tesseract/wiki  
   - App auto-searches common install paths.  
   - `pip install pytesseract` is already in `requirements.txt`.

### 5.5 Dual-model workflow (advanced)

If you have VRAM for one model at a time:

| Session | Load |
|---------|------|
| Pure chat night | Instruct 7B (no vision) |
| Market flip night | Qwen3-VL 2B/7B |

Swap in LM Studio; keep server on. Hyperline does not need a config change.

### 5.6 Optional: custom API URL

Default in config:

```json
"api_url": "http://127.0.0.1:1234/v1/chat/completions"
```

If LM Studio uses another port (e.g. 1235), edit `chat_helper_config.json` while the app is closed, or ask for a Setup field later. Always use `127.0.0.1` on Windows when possible.

---

## 6. First-run checklist

- [ ] `pip install -r requirements.txt`  
- [ ] LM Studio installed  
- [ ] Model downloaded + **loaded**  
- [ ] Local Server **started** on port 1234  
- [ ] Hyperline shows **AI · on**  
- [ ] Write an LFG → Copy works under char limit  
- [ ] (Optional) Tesseract installed for chat grab  
- [ ] (Optional) VL model loaded → Economy Set market area → Snap + price  
- [ ] Help → Full Manual skimmed once  

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| **AI · off** but LM Studio open | Start **Local Server**; load a model; use port **1234**; restart Hyperline |
| AI · off, server running | Prefer `127.0.0.1` not `localhost`; firewall allow LM Studio; only one process on 1234 |
| Write returns offline pack | Same as above; hover AI chip for last probe detail |
| Economy empty / nonsense | Load **vision** model; tighter market crop; fill **My item**; try Re-price last shot |
| OCR empty on chat grab | Recalibrate region; install Tesseract **or** load VL model |
| Out of memory / crash in LM Studio | Smaller quant (Q4), 2B VL, lower context, fewer GPU layers |
| Slow generations | Smaller model; full GPU offload; close browser GPU tabs |
| Copy blocked | Line over game limit — use Trim / Shorter |
| Steam Players n/a | Game has no Steam AppID in profile (e.g. some titles) |
| Restart doesn’t show new UI | Fully quit old window; run `.bat` again; title should show **v6.3+** |

### Quick server test (optional)

In PowerShell:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:1234/v1/models" -UseBasicParsing
```

Expect **200** and JSON with a `data` list of models.

---

## 8. FAQ (short)

**Q: Do I need an OpenAI / cloud API key?**  
A: No. Everything AI is local via LM Studio unless you change the URL yourself.

**Q: Does sampling in LM Studio matter?**  
A: This app **overrides** sampling per job in the request body. Leave LM Studio defaults.

**Q: Why 127.0.0.1 not localhost?**  
A: On Windows, `localhost` can hang on IPv6 (`::1`) and fake “offline.”

**Q: Is there a Quinfall market API?**  
A: Not a public one we ship against. Economy uses **screenshots + vision/OCR**.

**Q: Can I use the app offline (no net)?**  
A: Yes for chat/calculator/local AI. Steam player counts need net. LM Studio models must already be downloaded.

**Q: Where are settings and logs?**  
A: Next to the app — see Help Manual § Files.

**Q: Recommended single model if I only download one?**  
A: **Qwen3-VL 2B Instruct (Q4)** — balances chat, chat-OCR, and market snaps on modest VRAM.

---

## 9. Related docs in this folder

| File | Contents |
|------|----------|
| `SETUP_AND_FAQ.md` | **This file** — install + LM Studio + tuning |
| `HELP_MANUAL.md` | Full product manual (tabs, hotkeys, features) |
| `FEATURES.md` | Feature inventory + design notes |
| `COMMIT_MESSAGE.md` | Suggested GitHub commit title/body |
| `requirements.txt` | Python dependencies |
| `Start Hyperline.bat` | Launcher |

In the app: **Help → Setup & FAQ (LM Studio)** · **Help → Full Manual** · **Help → Open SETUP_AND_FAQ.md**.

---

*Hyperline AI — local companion. Not affiliated with LM Studio, Steam, or game publishers.*
