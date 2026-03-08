"""
Biblical Cinematic Generator — Web Server
==========================================
Run:  python app.py
URL:  http://localhost:8000

Endpoints:
  GET  /             → landing page
  POST /api/clean    → clean biblical text, return sections
  POST /api/generate → send approved text to n8n webhook
  GET  /api/status   → real-time generation status (polls JSON2Video)
"""

import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv, find_dotenv

# find_dotenv() walks up the directory tree from this file to locate .env
load_dotenv(find_dotenv(), override=True)

# Make the text_processor module importable
sys.path.insert(0, str(Path(__file__).parent.parent / "text_processor"))

import re
import threading
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from biblical_text_processor_v2 import (
    clean_text,
    kjv_narration_fix,
    split_into_words,
    create_sections,
    format_section,
)

app = FastAPI(title="Biblical Cinematic Generator")

# ── Generation state (single-user, in-memory) ─────────────────────────────────
# Resets each time a new video is triggered.
generation_state: dict = {
    "started_at": None,    # datetime (UTC) when /api/generate was called
    "project_id": None,    # JSON2Video project ID once discovered
    "video_url":  None,    # Final MP4 URL when render completes
}

JSON2VIDEO_BASE = "https://api.json2video.com/v2/movies"

# ── Post-production paths ──────────────────────────────────────────────────────
_SCRIPT_DIR   = Path(__file__).parent
_BIBLICAL_DIR = _SCRIPT_DIR.parent
_PROJECT_ROOT = _BIBLICAL_DIR.parent.parent   # c:/Users/Tommy/AI Movie
RAW_DIR       = _PROJECT_ROOT / "output" / "raw"
OUT_DIR       = _PROJECT_ROOT / "output"
POST_SCRIPT    = _BIBLICAL_DIR / "scripts" / "post_produce.py"
UPLOAD_SCRIPT  = _BIBLICAL_DIR / "scripts" / "upload_youtube.py"

# ── Upload state (single-user, in-memory) ─────────────────────────────────────
upload_state: dict = {
    "status":     "idle",   # idle | running | done | error
    "progress":   0,        # 0–100
    "label":      "",
    "file":       None,
    "video_url":  None,
    "studio_url": None,
    "error":      None,
}

# ── Render state (single-user, in-memory) ─────────────────────────────────────
render_state: dict = {
    "status":   "idle",   # idle | running | done | error
    "progress": 0,         # 0–100
    "label":    "",
    "file":     None,      # raw filename being processed
    "output":   None,      # final output filename
    "error":    None,
}


# ── Request / Response models ─────────────────────────────────────────────────

class CleanRequest(BaseModel):
    text: str


class Section(BaseModel):
    index: int
    text: str
    word_count: int
    estimated_minutes: float
    estimated_scenes: int


class CleanResponse(BaseModel):
    sections: list[Section]
    total_sections: int


class GenerateRequest(BaseModel):
    text: str           # The approved (possibly edited) section text
    section_index: int = 0


class GenerateResponse(BaseModel):
    status: str
    message: str


class RenderRequest(BaseModel):
    file: str


class UploadRequest(BaseModel):
    file: str
    scripture: str


# ── API Routes ────────────────────────────────────────────────────────────────

@app.post("/api/clean", response_model=CleanResponse)
async def api_clean(req: CleanRequest):
    """Clean and split raw biblical text into video-ready sections."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    cleaned = clean_text(req.text)
    cleaned = kjv_narration_fix(cleaned)
    words = split_into_words(cleaned)

    if not words:
        raise HTTPException(status_code=400, detail="No text remained after cleaning.")

    raw_sections = create_sections(words)

    sections: list[Section] = []
    for i, section_words in enumerate(raw_sections):
        formatted = format_section(section_words, i + 1)
        word_count = len(section_words)
        sections.append(
            Section(
                index=i,
                text=formatted.strip(),
                word_count=word_count,
                estimated_minutes=round(word_count / 214, 1),
                estimated_scenes=word_count // 40,
            )
        )

    return CleanResponse(sections=sections, total_sections=len(sections))


@app.post("/api/generate", response_model=GenerateResponse)
async def api_generate(req: GenerateRequest):
    """Send approved text to the n8n webhook to trigger video generation."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Approved text cannot be empty.")

    load_dotenv(find_dotenv(), override=True)
    N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

    if not N8N_WEBHOOK_URL:
        raise HTTPException(
            status_code=500,
            detail="N8N_WEBHOOK_URL is not set in your .env file.",
        )

    payload = {"text": req.text.strip()}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(N8N_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"n8n webhook returned an error: {e.response.status_code} — {e.response.text}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach n8n webhook: {e}",
        )

    # Record start time and reset state for this generation
    generation_state["started_at"] = datetime.now(timezone.utc)
    generation_state["project_id"] = None
    generation_state["video_url"]  = None

    return GenerateResponse(
        status="sent",
        message="Workflow triggered. Tracking progress in real time...",
    )


@app.get("/api/status")
async def api_status():
    """
    Real-time generation status.

    Phases (returned as JSON):
      idle            → no generation running
      perplexity      → n8n/Perplexity generating scenes  (0–90 s, time-estimated)
      fal_generation  → FLUX images + Kling videos         (90–2000 s, time-estimated)
      json2video      → JSON2Video assembling video        (2000 s+, real API poll)
      done            → video_url is ready
      error           → something went wrong
    """
    if not generation_state["started_at"]:
        return {"phase": "idle", "elapsed": 0}

    now     = datetime.now(timezone.utc)
    elapsed = (now - generation_state["started_at"]).total_seconds()

    # ── Already finished ──────────────────────────────────────────────────────
    if generation_state["video_url"]:
        return {"phase": "done", "elapsed": elapsed,
                "video_url": generation_state["video_url"]}

    # ── Phase 1: n8n / Perplexity (0–90 s) ──────────────────────────────────
    if elapsed < 90:
        return {"phase": "perplexity", "elapsed": elapsed}

    # ── Phase 2: fal.ai FLUX + Kling generation (90–2000 s) ─────────────────
    if elapsed < 2000:
        scene_estimate = min(20, int((elapsed - 90) / 90) + 1)
        return {"phase": "fal_generation", "elapsed": elapsed,
                "scenes_estimated": scene_estimate}

    # ── Phase 3: JSON2Video assembly (2000 s+) — poll real API ───────────────
    load_dotenv(find_dotenv(), override=True)
    api_key = os.getenv("JSON2VIDEO_API_KEY", "")

    if not api_key:
        # No API key — fall back to time estimate
        return {"phase": "json2video", "status": "rendering",
                "elapsed": elapsed, "realtime": False}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            headers = {"x-api-key": api_key}

            # ── Known project: just check its status ─────────────────────────
            if generation_state["project_id"]:
                r = await client.get(
                    JSON2VIDEO_BASE,
                    params={"project": generation_state["project_id"]},
                    headers=headers,
                )
                r.raise_for_status()
                movie = r.json().get("movie", {})
                status = movie.get("status", "rendering")

                if status == "done":
                    generation_state["video_url"] = movie.get("url", "")
                    return {"phase": "done", "elapsed": elapsed,
                            "video_url": generation_state["video_url"]}

                if status == "error":
                    return {"phase": "error", "elapsed": elapsed,
                            "message": movie.get("message", "JSON2Video render failed.")}

                return {"phase": "json2video", "status": status,
                        "elapsed": elapsed, "realtime": True}

            # ── No project ID yet: list recent projects, find ours ────────────
            r = await client.get(JSON2VIDEO_BASE, headers=headers)
            r.raise_for_status()
            data = r.json()

            # The response may be a list or {"movies": [...]}
            movies = data if isinstance(data, list) else data.get("movies", [])

            # Find the most recent project created at or after our trigger time
            trigger_ts = generation_state["started_at"].timestamp()
            found = None
            for m in movies:
                raw_ts = m.get("date") or m.get("created_at") or m.get("createdAt", "")
                if not raw_ts:
                    continue
                try:
                    # Handle both Z-suffix and +00:00 formats
                    created_ts = datetime.fromisoformat(
                        raw_ts.replace("Z", "+00:00")
                    ).timestamp()
                    if created_ts >= trigger_ts - 120:   # 2-min buffer for clock skew
                        found = m
                        break
                except ValueError:
                    continue

            if found:
                pid = found.get("id") or found.get("project") or found.get("project_id")
                generation_state["project_id"] = pid
                status = found.get("status", "queued")

                if status == "done":
                    generation_state["video_url"] = found.get("url", "")
                    return {"phase": "done", "elapsed": elapsed,
                            "video_url": generation_state["video_url"]}

                return {"phase": "json2video", "status": status,
                        "elapsed": elapsed, "realtime": True}

            # Project not in JSON2Video yet (n8n still running)
            return {"phase": "json2video", "status": "queued",
                    "elapsed": elapsed, "realtime": True}

    except Exception:
        # Network / parse error — fall back gracefully
        return {"phase": "json2video", "status": "rendering",
                "elapsed": elapsed, "realtime": False}


# ── Post-production background thread ────────────────────────────────────────

def _run_render(raw_file: Path):
    """Run post_produce.py as a subprocess; parse stdout to drive render_state."""
    TOTAL_SEGS = 5  # Into + main video + outro_1/2/3

    try:
        import os
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            [sys.executable, "-u", str(POST_SCRIPT), str(raw_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        normalize_count = 0
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            print(f"[render] {line}", flush=True)
            if "Normalizing" in line:
                normalize_count += 1
                pct = int(normalize_count / TOTAL_SEGS * 65)
                render_state["progress"] = pct
                render_state["label"] = line.lstrip("→ ").strip()
            elif "Concatenating" in line:
                render_state["progress"] = 70
                render_state["label"] = "Concatenating segments..."
            elif "Overlaying" in line:
                render_state["progress"] = 85
                render_state["label"] = "Overlaying logo..."
            elif "Done!" in line or "✓" in line:
                render_state["progress"] = 99
                render_state["label"] = "Finishing up..."

        proc.wait()
        print(f"[render] process exited with code {proc.returncode}", flush=True)

        if proc.returncode == 0:
            render_state["status"]   = "done"
            render_state["progress"] = 100
            render_state["label"]    = "Done!"
            render_state["output"]   = raw_file.stem + "_final.mp4"
        else:
            render_state["status"] = "error"
            render_state["error"]  = "FFmpeg post-production failed (see server console for details)."

    except Exception as exc:
        render_state["status"] = "error"
        render_state["error"]  = str(exc)


# ── YouTube upload background thread ─────────────────────────────────────────

def _run_upload(final_file: Path, scripture: str):
    """Run upload_youtube.py as a subprocess; parse stdout to drive upload_state."""
    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            [sys.executable, "-u", str(UPLOAD_SCRIPT), str(final_file), scripture],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            print(f"[upload] {line}", flush=True)

            if "Uploading..." in line:
                m = re.search(r"(\d+)%", line)
                if m:
                    pct = int(m.group(1))
                    upload_state["progress"] = min(int(pct * 0.88), 88)
                    upload_state["label"] = f"Uploading to YouTube... {pct}%"
            elif "Generating thumbnail" in line:
                upload_state["progress"] = 93
                upload_state["label"] = "Generating thumbnail..."
            elif "Thumbnail set" in line:
                upload_state["progress"] = 99
                upload_state["label"] = "Finalizing..."
            elif "youtu.be/" in line:
                m = re.search(r"https://youtu\.be/\S+", line)
                if m:
                    upload_state["video_url"] = m.group(0).rstrip(".")
            elif "studio.youtube.com" in line:
                m = re.search(r"https://studio\.youtube\.com/\S+", line)
                if m:
                    upload_state["studio_url"] = m.group(0).rstrip(".")

        proc.wait()

        if proc.returncode == 0:
            upload_state["status"]   = "done"
            upload_state["progress"] = 100
            upload_state["label"]    = "Done!"
        else:
            upload_state["status"] = "error"
            upload_state["error"]  = "Upload failed — check the server terminal for details."

    except Exception as exc:
        upload_state["status"] = "error"
        upload_state["error"]  = str(exc)


# ── YouTube upload API endpoints ──────────────────────────────────────────────

@app.get("/api/upload/check")
async def upload_check():
    """Return list of final videos in output/ (not output/raw/)."""
    if not OUT_DIR.exists():
        return {"files": [], "count": 0}
    exts = {".mp4", ".mov", ".mkv"}
    files = sorted(
        f.name for f in OUT_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in exts
    )
    return {"files": files, "count": len(files)}


@app.post("/api/upload/start")
async def upload_start(req: UploadRequest):
    """Validate final file + scripture, then launch upload in a background thread."""
    if upload_state["status"] == "running":
        return {"status": "error", "message": "An upload is already in progress."}

    if not req.scripture.strip():
        return {"status": "error", "message": "Scripture reference is required (e.g. Matthew 10)."}

    safe_name  = Path(req.file).name
    final_file = OUT_DIR / safe_name
    if not final_file.exists():
        return {"status": "error", "message": f"File not found: {safe_name}"}

    upload_state.update({
        "status":     "running",
        "progress":   0,
        "label":      "Starting upload...",
        "file":       safe_name,
        "video_url":  None,
        "studio_url": None,
        "error":      None,
    })

    threading.Thread(target=_run_upload, args=(final_file, req.scripture.strip()), daemon=True).start()
    return {"status": "started"}


@app.get("/api/upload/status")
async def upload_status_ep():
    """Return current upload_state as JSON."""
    return upload_state


# ── Post-production API endpoints ─────────────────────────────────────────────

@app.get("/api/render/check")
async def render_check():
    """Return list of video files found in output/raw/."""
    if not RAW_DIR.exists():
        return {"files": [], "count": 0}
    exts = {".mp4", ".mov", ".mkv", ".webm"}
    files = sorted(f.name for f in RAW_DIR.iterdir() if f.suffix.lower() in exts)
    return {"files": files, "count": len(files)}


@app.post("/api/render/start")
async def render_start(req: RenderRequest):
    """Validate raw file exists, then launch post-production in a background thread."""
    if render_state["status"] == "running":
        return {"status": "error", "message": "A render is already in progress."}

    # Strip any path separators to prevent directory traversal
    safe_name = Path(req.file).name
    raw_file  = RAW_DIR / safe_name

    if not raw_file.exists():
        return {"status": "error", "message": f"File not found: {safe_name}"}

    render_state.update({
        "status":   "running",
        "progress": 0,
        "label":    "Starting FFmpeg...",
        "file":     safe_name,
        "output":   None,
        "error":    None,
    })

    threading.Thread(target=_run_render, args=(raw_file,), daemon=True).start()
    return {"status": "started"}


@app.get("/api/render/status")
async def render_status_ep():
    """Return current render_state as JSON."""
    return render_state


@app.get("/api/render/download/{filename}")
async def render_download(filename: str):
    """Serve a final rendered video from output/ for browser download."""
    safe_name = Path(filename).name          # strip any path components
    file_path = OUT_DIR / safe_name
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(
        file_path,
        media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


# ── Landing Page ──────────────────────────────────────────────────────────────

LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Biblical Cinematic Generator</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&family=Inter:wght@300;400;500;600&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .title-font { font-family: 'Cinzel', serif; }
    .step-panel { transition: all 0.4s ease; }
    textarea { resize: vertical; }
    .spinner {
      border: 3px solid rgba(255,255,255,0.1);
      border-top-color: #f59e0b;
      border-radius: 50%;
      width: 20px; height: 20px;
      animation: spin 0.8s linear infinite;
      display: inline-block;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">

  <!-- Header -->
  <header class="border-b border-gray-800 px-6 py-5 flex items-center gap-4">
    <div class="text-amber-500 text-2xl">✦</div>
    <div>
      <h1 class="title-font text-xl font-semibold text-amber-400 tracking-wide">Biblical Cinematic Generator</h1>
      <p class="text-xs text-gray-500 mt-0.5">Perplexity AI · fal.ai FLUX + Kling · ElevenLabs · JSON2Video · n8n</p>
    </div>
    <div class="ml-auto flex items-center gap-4">
      <a href="#step4" onclick="document.getElementById('step4').scrollIntoView({behavior:'smooth'}); return false;"
        class="text-xs text-purple-400 hover:text-purple-300 border border-purple-800 hover:border-purple-600 px-3 py-1.5 rounded-lg transition-colors">
        ▼ Post-Production
      </a>
      <span class="text-xs text-gray-600">v8.0 · ~$7.31/video · 35–45 min</span>
    </div>
  </header>

  <main class="max-w-4xl mx-auto px-6 py-12">

    <!-- Hero -->
    <div class="text-center mb-12">
      <h2 class="title-font text-3xl font-bold text-white mb-3">Transform Scripture into Cinema</h2>
      <p class="text-gray-400 text-base max-w-xl mx-auto">
        Paste your KJV biblical text below. The pipeline will clean it,
        let you review, then automatically generate a professional 12–20 minute cinematic video.
      </p>
    </div>

    <!-- Step indicators -->
    <div class="flex items-center justify-center gap-2 mb-10 text-sm">
      <div id="step-dot-1" class="flex items-center gap-2">
        <div class="w-7 h-7 rounded-full bg-amber-500 text-black font-bold flex items-center justify-center text-xs">1</div>
        <span class="text-amber-400 font-medium">Input</span>
      </div>
      <div class="h-px w-10 bg-gray-700"></div>
      <div id="step-dot-2" class="flex items-center gap-2 opacity-40">
        <div class="w-7 h-7 rounded-full bg-gray-700 text-gray-300 font-bold flex items-center justify-center text-xs">2</div>
        <span class="text-gray-400 font-medium">Review</span>
      </div>
      <div class="h-px w-10 bg-gray-700"></div>
      <div id="step-dot-3" class="flex items-center gap-2 opacity-40">
        <div class="w-7 h-7 rounded-full bg-gray-700 text-gray-300 font-bold flex items-center justify-center text-xs">3</div>
        <span class="text-gray-400 font-medium">Generating</span>
      </div>
    </div>

    <!-- ── STEP 1: Input ── -->
    <div id="step1" class="step-panel">
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <label class="block text-sm font-medium text-gray-300 mb-3">
          Biblical Text <span class="text-gray-500 font-normal">(KJV scripture — any length)</span>
        </label>
        <textarea
          id="raw-text"
          rows="14"
          placeholder="Paste your KJV scripture or biblical story here...&#10;&#10;Example: In the beginning God created the heaven and the earth..."
          class="w-full bg-gray-950 border border-gray-700 rounded-xl px-4 py-3 text-gray-100 placeholder-gray-600 text-sm focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
        ></textarea>
        <div class="flex items-center justify-between mt-4">
          <span id="char-count" class="text-xs text-gray-600">0 characters</span>
          <button
            id="convert-btn"
            onclick="convertText()"
            class="bg-amber-500 hover:bg-amber-400 text-black font-semibold px-8 py-3 rounded-xl transition-colors duration-200 flex items-center gap-2"
          >
            <span>Convert &amp; Clean</span>
          </button>
        </div>
        <div id="convert-error" class="mt-3 text-red-400 text-sm hidden"></div>
      </div>
    </div>

    <!-- ── STEP 2: Review ── -->
    <div id="step2" class="step-panel hidden">
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-6">

        <div class="flex items-start justify-between mb-4">
          <div>
            <h3 class="text-base font-semibold text-white">Review Cleaned Text</h3>
            <p class="text-sm text-gray-400 mt-0.5">Edit if needed, then approve to start video generation.</p>
          </div>
          <button onclick="backToStep1()" class="text-xs text-gray-500 hover:text-gray-300 underline">← Start over</button>
        </div>

        <!-- Section tabs (hidden when only 1 section) -->
        <div id="section-tabs" class="flex gap-2 mb-4 hidden"></div>

        <!-- Stats bar -->
        <div id="stats-bar" class="flex gap-6 mb-4 p-3 bg-gray-800 rounded-lg text-xs text-gray-400"></div>

        <!-- Cleaned text area -->
        <textarea
          id="cleaned-text"
          rows="14"
          class="w-full bg-gray-950 border border-gray-700 rounded-xl px-4 py-3 text-gray-100 text-sm focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
        ></textarea>

        <div class="flex items-center justify-between mt-4">
          <p class="text-xs text-gray-500">✏️ You can edit the text above before approving.</p>
          <button
            id="approve-btn"
            onclick="approveText()"
            class="bg-green-600 hover:bg-green-500 text-white font-semibold px-8 py-3 rounded-xl transition-colors duration-200 flex items-center gap-2"
          >
            <span>✓ Approve &amp; Generate Video</span>
          </button>
        </div>
        <div id="approve-error" class="mt-3 text-red-400 text-sm hidden"></div>
      </div>
    </div>

    <!-- ── STEP 3: Generating ── -->
    <div id="step3" class="step-panel hidden">
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-8 text-center">
        <div id="step3-icon" class="text-5xl mb-5">🎬</div>
        <h3 id="step3-title" class="title-font text-xl font-semibold text-amber-400 mb-2">Video Generation In Progress</h3>

        <!-- Progress bar -->
        <div class="max-w-md mx-auto mb-2">
          <div class="flex justify-between text-xs text-gray-500 mb-1">
            <span id="progress-stage-label">Starting pipeline...</span>
            <span id="progress-percent">0%</span>
          </div>
          <div class="w-full bg-gray-800 rounded-full h-3 overflow-hidden">
            <div id="progress-bar"
              class="h-3 rounded-full transition-all duration-1000 ease-linear"
              style="width:0%; background: linear-gradient(90deg, #f59e0b, #fbbf24);">
            </div>
          </div>
          <div class="flex justify-between text-xs text-gray-600 mt-1">
            <span id="realtime-badge" class="text-gray-700"></span>
            <span><span id="progress-elapsed">0:00</span> elapsed</span>
          </div>
        </div>

        <!-- Pipeline steps -->
        <div class="bg-gray-800 rounded-xl p-5 text-left text-sm space-y-3 max-w-md mx-auto mb-6 mt-4">
          <div class="flex items-center gap-3 text-gray-300">
            <span class="text-green-400">✓</span> Text cleaned and processed
          </div>
          <div class="flex items-center gap-3 text-gray-300">
            <span class="text-green-400">✓</span> Sent to n8n workflow
          </div>
          <div id="step-perplexity" class="flex items-center gap-3 text-gray-400">
            <span id="icon-perplexity" class="text-gray-600">○</span> Perplexity AI generating 20 scenes...
          </div>
          <div id="step-fal" class="flex items-center gap-3 text-gray-400">
            <span id="icon-fal" class="text-gray-600">○</span> fal.ai generating FLUX images + Kling video clips...
          </div>
          <div id="step-json2video" class="flex items-center gap-3 text-gray-400">
            <span id="icon-json2video" class="text-gray-600">○</span> JSON2Video assembling final video...
          </div>
        </div>

        <!-- Video ready panel (hidden until done) -->
        <div id="video-ready-panel" class="hidden mb-6">
          <div class="bg-green-900/30 border border-green-700 rounded-xl p-5 max-w-md mx-auto">
            <p class="text-green-400 font-semibold mb-3">🎉 Your video is ready!</p>
            <a id="video-download-link" href="#" target="_blank"
              class="block w-full bg-green-600 hover:bg-green-500 text-white font-semibold py-3 rounded-xl transition-colors text-center">
              ⬇ Download Video
            </a>
          </div>
        </div>

        <button
          onclick="startOver()"
          class="text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-6 py-2 rounded-lg transition-colors"
        >
          Generate Another Video
        </button>
      </div>
    </div>

    <!-- Step 4 divider -->
    <div class="flex items-center gap-4 mt-12 mb-6">
      <div class="flex-1 h-px bg-gray-800"></div>
      <span class="text-xs text-gray-600 font-semibold tracking-widest uppercase">Post-Production</span>
      <div class="flex-1 h-px bg-gray-800"></div>
    </div>

    <!-- ── STEP 4: Post-Production ── -->
    <div id="step4">
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-6">

        <!-- Header row -->
        <div class="flex items-start justify-between mb-5">
          <div class="flex items-start gap-3">
            <div class="w-7 h-7 rounded-full bg-purple-600 text-white font-bold flex items-center justify-center text-xs flex-shrink-0 mt-0.5">4</div>
            <div>
              <h3 class="text-base font-semibold text-white">Post-Production</h3>
              <p class="text-sm text-gray-400 mt-0.5">Add intro, outros &amp; logo to your downloaded raw video.</p>
            </div>
          </div>
          <!-- File status badge + refresh -->
          <div class="flex items-center gap-2 flex-shrink-0">
            <div id="raw-file-badge" class="text-xs px-3 py-1 rounded-full bg-gray-800 text-gray-500">
              ○ Checking...
            </div>
            <button onclick="checkRawFiles()" title="Refresh"
              class="text-xs text-gray-500 hover:text-gray-200 border border-gray-700 hover:border-gray-500 px-2.5 py-1 rounded-lg transition-colors">
              ↺
            </button>
          </div>
        </div>

        <!-- Where to put the file (helper text) -->
        <p id="raw-hint" class="text-xs text-gray-600 mb-4">
          Drop your downloaded raw MP4 into <code class="text-gray-400">output/raw/</code> then click ↺ to refresh.
        </p>

        <!-- File selector (shown when >1 file found) -->
        <div id="file-selector-wrap" class="mb-4 hidden">
          <label class="text-xs text-gray-500 mb-1 block">Select raw video to render</label>
          <select id="file-selector"
            class="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-purple-500">
          </select>
        </div>

        <!-- Start button + error -->
        <div class="flex items-center gap-3 mb-5">
          <button id="render-btn" onclick="startRender()" disabled
            class="bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold px-6 py-2.5 rounded-xl transition-colors duration-200 flex items-center gap-2">
            <span id="render-btn-text">▶ Start Rendering</span>
          </button>
          <span id="render-error" class="text-red-400 text-sm hidden"></span>
        </div>

        <!-- Progress section (hidden until render starts) -->
        <div id="render-progress-wrap" class="hidden">
          <div class="flex justify-between text-xs text-gray-500 mb-1">
            <span id="render-stage-label">Preparing...</span>
            <span id="render-percent">0%</span>
          </div>
          <div class="w-full bg-gray-800 rounded-full h-3 overflow-hidden mb-4">
            <div id="render-bar"
              class="h-3 rounded-full transition-all duration-700 ease-linear"
              style="width:0%; background: linear-gradient(90deg,#7c3aed,#a855f7);">
            </div>
          </div>
          <!-- Stage steps -->
          <div class="bg-gray-800 rounded-xl p-4 space-y-2.5 text-sm">
            <div id="rstep-normalize" class="flex items-center gap-2 text-gray-400">
              <span id="ricon-normalize" class="text-gray-600">○</span> Normalizing segments (fps · audio · pixel format)
            </div>
            <div id="rstep-concat" class="flex items-center gap-2 text-gray-400">
              <span id="ricon-concat" class="text-gray-600">○</span> Concatenating: intro → video → outro 1 → 2 → 3
            </div>
            <div id="rstep-logo" class="flex items-center gap-2 text-gray-400">
              <span id="ricon-logo" class="text-gray-600">○</span> Overlaying logo watermark
            </div>
          </div>
        </div>

        <!-- Download panel (shown when done) -->
        <div id="render-done-panel" class="hidden mt-4">
          <div class="bg-purple-900/30 border border-purple-700 rounded-xl p-5">
            <p class="text-purple-300 font-semibold mb-3">🎉 Post-production complete!</p>
            <a id="render-download-link" href="#"
              class="block w-full bg-purple-600 hover:bg-purple-500 text-white font-semibold py-3 rounded-xl transition-colors text-center">
              ⬇ Download Final Video
            </a>
          </div>
        </div>

      </div>
    </div>

    <!-- Step 5 divider -->
    <div class="flex items-center gap-4 mt-8 mb-6">
      <div class="flex-1 h-px bg-gray-800"></div>
      <span class="text-xs text-gray-600 font-semibold tracking-widest uppercase">YouTube Upload</span>
      <div class="flex-1 h-px bg-gray-800"></div>
    </div>

    <!-- ── STEP 5: YouTube Upload ── -->
    <div id="step5">
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-6">

        <!-- Header row -->
        <div class="flex items-start justify-between mb-5">
          <div class="flex items-start gap-3">
            <div class="w-7 h-7 rounded-full bg-red-700 text-white font-bold flex items-center justify-center text-xs flex-shrink-0 mt-0.5">5</div>
            <div>
              <h3 class="text-base font-semibold text-white">Upload to YouTube</h3>
              <p class="text-sm text-gray-400 mt-0.5">Upload your final video as an unlisted draft — publish from YouTube Studio when ready.</p>
            </div>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <div id="final-file-badge" class="text-xs px-3 py-1 rounded-full bg-gray-800 text-gray-500">
              ○ Checking...
            </div>
            <button onclick="checkFinalFiles()" title="Refresh"
              class="text-xs text-gray-500 hover:text-gray-200 border border-gray-700 hover:border-gray-500 px-2.5 py-1 rounded-lg transition-colors">
              ↺
            </button>
          </div>
        </div>

        <!-- Helper text (shown when no files) -->
        <p id="final-hint" class="text-xs text-gray-600 mb-4 hidden">
          No final videos found in <code class="text-gray-400">output/</code>. Run post-production (Step 4) first.
        </p>

        <!-- File selector -->
        <div id="upload-file-selector-wrap" class="mb-4 hidden">
          <label class="text-xs text-gray-500 mb-1 block">Select final video to upload</label>
          <select id="upload-file-selector"
            class="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-red-500">
          </select>
        </div>

        <!-- Scripture reference input -->
        <div class="mb-5">
          <label class="text-xs text-gray-500 mb-1 block">Scripture reference <span class="text-gray-600">(used for title, tags &amp; thumbnail)</span></label>
          <input
            id="upload-scripture"
            type="text"
            placeholder='e.g. Matthew 10  or  1 Kings 3'
            class="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500"
          />
        </div>

        <!-- Upload button + error -->
        <div class="flex items-center gap-3 mb-5">
          <button id="upload-btn" onclick="startUpload()" disabled
            class="bg-red-700 hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold px-6 py-2.5 rounded-xl transition-colors duration-200 flex items-center gap-2">
            <span id="upload-btn-text">▶ Upload to YouTube</span>
          </button>
          <span id="upload-error" class="text-red-400 text-sm hidden"></span>
        </div>

        <!-- Progress section -->
        <div id="upload-progress-wrap" class="hidden">
          <div class="flex justify-between text-xs text-gray-500 mb-1">
            <span id="upload-stage-label">Preparing...</span>
            <span id="upload-percent">0%</span>
          </div>
          <div class="w-full bg-gray-800 rounded-full h-3 overflow-hidden mb-4">
            <div id="upload-bar"
              class="h-3 rounded-full transition-all duration-700 ease-linear"
              style="width:0%; background: linear-gradient(90deg,#b91c1c,#ef4444);">
            </div>
          </div>
          <!-- Stage steps -->
          <div class="bg-gray-800 rounded-xl p-4 space-y-2.5 text-sm">
            <div id="ustep-upload" class="flex items-center gap-2 text-gray-400">
              <span id="uicon-upload" class="text-gray-600">○</span> Uploading video to YouTube
            </div>
            <div id="ustep-thumb" class="flex items-center gap-2 text-gray-400">
              <span id="uicon-thumb" class="text-gray-600">○</span> Generating &amp; setting thumbnail
            </div>
          </div>
        </div>

        <!-- Done panel -->
        <div id="upload-done-panel" class="hidden mt-4">
          <div class="bg-red-900/20 border border-red-800 rounded-xl p-5">
            <p class="text-red-300 font-semibold mb-4">🎉 Uploaded as unlisted draft!</p>
            <div class="space-y-2.5">
              <a id="upload-video-link" href="#" target="_blank"
                class="flex items-center gap-2 text-sm text-white bg-red-700 hover:bg-red-600 font-semibold py-2.5 px-4 rounded-xl transition-colors justify-center">
                ▶ View on YouTube
              </a>
              <a id="upload-studio-link" href="#" target="_blank"
                class="flex items-center gap-2 text-sm text-gray-300 hover:text-white border border-gray-700 hover:border-gray-500 py-2.5 px-4 rounded-xl transition-colors justify-center">
                ✏ Edit in YouTube Studio
              </a>
            </div>
            <p class="text-xs text-gray-500 mt-3 text-center">Video is unlisted — go to Studio to publish it publicly.</p>
          </div>
        </div>

      </div>
    </div>

  </main>

  <script>
    // ── State ──
    let allSections = [];
    let activeSectionIndex = 0;
    let pollTimer = null;

    // ── Helpers ──────────────────────────────────────────────────────────────
    function fmt(s) {
      s = Math.floor(s);
      const m = Math.floor(s / 60), sec = s % 60;
      return m + ':' + String(sec).padStart(2, '0');
    }

    function setStageIcon(id, state) {
      const icon = document.getElementById('icon-' + id);
      const row  = document.getElementById('step-' + id);
      if (state === 'done') {
        icon.textContent = '✓';
        icon.className = 'text-green-400';
        row.className = 'flex items-center gap-3 text-gray-300';
      } else if (state === 'active') {
        icon.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px"></span>';
        row.className = 'flex items-center gap-3 text-white font-medium';
      } else {
        icon.textContent = '○';
        icon.className = 'text-gray-600';
        row.className = 'flex items-center gap-3 text-gray-400';
      }
    }

    function setBar(pct, label, realtime) {
      document.getElementById('progress-bar').style.width = Math.min(pct, 100) + '%';
      document.getElementById('progress-percent').textContent = Math.min(pct, 100) + '%';
      document.getElementById('progress-stage-label').textContent = label;
      const badge = document.getElementById('realtime-badge');
      if (realtime) {
        badge.textContent = '● Live';
        badge.className = 'text-green-500 font-medium';
      } else {
        badge.textContent = '~ Estimated';
        badge.className = 'text-gray-600';
      }
    }

    // ── Polling ───────────────────────────────────────────────────────────────
    function startPolling() {
      stopPolling();
      pollStatus();  // immediate first call
      pollTimer = setInterval(pollStatus, 6000);  // then every 6 s
    }

    function stopPolling() {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    async function pollStatus() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) return;
        const data = await res.json();
        applyStatus(data);
      } catch (_) { /* ignore network errors */ }
    }

    function applyStatus(data) {
      const elapsed = data.elapsed || 0;
      document.getElementById('progress-elapsed').textContent = fmt(elapsed);

      switch (data.phase) {
        case 'perplexity': {
          setStageIcon('perplexity', 'active');
          setStageIcon('fal', 'pending');
          setStageIcon('json2video', 'pending');
          const pct = Math.min(Math.floor(elapsed / 90 * 10), 10);
          setBar(pct, 'Perplexity AI generating 20 scenes...', false);
          break;
        }
        case 'fal_generation': {
          setStageIcon('perplexity', 'done');
          setStageIcon('fal', 'active');
          setStageIcon('json2video', 'pending');
          const sceneEst = data.scenes_estimated || 0;
          const pct = 10 + Math.min(Math.floor(sceneEst / 20 * 75), 75);
          setBar(pct, 'fal.ai: generating scene ' + sceneEst + '/20 (FLUX image + Kling video)...', false);
          break;
        }
        case 'json2video': {
          setStageIcon('perplexity', 'done');
          setStageIcon('fal', 'done');
          setStageIcon('json2video', 'active');
          const rt = data.realtime === true;
          const j2vPct = data.status === 'queued'
            ? 86
            : Math.min(86 + Math.floor((elapsed - 2000) / 420 * 13), 99);
          const label = data.status === 'queued'
            ? 'JSON2Video: queued — waiting for render slot...'
            : 'JSON2Video assembling final video...';
          setBar(j2vPct, label, rt);
          break;
        }
        case 'done': {
          stopPolling();
          setStageIcon('perplexity', 'done');
          setStageIcon('fal', 'done');
          setStageIcon('json2video', 'done');
          setBar(100, 'Video ready!', true);
          document.getElementById('step3-icon').textContent = '✅';
          document.getElementById('step3-title').textContent = 'Your Video Is Ready';
          document.getElementById('step3-title').className = 'title-font text-xl font-semibold text-green-400 mb-2';
          if (data.video_url) {
            const link = document.getElementById('video-download-link');
            link.href = data.video_url;
            document.getElementById('video-ready-panel').classList.remove('hidden');
          }
          break;
        }
        case 'error': {
          stopPolling();
          setBar(0, '⚠ Error: ' + (data.message || 'Generation failed'), false);
          break;
        }
      }
    }

    // ── Character counter ─────────────────────────────────────────────────────
    document.getElementById('raw-text').addEventListener('input', function() {
      const count = this.value.length;
      const words = this.value.trim() ? this.value.trim().split(/\\s+/).length : 0;
      document.getElementById('char-count').textContent = `${words.toLocaleString()} words · ${count.toLocaleString()} characters`;
    });

    // ── Step 1: Convert ───────────────────────────────────────────────────────
    async function convertText() {
      const rawText = document.getElementById('raw-text').value.trim();
      if (!rawText) {
        showError('convert-error', 'Please paste some biblical text first.');
        return;
      }

      const btn = document.getElementById('convert-btn');
      btn.innerHTML = '<span class="spinner"></span><span>Cleaning...</span>';
      btn.disabled = true;
      hideError('convert-error');

      try {
        const res = await fetch('/api/clean', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: rawText }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Cleaning failed.');
        }

        const data = await res.json();
        allSections = data.sections;
        activeSectionIndex = 0;
        showStep2();
      } catch (e) {
        showError('convert-error', e.message);
      } finally {
        btn.innerHTML = '<span>Convert &amp; Clean</span>';
        btn.disabled = false;
      }
    }

    function showStep2() {
      const tabsEl = document.getElementById('section-tabs');
      tabsEl.innerHTML = '';
      if (allSections.length > 1) {
        tabsEl.classList.remove('hidden');
        allSections.forEach((s, i) => {
          const btn = document.createElement('button');
          btn.textContent = `Section ${i + 1}`;
          btn.className = `px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            i === 0 ? 'bg-amber-500 text-black' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`;
          btn.onclick = () => switchSection(i);
          tabsEl.appendChild(btn);
        });
      }
      displaySection(0);
      setStep(2);
    }

    function switchSection(index) {
      activeSectionIndex = index;
      displaySection(index);
      const tabs = document.querySelectorAll('#section-tabs button');
      tabs.forEach((t, i) => {
        t.className = `px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
          i === index ? 'bg-amber-500 text-black' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
        }`;
      });
    }

    function displaySection(index) {
      const s = allSections[index];
      document.getElementById('cleaned-text').value = s.text;
      document.getElementById('stats-bar').innerHTML = `
        <span>📝 <strong class="text-white">${s.word_count.toLocaleString()}</strong> words</span>
        <span>⏱ ~<strong class="text-amber-400">${s.estimated_minutes} min</strong> video</span>
        <span>🎬 ~${s.estimated_scenes} scenes</span>
        ${allSections.length > 1 ? `<span class="ml-auto text-amber-500">Section ${index + 1} of ${allSections.length}</span>` : ''}
      `;
    }

    // ── Step 2: Approve ───────────────────────────────────────────────────────
    async function approveText() {
      const approvedText = document.getElementById('cleaned-text').value.trim();
      if (!approvedText) {
        showError('approve-error', 'Text cannot be empty.');
        return;
      }

      const btn = document.getElementById('approve-btn');
      btn.innerHTML = '<span class="spinner"></span><span>Sending to n8n...</span>';
      btn.disabled = true;
      hideError('approve-error');

      try {
        const res = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: approvedText, section_index: activeSectionIndex }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Failed to trigger workflow.');
        }

        setStep(3);
        startPolling();
      } catch (e) {
        showError('approve-error', e.message);
      } finally {
        btn.innerHTML = '<span>✓ Approve &amp; Generate Video</span>';
        btn.disabled = false;
      }
    }

    // ── Navigation ────────────────────────────────────────────────────────────
    function backToStep1() { setStep(1); }

    function startOver() {
      stopPolling();
      // Reset step 3 visual state
      ['perplexity', 'fal', 'json2video'].forEach(id => setStageIcon(id, 'pending'));
      document.getElementById('progress-bar').style.width = '0%';
      document.getElementById('progress-percent').textContent = '0%';
      document.getElementById('progress-elapsed').textContent = '0:00';
      document.getElementById('progress-stage-label').textContent = 'Starting pipeline...';
      document.getElementById('realtime-badge').textContent = '';
      document.getElementById('video-ready-panel').classList.add('hidden');
      document.getElementById('step3-icon').textContent = '🎬';
      document.getElementById('step3-title').textContent = 'Video Generation In Progress';
      document.getElementById('step3-title').className = 'title-font text-xl font-semibold text-amber-400 mb-2';
      setStep(1);
      document.getElementById('raw-text').value = '';
      document.getElementById('char-count').textContent = '0 characters';
    }

    function setStep(n) {
      [1, 2, 3].forEach(i => {
        document.getElementById(`step${i}`).classList.toggle('hidden', i !== n);
      });
      [1, 2, 3].forEach(i => {
        const dot    = document.getElementById(`step-dot-${i}`);
        const circle = dot.querySelector('div');
        if (i < n) {
          dot.classList.remove('opacity-40');
          circle.className = 'w-7 h-7 rounded-full bg-green-600 text-white font-bold flex items-center justify-center text-xs';
        } else if (i === n) {
          dot.classList.remove('opacity-40');
          circle.className = 'w-7 h-7 rounded-full bg-amber-500 text-black font-bold flex items-center justify-center text-xs';
        } else {
          dot.classList.add('opacity-40');
          circle.className = 'w-7 h-7 rounded-full bg-gray-700 text-gray-300 font-bold flex items-center justify-center text-xs';
        }
      });
    }

    function showError(id, msg) { const el = document.getElementById(id); el.textContent = '⚠ ' + msg; el.classList.remove('hidden'); }
    function hideError(id) { document.getElementById(id).classList.add('hidden'); }

    // ── Step 4: Post-Production ───────────────────────────────────────────────
    let renderPollTimer = null;
    let rawFiles = [];

    function setRenderStageIcon(id, state) {
      const icon = document.getElementById('ricon-' + id);
      const row  = document.getElementById('rstep-' + id);
      if (state === 'done') {
        icon.textContent = '✓';
        icon.className = 'text-green-400';
        row.className = 'flex items-center gap-2 text-gray-300';
      } else if (state === 'active') {
        icon.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px"></span>';
        row.className = 'flex items-center gap-2 text-white font-medium';
      } else {
        icon.textContent = '○';
        icon.className = 'text-gray-600';
        row.className = 'flex items-center gap-2 text-gray-400';
      }
    }

    async function checkRawFiles() {
      const badge = document.getElementById('raw-file-badge');
      badge.textContent = '○ Checking...';
      badge.className = 'text-xs px-3 py-1 rounded-full bg-gray-800 text-gray-500';
      try {
        const res  = await fetch('/api/render/check');
        const data = await res.json();
        rawFiles = data.files || [];

        const btn         = document.getElementById('render-btn');
        const selectorWrap = document.getElementById('file-selector-wrap');
        const selector    = document.getElementById('file-selector');
        const hint        = document.getElementById('raw-hint');

        if (rawFiles.length === 0) {
          badge.textContent = '○ No raw video found';
          badge.className = 'text-xs px-3 py-1 rounded-full bg-gray-800 text-gray-500';
          btn.disabled = true;
          selectorWrap.classList.add('hidden');
          hint.classList.remove('hidden');
        } else {
          badge.textContent = '● ' + rawFiles.length + ' raw video' + (rawFiles.length > 1 ? 's' : '') + ' ready';
          badge.className = 'text-xs px-3 py-1 rounded-full bg-green-900/50 text-green-400 border border-green-800';
          hint.classList.add('hidden');
          selector.innerHTML = rawFiles.map(f => '<option value="' + f + '">' + f + '</option>').join('');
          selectorWrap.classList.toggle('hidden', rawFiles.length <= 1);
          // Check if render already running
          const sres  = await fetch('/api/render/status');
          const sdata = await sres.json();
          if (sdata.status === 'running') {
            btn.disabled = true;
            document.getElementById('render-btn-text').textContent = 'Rendering...';
            document.getElementById('render-progress-wrap').classList.remove('hidden');
            applyRenderStatus(sdata);
            startRenderPolling();
          } else if (sdata.status === 'done') {
            btn.disabled = false;
            document.getElementById('render-btn-text').textContent = '▶ Render Again';
            document.getElementById('render-progress-wrap').classList.remove('hidden');
            applyRenderStatus(sdata);
          } else {
            btn.disabled = false;
          }
        }
      } catch(e) {
        badge.textContent = '⚠ Error';
        badge.className = 'text-xs px-3 py-1 rounded-full bg-red-900/30 text-red-400';
      }
    }

    async function startRender() {
      const selector = document.getElementById('file-selector');
      const fileName = rawFiles.length === 1 ? rawFiles[0] : selector.value;
      if (!fileName) return;

      const btn = document.getElementById('render-btn');
      btn.disabled = true;
      document.getElementById('render-btn-text').innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px"></span> Starting...';
      hideError('render-error');
      document.getElementById('render-done-panel').classList.add('hidden');

      try {
        const res  = await fetch('/api/render/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ file: fileName }),
        });
        const data = await res.json();
        if (data.status === 'error') throw new Error(data.message);

        // Reset stage icons and show progress bar
        ['normalize', 'concat', 'logo'].forEach(id => setRenderStageIcon(id, 'pending'));
        document.getElementById('render-bar').style.width = '0%';
        document.getElementById('render-percent').textContent = '0%';
        document.getElementById('render-stage-label').textContent = 'Starting FFmpeg...';
        document.getElementById('render-progress-wrap').classList.remove('hidden');
        document.getElementById('render-btn-text').textContent = 'Rendering...';
        startRenderPolling();
      } catch(e) {
        btn.disabled = false;
        document.getElementById('render-btn-text').textContent = '▶ Start Rendering';
        showError('render-error', e.message);
      }
    }

    function startRenderPolling() {
      stopRenderPolling();
      pollRenderStatus();
      renderPollTimer = setInterval(pollRenderStatus, 3000);
    }

    function stopRenderPolling() {
      if (renderPollTimer) { clearInterval(renderPollTimer); renderPollTimer = null; }
    }

    async function pollRenderStatus() {
      try {
        const res  = await fetch('/api/render/status');
        const data = await res.json();
        applyRenderStatus(data);
      } catch(_) {}
    }

    function applyRenderStatus(data) {
      const pct   = data.progress || 0;
      const label = data.label || '';
      document.getElementById('render-bar').style.width = pct + '%';
      document.getElementById('render-percent').textContent = pct + '%';
      if (label) document.getElementById('render-stage-label').textContent = label;

      // Update stage icons by progress threshold
      if (pct < 1) {
        ['normalize','concat','logo'].forEach(id => setRenderStageIcon(id, 'pending'));
      } else if (pct < 65) {
        setRenderStageIcon('normalize', 'active');
        setRenderStageIcon('concat', 'pending');
        setRenderStageIcon('logo', 'pending');
      } else if (pct < 85) {
        setRenderStageIcon('normalize', 'done');
        setRenderStageIcon('concat', 'active');
        setRenderStageIcon('logo', 'pending');
      } else if (pct < 100) {
        setRenderStageIcon('normalize', 'done');
        setRenderStageIcon('concat', 'done');
        setRenderStageIcon('logo', 'active');
      } else {
        setRenderStageIcon('normalize', 'done');
        setRenderStageIcon('concat', 'done');
        setRenderStageIcon('logo', 'done');
      }

      if (data.status === 'done') {
        stopRenderPolling();
        document.getElementById('render-done-panel').classList.remove('hidden');
        document.getElementById('render-btn-text').textContent = '▶ Render Again';
        document.getElementById('render-btn').disabled = false;
        if (data.output) {
          document.getElementById('render-download-link').href =
            '/api/render/download/' + encodeURIComponent(data.output);
        }
      } else if (data.status === 'error') {
        stopRenderPolling();
        document.getElementById('render-stage-label').textContent = '⚠ ' + (data.error || 'Render failed.');
        document.getElementById('render-btn-text').textContent = '▶ Try Again';
        document.getElementById('render-btn').disabled = false;
      }
    }

    // ── Step 5: YouTube Upload ────────────────────────────────────────────────
    let uploadPollTimer = null;
    let finalFiles = [];

    function setUploadStageIcon(id, state) {
      const icon = document.getElementById('uicon-' + id);
      const row  = document.getElementById('ustep-' + id);
      if (state === 'done') {
        icon.textContent = '✓';
        icon.className = 'text-green-400';
        row.className = 'flex items-center gap-2 text-gray-300';
      } else if (state === 'active') {
        icon.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px"></span>';
        row.className = 'flex items-center gap-2 text-white font-medium';
      } else {
        icon.textContent = '○';
        icon.className = 'text-gray-600';
        row.className = 'flex items-center gap-2 text-gray-400';
      }
    }

    async function checkFinalFiles() {
      const badge = document.getElementById('final-file-badge');
      badge.textContent = '○ Checking...';
      badge.className = 'text-xs px-3 py-1 rounded-full bg-gray-800 text-gray-500';
      try {
        const res  = await fetch('/api/upload/check');
        const data = await res.json();
        finalFiles = data.files || [];

        const btn          = document.getElementById('upload-btn');
        const selectorWrap = document.getElementById('upload-file-selector-wrap');
        const selector     = document.getElementById('upload-file-selector');
        const hint         = document.getElementById('final-hint');

        if (finalFiles.length === 0) {
          badge.textContent = '○ No final video found';
          badge.className = 'text-xs px-3 py-1 rounded-full bg-gray-800 text-gray-500';
          btn.disabled = true;
          selectorWrap.classList.add('hidden');
          hint.classList.remove('hidden');
        } else {
          badge.textContent = '● ' + finalFiles.length + ' video' + (finalFiles.length > 1 ? 's' : '') + ' ready';
          badge.className = 'text-xs px-3 py-1 rounded-full bg-green-900/50 text-green-400 border border-green-800';
          hint.classList.add('hidden');
          selector.innerHTML = finalFiles.map(f => '<option value="' + f + '">' + f + '</option>').join('');
          selectorWrap.classList.toggle('hidden', finalFiles.length <= 1);

          // Check if upload already running/done
          const sres  = await fetch('/api/upload/status');
          const sdata = await sres.json();
          if (sdata.status === 'running') {
            btn.disabled = true;
            document.getElementById('upload-btn-text').textContent = 'Uploading...';
            document.getElementById('upload-progress-wrap').classList.remove('hidden');
            applyUploadStatus(sdata);
            startUploadPolling();
          } else if (sdata.status === 'done') {
            btn.disabled = false;
            document.getElementById('upload-btn-text').textContent = '▶ Upload Another';
            document.getElementById('upload-progress-wrap').classList.remove('hidden');
            applyUploadStatus(sdata);
          } else {
            btn.disabled = false;
          }
        }
      } catch(e) {
        badge.textContent = '⚠ Error';
        badge.className = 'text-xs px-3 py-1 rounded-full bg-red-900/30 text-red-400';
      }
    }

    async function startUpload() {
      const selector   = document.getElementById('upload-file-selector');
      const scripture  = document.getElementById('upload-scripture').value.trim();
      const fileName   = finalFiles.length === 1 ? finalFiles[0] : selector.value;

      if (!scripture) {
        showError('upload-error', 'Enter a scripture reference (e.g. Matthew 10).');
        return;
      }
      if (!fileName) return;

      const btn = document.getElementById('upload-btn');
      btn.disabled = true;
      document.getElementById('upload-btn-text').innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px"></span> Starting...';
      hideError('upload-error');
      document.getElementById('upload-done-panel').classList.add('hidden');

      try {
        const res  = await fetch('/api/upload/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ file: fileName, scripture }),
        });
        const data = await res.json();
        if (data.status === 'error') throw new Error(data.message);

        ['upload', 'thumb'].forEach(id => setUploadStageIcon(id, 'pending'));
        document.getElementById('upload-bar').style.width = '0%';
        document.getElementById('upload-percent').textContent = '0%';
        document.getElementById('upload-stage-label').textContent = 'Starting upload...';
        document.getElementById('upload-progress-wrap').classList.remove('hidden');
        document.getElementById('upload-btn-text').textContent = 'Uploading...';
        startUploadPolling();
      } catch(e) {
        btn.disabled = false;
        document.getElementById('upload-btn-text').textContent = '▶ Upload to YouTube';
        showError('upload-error', e.message);
      }
    }

    function startUploadPolling() {
      stopUploadPolling();
      pollUploadStatus();
      uploadPollTimer = setInterval(pollUploadStatus, 2000);
    }

    function stopUploadPolling() {
      if (uploadPollTimer) { clearInterval(uploadPollTimer); uploadPollTimer = null; }
    }

    async function pollUploadStatus() {
      try {
        const res  = await fetch('/api/upload/status');
        const data = await res.json();
        applyUploadStatus(data);
      } catch(_) {}
    }

    function applyUploadStatus(data) {
      const pct   = data.progress || 0;
      const label = data.label || '';
      document.getElementById('upload-bar').style.width = pct + '%';
      document.getElementById('upload-percent').textContent = pct + '%';
      if (label) document.getElementById('upload-stage-label').textContent = label;

      if (pct < 89) {
        setUploadStageIcon('upload', pct > 0 ? 'active' : 'pending');
        setUploadStageIcon('thumb', 'pending');
      } else if (pct < 100) {
        setUploadStageIcon('upload', 'done');
        setUploadStageIcon('thumb', 'active');
      } else {
        setUploadStageIcon('upload', 'done');
        setUploadStageIcon('thumb', 'done');
      }

      if (data.status === 'done') {
        stopUploadPolling();
        document.getElementById('upload-done-panel').classList.remove('hidden');
        document.getElementById('upload-btn-text').textContent = '▶ Upload Another';
        document.getElementById('upload-btn').disabled = false;
        if (data.video_url) {
          document.getElementById('upload-video-link').href = data.video_url;
        }
        if (data.studio_url) {
          document.getElementById('upload-studio-link').href = data.studio_url;
        }
      } else if (data.status === 'error') {
        stopUploadPolling();
        document.getElementById('upload-stage-label').textContent = '⚠ ' + (data.error || 'Upload failed.');
        document.getElementById('upload-btn-text').textContent = '▶ Try Again';
        document.getElementById('upload-btn').disabled = false;
      }
    }

    // Auto-check files on page load
    window.addEventListener('load', () => { checkRawFiles(); checkFinalFiles(); });

  </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def landing_page():
    return HTMLResponse(content=LANDING_PAGE)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _webhook = os.getenv("N8N_WEBHOOK_URL", "")
    _j2v     = os.getenv("JSON2VIDEO_API_KEY", "")

    if not _webhook:
        print("\n⚠  WARNING: N8N_WEBHOOK_URL is not set in your .env file.")
        print("   The /api/generate endpoint will not work until you set it.\n")
    else:
        print(f"\n✓ n8n webhook configured")

    if not _j2v:
        print("⚠  WARNING: JSON2VIDEO_API_KEY is not set — live render tracking disabled.")
        print("   Add it to .env to enable real-time status polling.\n")
    else:
        print("✓ JSON2Video API key configured — real-time tracking enabled\n")

    print("Starting Biblical Cinematic Generator at http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
