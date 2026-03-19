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
from typing import Optional

# find_dotenv() walks up the directory tree from this file to locate .env
load_dotenv(find_dotenv(), override=True)

# Make the text_processor module importable
sys.path.insert(0, str(Path(__file__).parent.parent / "text_processor"))

# Make the custom-script router importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "custom-script"))

import json as json_module
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

# Mount custom script router
try:
    from router import custom_router
    app.include_router(custom_router, prefix="/custom")
    print("Custom Script router mounted at /custom")
except ImportError as e:
    print(f"WARNING: Custom Script router not loaded: {e}")

# Mount biblical v9 pipeline router (no n8n)
try:
    from biblical_pipeline import biblical_router
    app.include_router(biblical_router, prefix="/v9")
    print("Biblical v9 pipeline router mounted at /v9")
except ImportError as e:
    print(f"WARNING: Biblical v9 router not loaded: {e}")

# ── Generation state (single-user, in-memory) ─────────────────────────────────
# Resets each time a new video is triggered.
generation_state: dict = {
    "started_at": None,    # datetime (UTC) when /api/generate was called
    "project_id": None,    # JSON2Video project ID once discovered
    "video_url":  None,    # Final MP4 URL when render completes
}

JSON2VIDEO_BASE = "https://api.json2video.com/v2/movies"

# ── Bible chapter data (loaded once at startup) ──────────────────────────────
_BIBLE_JSON_PATH = Path(__file__).parent.parent / "assets" / "bible_chapters.json"
_BIBLE_DATA: list = []  # populated below

# OT/Apocrypha/NT grouping for the dropdown
_OT_BOOKS = {
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalms", "Proverbs", "Ecclesiastes", "Song of Songs", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel",
    "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
    "Zephaniah", "Haggai", "Zechariah", "Malachi",
}
_APOCRYPHA_BOOKS = {
    "Tobit", "Judith", "Esther (Greek)", "Wisdom",
    "Sirach (Ecclesiasticus)", "Baruch", "Letter of Jeremiah",
    "Prayer of Azariah and the Song of the Three Jews", "Susanna",
    "Bel and the Dragon", "1 Maccabees", "2 Maccabees",
    "1 Esdras", "2 Esdras", "Prayer of Manassah",
}

if _BIBLE_JSON_PATH.exists():
    with open(_BIBLE_JSON_PATH, "r", encoding="utf-8") as _bf:
        _raw = json_module.load(_bf)
    _BIBLE_DATA = _raw.get("books", [])
    print(f"Loaded {len(_BIBLE_DATA)} Bible books from {_BIBLE_JSON_PATH.name}")
else:
    print(f"WARNING: Bible data not found at {_BIBLE_JSON_PATH}")

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
    book: Optional[str] = None
    chapter: Optional[str] = None


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
    model: str = "v1.6"  # Kling model version (v1.6, v2.1, v3.0)


class GenerateResponse(BaseModel):
    status: str
    message: str


class RenderRequest(BaseModel):
    file: str


class UploadRequest(BaseModel):
    file: str
    scripture: str


# ── Bible Selector API ────────────────────────────────────────────────────────

@app.get("/api/bible/books")
async def api_bible_books():
    """Return list of all Bible books with chapter counts, grouped by testament."""
    ot, apoc, nt = [], [], []
    for book in _BIBLE_DATA:
        entry = {"name": book["name"], "chapters": len(book["chapters"])}
        if book["name"] in _OT_BOOKS:
            ot.append(entry)
        elif book["name"] in _APOCRYPHA_BOOKS:
            apoc.append(entry)
        else:
            nt.append(entry)
    return {"old_testament": ot, "apocrypha": apoc, "new_testament": nt}


@app.get("/api/bible/chapter")
async def api_bible_chapter(book: str, chapter: str):
    """Return the full text of a specific Bible chapter."""
    for b in _BIBLE_DATA:
        if b["name"] == book:
            text = b["chapters"].get(chapter)
            if text:
                return {"text": text}
            raise HTTPException(status_code=404, detail=f"Chapter {chapter} not found in {book}")
    raise HTTPException(status_code=404, detail=f"Book '{book}' not found")


# ── Cinematic Intro Generator ─────────────────────────────────────────────────

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
         "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

def _number_to_words(n: int) -> str:
    """Convert 1-150 to words. E.g. 1 → 'One', 42 → 'Forty Two', 150 → 'One Hundred Fifty'."""
    if n <= 0:
        return str(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()
    h = n // 100
    remainder = n % 100
    result = _ONES[h] + " Hundred"
    if remainder:
        result += " " + _number_to_words(remainder)
    return result


async def _generate_cinematic_intro(book: str, chapter: str, passage_text: str) -> str:
    """Use GPT-4o-mini to generate a brief cinematic intro for the chapter."""
    chapter_word = _number_to_words(int(chapter)) if chapter.isdigit() else chapter

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=120,
            temperature=0.7,
            messages=[{
                "role": "system",
                "content": (
                    "You write brief cinematic introductions for King James Bible chapters. "
                    "These intros will be narrated by a voice-over artist at the start of a cinematic video."
                ),
            }, {
                "role": "user",
                "content": (
                    f"Write a cinematic introduction for {book}, Chapter {chapter_word} from the King James Bible.\n\n"
                    f"Rules:\n"
                    f"- Start with exactly: 'The Book of {book}. Chapter {chapter_word}.'\n"
                    f"- Then add 1-2 sentences summarizing what happens in this chapter in a dramatic, cinematic tone.\n"
                    f"- Use present tense (e.g., 'God speaks', 'Moses leads').\n"
                    f"- Keep the total under 40 words.\n"
                    f"- Do NOT use quotes or colons.\n\n"
                    f"Here is the beginning of the chapter text for context:\n"
                    f"{passage_text[:500]}"
                ),
            }],
        )
        intro = resp.choices[0].message.content.strip()
        return intro
    except Exception as e:
        # Fallback to static intro if AI fails
        print(f"[WARN] AI intro generation failed: {e}. Using static fallback.")
        return f"The Book of {book}. Chapter {chapter_word}."


# ── API Routes ────────────────────────────────────────────────────────────────

@app.post("/api/clean", response_model=CleanResponse)
async def api_clean(req: CleanRequest):
    """Clean and split raw biblical text into video-ready sections."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    cleaned = clean_text(req.text)
    cleaned = kjv_narration_fix(cleaned)
    cleaned = kjv_narration_fix(cleaned)  # Second pass catches cascading substitutions

    # Generate cinematic intro if book/chapter provided
    cinematic_intro = ""
    if req.book and req.chapter:
        cinematic_intro = await _generate_cinematic_intro(req.book, req.chapter, cleaned)

    words = split_into_words(cleaned)

    if not words:
        raise HTTPException(status_code=400, detail="No text remained after cleaning.")

    raw_sections = create_sections(words)

    sections: list[Section] = []
    for i, section_words in enumerate(raw_sections):
        formatted = format_section(section_words, i + 1)
        # Prepend cinematic intro to the first section only
        if i == 0 and cinematic_intro:
            formatted = cinematic_intro + "\n\n" + formatted.strip()
        else:
            formatted = formatted.strip()
        word_count = len(formatted.split())
        sections.append(
            Section(
                index=i,
                text=formatted,
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

    # Model → webhook mapping (published n8n workflows)
    KLING_WEBHOOKS = {
        "v1.6": "https://bmbautomations.app.n8n.cloud/webhook/biblical-v8-kling-v16",
        "v2.1": "https://bmbautomations.app.n8n.cloud/webhook/biblical-v8-kling-v21",
        "v3.0": "https://bmbautomations.app.n8n.cloud/webhook/biblical-v8-kling-v30",
    }

    N8N_WEBHOOK_URL = KLING_WEBHOOKS.get(req.model)
    if not N8N_WEBHOOK_URL:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{req.model}'. Choose from: {', '.join(KLING_WEBHOOKS.keys())}",
        )

    print(f"🎬 Generating with Kling {req.model} → {N8N_WEBHOOK_URL[:60]}...")

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
    .nav-tab { transition: all 0.2s ease; }
    .nav-tab:hover { background: rgba(245,158,11,0.1); }
    .nav-tab.active { border-bottom: 2px solid #f59e0b; color: #f59e0b; }
  </style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">

  <!-- Navigation -->
  <nav class="border-b border-gray-800 bg-gray-950 sticky top-0 z-50">
    <div class="max-w-4xl mx-auto flex items-center">
      <div class="text-amber-500 text-2xl px-4">✦</div>
      <a href="/" class="nav-tab active px-5 py-4 text-sm font-medium">Scripture Mode</a>
      <a href="/custom" class="nav-tab px-5 py-4 text-sm text-gray-400 font-medium">Custom Script Mode</a>
      <div class="ml-auto flex items-center gap-4 pr-4">
        <a href="#step4" onclick="document.getElementById('step4').scrollIntoView({behavior:'smooth'}); return false;"
          class="text-xs text-purple-400 hover:text-purple-300 border border-purple-800 hover:border-purple-600 px-3 py-1.5 rounded-lg transition-colors">
          ▼ Post-Production
        </a>
        <span class="text-xs text-gray-600">v8.0 · ~$7.31/video</span>
      </div>
    </div>
  </nav>

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
      <!-- Bible Chapter Selector -->
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-4">
        <div class="flex items-center justify-between mb-4 cursor-pointer" onclick="toggleBibleSelector()">
          <label class="block text-sm font-medium text-gray-300">
            Select from Bible <span class="text-gray-500 font-normal">(81 books, KJV + Apocrypha)</span>
          </label>
          <svg id="bible-selector-arrow" class="w-5 h-5 text-gray-400 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
        </div>
        <div id="bible-selector-panel" class="hidden">
          <div class="flex flex-wrap gap-3 items-end">
            <div class="flex-1 min-w-[200px]">
              <label class="block text-xs text-gray-500 mb-1">Book</label>
              <select id="bible-book" onchange="onBookChange()" class="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2.5 text-gray-100 text-sm focus:outline-none focus:border-amber-500">
                <option value="">-- Select a book --</option>
              </select>
            </div>
            <div class="w-32">
              <label class="block text-xs text-gray-500 mb-1">Chapter</label>
              <select id="bible-chapter" class="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2.5 text-gray-100 text-sm focus:outline-none focus:border-amber-500">
                <option value="">--</option>
              </select>
            </div>
            <button onclick="loadBibleChapter()" class="bg-amber-600 hover:bg-amber-500 text-black font-semibold px-5 py-2.5 rounded-lg transition-colors duration-200 text-sm">
              Load Chapter
            </button>
          </div>
          <p id="bible-load-status" class="text-xs text-gray-500 mt-2 hidden"></p>
        </div>
      </div>

      <!-- Text Input -->
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <label class="block text-sm font-medium text-gray-300 mb-3">
          Biblical Text <span class="text-gray-500 font-normal">(KJV scripture — any length)</span>
        </label>
        <textarea
          id="raw-text"
          rows="14"
          placeholder="Select a chapter above, or paste your KJV scripture here...&#10;&#10;Example: In the beginning God created the heaven and the earth..."
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

        <!-- Model selector -->
        <div class="mt-4 mb-4 p-4 bg-gray-800 rounded-xl border border-gray-700">
          <label class="block text-sm font-medium text-gray-300 mb-2">Kling AI Model</label>
          <div class="grid grid-cols-3 gap-3">
            <label class="relative cursor-pointer">
              <input type="radio" name="kling-model" value="v1.6" class="peer sr-only" checked>
              <div class="p-3 rounded-lg border-2 border-gray-600 peer-checked:border-amber-500 peer-checked:bg-amber-500/10 transition-all">
                <div class="text-sm font-semibold text-white">v1.6 Standard</div>
                <div class="text-xs text-gray-400 mt-1">Basic motion · Fastest</div>
                <div class="text-xs text-amber-400 mt-1 font-medium">~$4.50/video</div>
              </div>
            </label>
            <label class="relative cursor-pointer">
              <input type="radio" name="kling-model" value="v2.1" class="peer sr-only">
              <div class="p-3 rounded-lg border-2 border-gray-600 peer-checked:border-amber-500 peer-checked:bg-amber-500/10 transition-all">
                <div class="text-sm font-semibold text-white">v2.1 Standard</div>
                <div class="text-xs text-gray-400 mt-1">Better motion · Mid-tier</div>
                <div class="text-xs text-amber-400 mt-1 font-medium">~$5.50/video</div>
              </div>
            </label>
            <label class="relative cursor-pointer">
              <input type="radio" name="kling-model" value="v3.0" class="peer sr-only">
              <div class="p-3 rounded-lg border-2 border-gray-600 peer-checked:border-amber-500 peer-checked:bg-amber-500/10 transition-all">
                <div class="text-sm font-semibold text-white">v3.0 Standard</div>
                <div class="text-xs text-gray-400 mt-1">Best quality · Slowest</div>
                <div class="text-xs text-amber-400 mt-1 font-medium">~$7.00/video</div>
              </div>
            </label>
          </div>
        </div>

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

        <!-- Per-scene progress -->
        <div id="v9-scene-progress" class="bg-gray-800 rounded-xl p-5 text-left text-sm max-w-md mx-auto mb-6 mt-4">
          <div class="flex items-center gap-3 text-gray-300 mb-3">
            <span class="text-green-400">✓</span> Text cleaned and processed
          </div>
          <div id="v9-scenes-list" class="space-y-1"></div>
        </div>

        <!-- Stop rendering button (visible during generation) -->
        <div id="v9-stop-panel" class="mb-4">
          <button onclick="stopV9Pipeline()" id="v9-stop-btn"
            class="bg-red-700 hover:bg-red-600 text-white font-semibold px-6 py-2 rounded-lg text-sm">
            ⏹ Stop Rendering
          </button>
          <p class="text-xs text-gray-500 mt-1">Stops the pipeline to save credits. Completed scenes are preserved.</p>
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

        <!-- Error panel with retry -->
        <div id="v9-error-panel" class="hidden mb-6">
          <div class="bg-red-900/30 border border-red-700 rounded-xl p-5 max-w-md mx-auto">
            <p class="text-red-400 font-semibold mb-2">Pipeline Error</p>
            <p id="v9-error-msg" class="text-xs text-red-300 mb-3"></p>
            <button onclick="retryV9()"
              class="bg-amber-600 hover:bg-amber-500 text-black font-semibold px-6 py-2 rounded-lg text-sm">
              Retry from Failed Scene →
            </button>
          </div>
        </div>

        <!-- Multi-Fix Scenes panel -->
        <div id="v9-fix-panel" class="hidden mb-6">
          <div class="bg-gray-800 border border-gray-700 rounded-xl p-5 max-w-2xl mx-auto text-left">
            <h4 class="text-sm font-semibold text-purple-400 mb-1">Fix Scenes</h4>
            <p class="text-xs text-gray-400 mb-3">Select scenes to fix, edit their prompts, then regenerate all at once with ONE render.</p>
            <div id="v9-fix-scene-list" class="space-y-2 mb-4 max-h-96 overflow-y-auto pr-1"></div>
            <div class="flex items-center justify-between mb-3">
              <p id="v9-fix-cost" class="text-xs text-yellow-400">Select scenes above</p>
              <p class="text-xs text-yellow-500">Tip: Never put text/words in image prompts</p>
            </div>
            <button onclick="fixV9Scenes()" id="v9-fix-btn"
              class="bg-purple-600 hover:bg-purple-500 text-white font-semibold px-6 py-2 rounded-lg text-sm disabled:opacity-40 disabled:cursor-not-allowed" disabled>
              Regenerate Selected Scenes →
            </button>
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

    <!-- ── Render History ── -->
    <div id="history-panel">
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-6">
        <div class="flex items-start justify-between mb-5">
          <div class="flex items-start gap-3">
            <div class="w-7 h-7 rounded-full bg-indigo-600 text-white font-bold flex items-center justify-center text-xs flex-shrink-0 mt-0.5">H</div>
            <div>
              <h3 class="text-base font-semibold text-white">Render History</h3>
              <p class="text-sm text-gray-400 mt-0.5">Past renders with scenes and video links.</p>
            </div>
          </div>
          <button onclick="loadHistory()" title="Refresh"
            class="text-xs text-gray-500 hover:text-gray-200 border border-gray-700 hover:border-gray-500 px-2.5 py-1 rounded-lg transition-colors">
            ↺
          </button>
        </div>
        <div id="history-list" class="space-y-2 max-h-96 overflow-y-auto">
          <p class="text-xs text-gray-600">Click ↺ to load history</p>
        </div>
      </div>
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

    // ── V9 per-scene progress ─────────────────────────────────────────────
    let v9Scenes = [];

    function initV9Progress(total) {
      const list = document.getElementById('v9-scenes-list');
      list.innerHTML = '';
      for (let i = 0; i < total; i++) {
        list.innerHTML += `<div class="flex items-center gap-2" id="v9sp_${i}">
          <span class="w-2 h-2 rounded-full bg-gray-600" id="v9dot_${i}"></span>
          <span class="text-xs text-gray-500" id="v9txt_${i}">Scene ${i+1} — waiting</span>
        </div>`;
      }
      document.getElementById('v9-error-panel').classList.add('hidden');
      document.getElementById('v9-fix-panel').classList.add('hidden');
      document.getElementById('video-ready-panel').classList.add('hidden');
    }

    function setBar(pct, label) {
      document.getElementById('progress-bar').style.width = Math.min(pct, 100) + '%';
      document.getElementById('progress-percent').textContent = Math.min(pct, 100) + '%';
      document.getElementById('progress-stage-label').textContent = label;
      document.getElementById('realtime-badge').textContent = '● Live';
      document.getElementById('realtime-badge').className = 'text-green-500 font-medium';
    }

    // ── Polling ───────────────────────────────────────────────────────────────
    function startPolling() {
      stopPolling();
      pollStatus();
      pollTimer = setInterval(pollStatus, 2000);
    }

    function stopPolling() {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    async function pollStatus() {
      try {
        const res = await fetch('/v9/api/status');
        if (!res.ok) return;
        const data = await res.json();
        applyV9Status(data);
      } catch (_) {}
    }

    function applyV9Status(data) {
      const msg = data.message || '';

      if (data.phase === 'generating_scenes') {
        setBar(5, 'Claude AI generating scene visuals...');
      } else if (data.phase === 'generating_media') {
        const pct = data.total_scenes > 0 ? Math.round((data.current_scene / data.total_scenes) * 80) : 0;
        setBar(pct, msg);
        for (let i = 0; i < data.total_scenes; i++) {
          const dot = document.getElementById('v9dot_' + i);
          const txt = document.getElementById('v9txt_' + i);
          if (!dot) continue;
          if (i < (data.processed || []).length) {
            dot.className = 'w-2 h-2 rounded-full bg-green-500';
            txt.className = 'text-xs text-green-400';
            txt.textContent = `Scene ${i+1} — done`;
          } else if (i === data.current_scene - 1) {
            dot.className = 'w-2 h-2 rounded-full bg-amber-500';
            txt.className = 'text-xs text-amber-400';
            txt.textContent = `Scene ${i+1} — ${msg.includes('FLUX') ? 'generating image...' : 'generating video...'}`;
          }
        }
      } else if (data.phase === 'rendering') {
        setBar(90, 'JSON2Video assembling final video...');
        // Mark all scenes done
        for (let i = 0; i < data.total_scenes; i++) {
          const dot = document.getElementById('v9dot_' + i);
          const txt = document.getElementById('v9txt_' + i);
          if (!dot) continue;
          dot.className = 'w-2 h-2 rounded-full bg-green-500';
          txt.className = 'text-xs text-green-400';
          txt.textContent = `Scene ${i+1} — done`;
        }
      } else if (data.phase === 'done') {
        stopPolling();
        setBar(100, 'Video ready!');
        document.getElementById('v9-stop-panel').classList.add('hidden');
        document.getElementById('step3-icon').textContent = '✅';
        document.getElementById('step3-title').textContent = 'Your Video Is Ready';
        document.getElementById('step3-title').className = 'title-font text-xl font-semibold text-green-400 mb-2';
        if (data.video_url) {
          document.getElementById('video-download-link').href = data.video_url;
          document.getElementById('video-ready-panel').classList.remove('hidden');
        }
        // Sync v9Scenes from backend so fix panel always shows latest scene data
        if (data.scenes && data.scenes.length) v9Scenes = data.scenes;
        showV9FixPanel();
      } else if (data.phase === 'error' || data.phase === 'stopped') {
        stopPolling();
        document.getElementById('v9-stop-panel').classList.add('hidden');
        if (data.phase === 'stopped') {
          setBar(0, 'Pipeline stopped by user');
          document.getElementById('v9-error-panel').classList.remove('hidden');
          document.getElementById('v9-error-msg').textContent = 'Stopped by user. Completed scenes preserved — use Retry to resume.';
        } else {
          setBar(0, 'Error');
          document.getElementById('v9-error-panel').classList.remove('hidden');
          document.getElementById('v9-error-msg').textContent = data.error || data.message || 'Unknown error';
        }
      }
    }

    async function retryV9() {
      document.getElementById('v9-error-panel').classList.add('hidden');
      document.getElementById('video-ready-panel').classList.add('hidden');
      try {
        const res = await fetch('/v9/api/retry', {method: 'POST', headers: {'Content-Type': 'application/json'}});
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
        const data = await res.json();
        setBar(0, `Resuming from Scene ${data.resume_from}...`);
        startPolling();
      } catch(e) {
        document.getElementById('v9-error-panel').classList.remove('hidden');
        document.getElementById('v9-error-msg').textContent = e.message;
      }
    }

    async function stopV9Pipeline() {
      if (!confirm('Stop rendering? Completed scenes are saved, but the current scene will be lost.')) return;
      try {
        const res = await fetch('/v9/api/stop', {method: 'POST'});
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
        stopPolling();
        setBar(0, 'Pipeline stopped by user');
        document.getElementById('v9-stop-panel').classList.add('hidden');
      } catch(e) {
        alert('Failed to stop: ' + e.message);
      }
    }

    function showV9FixPanel() {
      if (!v9Scenes.length) return;
      document.getElementById('v9-fix-panel').classList.remove('hidden');
      const list = document.getElementById('v9-fix-scene-list');
      list.innerHTML = '';
      for (let i = 0; i < v9Scenes.length; i++) {
        const s = v9Scenes[i] || {};
        const narr = (s.narration || '').substring(0, 60) + ((s.narration || '').length > 60 ? '...' : '');
        const type = s.type ? ` [${s.type}]` : '';
        list.innerHTML += `
          <div class="border border-gray-700 rounded-lg">
            <label class="flex items-start gap-3 p-3 cursor-pointer hover:bg-gray-750">
              <input type="checkbox" class="v9-fix-cb mt-1 accent-purple-500" data-idx="${i}" onchange="updateFixCost()">
              <div class="flex-1 min-w-0">
                <span class="text-xs font-semibold text-gray-300">Scene ${i+1}${type}</span>
                <span class="text-xs text-gray-500 ml-2">${narr}</span>
              </div>
            </label>
            <div id="v9-fix-editor-${i}" class="hidden px-3 pb-3">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>
                  <label class="text-xs text-gray-500 block mb-1">Image Prompt</label>
                  <textarea id="v9-fix-img-${i}" rows="3" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500">${s.imagePrompt || ''}</textarea>
                </div>
                <div>
                  <label class="text-xs text-gray-500 block mb-1">Narration (read-only)</label>
                  <textarea rows="3" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-400" readonly>${s.narration || ''}</textarea>
                </div>
                <div>
                  <label class="text-xs text-gray-500 block mb-1">Motion</label>
                  <input id="v9-fix-motion-${i}" type="text" value="${s.motion || ''}" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500" />
                </div>
                <div>
                  <label class="text-xs text-gray-500 block mb-1">Lighting</label>
                  <input id="v9-fix-lighting-${i}" type="text" value="${s.lighting || ''}" class="w-full bg-gray-900 border border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500" />
                </div>
              </div>
            </div>
          </div>`;
      }
      // Toggle inline editors when checkbox changes
      list.querySelectorAll('.v9-fix-cb').forEach(cb => {
        cb.addEventListener('change', () => {
          const editor = document.getElementById('v9-fix-editor-' + cb.dataset.idx);
          editor.classList.toggle('hidden', !cb.checked);
        });
      });
      updateFixCost();
    }

    function updateFixCost() {
      const checked = document.querySelectorAll('.v9-fix-cb:checked').length;
      const costEl = document.getElementById('v9-fix-cost');
      const btn = document.getElementById('v9-fix-btn');
      if (checked === 0) {
        costEl.textContent = 'Select scenes above';
        btn.disabled = true;
      } else {
        costEl.textContent = `~$1.50 for 1 render (${checked} scene${checked > 1 ? 's' : ''} selected)`;
        btn.disabled = false;
      }
    }

    async function fixV9Scenes() {
      const cbs = document.querySelectorAll('.v9-fix-cb:checked');
      if (!cbs.length) return;
      const model = document.querySelector('input[name="kling-model"]:checked')?.value || 'v1.6';
      const fixes = [];
      cbs.forEach(cb => {
        const idx = parseInt(cb.dataset.idx);
        const s = v9Scenes[idx] || {};
        const scene = {
          narration: s.narration || '',
          imagePrompt: document.getElementById('v9-fix-img-' + idx)?.value || s.imagePrompt || '',
          motion: document.getElementById('v9-fix-motion-' + idx)?.value || s.motion || '',
          lighting: document.getElementById('v9-fix-lighting-' + idx)?.value || s.lighting || '',
        };
        v9Scenes[idx] = scene;
        fixes.push({scene_index: idx, scene});
      });

      document.getElementById('v9-fix-btn').disabled = true;
      document.getElementById('video-ready-panel').classList.add('hidden');
      document.getElementById('v9-fix-panel').classList.add('hidden');
      document.getElementById('step3-icon').textContent = '🎬';
      document.getElementById('step3-title').textContent = 'Fixing ' + fixes.length + ' Scene' + (fixes.length > 1 ? 's' : '');
      document.getElementById('step3-title').className = 'title-font text-xl font-semibold text-amber-400 mb-2';
      setBar(0, `Regenerating ${fixes.length} scenes...`);
      initV9Progress(v9Scenes.length);

      try {
        const res = await fetch('/v9/api/fix-scenes', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({fixes, model})
        });
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
        startPolling();
      } catch(e) {
        document.getElementById('v9-error-panel').classList.remove('hidden');
        document.getElementById('v9-error-msg').textContent = e.message;
      } finally {
        document.getElementById('v9-fix-btn').disabled = false;
      }
    }

    // ── Render History ────────────────────────────────────────────────────────
    async function loadHistory() {
      const list = document.getElementById('history-list');
      list.innerHTML = '<p class="text-xs text-gray-500">Loading...</p>';
      try {
        const res = await fetch('/v9/api/history');
        const data = await res.json();
        if (!data.length) { list.innerHTML = '<p class="text-xs text-gray-600">No renders yet</p>'; return; }
        list.innerHTML = '';
        data.forEach(h => {
          const label = [h.book, h.chapter].filter(Boolean).join(' ') || 'Custom';
          const date = new Date(h.created_at).toLocaleString();
          const statusColor = h.status === 'done' ? 'text-green-400' : 'text-red-400';
          list.innerHTML += `
            <div class="border border-gray-700 rounded-lg p-3">
              <div class="flex items-center justify-between">
                <div class="flex-1 min-w-0">
                  <span class="text-sm font-semibold text-gray-200">${label}</span>
                  <span class="text-xs text-gray-500 ml-2">${date}</span>
                  <span class="text-xs ${statusColor} ml-2">${h.status}</span>
                  <span class="text-xs text-gray-600 ml-2">${h.scene_count} scenes · ${h.model}</span>
                </div>
                <div class="flex gap-2 flex-shrink-0">
                  ${h.video_url ? `<a href="${h.video_url}" target="_blank" class="text-xs text-blue-400 hover:text-blue-300 border border-gray-700 px-2 py-1 rounded">Download</a>` : ''}
                  <button onclick="viewHistoryItem('${h.id}')" class="text-xs text-indigo-400 hover:text-indigo-300 border border-gray-700 px-2 py-1 rounded">View</button>
                  <button onclick="loadHistoryIntoFix('${h.id}')" class="text-xs text-purple-400 hover:text-purple-300 border border-gray-700 px-2 py-1 rounded">Load & Fix</button>
                </div>
              </div>
              <div id="history-detail-${h.id}" class="hidden mt-3"></div>
            </div>`;
        });
      } catch(e) {
        list.innerHTML = '<p class="text-xs text-red-400">Failed to load history</p>';
      }
    }

    async function viewHistoryItem(id) {
      const detail = document.getElementById('history-detail-' + id);
      if (!detail) return;
      if (!detail.classList.contains('hidden')) { detail.classList.add('hidden'); return; }
      detail.innerHTML = '<p class="text-xs text-gray-500">Loading scenes...</p>';
      detail.classList.remove('hidden');
      try {
        const res = await fetch('/v9/api/history/' + id);
        const data = await res.json();
        if (!data.scenes || !data.scenes.length) { detail.innerHTML = '<p class="text-xs text-gray-600">No scene data</p>'; return; }
        let html = '<div class="space-y-1">';
        data.scenes.forEach((s, i) => {
          const type = s.type ? ` [${s.type}]` : '';
          const narr = (s.narration || '').substring(0, 80) + ((s.narration || '').length > 80 ? '...' : '');
          html += `<div class="text-xs text-gray-400 py-1 border-b border-gray-800">
            <span class="text-gray-300 font-semibold">Scene ${i+1}${type}</span> — ${narr}
          </div>`;
        });
        html += '</div>';
        detail.innerHTML = html;
      } catch(e) {
        detail.innerHTML = '<p class="text-xs text-red-400">Failed to load</p>';
      }
    }

    async function loadHistoryIntoFix(id) {
      try {
        const res = await fetch('/v9/api/history/' + id);
        const data = await res.json();
        if (!data.scenes || !data.scenes.length) { alert('No scene data to load'); return; }
        v9Scenes = data.scenes;
        // Switch to step 3 and show fix panel
        setStep(3);
        document.getElementById('step3-icon').textContent = '🔧';
        document.getElementById('step3-title').textContent = 'Fixing Scenes from History';
        document.getElementById('step3-title').className = 'title-font text-xl font-semibold text-purple-400 mb-2';
        document.getElementById('v9-scene-progress').classList.add('hidden');
        document.getElementById('v9-stop-panel').classList.add('hidden');
        document.getElementById('video-ready-panel').classList.add('hidden');
        document.getElementById('v9-error-panel').classList.add('hidden');
        setBar(0, 'Loaded from history — select scenes to fix');
        showV9FixPanel();
      } catch(e) {
        alert('Failed to load: ' + e.message);
      }
    }

    // ── Bible Chapter Selector ─────────────────────────────────────────────────
    let bibleBooks = null;  // cached from /api/bible/books

    function toggleBibleSelector() {
      const panel = document.getElementById('bible-selector-panel');
      const arrow = document.getElementById('bible-selector-arrow');
      panel.classList.toggle('hidden');
      arrow.style.transform = panel.classList.contains('hidden') ? '' : 'rotate(180deg)';
      if (!panel.classList.contains('hidden') && !bibleBooks) loadBibleBooks();
    }

    async function loadBibleBooks() {
      try {
        const res = await fetch('/api/bible/books');
        const data = await res.json();
        bibleBooks = data;
        const sel = document.getElementById('bible-book');
        sel.innerHTML = '<option value="">-- Select a book --</option>';
        const groups = [
          ['Old Testament', data.old_testament],
          ['Apocrypha', data.apocrypha],
          ['New Testament', data.new_testament],
        ];
        for (const [label, books] of groups) {
          if (!books || books.length === 0) continue;
          const og = document.createElement('optgroup');
          og.label = label;
          for (const b of books) {
            const opt = document.createElement('option');
            opt.value = b.name;
            opt.dataset.chapters = b.chapters;
            opt.textContent = b.name;
            og.appendChild(opt);
          }
          sel.appendChild(og);
        }
      } catch (e) {
        console.error('Failed to load Bible books:', e);
      }
    }

    function onBookChange() {
      const sel = document.getElementById('bible-book');
      const chSel = document.getElementById('bible-chapter');
      chSel.innerHTML = '<option value="">--</option>';
      const opt = sel.options[sel.selectedIndex];
      if (!opt || !opt.dataset.chapters) return;
      const count = parseInt(opt.dataset.chapters);
      for (let i = 1; i <= count; i++) {
        const o = document.createElement('option');
        o.value = i;
        o.textContent = 'Chapter ' + i;
        chSel.appendChild(o);
      }
      if (count === 1) chSel.value = '1';
    }

    async function loadBibleChapter() {
      const book = document.getElementById('bible-book').value;
      const chapter = document.getElementById('bible-chapter').value;
      if (!book || !chapter) return alert('Please select a book and chapter.');
      const textarea = document.getElementById('raw-text');
      if (textarea.value.trim() && !confirm('This will replace the current text. Continue?')) return;
      const status = document.getElementById('bible-load-status');
      status.textContent = 'Loading...';
      status.classList.remove('hidden');
      try {
        const res = await fetch(`/api/bible/chapter?book=${encodeURIComponent(book)}&chapter=${chapter}`);
        if (!res.ok) throw new Error('Chapter not found');
        const data = await res.json();
        textarea.value = data.text;
        textarea.dispatchEvent(new Event('input'));
        status.textContent = `Loaded ${book} Chapter ${chapter}`;
        status.className = 'text-xs text-green-500 mt-2';
        setTimeout(() => { status.classList.add('hidden'); }, 3000);
      } catch (e) {
        status.textContent = 'Failed to load chapter: ' + e.message;
        status.className = 'text-xs text-red-400 mt-2';
      }
    }

    // Auto-load bible books on page load
    fetch('/api/bible/books').then(r => r.json()).then(data => {
      bibleBooks = data;
      const sel = document.getElementById('bible-book');
      sel.innerHTML = '<option value="">-- Select a book --</option>';
      const groups = [
        ['Old Testament', data.old_testament],
        ['Apocrypha', data.apocrypha],
        ['New Testament', data.new_testament],
      ];
      for (const [label, books] of groups) {
        if (!books || books.length === 0) continue;
        const og = document.createElement('optgroup');
        og.label = label;
        for (const b of books) {
          const opt = document.createElement('option');
          opt.value = b.name;
          opt.dataset.chapters = b.chapters;
          opt.textContent = b.name;
          og.appendChild(opt);
        }
        sel.appendChild(og);
      }
    }).catch(() => {});

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
          body: JSON.stringify({
            text: rawText,
            book: document.getElementById('bible-book')?.value || null,
            chapter: document.getElementById('bible-chapter')?.value || null,
          }),
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
      const model = document.querySelector('input[name="kling-model"]:checked')?.value || 'v1.6';
      btn.innerHTML = '<span class="spinner"></span><span>Claude AI generating scenes...</span>';
      btn.disabled = true;
      hideError('approve-error');

      try {
        const res = await fetch('/v9/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: approvedText,
            model: model,
            scene_count: 20,
            book: document.getElementById('bible-book')?.value || '',
            chapter: document.getElementById('bible-chapter')?.value || '',
          }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Failed to start v9 pipeline.');
        }

        const data = await res.json();
        v9Scenes = data.scenes || [];

        setStep(3);
        initV9Progress(data.total_scenes || v9Scenes.length);
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
      document.getElementById('progress-bar').style.width = '0%';
      document.getElementById('progress-percent').textContent = '0%';
      document.getElementById('progress-elapsed').textContent = '0:00';
      document.getElementById('progress-stage-label').textContent = 'Starting pipeline...';
      document.getElementById('realtime-badge').textContent = '';
      document.getElementById('video-ready-panel').classList.add('hidden');
      document.getElementById('v9-error-panel').classList.add('hidden');
      document.getElementById('v9-fix-panel').classList.add('hidden');
      document.getElementById('v9-scenes-list').innerHTML = '';
      document.getElementById('step3-icon').textContent = '🎬';
      document.getElementById('step3-title').textContent = 'Video Generation In Progress';
      document.getElementById('step3-title').className = 'title-font text-xl font-semibold text-amber-400 mb-2';
      v9Scenes = [];
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
