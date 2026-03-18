#!/usr/bin/env python3
"""
Custom Script → Cinematic Video Pipeline

Takes a raw script/concept as a text file, uses Claude AI to break it into
cinematic scenes (with image prompts, motion, lighting), then generates
a full video via FLUX → Kling → ElevenLabs → JSON2Video.

Usage:
  python generate.py script.txt
  python generate.py script.txt --post-produce
  python generate.py script.txt --scenes-only   # just output scenes JSON, no video
"""

import argparse
import json
import os
import subprocess
import sys
import time

import requests
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

FAL_KEY = os.getenv("FAL_KEY")
JSON2VIDEO_API_KEY = os.getenv("JSON2VIDEO_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

FLUX_URL = "https://fal.run/fal-ai/flux-pro"
KLING_URL = "https://fal.run/fal-ai/kling-video/v3/standard/image-to-video"
JSON2VIDEO_URL = "https://api.json2video.com/v2/movies"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

VOICE_ID = "NgBYGKDDq2Z8Hnhatgma"
VOICE_SPEED = 0.9

POST_PRODUCE_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "biblical-cinematic", "scripts", "post_produce.py"
)

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
2. **imagePrompt**: Extremely detailed visual description for AI image generation. Include character ethnicity per rules above, clothing details, setting, camera angle, atmosphere. End with "photorealistic, cinematic, 8K detail".
3. **motion**: Camera movement description for video animation (zoom, pan, tilt, pull back, tracking shot, etc.). Vary angles — never repeat the same motion twice in a row.
4. **lighting**: Specific dramatic lighting for the scene (golden hour, divine shaft of light, torch-lit darkness, moonlit, etc.).

GUIDELINES:
- Create as many scenes as the content naturally needs (don't pad, don't compress)
- Vary camera angles: close-up → wide shot → medium → aerial → over-shoulder
- Vary lighting: golden divine light, torch-lit darkness, moonlit night, storm clouds, sunrise
- Make narration powerful and revelatory — this is awakening content
- Each scene should be visually distinct from the one before it
- For channel branding scenes (subscribe, logo, etc.), describe the visual elements cinematically

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


def generate_scenes_from_script(script_text):
    """Use Claude to break a raw script into cinematic scenes."""
    print("Generating cinematic scenes with Claude AI...")
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 8000,
            "messages": [
                {
                    "role": "user",
                    "content": f"{SCENE_GENERATION_PROMPT}\n\n---\n\nSCRIPT/CONCEPT:\n\n{script_text}",
                }
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"]

    # Strip markdown fences if present
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    data = json.loads(content.strip())
    scenes = data["scenes"]
    print(f"Claude generated {len(scenes)} scenes\n")
    return scenes


def fal_headers():
    return {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json",
    }


def generate_image(scene, index, total):
    """Generate a FLUX image for a scene."""
    prompt = scene["imagePrompt"]
    if scene.get("lighting"):
        prompt += f", {scene['lighting']}"

    print(f"  [{index}/{total}] Generating FLUX image...")
    resp = requests.post(
        FLUX_URL,
        headers=fal_headers(),
        json={
            "prompt": prompt,
            "image_size": "landscape_16_9",
            "num_inference_steps": 28,
            "num_images": 1,
        },
        timeout=120,
    )
    resp.raise_for_status()
    url = resp.json()["images"][0]["url"]
    print(f"  [{index}/{total}] Image ready: {url[:80]}...")
    return url


def generate_video(image_url, scene, index, total):
    """Generate a Kling video from a FLUX image."""
    print(f"  [{index}/{total}] Generating Kling video...")
    resp = requests.post(
        KLING_URL,
        headers=fal_headers(),
        json={
            "image_url": image_url,
            "prompt": scene.get("motion", "Slow cinematic camera movement"),
            "duration": "15",
            "cfg_scale": 0.5,
        },
        timeout=600,
    )
    resp.raise_for_status()
    data = resp.json()
    url = data.get("video", {}).get("url") or data["data"]["video"]["url"]
    print(f"  [{index}/{total}] Video ready: {url[:80]}...")
    return url


def build_json2video_payload(scenes_data):
    """Build a JSON2Video project payload dynamically for N scenes."""
    subtitle_settings = {
        "style": "classic",
        "font-family": "Oswald Bold",
        "font-size": 80,
        "position": "bottom-center",
        "line-color": "#CCCCCC",
        "word-color": "#FFFF00",
        "outline-color": "#000000",
        "outline-width": 8,
        "shadow-color": "#000000",
        "shadow-offset": 6,
        "max-words-per-line": 4,
    }

    scenes = []
    for i, s in enumerate(scenes_data, 1):
        scenes.append({
            "id": f"scene{i}",
            "comment": f"Scene {i}",
            "duration": "auto",
            "elements": [
                {
                    "id": f"scene{i}_bg",
                    "type": "video",
                    "src": s["video_url"],
                    "resize": "cover",
                    "loop": -1,
                    "duration": -2,
                },
                {
                    "id": f"scene{i}_voice",
                    "type": "voice",
                    "text": s["narration"],
                    "voice": VOICE_ID,
                    "model": "elevenlabs",
                    "speed": VOICE_SPEED,
                },
                {
                    "id": f"scene{i}_subs",
                    "type": "subtitles",
                    "language": "en",
                    "model": "transcription",
                    "settings": subtitle_settings,
                    "transcript": s["narration"],
                },
            ],
        })

    return {
        "resolution": "full-hd",
        "quality": "high",
        "scenes": scenes,
    }


def submit_json2video(payload):
    """Submit project to JSON2Video and return the project ID."""
    print("\nSubmitting to JSON2Video...")
    resp = requests.post(
        JSON2VIDEO_URL,
        headers={
            "x-api-key": JSON2VIDEO_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    project_id = data.get("project") or data.get("id")
    print(f"Project submitted: {project_id}")
    return project_id


def poll_json2video(project_id):
    """Poll JSON2Video until done or error. Returns the MP4 URL."""
    print("Polling for render completion...")
    while True:
        time.sleep(10)
        resp = requests.get(
            JSON2VIDEO_URL,
            headers={"x-api-key": JSON2VIDEO_API_KEY},
            params={"project": project_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        movie = data.get("movie", data)
        status = movie.get("status", "unknown")
        print(f"  Status: {status}")

        if status == "done":
            url = movie["url"]
            print(f"\nVideo ready: {url}")
            return url
        elif status == "error":
            raise RuntimeError(f"JSON2Video render failed: {movie.get('message')}")


def run_post_produce(video_url):
    """Download the video and run the existing post_produce.py script."""
    os.makedirs("output", exist_ok=True)
    raw_path = os.path.join("output", "raw_video.mp4")

    print(f"\nDownloading raw video to {raw_path}...")
    resp = requests.get(video_url, stream=True, timeout=300)
    resp.raise_for_status()
    with open(raw_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    print("Running post-production...")
    subprocess.run(
        [sys.executable, POST_PRODUCE_SCRIPT, raw_path],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Custom script → cinematic video")
    parser.add_argument("script_file", help="Path to script text file (or .json for pre-built scenes)")
    parser.add_argument("--post-produce", action="store_true", help="Run post-production (intro/outro/logo)")
    parser.add_argument("--scenes-only", action="store_true", help="Only generate scenes JSON, skip video production")
    args = parser.parse_args()

    # Validate env
    required = {"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY}
    if not args.scenes_only:
        required.update({"FAL_KEY": FAL_KEY, "JSON2VIDEO_API_KEY": JSON2VIDEO_API_KEY})
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"Error: Missing env vars: {', '.join(missing)}")
        print("Set them in .env or environment.")
        sys.exit(1)

    # Load input — either a raw script (.txt/.md) or pre-built scenes (.json)
    with open(args.script_file) as f:
        raw = f.read()

    if args.script_file.endswith(".json"):
        scenes = json.loads(raw)["scenes"]
        print(f"Loaded {len(scenes)} pre-built scenes from {args.script_file}\n")
    else:
        scenes = generate_scenes_from_script(raw)
        # Save generated scenes for reference
        out_path = args.script_file.rsplit(".", 1)[0] + "_scenes.json"
        with open(out_path, "w") as f:
            json.dump({"scenes": scenes}, f, indent=2)
        print(f"Scenes saved to {out_path}\n")

    if args.scenes_only:
        print("Scenes-only mode — skipping video generation.")
        for i, s in enumerate(scenes, 1):
            print(f"\n--- Scene {i} ---")
            print(f"  Narration: {s['narration'][:80]}...")
            print(f"  Motion: {s['motion']}")
            print(f"  Lighting: {s['lighting']}")
        return

    total = len(scenes)
    print(f"Processing {total} scenes through FLUX → Kling pipeline\n")

    # Generate images and videos for each scene
    processed = []
    for i, scene in enumerate(scenes, 1):
        print(f"--- Scene {i}/{total} ---")
        image_url = generate_image(scene, i, total)
        video_url = generate_video(image_url, scene, i, total)
        processed.append({
            "narration": scene["narration"],
            "video_url": video_url,
        })
        print()

    # Build and submit JSON2Video payload
    payload = build_json2video_payload(processed)
    project_id = submit_json2video(payload)
    mp4_url = poll_json2video(project_id)

    # Optional post-production
    if args.post_produce:
        run_post_produce(mp4_url)

    print(f"\nDone! Final video: {mp4_url}")
    return mp4_url


if __name__ == "__main__":
    main()
