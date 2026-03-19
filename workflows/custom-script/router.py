"""
Custom Script → Cinematic Video — FastAPI Router

Mount this in the main biblical-cinematic app.py to add custom script
functionality under /custom/* routes.

Usage in app.py:
    from custom_script_router import custom_router, CUSTOM_LANDING_HTML
    app.include_router(custom_router, prefix="/custom")
"""

import json
import os
import threading
import time
import traceback

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

FAL_KEY = os.getenv("FAL_KEY")
JSON2VIDEO_API_KEY = os.getenv("JSON2VIDEO_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

FLUX_URL = "https://fal.run/fal-ai/flux-pro"
KLING_URL = "https://fal.run/fal-ai/kling-video/v3/standard/image-to-video"
JSON2VIDEO_URL = "https://api.json2video.com/v2/movies"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

VOICE_ID = "NgBYGKDDq2Z8Hnhatgma"
VOICE_SPEED = 0.9

# ---------------------------------------------------------------------------
# Shared pipeline state
# ---------------------------------------------------------------------------
pipeline_state = {
    "phase": "idle",
    "scenes": None,
    "current_scene": 0,
    "total_scenes": 0,
    "message": "",
    "video_url": None,
    "error": None,
    "processed": [],
}

lock = threading.Lock()

SCENE_GENERATION_PROMPT = """You are a cinematic video production expert for AI Bible Gospels — a channel revealing the hidden identity of the 12 Tribes of Israel through Scripture, history, and prophecy.

BRAND STYLE:
- Dark, dramatic backgrounds with golden divine light
- Cinematic, reverent, powerful tone
- Photorealistic ancient biblical settings

CHARACTER ETHNICITY RULES (CRITICAL):
- ISRAELITES / HEBREWS: Black Hebrew Israelites with rich, deeply melanated dark skin. Natural Afro-textured hair: locs, braids, twists, afros, or traditional head wraps. Traditional Hebrew robes, garments with tzitzit fringes, priestly vestments.
- ROMANS: Caucasian with light skin. Roman armor, togas, military regalia.
- GREEKS / MACEDONIANS: Mediterranean olive skin. Hellenistic armor, robes, classical styling.
- EGYPTIANS: Brown skin. Traditional Egyptian garments and headdress.
- PERSIANS / MEDES: Olive-brown skin. Ornate Persian robes.
- PHILISTINES / CANAANITES: Mediterranean/Levantine appearance. Bronze armor, distinctive garments.
- For scenes with MULTIPLE nations, depict EACH character according to their own nation's ethnicity.
- CRITICAL: Israelites = Black Hebrew Israelites. All other nations = their own historical ethnicity.

YOUR TASK:
Read the script/concept below and break it into cinematic scenes for video production. You are NOT narrating it word-for-word — you are a creative director interpreting the concept into powerful, cinematic narration and visuals.

For each scene, create:
1. **narration**: Your own cinematic narration inspired by the script (not word-for-word copy). Write powerful, revelatory prose that captures the spirit and message. Keep each scene's narration between 20-60 words.
2. **imagePrompt**: Extremely detailed visual description for AI image generation. Include character ethnicity per rules above, clothing details, setting, camera angle, atmosphere. End with "photorealistic, cinematic, 8K detail". NEVER include text or words in the image prompt — AI misspells them.
3. **motion**: Camera movement description for video animation (zoom, pan, tilt, pull back, tracking shot, etc.). Vary angles — never repeat the same motion twice in a row.
4. **lighting**: Specific dramatic lighting for the scene (golden hour, divine shaft of light, torch-lit darkness, moonlit, etc.).
GUIDELINES:
- Create as many scenes as the content naturally needs (don't pad, don't compress)
- Vary camera angles: close-up → wide shot → medium → aerial → over-shoulder
- Vary lighting: golden divine light, torch-lit darkness, moonlit night, storm clouds, sunrise
- Make narration powerful and revelatory — this is awakening content
- Each scene should be visually distinct from the one before it
- For channel branding scenes (subscribe, logo, etc.), describe the visual elements cinematically
- NEVER put text, words, letters, or titles in image prompts

Return ONLY valid JSON in this exact format:
{
  "scenes": [
    {
      "narration": "...",
      "imagePrompt": "...",
      "motion": "...",
      "lighting": "..."
    }
  ]
}"""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ScriptInput(BaseModel):
    script: str

class ScenesInput(BaseModel):
    scenes: list

class FixSceneInput(BaseModel):
    scene_index: int
    scene: dict


# ---------------------------------------------------------------------------
# Pipeline functions
# ---------------------------------------------------------------------------
def generate_scenes_from_script(script_text):
    resp = requests.post(
        ANTHROPIC_URL,
        headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        json={"model": "claude-sonnet-4-20250514", "max_tokens": 8000,
              "messages": [{"role": "user", "content": f"{SCENE_GENERATION_PROMPT}\n\n---\n\nSCRIPT/CONCEPT:\n\n{script_text}"}]},
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"]
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    return json.loads(content.strip())["scenes"]


def fal_headers():
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}


def generate_image(scene):
    prompt = scene["imagePrompt"]
    if scene.get("lighting"):
        prompt += f", {scene['lighting']}"
    resp = requests.post(FLUX_URL, headers=fal_headers(), json={
        "prompt": prompt, "image_size": "landscape_16_9", "num_inference_steps": 28, "num_images": 1,
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["images"][0]["url"]


def generate_video(image_url, scene):
    resp = requests.post(KLING_URL, headers=fal_headers(), json={
        "image_url": image_url, "prompt": scene.get("motion", "Slow cinematic camera movement"),
        "duration": "15", "cfg_scale": 0.5,
    }, timeout=600)
    resp.raise_for_status()
    data = resp.json()
    return data.get("video", {}).get("url") or data["data"]["video"]["url"]


def build_json2video_payload(scenes_data):
    subtitle_settings = {
        "style": "classic", "font-family": "Oswald Bold", "font-size": 80,
        "position": "bottom-center", "line-color": "#CCCCCC", "word-color": "#FFFF00",
        "outline-color": "#000000", "outline-width": 8, "shadow-color": "#000000",
        "shadow-offset": 6, "max-words-per-line": 4,
    }
    scenes = []
    for i, s in enumerate(scenes_data, 1):
        scenes.append({
            "id": f"scene{i}", "comment": f"Scene {i}", "duration": "auto",
            "elements": [
                {"id": f"scene{i}_bg", "type": "video", "src": s["video_url"], "resize": "cover", "loop": -1, "duration": -2},
                {"id": f"scene{i}_voice", "type": "voice", "text": s["narration"], "voice": VOICE_ID, "model": "elevenlabs", "speed": VOICE_SPEED},
                {"id": f"scene{i}_subs", "type": "subtitles", "language": "en", "model": "transcription", "settings": subtitle_settings, "transcript": s["narration"]},
            ],
        })
    return {"resolution": "full-hd", "quality": "high", "scenes": scenes}


def submit_and_poll_json2video(payload):
    resp = requests.post(JSON2VIDEO_URL, headers={"x-api-key": JSON2VIDEO_API_KEY, "Content-Type": "application/json"}, json=payload, timeout=30)
    resp.raise_for_status()
    project_id = resp.json().get("project") or resp.json().get("id")
    while True:
        time.sleep(10)
        resp = requests.get(JSON2VIDEO_URL, headers={"x-api-key": JSON2VIDEO_API_KEY}, params={"project": project_id}, timeout=30)
        resp.raise_for_status()
        movie = resp.json().get("movie", resp.json())
        status = movie.get("status", "unknown")
        with lock:
            pipeline_state["message"] = f"JSON2Video: {status}"
        if status == "done":
            return movie["url"]
        elif status == "error":
            raise RuntimeError(f"Render failed: {movie.get('message')}")


# ---------------------------------------------------------------------------
# Background runners
# ---------------------------------------------------------------------------
def run_pipeline(scenes, resume_from=0, existing_processed=None):
    global pipeline_state
    try:
        total = len(scenes)
        processed = list(existing_processed) if existing_processed else []
        with lock:
            pipeline_state.update(phase="generating_media", current_scene=resume_from, total_scenes=total,
                                  message=f"Generating media for {total} scenes...", processed=list(processed), error=None, video_url=None)
        for i, scene in enumerate(scenes, 1):
            if i <= resume_from:
                continue
            with lock:
                pipeline_state["current_scene"] = i
                pipeline_state["message"] = f"Scene {i}/{total} — Generating FLUX image..."
            image_url = generate_image(scene)
            with lock:
                pipeline_state["message"] = f"Scene {i}/{total} — Generating Kling video..."
            video_url = generate_video(image_url, scene)
            processed.append({"narration": scene["narration"], "video_url": video_url})
            with lock:
                pipeline_state["processed"] = list(processed)
                pipeline_state["message"] = f"Scene {i}/{total} complete"
        with lock:
            pipeline_state["phase"] = "rendering"
            pipeline_state["message"] = "Submitting to JSON2Video for final render..."
        payload = build_json2video_payload(processed)
        mp4_url = submit_and_poll_json2video(payload)
        with lock:
            pipeline_state.update(phase="done", video_url=mp4_url, message="Video complete!")
    except Exception as e:
        with lock:
            pipeline_state.update(phase="error", error=str(e), message=f"Error: {e}")
        traceback.print_exc()


def run_fix_scene(scene_index, scene, processed):
    global pipeline_state
    try:
        total = len(processed)
        idx = scene_index + 1
        with lock:
            pipeline_state.update(phase="generating_media", current_scene=idx, total_scenes=total,
                                  message=f"Fixing Scene {idx}/{total} — Generating FLUX image...", error=None, video_url=None)
        image_url = generate_image(scene)
        with lock:
            pipeline_state["message"] = f"Fixing Scene {idx}/{total} — Generating Kling video..."
        video_url = generate_video(image_url, scene)
        processed[scene_index] = {"narration": scene["narration"], "video_url": video_url}
        with lock:
            pipeline_state.update(phase="rendering", processed=list(processed), message="Re-submitting all scenes to JSON2Video...")
        payload = build_json2video_payload(processed)
        mp4_url = submit_and_poll_json2video(payload)
        with lock:
            pipeline_state.update(phase="done", video_url=mp4_url, message="Fixed video complete!")
    except Exception as e:
        with lock:
            pipeline_state.update(phase="error", error=str(e), message=f"Error: {e}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
custom_router = APIRouter()


@custom_router.post("/api/generate-scenes")
async def api_generate_scenes(body: ScriptInput):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY not set in .env")
    try:
        with lock:
            pipeline_state.update(phase="generating_scenes", message="Claude is generating scenes...", scenes=None, error=None, video_url=None)
        scenes = generate_scenes_from_script(body.script)
        with lock:
            pipeline_state.update(phase="idle", scenes=scenes, message=f"Generated {len(scenes)} scenes")
        return {"scenes": scenes}
    except Exception as e:
        with lock:
            pipeline_state.update(phase="error", error=str(e))
        raise HTTPException(500, str(e))


@custom_router.post("/api/generate-video")
async def api_generate_video(body: ScenesInput):
    missing = [k for k, v in {"FAL_KEY": FAL_KEY, "JSON2VIDEO_API_KEY": JSON2VIDEO_API_KEY}.items() if not v]
    if missing:
        raise HTTPException(400, f"Missing env vars: {', '.join(missing)}")
    if pipeline_state["phase"] in ("generating_media", "rendering"):
        raise HTTPException(409, "Pipeline already running")
    with lock:
        pipeline_state["scenes"] = body.scenes
    thread = threading.Thread(target=run_pipeline, args=(body.scenes,), daemon=True)
    thread.start()
    return {"status": "started", "total_scenes": len(body.scenes)}


@custom_router.post("/api/retry")
async def api_retry():
    missing = [k for k, v in {"FAL_KEY": FAL_KEY, "JSON2VIDEO_API_KEY": JSON2VIDEO_API_KEY}.items() if not v]
    if missing:
        raise HTTPException(400, f"Missing env vars: {', '.join(missing)}")
    with lock:
        if pipeline_state["phase"] not in ("error", "idle", "done"):
            raise HTTPException(409, "Pipeline is still running")
        scenes = pipeline_state.get("scenes")
        processed = pipeline_state.get("processed", [])
        resume_from = len(processed)
    if not scenes:
        raise HTTPException(400, "No scenes to retry — generate scenes first")
    thread = threading.Thread(target=run_pipeline, args=(scenes, resume_from, processed), daemon=True)
    thread.start()
    return {"status": "resuming", "resume_from": resume_from + 1, "total_scenes": len(scenes)}


@custom_router.post("/api/fix-scene")
async def api_fix_scene(body: FixSceneInput):
    missing = [k for k, v in {"FAL_KEY": FAL_KEY, "JSON2VIDEO_API_KEY": JSON2VIDEO_API_KEY}.items() if not v]
    if missing:
        raise HTTPException(400, f"Missing env vars: {', '.join(missing)}")
    if pipeline_state["phase"] in ("generating_media", "rendering"):
        raise HTTPException(409, "Pipeline already running")
    with lock:
        processed = pipeline_state.get("processed", [])
    if not processed:
        raise HTTPException(400, "No completed video to fix — generate a video first")
    if body.scene_index < 0 or body.scene_index >= len(processed):
        raise HTTPException(400, f"Scene index {body.scene_index} out of range")
    thread = threading.Thread(target=run_fix_scene, args=(body.scene_index, body.scene, list(processed)), daemon=True)
    thread.start()
    return {"status": "fixing", "scene": body.scene_index + 1, "total_scenes": len(processed)}


@custom_router.get("/api/status")
async def api_status():
    with lock:
        return JSONResponse(dict(pipeline_state))


@custom_router.get("/", response_class=HTMLResponse)
async def custom_landing():
    return HTMLResponse(content=CUSTOM_LANDING_HTML)


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------
CUSTOM_LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Custom Script → Video | AI Bible Gospels</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&family=Inter:wght@300;400;500;600&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .title-font { font-family: 'Cinzel', serif; }
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
    .scene-card { transition: all 0.3s ease; }
    .scene-card:hover { border-color: #f59e0b; }
    .progress-fill { transition: width 0.5s ease; }
    .nav-tab { transition: all 0.2s ease; }
    .nav-tab:hover { background: rgba(245,158,11,0.1); }
    .nav-tab.active { border-bottom: 2px solid #f59e0b; color: #f59e0b; }
  </style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">

  <!-- Navigation -->
  <nav class="border-b border-gray-800 bg-gray-950 sticky top-0 z-50">
    <div class="max-w-5xl mx-auto flex items-center">
      <div class="text-amber-500 text-2xl px-4">✦</div>
      <a href="/" class="nav-tab px-5 py-4 text-sm text-gray-400 font-medium">Scripture Mode</a>
      <a href="/custom" class="nav-tab active px-5 py-4 text-sm font-medium">Custom Script Mode</a>
      <span class="ml-auto text-xs text-gray-600 pr-4">AI Bible Gospels</span>
    </div>
  </nav>

  <!-- Header -->
  <header class="px-6 py-5 flex items-center gap-4">
    <div>
      <h1 class="title-font text-xl font-semibold text-amber-400 tracking-wide">Custom Script → Cinematic Video</h1>
      <p class="text-xs text-gray-500 mt-0.5">Claude AI · fal.ai FLUX + Kling · ElevenLabs · JSON2Video</p>
    </div>
  </header>

  <main class="max-w-5xl mx-auto px-6 py-10">

    <!-- STEP 1: Script Input -->
    <section id="step1" class="mb-10">
      <div class="flex items-center gap-3 mb-4">
        <span class="bg-amber-500 text-black text-xs font-bold px-2.5 py-1 rounded-full">1</span>
        <h2 class="title-font text-lg font-semibold text-white">Paste Your Script</h2>
      </div>
      <textarea id="scriptInput" rows="12"
        class="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200 focus:outline-none focus:border-amber-500 placeholder-gray-600"
        placeholder="Paste your script, concept, or idea here...

Example: A channel trailer about the 12 Tribes of Israel, their scattering, and the prophecy of awakening..."></textarea>
      <div class="flex items-center gap-4 mt-4">
        <button onclick="generateScenes()" id="btnGenScenes"
          class="bg-amber-600 hover:bg-amber-500 text-black font-semibold px-6 py-2.5 rounded-lg transition-colors text-sm">
          Generate Scenes with Claude AI
        </button>
        <span id="scenesSpinner" class="hidden"><span class="spinner"></span> <span class="text-xs text-gray-400 ml-2">Claude is thinking...</span></span>
      </div>
    </section>

    <!-- STEP 2: Scene Preview & Edit -->
    <section id="step2" class="mb-10 hidden">
      <div class="flex items-center gap-3 mb-4">
        <span class="bg-amber-500 text-black text-xs font-bold px-2.5 py-1 rounded-full">2</span>
        <h2 class="title-font text-lg font-semibold text-white">Review & Edit Scenes</h2>
        <span id="sceneCount" class="text-xs text-gray-500 ml-2"></span>
      </div>
      <p class="text-xs text-gray-400 mb-4">Edit any scene below before generating video. Add or remove scenes as needed.</p>
      <div id="scenesContainer" class="space-y-4"></div>
      <div class="flex items-center gap-4 mt-6">
        <button onclick="addScene()" class="border border-gray-600 hover:border-amber-500 text-gray-300 hover:text-amber-400 px-4 py-2 rounded-lg transition-colors text-sm">
          + Add Scene
        </button>
        <button onclick="generateVideo()" id="btnGenVideo"
          class="bg-green-600 hover:bg-green-500 text-white font-semibold px-6 py-2.5 rounded-lg transition-colors text-sm ml-auto">
          Generate Video →
        </button>
      </div>
    </section>

    <!-- STEP 3: Progress -->
    <section id="step3" class="mb-10 hidden">
      <div class="flex items-center gap-3 mb-4">
        <span class="bg-amber-500 text-black text-xs font-bold px-2.5 py-1 rounded-full">3</span>
        <h2 class="title-font text-lg font-semibold text-white">Generating Video</h2>
      </div>
      <div class="bg-gray-900 border border-gray-700 rounded-xl p-6">
        <div class="flex items-center gap-3 mb-4">
          <span class="spinner" id="pipelineSpinner"></span>
          <span id="pipelinePhase" class="text-sm text-amber-400 font-medium">Starting...</span>
        </div>
        <div class="w-full bg-gray-800 rounded-full h-3 mb-3">
          <div id="progressBar" class="progress-fill bg-amber-500 h-3 rounded-full" style="width:0%"></div>
        </div>
        <p id="pipelineMessage" class="text-xs text-gray-400"></p>
        <div id="sceneProgress" class="mt-4 space-y-1"></div>
      </div>
    </section>

    <!-- STEP 4: Result -->
    <section id="step4" class="mb-10 hidden">
      <div class="flex items-center gap-3 mb-4">
        <span class="bg-green-500 text-black text-xs font-bold px-2.5 py-1 rounded-full">✓</span>
        <h2 class="title-font text-lg font-semibold text-white">Video Complete</h2>
      </div>
      <div class="bg-gray-900 border border-green-800 rounded-xl p-6 text-center">
        <p class="text-green-400 font-medium mb-4">Your cinematic video is ready!</p>
        <a id="videoLink" href="#" target="_blank"
          class="inline-block bg-green-600 hover:bg-green-500 text-white font-semibold px-8 py-3 rounded-lg transition-colors">
          Download MP4 →
        </a>
        <p id="videoUrl" class="text-xs text-gray-500 mt-3 break-all"></p>
      </div>
    </section>

    <!-- STEP 5: Fix a Scene -->
    <section id="step5" class="mb-10 hidden">
      <div class="flex items-center gap-3 mb-4">
        <span class="bg-purple-500 text-white text-xs font-bold px-2.5 py-1 rounded-full">5</span>
        <h2 class="title-font text-lg font-semibold text-white">Fix a Scene</h2>
      </div>
      <p class="text-xs text-gray-400 mb-4">Not happy with an image? Edit the prompt below and regenerate just that one scene. All other scenes stay the same — only costs ~$1.74 (FLUX + Kling + JSON2Video render).</p>
      <div class="bg-gray-900 border border-gray-700 rounded-xl p-5">
        <div class="flex items-center gap-3 mb-4">
          <label class="text-xs text-gray-400">Scene #</label>
          <select id="fixSceneIndex" class="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500">
          </select>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
          <div>
            <label class="text-xs text-gray-500 block mb-1">Narration</label>
            <textarea id="fixNarration" rows="3" class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-purple-500"></textarea>
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Image Prompt</label>
            <textarea id="fixImagePrompt" rows="3" class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-purple-500"></textarea>
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Motion</label>
            <input id="fixMotion" type="text" class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-purple-500" />
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Lighting</label>
            <input id="fixLighting" type="text" class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-purple-500" />
          </div>
        </div>
        <p class="text-xs text-yellow-500 mb-3">Tip: Never put text/words in the image prompt — FLUX misspells them. Let subtitles handle all on-screen text.</p>
        <button onclick="fixScene()" id="btnFixScene"
          class="bg-purple-600 hover:bg-purple-500 text-white font-semibold px-6 py-2.5 rounded-lg transition-colors text-sm">
          Regenerate This Scene →
        </button>
      </div>
    </section>

    <!-- Error -->
    <section id="stepError" class="mb-10 hidden">
      <div class="bg-red-950 border border-red-800 rounded-xl p-6">
        <p class="text-red-400 font-medium mb-2">Pipeline Error</p>
        <p id="errorMessage" class="text-xs text-red-300"></p>
        <div class="flex gap-3 mt-4">
          <button onclick="retryPipeline()" id="btnRetry"
            class="bg-amber-600 hover:bg-amber-500 text-black font-semibold px-6 py-2 rounded-lg text-sm">
            Retry from Failed Scene →
          </button>
          <button onclick="resetUI()" class="border border-red-700 text-red-400 hover:text-red-300 px-4 py-2 rounded-lg text-sm">
            Start Over
          </button>
        </div>
      </div>
    </section>

  </main>

<script>
const API_PREFIX = '/custom';
let currentScenes = [];
let pollInterval = null;

async function generateScenes() {
  const script = document.getElementById('scriptInput').value.trim();
  if (!script) return alert('Paste a script first');

  document.getElementById('btnGenScenes').disabled = true;
  document.getElementById('scenesSpinner').classList.remove('hidden');

  try {
    const res = await fetch(API_PREFIX + '/api/generate-scenes', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({script})
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Scene generation failed');
    }
    const data = await res.json();
    currentScenes = data.scenes;
    renderScenes();
    document.getElementById('step2').classList.remove('hidden');
    document.getElementById('step2').scrollIntoView({behavior: 'smooth'});
  } catch(e) {
    alert('Error: ' + e.message);
  } finally {
    document.getElementById('btnGenScenes').disabled = false;
    document.getElementById('scenesSpinner').classList.add('hidden');
  }
}

function renderScenes() {
  const c = document.getElementById('scenesContainer');
  document.getElementById('sceneCount').textContent = `${currentScenes.length} scenes`;
  c.innerHTML = '';
  currentScenes.forEach((s, i) => {
    c.innerHTML += `
      <div class="scene-card bg-gray-900 border border-gray-700 rounded-xl p-5" data-idx="${i}">
        <div class="flex items-center justify-between mb-3">
          <span class="text-amber-400 font-semibold text-sm">Scene ${i+1}</span>
          <button onclick="removeScene(${i})" class="text-red-500 hover:text-red-400 text-xs">✕ Remove</button>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label class="text-xs text-gray-500 block mb-1">Narration</label>
            <textarea rows="3" class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
              onchange="currentScenes[${i}].narration=this.value">${esc(s.narration)}</textarea>
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Image Prompt</label>
            <textarea rows="3" class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
              onchange="currentScenes[${i}].imagePrompt=this.value">${esc(s.imagePrompt)}</textarea>
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Motion</label>
            <input type="text" class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
              value="${esc(s.motion)}" onchange="currentScenes[${i}].motion=this.value" />
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Lighting</label>
            <input type="text" class="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
              value="${esc(s.lighting)}" onchange="currentScenes[${i}].lighting=this.value" />
          </div>
        </div>
      </div>`;
  });
}

function removeScene(i) { currentScenes.splice(i, 1); renderScenes(); }

function addScene() {
  currentScenes.push({narration:'', imagePrompt:'', motion:'Slow cinematic camera movement', lighting:'Golden divine light from above'});
  renderScenes();
  document.getElementById('scenesContainer').lastElementChild.scrollIntoView({behavior:'smooth'});
}

async function generateVideo() {
  document.querySelectorAll('.scene-card').forEach((card, i) => {
    const tas = card.querySelectorAll('textarea');
    const ins = card.querySelectorAll('input');
    currentScenes[i].narration = tas[0].value;
    currentScenes[i].imagePrompt = tas[1].value;
    currentScenes[i].motion = ins[0].value;
    currentScenes[i].lighting = ins[1].value;
  });

  if (currentScenes.length === 0) return alert('No scenes to generate');

  document.getElementById('step3').classList.remove('hidden');
  document.getElementById('step4').classList.add('hidden');
  document.getElementById('stepError').classList.add('hidden');
  document.getElementById('step3').scrollIntoView({behavior: 'smooth'});
  document.getElementById('btnGenVideo').disabled = true;

  const sp = document.getElementById('sceneProgress');
  sp.innerHTML = currentScenes.map((_, i) =>
    `<div class="flex items-center gap-2" id="sp_${i}">
      <span class="w-2 h-2 rounded-full bg-gray-600" id="spDot_${i}"></span>
      <span class="text-xs text-gray-500" id="spText_${i}">Scene ${i+1} — waiting</span>
    </div>`
  ).join('');

  try {
    const res = await fetch(API_PREFIX + '/api/generate-video', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({scenes: currentScenes})
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to start pipeline');
    }
    startPolling();
  } catch(e) { showError(e.message); }
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(API_PREFIX + '/api/status');
      const s = await res.json();
      updateProgress(s);
      if (s.phase === 'done' || s.phase === 'error') {
        clearInterval(pollInterval);
        pollInterval = null;
      }
    } catch(e) {}
  }, 2000);
}

function updateProgress(s) {
  const phase = document.getElementById('pipelinePhase');
  const msg = document.getElementById('pipelineMessage');
  const bar = document.getElementById('progressBar');
  const spinner = document.getElementById('pipelineSpinner');

  msg.textContent = s.message || '';

  if (s.phase === 'generating_media') {
    phase.textContent = `Generating Media — Scene ${s.current_scene}/${s.total_scenes}`;
    const pct = s.total_scenes > 0 ? Math.round((s.current_scene / s.total_scenes) * 80) : 0;
    bar.style.width = pct + '%';
    for (let i = 0; i < s.total_scenes; i++) {
      const dot = document.getElementById('spDot_' + i);
      const txt = document.getElementById('spText_' + i);
      if (!dot) continue;
      if (i < s.current_scene) {
        dot.className = 'w-2 h-2 rounded-full bg-green-500';
        txt.className = 'text-xs text-green-400';
        txt.textContent = `Scene ${i+1} — done`;
      } else if (i === s.current_scene - 1) {
        dot.className = 'w-2 h-2 rounded-full bg-amber-500';
        txt.className = 'text-xs text-amber-400';
        txt.textContent = `Scene ${i+1} — in progress`;
      }
    }
  } else if (s.phase === 'rendering') {
    phase.textContent = 'Final Render — JSON2Video';
    bar.style.width = '90%';
    for (let i = 0; i < s.total_scenes; i++) {
      const dot = document.getElementById('spDot_' + i);
      const txt = document.getElementById('spText_' + i);
      if (!dot) continue;
      dot.className = 'w-2 h-2 rounded-full bg-green-500';
      txt.className = 'text-xs text-green-400';
      txt.textContent = `Scene ${i+1} — done`;
    }
  } else if (s.phase === 'done') {
    spinner.style.display = 'none';
    phase.textContent = 'Complete!';
    bar.style.width = '100%';
    bar.classList.remove('bg-amber-500');
    bar.classList.add('bg-green-500');
    document.getElementById('step4').classList.remove('hidden');
    document.getElementById('videoLink').href = s.video_url;
    document.getElementById('videoUrl').textContent = s.video_url;
    document.getElementById('btnGenVideo').disabled = false;
    showFixPanel();
  } else if (s.phase === 'error') {
    spinner.style.display = 'none';
    showError(s.error || s.message);
    document.getElementById('btnGenVideo').disabled = false;
  }
}

async function retryPipeline() {
  document.getElementById('stepError').classList.add('hidden');
  document.getElementById('step3').classList.remove('hidden');
  document.getElementById('pipelineSpinner').style.display = '';
  document.getElementById('progressBar').classList.remove('bg-green-500');
  document.getElementById('progressBar').classList.add('bg-amber-500');
  document.getElementById('step4').classList.add('hidden');

  try {
    const res = await fetch(API_PREFIX + '/api/retry', {method: 'POST', headers: {'Content-Type': 'application/json'}});
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Retry failed');
    }
    const data = await res.json();
    document.getElementById('pipelinePhase').textContent = `Resuming from Scene ${data.resume_from}/${data.total_scenes}`;
    startPolling();
  } catch(e) { showError(e.message); }
}

function showFixPanel() {
  document.getElementById('step5').classList.remove('hidden');
  const sel = document.getElementById('fixSceneIndex');
  sel.innerHTML = '';
  for (let i = 0; i < currentScenes.length; i++) {
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = `Scene ${i+1}`;
    sel.appendChild(opt);
  }
  sel.onchange = () => loadFixScene(parseInt(sel.value));
  loadFixScene(0);
}

function loadFixScene(idx) {
  const s = currentScenes[idx] || {};
  document.getElementById('fixNarration').value = s.narration || '';
  document.getElementById('fixImagePrompt').value = s.imagePrompt || '';
  document.getElementById('fixMotion').value = s.motion || '';
  document.getElementById('fixLighting').value = s.lighting || '';
}

async function fixScene() {
  const idx = parseInt(document.getElementById('fixSceneIndex').value);
  const scene = {
    narration: document.getElementById('fixNarration').value,
    imagePrompt: document.getElementById('fixImagePrompt').value,
    motion: document.getElementById('fixMotion').value,
    lighting: document.getElementById('fixLighting').value,
  };
  currentScenes[idx] = scene;

  document.getElementById('btnFixScene').disabled = true;
  document.getElementById('step3').classList.remove('hidden');
  document.getElementById('step4').classList.add('hidden');
  document.getElementById('stepError').classList.add('hidden');
  document.getElementById('pipelineSpinner').style.display = '';
  document.getElementById('progressBar').classList.remove('bg-green-500');
  document.getElementById('progressBar').classList.add('bg-amber-500');
  document.getElementById('progressBar').style.width = '0%';
  document.getElementById('pipelinePhase').textContent = `Fixing Scene ${idx+1}...`;
  document.getElementById('sceneProgress').innerHTML = `
    <div class="flex items-center gap-2">
      <span class="w-2 h-2 rounded-full bg-amber-500"></span>
      <span class="text-xs text-amber-400">Regenerating Scene ${idx+1} (FLUX + Kling)...</span>
    </div>`;
  document.getElementById('step3').scrollIntoView({behavior: 'smooth'});

  try {
    const res = await fetch(API_PREFIX + '/api/fix-scene', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({scene_index: idx, scene})
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Fix failed');
    }
    startPolling();
  } catch(e) { showError(e.message); }
  finally { document.getElementById('btnFixScene').disabled = false; }
}

function showError(msg) {
  document.getElementById('stepError').classList.remove('hidden');
  document.getElementById('errorMessage').textContent = msg;
}

function resetUI() {
  document.getElementById('step2').classList.add('hidden');
  document.getElementById('step3').classList.add('hidden');
  document.getElementById('step4').classList.add('hidden');
  document.getElementById('stepError').classList.add('hidden');
  document.getElementById('btnGenVideo').disabled = false;
  currentScenes = [];
  window.scrollTo({top: 0, behavior: 'smooth'});
}

function esc(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>"""
