# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI Movie — a personal workspace for building AI-generated video systems. Contains three workflows, with the two production workflows merged into a single unified web app:

| Workflow | Location | Status | Description |
|---|---|---|---|
| **General AI Movie** | root (`app.py`, `pipeline.py`, `src/`) | Reference | Python/Gradio pipeline: text prompt → images → video clips → narrated movie via fal.ai + OpenAI |
| **Biblical Cinematic** | `workflows/biblical-cinematic/` | ✓ Production (v12) | KJV scripture → cleaned text → Claude AI scenes → FLUX + Kling + JSON2Video → cinematic MP4 |
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

### Full Pipeline (v12 — no n8n)
```
Browser (http://localhost:8000)
  → POST /api/clean               FastAPI server runs text processor → returns cleaned sections
  → POST /v9/api/generate-scenes  Splits scripture → Claude AI generates scenes (image prompts, motion, lighting)
  → User reviews & edits scenes in the browser (narration, imagePrompt, motion, lighting)
  → POST /v9/api/generate-video   Takes edited scenes → kicks off FLUX + Kling + JSON2Video pipeline
      → Python pipeline (background thread):
          → fal.ai FLUX Pro         → generate image per scene
          → fal.ai Kling v1.6/v2.1/v3.0/v3.0-pro/o3/o3-pro → animate each image to video clip
          → JSON2Video              → templateless payload with ElevenLabs narration + subtitles → final MP4
          → Auto-split              → chapters over 900 words split into 2 renders automatically
  → GET  /v9/api/status            Browser polls every 2s → real per-scene progress bar
  → POST /v9/api/retry             Resume from failed scene (state persisted to Modal Volume)
  → POST /v9/api/fix-scene         Regenerate one scene without redoing the whole video
  → POST /v9/api/fix-scenes        Batch-fix multiple scenes with ONE JSON2Video render
  → POST /v9/api/stop              Stop pipeline mid-render to save credits
  → GET  /v9/api/history           Browse past renders (persisted to JSON file)
  → GET  /v9/api/history/{id}      Full scene data for a past render
  → Final MP4 with Download button (Part 1 / Part 2 if auto-split)
```

**No n8n required.** Narration is the scripture text word-for-word. Claude only generates image prompts, motion, and lighting.

**Cost:** ~$4.50–7.00/video depending on Kling model | **Version:** v12

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
3. Review/edit the cleaned text → **Generate Scenes** (Claude AI only — no credits spent yet)
4. **Review & Edit Scenes** — edit narration, image prompts, motion, lighting for each scene. Add/remove scenes.
5. Click **Generate Video →** to start FLUX + Kling + JSON2Video pipeline
6. Live progress bar tracks scene-by-scene progress in real time
7. Use **⏹ Stop Rendering** to cancel mid-render and save credits (completed scenes preserved)
8. Use **Retry** to resume from where it stopped (state persisted across container restarts)
9. Use **Fix Scenes** panel: check multiple scenes, edit prompts inline, regenerate all with ONE render
10. Download the raw MP4 when done (auto-split into Part 1/Part 2 for long chapters)
11. Browse **Render History** panel to view past renders or reload scenes into the fix panel
12. Scroll to **Step 4 — Post-Production** → click **↺ Refresh** → click **▶ Start Rendering**
13. Progress bar tracks normalize → concat → logo overlay → **Download Final Video**

### n8n setup notes
- The n8n workflow must be **Published/Active** for the production webhook to fire
- The `Bible Chapter Text Input` Set node must have field NAME=`inputText`, VALUE=`{{ $json.body.text }}` (expression mode ON for value, not name)
- `find_dotenv()` is used (not manual path) to locate `.env` — walks up from `server/app.py`
- Server runs with `reload=False` — if you edit app.py, restart the server manually
- **Kill stale servers on Windows:** `taskkill` is unreliable for orphaned processes; use PowerShell:
  `Stop-Process -Id <pid> -Force` or kill all python: `Get-Process python | Stop-Process -Force`
- **Duplicate `.env` keys:** `python-dotenv` uses the **first** occurrence. If a key appears twice, the placeholder wins. Always edit the existing line rather than appending a new one.

### Recovery (if container restarts mid-render)
Pipeline state is persisted to a Modal Volume (`/data/pipeline_state.json`). On restart, the Retry button resumes from the last completed scene. If state is lost, **recover Kling video URLs from fal.ai history**:
```python
import fal_client, requests, os
os.environ['FAL_KEY'] = '<key>'
# 1. Get request IDs from fal.ai history API
resp = requests.get('https://api.fal.ai/v1/models/requests/by-endpoint',
    headers={'Authorization': 'Key <FAL_KEY>'},
    params={'endpoint_id': 'fal-ai/kling-video/v3/standard/image-to-video', 'limit': 40, 'status': 'success'})
items = sorted(resp.json()['items'], key=lambda x: x['started_at'])
# 2. Fetch video URLs using fal_client SDK (history API doesn't return payloads reliably)
for item in items:
    result = fal_client.result('fal-ai/kling-video/v3/standard/image-to-video', item['request_id'])
    print(result['video']['url'])
# 3. Re-generate narration with Claude, pair with recovered URLs, submit to JSON2Video
```
**IMPORTANT:** The fal.ai history API `expand=payloads` does NOT reliably return `json_output` for older requests. Always use `fal_client.result()` to fetch individual request results — this works reliably.

### Key Files
| File | Purpose |
|---|---|
| [workflows/biblical-cinematic/README.md](workflows/biblical-cinematic/README.md) | Complete setup guide |
| [workflows/biblical-cinematic/ERRORS.md](workflows/biblical-cinematic/ERRORS.md) | Running log of bugs and root-cause fixes — check before debugging |
| [workflows/biblical-cinematic/server/app.py](workflows/biblical-cinematic/server/app.py) | FastAPI server — `/api/clean`, `/api/render/*` (Step 4), `/api/upload/*` (Step 5), mounts v9 router at `/v9` + custom router at `/custom` |
| [workflows/biblical-cinematic/server/biblical_pipeline.py](workflows/biblical-cinematic/server/biblical_pipeline.py) | v12 pipeline router — `/v9/api/generate-scenes`, `/v9/api/generate-video`, `/v9/api/status`, `/v9/api/retry`, `/v9/api/fix-scene`, `/v9/api/fix-scenes`, `/v9/api/stop`, `/v9/api/history` (no n8n) |
| [workflows/biblical-cinematic/server/rate_limit.py](workflows/biblical-cinematic/server/rate_limit.py) | Shared `slowapi` Limiter — 5/hour on render endpoints, 30/hour on Claude-only endpoints. IP from `X-Forwarded-For` (Modal proxy). Imported by app.py, biblical_pipeline.py, custom-script/router.py |
| [workflows/biblical-cinematic/server/usage.py](workflows/biblical-cinematic/server/usage.py) | Usage tracking — one event per money-spending API hit. Dual-writes to `/data/usage_log.json` (fallback) and Supabase `usage_events` table. Read via `GET /admin/usage`. |
| [workflows/biblical-cinematic/server/db.py](workflows/biblical-cinematic/server/db.py) | Supabase client singleton + helpers. Gated by `SUPABASE_URL` + `SUPABASE_SECRET_KEY` — if either is missing, `is_enabled()` returns False and all DB calls become no-ops so the app runs identically to pre-Supabase state. Never raises. |
| [docs/supabase_schema.sql](docs/supabase_schema.sql) | Idempotent SQL for initial schema — `profiles`, `renders`, `usage_events`. Paste into Supabase SQL Editor once per project. |
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
| `APP_USERNAME` | Modal deployment — Basic Auth username (optional, local dev skips auth) |
| `APP_PASSWORD` | Modal deployment — Basic Auth password (optional, local dev skips auth) |
| `SUPABASE_URL` | Supabase project URL — `db.py` uses this + `SUPABASE_SECRET_KEY` to init the client. If unset, app falls back to JSON-only logging. |
| `SUPABASE_SECRET_KEY` | Supabase server-side key (`sb_secret_...`). Required for DB writes. Never ship to browser. |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase client-side key (`sb_publishable_...`). Used later for browser auth UI. |
| `SUPABASE_DB_URL` | Direct Postgres connection string. Only used for admin/migration scripts, not the app. |

The biblical server uses `find_dotenv()` to locate `.env` by walking up the directory tree from `server/app.py`.

---

## Modal Deployment (v11)

The unified web app is deployed to **Modal.com** with Basic Auth protection.

**Live URL:** `https://tribesofisrael--ai-bible-gospels-web.modal.run`
- Scripture Mode: `/`
- Custom Script Mode: `/custom/`

### Deploy
```bash
modal deploy modal_app.py
```

### Setup
1. Create a Modal secret named `ai-bible-gospels` with: `FAL_KEY`, `JSON2VIDEO_API_KEY`, `ANTHROPIC_API_KEY`, `APP_USERNAME`, `APP_PASSWORD`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_DB_URL`
2. Run `modal deploy modal_app.py`

### Key Files
| File | Purpose |
|---|---|
| [modal_app.py](modal_app.py) | Modal deployment entry point — mounts project dirs, serves FastAPI via `@modal.asgi_app()` |

### Notes
- Auth middleware only activates when `APP_USERNAME` + `APP_PASSWORD` are set (skipped in local dev)
- Step 4 (post-production) and Step 5 (YouTube upload) are local-only — they require FFmpeg and filesystem access
- Container stays warm for 5 minutes (`scaledown_window=300`), timeout 30 minutes (`timeout=1800`)
- Pipeline state persisted to Modal Volume (`ai-bible-gospels-data`) at `/data/pipeline_state.json` — survives container restarts
- Redeploy updates code but warm containers keep old code — run `modal app stop ai-bible-gospels` before `modal deploy` to force refresh

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
