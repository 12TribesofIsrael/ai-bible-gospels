# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI Movie — a personal workspace for building AI-generated video systems. Contains two workflows:

| Workflow | Location | Status | Description |
|---|---|---|---|
| **General AI Movie** | root (`app.py`, `pipeline.py`, `src/`) | Reference | Python/Gradio pipeline: text prompt → images → video clips → narrated movie via fal.ai + OpenAI |
| **Biblical Cinematic** | `workflows/biblical-cinematic/` | ✓ Production (v7.2) | KJV scripture → cleaned text → n8n Perplexity + ElevenLabs + JSON2Video → 8–13 min MP4 |
| **Custom Script** | `workflows/custom-script/` | ✓ Production | Any script/concept → Claude AI scenes → FLUX + Kling + JSON2Video → dynamic-length MP4 |

---

## Workflow 1: General AI Movie Pipeline

### Stack
- Python 3.11+, **Gradio** (UI), **OpenAI** (GPT-4o + TTS), **fal.ai** (FLUX + Kling), **FFmpeg**

### Pipeline
```
Script text
  → GPT-4o          parse into Scene objects     (src/features/script_parser/)
  → FLUX/fal.ai     generate image per scene     (src/features/image_gen/)
  → Kling/fal.ai    animate image to video clip  (src/features/video_gen/)
  → OpenAI TTS      generate narration audio     (src/features/audio_gen/)
  → FFmpeg          assemble final movie.mp4     (src/features/assembler/)
```

Each run saves to `output/<run-id>/`.

### Setup
```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env         # fill in OPENAI_API_KEY and FAL_KEY
# Also install FFmpeg and add to PATH: https://ffmpeg.org/download.html
```

### Commands
```bash
python app.py                          # Gradio UI at http://localhost:7860
python pipeline.py path/to/script.txt  # CLI mode
pytest tests/
```

### Key Files
| File | Purpose |
|---|---|
| [app.py](app.py) | Gradio UI entry point |
| [pipeline.py](pipeline.py) | Full pipeline orchestrator |
| [src/features/script_parser/models.py](src/features/script_parser/models.py) | `Scene` + `Script` dataclasses |
| [src/features/script_parser/parser.py](src/features/script_parser/parser.py) | GPT-4o scene breakdown |
| [src/features/image_gen/generator.py](src/features/image_gen/generator.py) | FLUX image generation |
| [src/features/video_gen/generator.py](src/features/video_gen/generator.py) | Kling image-to-video (reference for v7 HTTP call patterns) |
| [src/features/audio_gen/generator.py](src/features/audio_gen/generator.py) | OpenAI TTS narration |
| [src/features/assembler/assembler.py](src/features/assembler/assembler.py) | FFmpeg stitching |
| [src/shared/config.py](src/shared/config.py) | Settings from `.env` |

---

## Workflow 2: Biblical Cinematic (Web App + n8n)

### Stack
- **FastAPI** (web server + API), **Python** (text processing), **n8n** (video pipeline orchestration)
- **Perplexity AI** (scene gen), **fal.ai** (FLUX + Kling), **ElevenLabs** (voice), **JSON2Video** (assembly)

### Full Pipeline (v8.0)
```
Browser (http://localhost:8000)
  → POST /api/clean    FastAPI server runs text processor → returns cleaned sections
  → POST /api/generate FastAPI POSTs to n8n webhook
      → n8n workflow:
          → Perplexity sonar-pro    → 20 cinematic scene descriptions
          → fal.ai FLUX Pro         → generate image per scene
          → fal.ai Kling v1.6       → animate each image to 5s video clip
          → ElevenLabs              → narration audio (214 WPM)
          → JSON2Video              → assembles video clips into final MP4
  → GET  /api/status   Browser polls every 6s → real-time progress bar
  → Final MP4 (8–13 min) with Download button
```

**Cost:** ~$4.51/video (Kling Standard) | **Time:** ~15-25 min | **Version:** v8.0 (testing)

### Start the web app
```bash
cd workflows/biblical-cinematic/server
pip install -r requirements.txt   # first time only
python app.py
# Opens at http://localhost:8000
```

### How to use
1. Go to **http://localhost:8000**
2. Paste KJV scripture → **Convert & Clean**
3. Review/edit the cleaned text → **Approve & Generate Video**
4. Live progress bar tracks Perplexity → ElevenLabs → JSON2Video in real time
5. Download the raw MP4 when done → drop it into `output/raw/`
6. Scroll to **Step 4 — Post-Production** → click **↺ Refresh** → click **▶ Start Rendering**
7. Progress bar tracks normalize → concat → logo overlay → **Download Final Video**

### n8n setup notes
- The n8n workflow must be **Published/Active** for the production webhook to fire
- The `Bible Chapter Text Input` Set node must have field NAME=`inputText`, VALUE=`{{ $json.body.text }}` (expression mode ON for value, not name)
- `find_dotenv()` is used (not manual path) to locate `.env` — walks up from `server/app.py`
- Server runs with `reload=False` — if you edit app.py, restart the server manually
- **Kill stale servers on Windows:** `taskkill` is unreliable for orphaned processes; use PowerShell:
  `Stop-Process -Id <pid> -Force` or kill all python: `Get-Process python | Stop-Process -Force`
- **Duplicate `.env` keys:** `python-dotenv` uses the **first** occurrence. If a key appears twice, the placeholder wins. Always edit the existing line rather than appending a new one.

### Key Files
| File | Purpose |
|---|---|
| [workflows/biblical-cinematic/README.md](workflows/biblical-cinematic/README.md) | Complete setup guide |
| [workflows/biblical-cinematic/ERRORS.md](workflows/biblical-cinematic/ERRORS.md) | Running log of bugs and root-cause fixes — check before debugging |
| [workflows/biblical-cinematic/server/app.py](workflows/biblical-cinematic/server/app.py) | FastAPI server — `/api/clean`, `/api/generate`, `/api/status`, `/api/render/*` (Step 4), `/api/upload/*` (Step 5 YouTube) |
| [workflows/biblical-cinematic/server/requirements.txt](workflows/biblical-cinematic/server/requirements.txt) | Server dependencies |
| [workflows/biblical-cinematic/text_processor/biblical_text_processor_v2.py](workflows/biblical-cinematic/text_processor/biblical_text_processor_v2.py) | KJV text cleaner/splitter (imported by server) |
| [workflows/biblical-cinematic/n8n/v7.2-production.json](workflows/biblical-cinematic/n8n/v7.2-production.json) | **Current production workflow** — Import into n8n (v7.2: field-name-anchored JSON extraction, proven stable) |
| [workflows/biblical-cinematic/n8n/v8.0-kling.json](workflows/biblical-cinematic/n8n/v8.0-kling.json) | **v8.0 Kling workflow** — FLUX + Kling AI video motion (testing) |
| [workflows/biblical-cinematic/templates/v7-ken-burns.json](workflows/biblical-cinematic/templates/v7-ken-burns.json) | v7.2 production template — 20 scenes, Ken Burns, proven working baseline |
| [workflows/biblical-cinematic/templates/v8-kling.json](workflows/biblical-cinematic/templates/v8-kling.json) | **v8.0 Kling template** — 20 scenes with video elements (testing) |
| [workflows/biblical-cinematic/scripts/post_produce.py](workflows/biblical-cinematic/scripts/post_produce.py) | FFmpeg post-production — concat intro/outro, overlay logo, mix music |
| [workflows/biblical-cinematic/scripts/batch_post_produce.py](workflows/biblical-cinematic/scripts/batch_post_produce.py) | Batch mode — process all videos in output/raw/ at once |
| [workflows/biblical-cinematic/scripts/upload_youtube.py](workflows/biblical-cinematic/scripts/upload_youtube.py) | YouTube uploader — OAuth2, auto-generates title/description/thumbnail, uploads as unlisted |
| [workflows/biblical-cinematic/assets/](workflows/biblical-cinematic/assets/) | Drop-in folder for logo.png, intro.mp4, outro.mp4, music/ |

### Post-Production (Step 4 in web app — preferred)
Drop raw MP4 into `output/raw/`, then use the **Step 4** panel at http://localhost:8000 — click ↺ Refresh, then ▶ Start Rendering. Progress bar tracks all FFmpeg stages. Download button appears when done.

**CLI fallback (terminal):**
```bash
# Single video:
python workflows/biblical-cinematic/scripts/post_produce.py output/raw/video.mp4

# Batch — all videos in output/raw/:
python workflows/biblical-cinematic/scripts/batch_post_produce.py
```
Options: `--width 3840` (for 4K, default 1920)

### YouTube Upload (Step 5 in web app — preferred)
Select a final video from the **Step 5** panel at http://localhost:8000, enter the scripture reference (e.g. "Genesis 1"), click **Upload to YouTube**. Progress bar tracks upload + thumbnail. Done panel shows YouTube URL + Studio edit link.

**CLI fallback (terminal):**
```bash
python workflows/biblical-cinematic/scripts/upload_youtube.py output/video_final.mp4 "Genesis 1"
```
- First run: browser opens for Google OAuth2 → token saved to `scripts/.youtube_token.json`
- Subsequent runs: no browser needed
- Uploads as **unlisted** — go to YouTube Studio to review and publish
- Requires `client_secrets.json` in `workflows/biblical-cinematic/scripts/` (one-time Google Cloud setup)
- Optional: `--no-thumbnail` to skip thumbnail generation

---

## Workflow 2b: Biblical Cinematic UI (React Frontend)

An alternative standalone frontend at `workflows/biblical-cinematic/ui/`. React 18 + TypeScript + Vite + Tailwind. Posts directly to the n8n webhook (bypasses the FastAPI server). Currently scaffolded via Bolt — `src/` components are defined in the README but may need to be generated.

### Commands
```bash
cd workflows/biblical-cinematic/ui
npm install        # first time only
npm run dev        # dev server (default Vite port)
npm run build      # production build → dist/
npm run lint       # ESLint
```

### Key Files
| File | Purpose |
|---|---|
| [workflows/biblical-cinematic/ui/README.md](workflows/biblical-cinematic/ui/README.md) | Component architecture + API integration guide |
| [workflows/biblical-cinematic/ui/MVP_INTEGRATION_GUIDE.md](workflows/biblical-cinematic/ui/MVP_INTEGRATION_GUIDE.md) | How this UI connects to n8n and the FastAPI server |
| [workflows/biblical-cinematic/ui/vite.config.ts](workflows/biblical-cinematic/ui/vite.config.ts) | Vite config |

---

## v7 Workflow (Current Production — v7.2)

**Status:** ✓ Stable | **Cost:** ~$1.32/video | **Time:** 8–13 min

### Key Features
- **20 cinematic scenes** with variable Ken Burns motion (zoom-in, zoom-out, ken-burns, pan-right, pan-left)
- **Bulletproof JSON parsing** — field-name-anchored extraction immune to Perplexity's unescaped quotes (100% reliable)
- **ElevenLabs narration** — 214 WPM, professional voice (NgBYGKDDq2Z8Hnhatgma)
- **JSON2Video rendering** — HD 1920×1080 with Ken Burns effects

### Files
- **Workflow:** `n8n/v7.2-production.json` (current production)
- **Template:** `templates/v7-ken-burns.json` (proven working baseline, 20 scenes, no title card)
- **Legacy backups:** `backups/workflows/v6.0.2-master_2026-03-08.json` (reference only)

### Critical Notes

**Perplexity JSON parsing:** Perplexity sonar-pro returns unescaped `"` inside string values (e.g., `"the "Pharisees" confronted"`). The solution uses field-name-anchored extraction: `indexOf('"fieldName"')` as structural boundaries, since field names never appear in biblical text or image prompts. This is 100% reliable and immune to Perplexity output variations. See `ERRORS.md` 2026-03-07 for full root cause analysis.

**n8n workflow:** `pan: ""` empty strings are invalid for JSON2Video. For zoom-in/zoom-out scenes, the workflow now sends `pan: "right"` and `pan: "left"` with minimal distance (0.05) instead.

### Phase 2 (Future)
See **[docs/v7-upgrade-plan.md](docs/v7-upgrade-plan.md)** for v8.0 spec: Kling AI video motion (~$7.31/video, ~35–45 min render time).

---

## Workflow 3: Custom Script Pipeline

### Stack
- **Python** (FastAPI web UI + CLI), **Claude AI** (scene generation), **fal.ai** (FLUX + Kling), **ElevenLabs** (via JSON2Video), **JSON2Video** (assembly)

### Full Pipeline
```
Browser (http://localhost:8500) or CLI
  → Paste script/concept
  → Claude AI           → N cinematic scenes (dynamic count)
  → fal.ai FLUX Pro     → generate image per scene
  → fal.ai Kling v3     → animate each image to 15s video clip
  → JSON2Video          → templateless inline payload → ElevenLabs narration + subtitles → final MP4
```

**No n8n required.** No template ID. Payload built dynamically in code.

### Start the web app
```bash
python workflows/custom-script/server.py
# Opens at http://localhost:8500
```

### CLI usage
```bash
python workflows/custom-script/generate.py script.txt              # full pipeline
python workflows/custom-script/generate.py script.txt --scenes-only # preview scenes only
python workflows/custom-script/generate.py script.txt --post-produce # with intro/outro
```

### Recovery (if pipeline fails mid-generation)
```bash
python workflows/custom-script/recover.py  # recovers completed videos from fal.ai history
```

### Key Files
| File | Purpose |
|---|---|
| [workflows/custom-script/server.py](workflows/custom-script/server.py) | FastAPI web UI — paste script, edit scenes, generate video, real-time progress (port 8500) |
| [workflows/custom-script/generate.py](workflows/custom-script/generate.py) | CLI pipeline — script → Claude scenes → FLUX → Kling → JSON2Video |
| [workflows/custom-script/recover.py](workflows/custom-script/recover.py) | Recovery — fetches completed Kling videos from fal.ai history API, regenerates only missing scenes |
| [workflows/custom-script/example-trailer.txt](workflows/custom-script/example-trailer.txt) | Example input — channel trailer script |
| [workflows/custom-script/README.md](workflows/custom-script/README.md) | Complete usage guide |

### Important Notes
- **Never put text in FLUX image prompts** — AI misspells words. Use subtitles for all on-screen text.
- **Subtitles use transcription mode** — exact narration text provided, not auto-detected from audio. Ensures correct biblical name spelling.
- **Single-scene re-generation** — fix one scene without re-doing the whole video (~$1.50 JSON2Video render only).
- **Retry button** in web UI picks up from failed scene without re-generating completed scenes.

---

## Environment Variables

See [.env.example](.env.example) for all keys. The `.env` file lives at the workspace root.

| Variable | Used By |
|---|---|
| `OPENAI_API_KEY` | General pipeline (GPT-4o + TTS) |
| `FAL_KEY` | General pipeline (FLUX + Kling); **required in n8n env vars for v8.0** (FLUX image gen + Kling video) |
| `N8N_WEBHOOK_URL` | Biblical web app → triggers n8n workflow |
| `PERPLEXITY_API_KEY` | Reference only (configured inside n8n) |
| `ELEVENLABS_API_KEY` | Reference only (configured inside n8n) |
| `JSON2VIDEO_API_KEY` | Biblical server `/api/status` + Custom Script pipeline — polls render progress + provides download URL |
| `ANTHROPIC_API_KEY` | Custom Script pipeline — Claude AI scene generation |

The biblical server uses `find_dotenv()` to locate `.env` by walking up the directory tree from `server/app.py`.

---

## Documentation Update Rules

These run **automatically** at the end of every session where code changed.

### Always update when:
| Change made | Files to update |
|---|---|
| New endpoint, script, or key file added | `CLAUDE.md` Key Files table + workflow `README.md` |
| New env var added or fixed | `CLAUDE.md` env table + `.env` comment |
| How-to-use steps changed | workflow `README.md` Quick Start |
| Windows/server behavior discovered | `CLAUDE.md` setup notes + `MEMORY.md` |
| Bug fixed with a non-obvious root cause | `ERRORS.md` + `MEMORY.md` |

### Never update for:
- Internal logic changes that don't affect usage
- Bug fixes where behavior is unchanged from the user's perspective
- Style or comment tweaks

### Session-end checklist (Claude runs this automatically):
1. Did any **endpoints, scripts, or key files** change? → update Key Files tables
2. Did any **env vars** change? → update env table + `.env` comments
3. Did any **run commands or usage steps** change? → update READMEs
4. Did we discover a **Windows/server quirk**? → add to `ERRORS.md` + `MEMORY.md`
5. Update `MEMORY.md` with anything that should persist across sessions
