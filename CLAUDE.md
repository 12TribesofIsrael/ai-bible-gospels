# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI Movie — a personal workspace for building AI-generated video systems. Contains three workflows, with the two production workflows merged into a single unified web app:

| Workflow | Location | Status | Description |
|---|---|---|---|
| **General AI Movie** | root (`app.py`, `pipeline.py`, `src/`) | Reference | Python/Gradio pipeline: text prompt → images → video clips → narrated movie via fal.ai + OpenAI |
| **Biblical Cinematic** | `workflows/biblical-cinematic/` | ✓ Production (v10) | KJV scripture → cleaned text → Claude AI scenes → FLUX + Kling + JSON2Video → cinematic MP4 |
| **Custom Script** | `workflows/custom-script/` | ✓ Production | Any script/concept → Claude AI scenes → FLUX + Kling + JSON2Video → dynamic-length MP4 |

**Unified Web App:** Both production workflows run on a single server at **http://localhost:8000** with tab navigation:
- **Scripture Mode** (`/`) — Biblical Cinematic pipeline
- **Custom Script Mode** (`/custom`) — Custom Script pipeline

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

### Full Pipeline (v10 — no n8n)
```
Browser (http://localhost:8000)
  → POST /api/clean          FastAPI server runs text processor → returns cleaned sections
  → POST /v9/api/generate    Splits scripture into scene chunks → Claude AI generates image prompts
      → Python pipeline (background thread):
          → fal.ai FLUX Pro         → generate image per scene
          → fal.ai Kling v1.6/v2.1/v3.0 → animate each image to video clip
          → JSON2Video              → templateless payload with ElevenLabs narration + subtitles → final MP4
  → GET  /v9/api/status      Browser polls every 2s → real per-scene progress bar
  → POST /v9/api/retry       Resume from failed scene
  → POST /v9/api/fix-scene   Regenerate one scene without redoing the whole video
  → POST /v9/api/fix-scenes  Batch-fix multiple scenes with ONE JSON2Video render
  → POST /v9/api/stop        Stop pipeline mid-render to save credits
  → GET  /v9/api/history     Browse past renders (persisted to JSON file)
  → GET  /v9/api/history/{id} Full scene data for a past render
  → Final MP4 with Download button
```

**No n8n required.** Narration is the scripture text word-for-word. Claude only generates image prompts, motion, and lighting.

**Cost:** ~$4.50–7.00/video depending on Kling model | **Version:** v10

### Start the unified web app
```bash
cd workflows/biblical-cinematic/server
pip install -r requirements.txt   # first time only
python app.py
# Opens at http://localhost:8000
# Scripture Mode at /  |  Custom Script Mode at /custom
```

### How to use
1. Go to **http://localhost:8000** (use nav tabs to switch between Scripture Mode and Custom Script Mode)
2. Paste KJV scripture → **Convert & Clean**
3. Review/edit the cleaned text → **Approve & Generate Video**
4. Live progress bar tracks Claude AI → FLUX → Kling → JSON2Video in real time
5. Use **⏹ Stop Rendering** to cancel mid-render and save credits (completed scenes preserved)
6. Use **Fix Scenes** panel: check multiple scenes, edit prompts inline, regenerate all with ONE render
7. Download the raw MP4 when done → drop it into `output/raw/`
8. Browse **Render History** panel to view past renders or reload scenes into the fix panel
9. Scroll to **Step 4 — Post-Production** → click **↺ Refresh** → click **▶ Start Rendering**
10. Progress bar tracks normalize → concat → logo overlay → **Download Final Video**

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
| [workflows/biblical-cinematic/server/app.py](workflows/biblical-cinematic/server/app.py) | FastAPI server — `/api/clean`, `/api/render/*` (Step 4), `/api/upload/*` (Step 5), mounts v9 router at `/v9` + custom router at `/custom` |
| [workflows/biblical-cinematic/server/biblical_pipeline.py](workflows/biblical-cinematic/server/biblical_pipeline.py) | v10 pipeline router — `/v9/api/generate`, `/v9/api/status`, `/v9/api/retry`, `/v9/api/fix-scene`, `/v9/api/fix-scenes`, `/v9/api/stop`, `/v9/api/history` (no n8n) |
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
Browser (http://localhost:8000/custom) or CLI
  → Paste script/concept
  → Claude AI           → N cinematic scenes (dynamic count)
  → fal.ai FLUX Pro     → generate image per scene
  → fal.ai Kling v3     → animate each image to 15s video clip
  → JSON2Video          → templateless inline payload → ElevenLabs narration + subtitles → final MP4
  → Fix Scenes          → preview (FLUX+Kling only) or batch fix + ONE re-render
```

**No n8n required.** No template ID. Payload built dynamically in code.

### API Routes
```
POST /custom/api/generate-scenes   — Claude AI generates scenes from script
POST /custom/api/generate-video    — Start full pipeline (FLUX → Kling → JSON2Video)
POST /custom/api/retry             — Resume from failed scene
POST /custom/api/fix-scene         — Fix single scene + re-render
POST /custom/api/fix-scenes        — Batch fix multiple scenes + ONE re-render
POST /custom/api/preview-scenes    — Preview fixes (FLUX + Kling only, no render)
POST /custom/api/approve-fixes     — Render after preview approval
POST /custom/api/stop              — Stop pipeline mid-render
GET  /custom/api/status            — Poll pipeline progress
GET  /custom/api/history           — Browse past renders
GET  /custom/api/history/{id}      — Full scene data for a past render
```

### Web App (merged into unified server)
The custom script UI is available at **http://localhost:8000/custom** — part of the unified server.
Start with `python workflows/biblical-cinematic/server/app.py`.

**Standalone server (legacy):**
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
| [workflows/custom-script/router.py](workflows/custom-script/router.py) | FastAPI APIRouter — mounted in main app.py at `/custom`, all API routes + HTML UI (preview-first batch fix, stop, history) |
| [workflows/custom-script/server.py](workflows/custom-script/server.py) | Standalone FastAPI web UI (legacy, port 8500) — use the unified server instead |
| [workflows/custom-script/generate.py](workflows/custom-script/generate.py) | CLI pipeline — script → Claude scenes → FLUX → Kling → JSON2Video |
| [workflows/custom-script/recover.py](workflows/custom-script/recover.py) | Recovery — fetches completed Kling videos from fal.ai history API, regenerates only missing scenes |
| [workflows/custom-script/example-trailer.txt](workflows/custom-script/example-trailer.txt) | Example input — channel trailer script |
| [workflows/custom-script/README.md](workflows/custom-script/README.md) | Complete usage guide |

### Features (matching Biblical mode)
- **Preview-first batch fix** — check multiple scenes, edit prompts inline, preview FLUX+Kling (~$0.69/scene) before committing to render (~$1.50)
- **Batch fix (skip preview)** — regenerate + render in one shot for users who don't need preview
- **Stop rendering** — cancel mid-render to save credits; completed scenes preserved for retry
- **Render history** — persisted to `custom_render_history.json`, browse past renders, reload into fix panel
- **Movie-level subtitles** — yellow word-by-word captions via JSON2Video `model: "default"`
- **Retry button** — picks up from failed scene without re-generating completed scenes

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
