#!/usr/bin/env python3
"""
One-shot recovery for a frozen custom-script render.

Pulls the N most-recent successful Kling v3 standard videos from fal.ai history,
pairs them with the first N scenes of the supplied scenes JSON, generates images
and videos for the remaining scenes, and submits all scenes to JSON2Video.

Usage:
  python recover_run.py --scenes recovery_scenes.json --recovered 3
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

FAL_KEY = os.getenv("FAL_KEY")
JSON2VIDEO_API_KEY = os.getenv("JSON2VIDEO_API_KEY")

FLUX_URL = "https://fal.run/fal-ai/flux-pro/v1.1"
KLING_URL = "https://fal.run/fal-ai/kling-video/v3/standard/image-to-video"
JSON2VIDEO_URL = "https://api.json2video.com/v2/movies"
FAL_HISTORY_URL = "https://api.fal.ai/v1/models/requests/by-endpoint"
KLING_ENDPOINT_ID = "fal-ai/kling-video/v3/standard/image-to-video"

VOICE_ID = "NgBYGKDDq2Z8Hnhatgma"
VOICE_SPEED = 0.9

NEGATIVE_PROMPT = "text, letters, words, writing, typography, captions, subtitles, watermark, logo, signature"


def fal_headers():
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}


def recover_kling_videos(n: int):
    """Pull the n most-recent successful Kling v3 standard videos from fal.ai."""
    print(f"Querying fal.ai history for last {max(n, 20)} v3 standard successes...")
    resp = requests.get(
        FAL_HISTORY_URL,
        headers={"Authorization": f"Key {FAL_KEY}"},
        params={
            "endpoint_id": KLING_ENDPOINT_ID,
            "limit": max(n, 20),
            "status": "success",
        },
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    # Sort newest-first so we grab the freshest runs.
    items.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    items = items[:n]
    if len(items) < n:
        print(f"WARNING: only found {len(items)} successes in history, needed {n}")
    # fal_client.result() is more reliable than history payloads for video URLs.
    import fal_client
    os.environ["FAL_KEY"] = FAL_KEY
    urls = []
    for item in items:
        rid = item["request_id"]
        result = fal_client.result(KLING_ENDPOINT_ID, rid)
        video_url = result.get("video", {}).get("url")
        started_at = item.get("started_at", "?")
        print(f"  {started_at}  {rid}  ->  {video_url}")
        urls.append(video_url)
    # Reverse to chronological so scene order matches render order.
    urls.reverse()
    return urls


def generate_image(scene):
    prompt = scene["imagePrompt"]
    if scene.get("lighting"):
        prompt += f", {scene['lighting']}"
    print(f"  FLUX: {prompt[:80]}...")
    resp = requests.post(FLUX_URL, headers=fal_headers(), json={
        "prompt": prompt, "negative_prompt": NEGATIVE_PROMPT,
        "image_size": "landscape_16_9", "num_inference_steps": 28, "num_images": 1,
    }, timeout=180)
    resp.raise_for_status()
    return resp.json()["images"][0]["url"]


def generate_video(image_url, scene):
    print(f"  Kling: {scene.get('motion', 'slow cinematic')[:60]}")
    resp = requests.post(KLING_URL, headers=fal_headers(), json={
        "image_url": image_url,
        "prompt": scene.get("motion", "Slow cinematic camera movement"),
        "duration": "15", "cfg_scale": 0.5,
    }, timeout=900)
    resp.raise_for_status()
    data = resp.json()
    return data.get("video", {}).get("url") or data["data"]["video"]["url"]


def build_json2video_payload(processed):
    """Matches router.py's current payload shape — movie-level subtitles."""
    subtitle_settings = {
        "style": "classic", "font-family": "Oswald Bold", "font-size": 80,
        "position": "bottom-center", "line-color": "#CCCCCC", "word-color": "#FFFF00",
        "outline-color": "#000000", "outline-width": 8, "shadow-color": "#000000",
        "shadow-offset": 6, "max-words-per-line": 4,
    }
    movie_subtitles = {
        "id": "movie_subtitles", "type": "subtitles", "language": "en",
        "model": "default", "settings": subtitle_settings,
    }
    scenes = []
    for i, s in enumerate(processed, 1):
        elements = [
            {"id": f"scene{i}_bg", "type": "video", "src": s["video_url"],
             "resize": "cover", "loop": -1, "duration": -2},
        ]
        if s.get("narration", "").strip():
            elements.append({"id": f"scene{i}_voice", "type": "voice",
                             "text": s["narration"], "voice": VOICE_ID,
                             "model": "elevenlabs", "speed": VOICE_SPEED})
        scenes.append({"id": f"scene{i}", "comment": f"Scene {i}",
                       "duration": "auto", "elements": elements})
    return {"resolution": "full-hd", "quality": "high",
            "elements": [movie_subtitles], "scenes": scenes}


def submit_and_poll(payload):
    resp = requests.post(JSON2VIDEO_URL,
        headers={"x-api-key": JSON2VIDEO_API_KEY, "Content-Type": "application/json"},
        json=payload, timeout=60)
    resp.raise_for_status()
    project_id = resp.json().get("project") or resp.json().get("id")
    print(f"JSON2Video project: {project_id}")
    while True:
        time.sleep(10)
        r = requests.get(JSON2VIDEO_URL,
            headers={"x-api-key": JSON2VIDEO_API_KEY},
            params={"project": project_id}, timeout=30)
        r.raise_for_status()
        movie = r.json().get("movie", r.json())
        status = movie.get("status", "unknown")
        print(f"  {status}")
        if status == "done":
            return movie["url"]
        if status == "error":
            raise RuntimeError(f"JSON2Video failed: {movie.get('message')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", default="recovery_scenes.json",
                        help="JSON file with {scenes: [...]} from the browser")
    parser.add_argument("--recovered", type=int, default=3,
                        help="Number of already-completed Kling clips to pull from fal.ai history")
    args = parser.parse_args()

    with open(args.scenes, encoding="utf-8") as f:
        scenes = json.load(f)["scenes"]
    total = len(scenes)
    print(f"Loaded {total} scenes from {args.scenes}")
    print(f"Recovering first {args.recovered} from fal.ai history; regenerating {total - args.recovered}")
    print()

    urls = recover_kling_videos(args.recovered)
    print()

    processed = []
    for i in range(len(urls)):
        if not urls[i]:
            print(f"Scene {i+1}: recovery returned no URL — will regenerate instead")
            processed.append(None)
        else:
            processed.append({"narration": scenes[i]["narration"], "video_url": urls[i]})
            print(f"Scene {i+1}/{total} — using recovered video")

    # Regenerate any gaps + remaining scenes
    for i in range(total):
        if i < len(processed) and processed[i] is not None:
            continue
        scene = scenes[i]
        print(f"\n--- Scene {i+1}/{total} (generating) ---")
        image_url = generate_image(scene)
        video_url = generate_video(image_url, scene)
        entry = {"narration": scene["narration"], "video_url": video_url}
        if i < len(processed):
            processed[i] = entry
        else:
            processed.append(entry)

    print(f"\n{'='*60}")
    print(f"All {total} scenes ready. Submitting to JSON2Video...")
    payload = build_json2video_payload(processed)
    with open(os.path.join(os.path.dirname(__file__), "recovered_payload.json"), "w") as f:
        json.dump(payload, f, indent=2)
    final_url = submit_and_poll(payload)
    print(f"\nDONE: {final_url}")


if __name__ == "__main__":
    main()
