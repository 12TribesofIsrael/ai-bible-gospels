#!/usr/bin/env python3
"""
Recovery script: Recovers 9 completed Kling videos from fal.ai history,
generates scenes 10-13, and submits all 13 to JSON2Video.
"""

import json
import os
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
FAL_HISTORY_URL = "https://api.fal.ai/v1/models/requests/by-endpoint"

VOICE_ID = "NgBYGKDDq2Z8Hnhatgma"
VOICE_SPEED = 0.9

# Import the scene generation prompt from generate.py
sys.path.insert(0, os.path.dirname(__file__))
from generate import SCENE_GENERATION_PROMPT


def recover_kling_videos():
    """Fetch completed Kling video URLs from fal.ai history."""
    print("Recovering completed Kling videos from fal.ai...")
    resp = requests.get(
        FAL_HISTORY_URL,
        headers={"Authorization": f"Key {FAL_KEY}"},
        params={
            "endpoint_id": "fal-ai/kling-video/v3/standard/image-to-video",
            "limit": 20,
            "status": "success",
            "expand": "payloads",
        },
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json()["items"]
    items.sort(key=lambda x: x["started_at"])
    urls = [item["json_output"]["video"]["url"] for item in items]
    print(f"Recovered {len(urls)} video URLs\n")
    return urls


def regenerate_scenes(script_path):
    """Re-generate scenes with Claude to get the narration text."""
    print("Re-generating scene data with Claude AI...")
    with open(script_path) as f:
        script_text = f.read()

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
            "messages": [{"role": "user", "content": f"{SCENE_GENERATION_PROMPT}\n\n---\n\nSCRIPT/CONCEPT:\n\n{script_text}"}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"]
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    scenes = json.loads(content.strip())["scenes"]
    print(f"Claude generated {len(scenes)} scenes\n")

    # Save for reference
    out_path = os.path.join(os.path.dirname(__file__), "recovered_scenes.json")
    with open(out_path, "w") as f:
        json.dump({"scenes": scenes}, f, indent=2)
    print(f"Scenes saved to {out_path}\n")
    return scenes


def fal_headers():
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}


def generate_image(scene, index, total):
    prompt = scene["imagePrompt"]
    if scene.get("lighting"):
        prompt += f", {scene['lighting']}"
    print(f"  [{index}/{total}] Generating FLUX image...")
    resp = requests.post(FLUX_URL, headers=fal_headers(), json={
        "prompt": prompt, "image_size": "landscape_16_9", "num_inference_steps": 28, "num_images": 1,
    }, timeout=120)
    resp.raise_for_status()
    url = resp.json()["images"][0]["url"]
    print(f"  [{index}/{total}] Image ready")
    return url


def generate_video(image_url, scene, index, total):
    print(f"  [{index}/{total}] Generating Kling video...")
    resp = requests.post(KLING_URL, headers=fal_headers(), json={
        "image_url": image_url,
        "prompt": scene.get("motion", "Slow cinematic camera movement"),
        "duration": "15", "cfg_scale": 0.5,
    }, timeout=600)
    resp.raise_for_status()
    data = resp.json()
    url = data.get("video", {}).get("url") or data["data"]["video"]["url"]
    print(f"  [{index}/{total}] Video ready")
    return url


def build_json2video_payload(processed):
    subtitle_settings = {
        "style": "classic", "font-family": "Oswald Bold", "font-size": 80,
        "position": "bottom-center", "line-color": "#CCCCCC", "word-color": "#FFFF00",
        "outline-color": "#000000", "outline-width": 8, "shadow-color": "#000000",
        "shadow-offset": 6, "max-words-per-line": 4,
    }
    scenes = []
    for i, s in enumerate(processed, 1):
        scenes.append({
            "id": f"scene{i}", "comment": f"Scene {i}", "duration": "auto",
            "elements": [
                {"id": f"scene{i}_bg", "type": "video", "src": s["video_url"], "resize": "cover", "loop": -1, "duration": -2},
                {"id": f"scene{i}_voice", "type": "voice", "text": s["narration"], "voice": VOICE_ID, "model": "elevenlabs", "speed": VOICE_SPEED},
                {"id": f"scene{i}_subs", "type": "subtitles", "language": "en", "model": "transcription", "settings": subtitle_settings, "transcript": s["narration"]},
            ],
        })
    return {"resolution": "full-hd", "quality": "high", "scenes": scenes}


def main():
    script_path = os.path.join(os.path.dirname(__file__), "example-trailer.txt")

    # Step 1: Recover existing videos
    recovered_urls = recover_kling_videos()
    num_recovered = len(recovered_urls)

    # Step 2: Re-generate scenes with Claude (just for narration text)
    scenes = regenerate_scenes(script_path)
    total = len(scenes)

    if num_recovered > total:
        recovered_urls = recovered_urls[:total]
        num_recovered = total

    print(f"Recovered {num_recovered}/{total} scenes from fal.ai")
    print(f"Need to generate {total - num_recovered} remaining scenes\n")

    # Step 3: Build processed list — recovered scenes use existing URLs
    processed = []
    for i in range(num_recovered):
        processed.append({"narration": scenes[i]["narration"], "video_url": recovered_urls[i]})
        print(f"Scene {i+1}/{total} — using recovered video")

    # Step 4: Generate remaining scenes
    for i in range(num_recovered, total):
        scene = scenes[i]
        idx = i + 1
        print(f"\n--- Scene {idx}/{total} (NEW) ---")
        image_url = generate_image(scene, idx, total)
        video_url = generate_video(image_url, scene, idx, total)
        processed.append({"narration": scene["narration"], "video_url": video_url})

    # Step 5: Submit to JSON2Video
    print(f"\n{'='*50}")
    print(f"All {total} scenes ready. Submitting to JSON2Video...")
    payload = build_json2video_payload(processed)

    # Save payload for debugging
    with open(os.path.join(os.path.dirname(__file__), "recovered_payload.json"), "w") as f:
        json.dump(payload, f, indent=2)

    resp = requests.post(JSON2VIDEO_URL, headers={"x-api-key": JSON2VIDEO_API_KEY, "Content-Type": "application/json"}, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    project_id = data.get("project") or data.get("id")
    print(f"Project submitted: {project_id}")

    # Step 6: Poll until done
    print("Polling for render completion...")
    while True:
        time.sleep(10)
        resp = requests.get(JSON2VIDEO_URL, headers={"x-api-key": JSON2VIDEO_API_KEY}, params={"project": project_id}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        movie = data.get("movie", data)
        status = movie.get("status", "unknown")
        print(f"  Status: {status}")
        if status == "done":
            print(f"\nVideo ready: {movie['url']}")
            return movie["url"]
        elif status == "error":
            print(f"\nRender failed: {movie.get('message')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
