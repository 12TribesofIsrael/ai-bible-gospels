# AI Movie

A personal workspace for building AI-generated video systems. Paste in text — get back a fully produced, narrated cinematic video.

Contains three workflows, with the two production workflows merged into a **unified web app** at http://localhost:8000:

| Workflow | Status | What it does |
|---|---|---|
| **Biblical Cinematic** (Scripture Mode) | Production (v10) | KJV scripture → cinematic video with narration, batch scene fixing, stop rendering, render history |
| **Custom Script** (Custom Script Mode) | Production | Any script/concept → Claude AI scenes → dynamic-length cinematic video, preview-first batch fix, stop rendering, render history |
| **General AI Movie** | In Development | Script/prompt → images → animated video clips → narrated movie |

### Quick Start
```bash
python workflows/biblical-cinematic/server/app.py
# http://localhost:8000     → Scripture Mode
# http://localhost:8000/custom → Custom Script Mode
```

---

## Workflow 1: Biblical Cinematic

### What It Does

You paste in raw KJV scripture text. The app cleans and formats it, you review it, click one button, and a fully produced cinematic video is waiting for you — complete with:

- Claude AI-generated cinematic scene descriptions (intro + scripture scenes + outro)
- FLUX Pro AI-generated images per scene
- Kling AI video animation (v1.6/v2.1/v3.0)
- Professional narration audio (ElevenLabs voices via JSON2Video)
- HD video with synchronized visuals, narration, and subtitles

**v10 Features:**
- **Batch Fix Scenes** — check multiple scenes, edit prompts inline, regenerate all with ONE JSON2Video render (~$1.50 instead of $1.50 per scene)
- **Stop Rendering** — cancel mid-render to save credits; completed scenes preserved for retry
- **Render History** — browse past renders, view scenes, reload into fix panel
- **Scene data sync** — fix panel always shows latest prompt data after edits

**Cost per video:** ~$4.50–7.00 depending on Kling model | **Render time:** 10–20 minutes

---

### The Full Pipeline (What Happens Behind the Scenes)

```
You (browser at http://localhost:8000)
  │
  ▼
Step 1 — TEXT CLEANING
  Your raw KJV scripture is sent to the FastAPI server.
  The biblical_text_processor_v2.py script:
    - Removes verse numbers (e.g. "1:1", "[1]")
    - Fixes 95+ OCR artifacts and punctuation errors
    - Normalizes archaic spellings for TTS
    - Splits the text into ~1000-word narration sections
  → Cleaned text is returned to your browser for review.
  │
  ▼
Step 2 — YOUR REVIEW
  You read through the cleaned text in the browser.
  You can edit anything before approving.
  When satisfied, click "Approve & Generate Video."
  │
  ▼
Step 3 — VIDEO PIPELINE (v10 — no n8n)
  The server splits scripture into narration chunks, then
  Claude AI generates imagePrompt, motion, lighting per scene
  plus intro/outro narration.
  │
  ▼
Step 4 — MEDIA GENERATION (background thread)
  For each scene:
    → fal.ai FLUX Pro      → photorealistic 16:9 image
    → fal.ai Kling v1.6/v2.1/v3.0 → 10-15s animated video clip
  Progress bar tracks each scene in real time.
  Use ⏹ Stop Rendering to cancel and save credits.
  │
  ▼
Step 5 — FINAL RENDER (JSON2Video)
  All scene videos + ElevenLabs narration + subtitles
  assembled into one HD MP4. Download when done.
  │
  ▼
Step 6 — FIX SCENES (optional)
  Check scenes to fix, edit prompts inline, click
  "Regenerate Selected Scenes" → ONE re-render.
  │
  ▼
Step 7 — POST-PRODUCTION & UPLOAD
  Add intro/outro/logo (Step 4 panel), upload to YouTube (Step 5 panel).
  Render history tracks all past renders for future reference.
```

---

### Prerequisites (Accounts You Need)

Before first use, make sure you have:

- **n8n** — [n8n.io](https://n8n.io) — cloud ($20/mo) or self-hosted (free)
- **Perplexity AI** — [perplexity.ai](https://perplexity.ai) — API key for sonar-pro model
- **ElevenLabs** — [elevenlabs.io](https://elevenlabs.io) — API key for TTS
- **JSON2Video** — [json2video.com](https://json2video.com) — API key + imported template
- **Python 3.7+** — installed locally

---

### One-Time Setup

#### 1. Configure your `.env` file

At the workspace root, copy the example and fill it in:

```bash
cp .env.example .env
```

Open `.env` and set:

```
N8N_WEBHOOK_URL=https://your-n8n-instance.app.n8n.cloud/webhook/your-webhook-id
```

> This is the **Production URL** from your n8n webhook node — it starts with `/webhook/`, not `/webhook-test/`.

---

#### 2. Set up the n8n Workflow (one-time)

1. Open your n8n instance
2. Import `workflows/biblical-cinematic/n8n/Biblical-Video-Workflow-v6.0.2.json`
3. Add your API credentials inside n8n:
   - **Perplexity node** → `Bearer YOUR_PERPLEXITY_API_KEY`
   - **ElevenLabs node** → your ElevenLabs API key
   - **JSON2Video node** → your JSON2Video API key
4. In n8n, make sure the **Webhook** node is connected to the **"Bible Chapter Text Input"** node
5. In the **"Bible Chapter Text Input"** Set node, the value must be: `{{ $json.body.text }}`
6. **Toggle the workflow to Published/Active** (green badge, top-right of editor)
7. Copy the Production webhook URL → paste into `.env` as `N8N_WEBHOOK_URL`

---

#### 3. Set up JSON2Video (one-time)

1. Log into [json2video.com](https://json2video.com)
2. Import `workflows/biblical-cinematic/templates/JSON2Video-Template-FIXED.json`
3. Copy the Template ID it generates
4. Paste that Template ID into the JSON2Video node inside your n8n workflow

---

#### 4. Install server dependencies (first time only)

```bash
cd workflows/biblical-cinematic/server
pip install -r requirements.txt
```

---

### How to Use the App (Step by Step)

#### Step 1 — Start the server

**Option A — Double-click (fastest):**
Double-click `start.bat` at the project root. A terminal opens, the server starts, and the window stays open.

**Option B — Terminal:**
```bash
cd workflows/biblical-cinematic/server
python app.py
# or: npm start
```

You'll see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

#### Step 2 — Open the web app

Go to **http://localhost:8000** in your browser.

You'll see the landing page with a text area and three-step progress indicator.

#### Step 3 — Paste your scripture

Paste raw KJV text into the text area. It can be messy — verse numbers, OCR artifacts, and formatting errors are all handled automatically.

Example input:
```
Genesis 1:1 In the beginning God created the heaven and the earth. 1:2 And the
earth was without form, and void; and darkness [was] upon the face of the deep.
```

Click **"Convert & Clean"**.

#### Step 4 — Review the cleaned text

The app processes your text and displays the cleaned version. It will have:
- Verse numbers removed
- Punctuation corrected
- Text split into natural narration sections

Read through it. You can edit directly in the browser if anything looks wrong.

#### Step 5 — Approve and generate

Click **"Approve & Generate Video"**.

The app immediately:
1. Sends the text to your n8n webhook
2. Shows a confirmation message

You'll see: *"Your video is being generated — check your JSON2Video dashboard in 8–13 minutes."*

#### Step 6 — Wait for the render

The n8n pipeline runs automatically:
- Perplexity generates 20 scene descriptions (~30 sec)
- ElevenLabs renders narration audio (~1–2 min)
- JSON2Video renders the full HD video (~8–13 min total)

#### Step 7 — Download your video

Log into [json2video.com](https://json2video.com), go to your dashboard, and download the finished MP4.

---

### Available Narrator Voices

Configured inside the n8n ElevenLabs node:

| Voice | ElevenLabs ID | Style |
|---|---|---|
| Young Jamal *(default)* | `6OzrBCQf8cjERkYgzSg8` | Young, clear narration |
| Tommy Israel *(personal)* | `T4sLxEj9xEGMREO21ACw` | Personal voice |
| William J | `C8OtYB0OTgD7K0YWkg7y` | Professional |
| Hakeem | `nJvj5shg2xu1GKGxqfkE` | Deep, authoritative |
| Lamar Lincoln | `CVRACyqNcQefTlxMj9b` | Rich narrator tone |

To change the voice, update the Voice ID in the ElevenLabs node inside n8n.

---

### Troubleshooting

**"N8N_WEBHOOK_URL is not set" error**
- Make sure `.env` exists at the workspace root (not inside `server/`)
- Restart the server after editing `.env`
- The URL must use `/webhook/` — not `/webhook-test/`

**Approved but nothing happens in n8n**
- Check that the workflow is **Published** (not just saved)
- Confirm the Webhook node is connected to "Bible Chapter Text Input"
- Confirm the Set node value is `{{ $json.body.text }}` (expression mode, not fixed)

**Port 8000 already in use (Windows)**
- Find the PID: `netstat -ano | findstr :8000`
- Kill it: `python -c "import subprocess; subprocess.run(['taskkill', '/F', '/PID', 'THE_PID'], shell=True)"`

---

---

## Workflow 2: General AI Movie Pipeline

### What It Does

Turn any script, screenplay, or text prompt into a fully produced movie with:
- AI-generated images for each scene (FLUX via fal.ai)
- Animated video clips from each image (Kling via fal.ai)
- AI narration audio for each scene (OpenAI TTS)
- Final assembled MP4 (FFmpeg)

**Status:** In development — pipeline is built, API keys not yet configured.

---

### The Full Pipeline

```
You enter a script or prompt into the Gradio UI
  │
  ▼
Step 1 — SCENE PARSING (GPT-4o)
  GPT-4o reads your script and breaks it into structured Scene objects.
  Each scene has: title, description, narration text, duration.
  │
  ▼
Step 2 — IMAGE GENERATION (FLUX via fal.ai)
  For each scene, FLUX generates a cinematic still image
  based on the scene description.
  │
  ▼
Step 3 — VIDEO ANIMATION (Kling via fal.ai)
  Each still image is animated into a short video clip
  using Kling's image-to-video model.
  │
  ▼
Step 4 — NARRATION AUDIO (OpenAI TTS)
  Each scene's narration text is converted to speech.
  │
  ▼
Step 5 — FINAL ASSEMBLY (FFmpeg)
  All video clips and audio tracks are stitched together
  into a single MP4 saved to output/<run-id>/movie.mp4
```

---

### Setup

```bash
# Install dependencies
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env — add OPENAI_API_KEY and FAL_KEY

# Also install FFmpeg and add to PATH
# Download: https://ffmpeg.org/download.html
```

### Run

```bash
python app.py          # Gradio UI at http://localhost:7860
# or
python pipeline.py path/to/script.txt   # CLI mode
```

---

## Project Structure

```
AI Movie/
├── README.md                               ← you are here
├── CLAUDE.md                               ← AI assistant context file
├── start.bat                               ← double-click to start Biblical server
├── .env.example                            ← copy to .env, fill in keys
├── app.py                                  ← General pipeline — Gradio UI
├── pipeline.py                             ← General pipeline — orchestrator
│
├── src/
│   └── features/
│       ├── script_parser/                  ← GPT-4o scene breakdown
│       ├── image_gen/                      ← FLUX image generation
│       ├── video_gen/                      ← Kling image-to-video
│       ├── audio_gen/                      ← OpenAI TTS narration
│       └── assembler/                      ← FFmpeg final assembly
│
├── workflows/
│   ├── biblical-cinematic/
│   │   ├── README.md                       ← detailed biblical workflow docs
│   │   ├── server/
│   │   │   ├── app.py                      ← Unified FastAPI web server (run this)
│   │   │   ├── requirements.txt
│   │   │   └── package.json                ← enables: npm start
│   │   ├── text_processor/
│   │   │   └── biblical_text_processor_v2.py  ← KJV text cleaner
│   │   ├── n8n/
│   │   │   └── Biblical-Video-Workflow-v6.0.2.json  ← import into n8n
│   │   ├── templates/
│   │   │   └── JSON2Video-Template-FIXED.json       ← import into JSON2Video
│   │   └── archive/                        ← v1.0 through v6.0.1 history
│   │
│   └── custom-script/
│       ├── README.md                       ← custom script workflow docs
│       ├── router.py                       ← FastAPI APIRouter (mounted at /custom)
│       ├── server.py                       ← Standalone server (legacy, port 8500)
│       ├── generate.py                     ← CLI pipeline
│       ├── recover.py                      ← Recovery from fal.ai history
│       └── example-trailer.txt             ← Example input script
│
└── output/                                 ← generated videos saved here
```
