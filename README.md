# AI Bible Gospels

A personal AI video production platform. Paste in text — scripture or any script — and get back a fully produced, narrated cinematic video.

Two production workflows run on a **unified web app** at http://localhost:8000:

| Workflow | Status | What it does |
|---|---|---|
| **Biblical Cinematic** (Scripture Mode) | Production (v13) | KJV scripture → Claude AI scenes → FLUX + Kling + JSON2Video → cinematic MP4 (16:9 YouTube / 1:1 Feed / 9:16 Shorts) |
| **Custom Script** (Custom Script Mode) | Production | Any script/concept → Claude AI scenes → dynamic-length cinematic video (16:9 / 1:1 / 9:16) with preview-first batch fix |
| **General AI Movie** | Reference | Script → GPT-4o → FLUX → Kling → OpenAI TTS → FFmpeg assembled movie |

### Quick Start
```bash
# Install (first time only)
cd workflows/biblical-cinematic/server
pip install -r requirements.txt

# Run locally
python app.py
# http://localhost:8000       → Scripture Mode
# http://localhost:8000/custom → Custom Script Mode

# Deploy to Modal (public with auth)
modal deploy modal_app.py
# https://tribesofisrael--ai-bible-gospels-web.modal.run
```

---

## Biblical Cinematic (Scripture Mode)

### What It Does

Paste raw KJV scripture. The app cleans and formats it, Claude AI generates cinematic scenes, and a fully produced video is rendered — complete with:

- **Claude AI** cinematic scene descriptions (intro + scripture scenes + outro)
- **FLUX Pro** AI-generated photorealistic images per scene
- **Kling AI** video animation (v1.6 / v2.1 / v3.0 / v3.0-pro / o3 / o3-pro)
- **ElevenLabs** professional narration (via JSON2Video)
- HD video with synchronized visuals, narration, and subtitles

### Features

- **Aspect Ratio Picker** — choose 16:9 (YouTube/TV · 1920×1080), 1:1 (Instagram/Facebook feed · 1080×1080), or 9:16 (Reels/TikTok/Shorts · 1080×1920). FLUX, Kling, and JSON2Video all switch together; subtitles resize per ratio.
- **ElevenLabs Voice Picker** — Pro Narrator, Daniel Steady Broadcaster, Young Jamal, Tommy Israel, William J, Hakeem, Lamar Lincoln, or paste any ElevenLabs voice ID
- **Scene Preview & Edit** — review and edit every scene (narration, image prompt, motion, lighting) before spending render credits
- **Auto-Split** — chapters over 900 words automatically split into Part 1 / Part 2
- **Batch Fix Scenes** — check multiple scenes, edit prompts inline, regenerate all with ONE JSON2Video render
- **Stop Rendering** — cancel mid-render to save credits; completed scenes preserved for retry
- **Retry** — resume from the last completed scene (state persisted across container restarts)
- **Render History** — browse past renders, view scene data, reload into fix panel
- **Post-Production** — FFmpeg adds intro/outro clips, logo overlay, background music (local only)
- **YouTube Upload** — one-click upload with auto-generated title, description, and thumbnail (local only)

**Cost per video:** ~$4.50-7.00 depending on Kling model | **Render time:** 10-20 minutes

---

### The Full Pipeline

```
You (browser at http://localhost:8000)
  |
  v
Step 1 -- TEXT CLEANING
  Raw KJV scripture is sent to the FastAPI server.
  biblical_text_processor_v2.py:
    - Removes verse numbers (e.g. "1:1", "[1]")
    - Fixes 95+ OCR artifacts and punctuation errors
    - Normalizes archaic spellings for TTS
    - Splits text into ~1000-word narration sections
  Cleaned text returned to browser for review.
  |
  v
Step 2 -- SCENE GENERATION (Claude AI)
  Click "Generate Scenes" -- no credits spent yet.
  Claude AI generates per scene:
    - imagePrompt (photorealistic FLUX prompt)
    - motion (zoom-in, zoom-out, ken-burns, pan-right, pan-left)
    - lighting description
  Plus intro/outro narration.
  |
  v
Step 3 -- REVIEW & EDIT SCENES
  Edit any scene in the browser before rendering:
    - Narration text
    - Image prompts
    - Motion type and lighting
    - Add or remove scenes
  |
  v
Step 4 -- VIDEO PIPELINE (background thread)
  Click "Generate Video" to start rendering.
  For each scene:
    -> fal.ai FLUX Pro       -> photorealistic 16:9 image
    -> fal.ai Kling AI       -> 10-15s animated video clip
  Auto-splits long chapters into Part 1 / Part 2.
  Live progress bar tracks each scene in real time.
  Use "Stop Rendering" to cancel and save credits.
  |
  v
Step 5 -- FINAL RENDER (JSON2Video)
  All scene videos + ElevenLabs narration + subtitles
  assembled into one HD MP4. Download button appears when done.
  |
  v
Step 6 -- FIX SCENES (optional)
  Check scenes to fix, edit prompts inline, click
  "Regenerate Selected Scenes" -> ONE re-render.
  Or use preview mode: FLUX + Kling only (~$0.69/scene)
  before committing to full render (~$1.50).
  |
  v
Step 7 -- POST-PRODUCTION & UPLOAD (local only)
  Step 4 panel: add intro/outro/logo via FFmpeg.
  Step 5 panel: upload to YouTube with auto-generated metadata.
```

---

### Prerequisites

| Service | What for | Sign up |
|---|---|---|
| **Anthropic** | Claude AI scene generation | [console.anthropic.com](https://console.anthropic.com) |
| **fal.ai** | FLUX image gen + Kling video animation | [fal.ai](https://fal.ai) |
| **JSON2Video** | Final video assembly + ElevenLabs narration | [json2video.com](https://json2video.com) |
| **Python 3.11+** | Runtime | [python.org](https://python.org) |

Optional (for post-production & upload):
- **FFmpeg** — for intro/outro/logo overlay ([ffmpeg.org](https://ffmpeg.org/download.html))
- **Google OAuth2** — for YouTube upload (one-time setup, see `scripts/` folder)

---

### Setup

```bash
# 1. Install dependencies
cd workflows/biblical-cinematic/server
pip install -r requirements.txt

# 2. Configure API keys
cp .env.example .env
# Edit .env and set:
#   ANTHROPIC_API_KEY=sk-ant-...
#   FAL_KEY=...
#   JSON2VIDEO_API_KEY=...

# 3. Start the server
python app.py
```

Open **http://localhost:8000** in your browser.

---

### How to Use

1. Go to **http://localhost:8000**
2. Paste raw KJV scripture -> click **Convert & Clean**
3. Review/edit the cleaned text -> click **Generate Scenes** (Claude AI only, no credits spent)
4. **Review & Edit Scenes** -- edit narration, image prompts, motion, lighting for each scene
5. Click **Generate Video** to start the FLUX + Kling + JSON2Video pipeline
6. Watch the live progress bar track scene-by-scene rendering
7. Use **Stop Rendering** to cancel mid-render and save credits (completed scenes preserved)
8. Use **Retry** to resume from where it stopped
9. Use **Fix Scenes** panel to check and regenerate specific scenes with ONE render
10. **Download** the raw MP4 when done (auto-split into Part 1 / Part 2 for long chapters)
11. *(Optional)* **Post-Production** panel -- add intro/outro/logo overlay via FFmpeg
12. *(Optional)* **YouTube Upload** panel -- one-click upload with auto-generated metadata

---

## Custom Script Mode

### What It Does

Same AI pipeline as Biblical mode, but for **any script or concept**. Dynamic scene count (not fixed to 20). Includes all the same features: batch fix, stop/retry, render history, preview-first fixes.

### How to Use

1. Go to **http://localhost:8000/custom**
2. Paste your script or concept
3. Claude AI generates scenes -> review and edit
4. Generate video -> same FLUX + Kling + JSON2Video pipeline
5. Fix scenes with preview mode (~$0.69/scene) before committing to render

### CLI Usage

```bash
python workflows/custom-script/generate.py script.txt              # full pipeline
python workflows/custom-script/generate.py script.txt --scenes-only # preview scenes only
python workflows/custom-script/generate.py script.txt --post-produce # with intro/outro
```

---

## General AI Movie Pipeline (Reference)

An earlier pipeline using OpenAI instead of Claude/ElevenLabs. Uses Gradio UI.

```bash
python app.py                          # Gradio UI at http://localhost:7860
python pipeline.py path/to/script.txt  # CLI mode
```

Requires `OPENAI_API_KEY` and `FAL_KEY` in `.env`.

---

## Modal Deployment

The unified web app is deployed to **Modal.com** with Basic Auth.

**Live URL:** https://tribesofisrael--ai-bible-gospels-web.modal.run

### Deploy

```bash
# 1. Create Modal secret named "ai-bible-gospels" with:
#    FAL_KEY, JSON2VIDEO_API_KEY, ANTHROPIC_API_KEY, APP_USERNAME, APP_PASSWORD

# 2. Deploy
modal deploy modal_app.py
```

### Notes
- Auth middleware only activates when `APP_USERNAME` + `APP_PASSWORD` are set (skipped in local dev)
- Post-production and YouTube upload are local-only (require FFmpeg and filesystem access)
- Pipeline state persisted to Modal Volume -- survives container restarts
- Run `modal app stop ai-bible-gospels` before redeploying to force-refresh warm containers

---

## Environment Variables

| Variable | Used By | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude AI scene generation | Yes |
| `FAL_KEY` | FLUX image gen + Kling video animation | Yes |
| `JSON2VIDEO_API_KEY` | Video assembly + render status polling | Yes |
| `APP_USERNAME` | Modal deployment Basic Auth | For deploy only |
| `APP_PASSWORD` | Modal deployment Basic Auth | For deploy only |
| `OPENAI_API_KEY` | General pipeline (GPT-4o + TTS) | General pipeline only |
| `N8N_WEBHOOK_URL` | Legacy n8n workflow (no longer used) | No |

---

## Project Structure

```
ai-bible-gospels/
├── README.md                              <- you are here
├── CLAUDE.md                              <- AI assistant context
├── modal_app.py                           <- Modal.com deployment entry point
├── start.bat                              <- double-click to start server (Windows)
├── .env.example                           <- copy to .env, fill in keys
│
├── app.py                                 <- General pipeline -- Gradio UI
├── pipeline.py                            <- General pipeline -- orchestrator
├── src/features/                          <- General pipeline modules
│   ├── script_parser/                     <- GPT-4o scene breakdown
│   ├── image_gen/                         <- FLUX image generation
│   ├── video_gen/                         <- Kling image-to-video
│   ├── audio_gen/                         <- OpenAI TTS narration
│   └── assembler/                         <- FFmpeg final assembly
│
├── workflows/
│   ├── biblical-cinematic/
│   │   ├── README.md                      <- detailed biblical workflow docs
│   │   ├── ERRORS.md                      <- bug log with root-cause fixes
│   │   ├── server/
│   │   │   ├── app.py                     <- Unified FastAPI server (run this)
│   │   │   ├── biblical_pipeline.py       <- v12 pipeline router (/v9/api/*)
│   │   │   └── requirements.txt
│   │   ├── text_processor/
│   │   │   └── biblical_text_processor_v2.py  <- KJV text cleaner
│   │   ├── scripts/
│   │   │   ├── post_produce.py            <- FFmpeg post-production
│   │   │   ├── batch_post_produce.py      <- Batch post-production
│   │   │   └── upload_youtube.py          <- YouTube uploader
│   │   ├── assets/                        <- logo.png, intro.mp4, outro.mp4, music/
│   │   ├── n8n/                           <- Legacy n8n workflows (reference only)
│   │   └── templates/                     <- Legacy JSON2Video templates
│   │
│   └── custom-script/
│       ├── README.md                      <- custom script workflow docs
│       ├── router.py                      <- FastAPI APIRouter (mounted at /custom)
│       ├── generate.py                    <- CLI pipeline
│       ├── recover.py                     <- Recovery from fal.ai history
│       └── example-trailer.txt            <- Example input script
│
└── output/                                <- generated videos saved here
```

---

## Troubleshooting

**Port 8000 already in use (Windows)**
```powershell
# Find the PID
netstat -ano | findstr :8000
# Kill it
Stop-Process -Id <PID> -Force
```

**Pipeline fails mid-render**
- Click **Retry** -- it resumes from the last completed scene
- State is persisted to disk (or Modal Volume in production)

**Duplicate `.env` keys**
- `python-dotenv` uses the **first** occurrence. Edit the existing line, don't append a new one.

---

## Recovery (if state is lost)

Recover completed Kling video URLs from fal.ai history:

```python
import fal_client, requests, os
os.environ['FAL_KEY'] = '<key>'

# Get request IDs from fal.ai history
resp = requests.get('https://api.fal.ai/v1/models/requests/by-endpoint',
    headers={'Authorization': 'Key <FAL_KEY>'},
    params={'endpoint_id': 'fal-ai/kling-video/v3/standard/image-to-video',
            'limit': 40, 'status': 'success'})
items = sorted(resp.json()['items'], key=lambda x: x['started_at'])

# Fetch video URLs (always use fal_client.result, not the history API)
for item in items:
    result = fal_client.result('fal-ai/kling-video/v3/standard/image-to-video',
                               item['request_id'])
    print(result['video']['url'])
```
