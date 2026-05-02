#!/usr/bin/env python3
"""
One-shot recovery for a frozen custom-script render.

Pulls the N most-recent successful Kling videos (matching --model) from fal.ai
history, pairs them with the first N scenes of the supplied scenes JSON,
generates images and videos for the remaining scenes, and submits all scenes
to JSON2Video. Mirrors router.py's queue-submit pattern + aspect/voice config.

Usage:
  python recover_run.py --scenes recovery_scenes.json --recovered 1 \
      --aspect 9:16 --voice onwK4e9ZLuTAKqWW03F9 --model v3.0
"""
import argparse
import json
import os
import sys
import time

import requests
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

FAL_KEY = os.getenv("FAL_KEY")
JSON2VIDEO_API_KEY = os.getenv("JSON2VIDEO_API_KEY")

KLING_MODELS = {
    "v1.6":     {"url": "https://fal.run/fal-ai/kling-video/v1.6/standard/image-to-video", "duration": "10"},
    "v2.1":     {"url": "https://fal.run/fal-ai/kling-video/v2.1/standard/image-to-video", "duration": "10"},
    "v3.0":     {"url": "https://fal.run/fal-ai/kling-video/v3/standard/image-to-video",   "duration": "15"},
    "v3.0-pro": {"url": "https://fal.run/fal-ai/kling-video/v3/pro/image-to-video",        "duration": "15"},
    "o3":       {"url": "https://fal.run/fal-ai/kling-video/o3/standard/image-to-video",   "duration": "15"},
    "o3-pro":   {"url": "https://fal.run/fal-ai/kling-video/o3/pro/image-to-video",        "duration": "15"},
}

ASPECT_RATIOS = {
    "16:9": {"flux": "landscape_16_9", "kling": "16:9", "j2v": "full-hd",         "sub_font_size": 80, "sub_max_words": 4},
    "1:1":  {"flux": "square_hd",      "kling": "1:1",  "j2v": "instagram-feed",  "sub_font_size": 70, "sub_max_words": 3},
    "9:16": {"flux": "portrait_16_9",  "kling": "9:16", "j2v": "instagram-story", "sub_font_size": 64, "sub_max_words": 3},
}

FLUX_URL = "https://fal.run/fal-ai/flux-pro/v1.1"
JSON2VIDEO_URL = "https://api.json2video.com/v2/movies"
FAL_HISTORY_URL = "https://api.fal.ai/v1/models/requests/by-endpoint"

VOICE_SPEED = 0.9
DEFAULT_VOICE = "NgBYGKDDq2Z8Hnhatgma"

NEGATIVE_PROMPT = "cartoon, anime, illustration, painting, drawing, digital art, concept art, stylized, 3D render, CGI, plastic skin, smooth skin, airbrushed, watercolor, sketch, unrealistic, low quality, blurry"


def fal_headers():
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}


def fal_queue_submit(sync_url, payload, kind=None, poll_seconds=10, max_wait_seconds=1800):
    """Submit to fal.ai's async queue endpoint and poll until completion.
    Mirrors router.py — avoids the duplicate-charge trap of sync endpoints.
    """
    queue_url = sync_url.replace("https://fal.run/", "https://queue.fal.run/", 1)
    submit = requests.post(queue_url, headers=fal_headers(), json=payload, timeout=60)
    submit.raise_for_status()
    job = submit.json()
    status_url = job.get("status_url")
    response_url = job.get("response_url")
    if not status_url or not response_url:
        raise RuntimeError(f"fal.ai queue missing status/response url: {job}")

    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        time.sleep(poll_seconds)
        err = None
        for _ in range(3):
            try:
                s = requests.get(status_url, headers=fal_headers(), timeout=30)
                s.raise_for_status()
                err = None
                break
            except Exception as e:
                err = e
                time.sleep(2)
        if err:
            continue
        status = s.json().get("status")
        if status == "COMPLETED":
            r = requests.get(response_url, headers=fal_headers(), timeout=60)
            r.raise_for_status()
            return r.json()
        if status in ("FAILED", "ERROR", "CANCELLED"):
            raise RuntimeError(f"fal.ai queue status={status}: {s.json()}")
    raise RuntimeError(f"fal.ai queue timed out after {max_wait_seconds}s (request_id={job.get('request_id')})")


def recover_kling_videos(n: int, kling_url: str):
    """Pull the n most-recent successful Kling videos from fal.ai history (chronological order)."""
    endpoint_id = kling_url.replace("https://fal.run/", "")
    print(f"Querying fal.ai history for last {max(n, 20)} successes on {endpoint_id}...")
    resp = requests.get(
        FAL_HISTORY_URL,
        headers={"Authorization": f"Key {FAL_KEY}"},
        params={"endpoint_id": endpoint_id, "limit": max(n, 20), "status": "success"},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    items.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    items = items[:n]
    if len(items) < n:
        print(f"WARNING: only found {len(items)} successes in history, needed {n}")
    import fal_client
    os.environ["FAL_KEY"] = FAL_KEY
    urls = []
    for item in items:
        rid = item["request_id"]
        result = fal_client.result(endpoint_id, rid)
        video_url = result.get("video", {}).get("url")
        started_at = item.get("started_at", "?")
        print(f"  {started_at}  {rid}  ->  {video_url}")
        urls.append(video_url)
    urls.reverse()  # chronological so scene order matches render order
    return urls


def generate_image(scene, flux_size):
    prompt = scene["imagePrompt"]
    if scene.get("lighting"):
        prompt += f", {scene['lighting']}"
    print(f"  FLUX: {prompt[:80]}...")
    data = fal_queue_submit(FLUX_URL, {
        "prompt": prompt, "negative_prompt": NEGATIVE_PROMPT,
        "image_size": flux_size, "num_inference_steps": 28, "num_images": 1,
    }, kind="flux", poll_seconds=5, max_wait_seconds=300)
    return data["images"][0]["url"]


def generate_video(image_url, scene, kling_url, kling_aspect, kling_duration):
    print(f"  Kling: {scene.get('motion', 'slow cinematic')[:60]}")
    data = fal_queue_submit(kling_url, {
        "image_url": image_url,
        "prompt": scene.get("motion", "Slow cinematic camera movement"),
        "duration": kling_duration, "cfg_scale": 0.5,
        "aspect_ratio": kling_aspect,
    }, kind="kling", poll_seconds=10, max_wait_seconds=1800)
    return data.get("video", {}).get("url") or data["data"]["video"]["url"]


def build_json2video_payload(processed, voice_id, ratio):
    subtitle_settings = {
        "style": "classic", "font-family": "Oswald Bold", "font-size": ratio["sub_font_size"],
        "position": "bottom-center", "line-color": "#CCCCCC", "word-color": "#FFFF00",
        "outline-color": "#000000", "outline-width": 8, "shadow-color": "#000000",
        "shadow-offset": 6, "max-words-per-line": ratio["sub_max_words"],
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
                             "text": s["narration"], "voice": voice_id,
                             "model": "elevenlabs", "speed": VOICE_SPEED})
        scenes.append({"id": f"scene{i}", "comment": f"Scene {i}",
                       "duration": "auto", "elements": elements})
    return {"resolution": ratio["j2v"], "quality": "high",
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
    parser.add_argument("--recovered", type=int, default=1,
                        help="Number of already-completed Kling clips to pull from fal.ai history")
    parser.add_argument("--aspect", default="9:16", choices=list(ASPECT_RATIOS.keys()))
    parser.add_argument("--voice", default=DEFAULT_VOICE,
                        help="ElevenLabs voice id")
    parser.add_argument("--model", default="v3.0", choices=list(KLING_MODELS.keys()))
    args = parser.parse_args()

    if not FAL_KEY or not JSON2VIDEO_API_KEY:
        print("Missing FAL_KEY or JSON2VIDEO_API_KEY in .env", file=sys.stderr)
        sys.exit(1)

    ratio = ASPECT_RATIOS[args.aspect]
    kling = KLING_MODELS[args.model]

    scenes_path = args.scenes if os.path.isabs(args.scenes) else os.path.join(os.path.dirname(__file__), args.scenes)
    with open(scenes_path, encoding="utf-8") as f:
        scenes = json.load(f)["scenes"]
    total = len(scenes)
    print(f"Loaded {total} scenes from {scenes_path}")
    print(f"Aspect={args.aspect}  Voice={args.voice}  Model={args.model} ({kling['duration']}s clips)")
    print(f"Recovering first {args.recovered} from fal.ai history; regenerating {total - args.recovered}")
    print()

    urls = recover_kling_videos(args.recovered, kling["url"])
    print()

    processed = []
    for i in range(len(urls)):
        if not urls[i]:
            print(f"Scene {i+1}: recovery returned no URL — will regenerate instead")
            processed.append(None)
        else:
            processed.append({"narration": scenes[i]["narration"], "video_url": urls[i]})
            print(f"Scene {i+1}/{total} — using recovered video")

    for i in range(total):
        if i < len(processed) and processed[i] is not None:
            continue
        scene = scenes[i]
        print(f"\n--- Scene {i+1}/{total} (generating) ---")
        image_url = generate_image(scene, ratio["flux"])
        video_url = generate_video(image_url, scene, kling["url"], ratio["kling"], kling["duration"])
        entry = {"narration": scene["narration"], "video_url": video_url}
        if i < len(processed):
            processed[i] = entry
        else:
            processed.append(entry)

    print(f"\n{'='*60}")
    print(f"All {total} scenes ready. Submitting to JSON2Video...")
    payload = build_json2video_payload(processed, args.voice, ratio)
    payload_path = os.path.join(os.path.dirname(__file__), "recovered_payload.json")
    with open(payload_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Payload saved to {payload_path}")
    final_url = submit_and_poll(payload)
    print(f"\nDONE: {final_url}")


if __name__ == "__main__":
    main()
