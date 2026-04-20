# Biblical Cinematic Video Workflow

Generates professional 8–13 minute biblical cinematic videos from KJV scripture text.
A web app handles text cleaning and review, then automatically triggers the n8n pipeline.

**Current version: v7.2** (stable, production, field-name-anchored JSON parsing)

---

## How It Works

```
Browser (http://localhost:8000)
  → Paste scripture → Convert & Clean
  → Review cleaned text → Approve & Generate Video
  → FastAPI server POSTs to n8n webhook
      → Perplexity AI (sonar-pro)    → 20 cinematic scenes
      → ElevenLabs                   → narration audio
      → JSON2Video (Ken Burns)       → HD video render
  → Live progress bar (polls /api/status every 6s)
  → Download raw MP4 when done (~8–13 min)
  → Drop raw MP4 into output/raw/ → Step 4 panel → Start Rendering
      → FFmpeg: normalize → concat intro/outros → overlay logo
  → Download final MP4
```

**Cost per video:** ~$1.32 — Perplexity $0.15 + ElevenLabs $0.65 + JSON2Video $0.52
**Render time:** 8–13 minutes (Perplexity + ElevenLabs + JSON2Video)

---

## Quick Start

### 1. Set required keys in `.env` (workspace root)

```
N8N_WEBHOOK_URL=https://your-n8n-instance.app.n8n.cloud/webhook/your-path
JSON2VIDEO_API_KEY=your-json2video-api-key
```

`JSON2VIDEO_API_KEY` powers the real-time progress bar — the page still works without it but status tracking falls back to time estimates.

### 2. Start the web server

**Option A — Double-click (fastest):**
Double-click `start.bat` at the project root. The terminal opens, the server starts, and stays open.

**Option B — Terminal:**
```bash
cd workflows/biblical-cinematic/server
pip install -r requirements.txt   # first time only
python app.py
# or: npm start
```

### 3. Open the web app

Go to **http://localhost:8000** — paste scripture, convert, approve.

---

## n8n Workflow Setup (one-time)

If setting up from scratch or on a new n8n instance:

1. Import `n8n/Biblical-Video-Workflow-v6.0.2.json` into n8n
2. Import `templates/JSON2Video-Template-FIXED.json` into JSON2Video → copy the Template ID
3. In the workflow, configure credentials:
   - **Perplexity AI node**: `Bearer YOUR_PERPLEXITY_API_KEY`
   - **ElevenLabs node**: your ElevenLabs API key
   - **JSON2Video node**: your JSON2Video API key + Template ID
4. Replace the **Manual Trigger** node with a **Webhook** node:
   - HTTP Method: POST
   - Respond: Immediately
   - Connect it to **"Bible Chapter Text Input"**
5. In **"Bible Chapter Text Input"** Set node: field NAME = `inputText`, VALUE = `{{ $json.body.text }}` (enable expression mode)
6. **Save** the workflow and toggle it to **Published/Active**
7. Copy the **Production URL** → paste into `.env` as `N8N_WEBHOOK_URL`

---

## Post-Production (Step 4 in the web app)

After downloading your raw MP4 from JSON2Video:
1. Drop the file into `output/raw/`
2. In the web app, scroll to **Step 4 — Post-Production**
3. Click **↺ Refresh** — badge turns green showing the file is ready
4. Click **▶ Start Rendering** — progress bar tracks all FFmpeg stages
5. Click **⬇ Download Final Video** when done

Adds: intro → main video → outro_1 → outro_2 → outro_3 → logo watermark.
*(Music is disabled until caption sync is resolved.)*

### Assets required in `assets/`
```
assets/
├── logo1.png       ← AI Bible Gospels logo (transparent PNG, centered crop)
├── Into.mp4        ← Intro clip
├── outro_1.mp4     ← Outro part 1
├── outro_2.mp4     ← Outro part 2
└── outro_3.mp4     ← Outro part 3
```

### Run — single video
```bash
# From project root:
python workflows/biblical-cinematic/scripts/post_produce.py output/raw/your-video.mp4

# For 4K output:
python workflows/biblical-cinematic/scripts/post_produce.py output/raw/your-video.mp4 --width 3840
```

### Run — batch (all videos in output/raw/)
```bash
python workflows/biblical-cinematic/scripts/batch_post_produce.py

# 4K output:
python workflows/biblical-cinematic/scripts/batch_post_produce.py --width 3840
```

The script will:
1. Normalize all segments to identical specs (prevents freeze at join points)
2. Concatenate: intro → video → outro_1 → outro_2 → outro_3
3. Overlay logo (bottom-left, 500px wide)
4. Save to `output/{name}_final.mp4`

---

## Prerequisites

- **n8n** — cloud ($20/mo) or self-hosted (free): https://n8n.io
- **Perplexity AI** API key: https://perplexity.ai
- **ElevenLabs** API key: https://elevenlabs.io
- **JSON2Video** API key: https://json2video.com
- **Python 3.7+**

---

## ElevenLabs Voice IDs

The web app exposes a voice picker (Step 2b in Scripture Mode and Step 2 in Custom Script Mode) backed by `GET /v9/api/voices` and `GET /custom/api/voices`. The catalog lives in `biblical_pipeline.py` (`VOICES`) and `custom-script/router.py` (`VOICES`) — keep both in sync when adding voices.

| Voice | ID | Style |
|---|---|---|
| Pro Narrator *(default — both modes)* | `NgBYGKDDq2Z8Hnhatgma` | Professional, 214 WPM — long-standing biblical narrator |
| Young Jamal | `6OzrBCQf8cjERkYgzSg8` | Young, clear narration |
| Tommy Israel *(personal)* | `T4sLxEj9xEGMREO21ACw` | Personal voice |
| William J | `C8OtYB0OTgD7K0YWkg7y` | Professional |
| Hakeem | `nJvj5shg2xu1GKGxqfkE` | African American, deep |
| Lamar Lincoln | `CVRACyqNcQefTlxMj9b` | Black narrator |

---

## Folder Structure

```
biblical-cinematic/
├── README.md                              ← this file
├── ERRORS.md                              ← running build error log (archive when fully in production)
├── server/
│   ├── app.py                             ← FastAPI web server (run this)
│   ├── requirements.txt                   ← pip install -r requirements.txt
│   └── package.json                       ← enables: npm start
├── text_processor/
│   ├── biblical_text_processor_v2.py      ← imported by server; also runnable standalone
│   ├── Input                              ← paste KJV text here (standalone use)
│   └── Output                             ← cleaned text (standalone use)
├── n8n/
│   └── Biblical-Video-Workflow-v6.0.2.json ← import into n8n
├── scripts/
│   ├── post_produce.py                    ← single video post-production
│   └── batch_post_produce.py             ← batch: process all videos in output/raw/
├── templates/
│   └── JSON2Video-Template-FIXED.json     ← import into JSON2Video
├── ui/                                    ← original React frontend (unused, replaced by server/)
└── archive/
    └── releases/                          ← v1.0 through v6.0.1 history
```

---

## Troubleshooting

**Workflow not triggering:**
- Make sure the n8n workflow is **Published** (green badge, top-right of workflow editor)
- Check `N8N_WEBHOOK_URL` uses `/webhook/` not `/webhook-test/`
- Test directly: `python -c "import httpx; r=httpx.post('YOUR_URL', json={'text':'test'}); print(r.status_code, r.text)"`

**n8n generating wrong content ("undefined" chapter):**
- The `Bible Chapter Text Input` Set node has wrong field config
- Fix: NAME = `inputText`, VALUE = `{{ $json.body.text }}` with expression mode ON

**Progress bar shows "estimated" instead of live tracking:**
- `JSON2VIDEO_API_KEY` is missing or wrong in `.env`
- Real key goes in `.env` at workspace root — one entry only (no duplicates; python-dotenv uses the first one)

**Server not reading `.env`:**
- The server uses `find_dotenv()` which walks up from `server/` to find `.env` at workspace root

**Stale server process holding port 8000 (Windows):**
- `taskkill` is unreliable for orphaned Python processes — use PowerShell instead:
  ```powershell
  # Kill a specific PID:
  Stop-Process -Id <pid> -Force
  # Kill all Python (nuclear option):
  Get-Process python | Stop-Process -Force
  ```

**Server serving old code after editing app.py:**
- Server runs with `reload=False` — you must restart it manually after any code change

**Text processor errors:**
- The server imports `biblical_text_processor_v2.py` directly from `text_processor/`
- Can also run standalone: paste into `Input` file, run `python biblical_text_processor_v2.py`, read `Output`
