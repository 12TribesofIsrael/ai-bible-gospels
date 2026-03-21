"""Resume Heaven on Earth render from scene 6"""
import os, requests, time, json
from dotenv import load_dotenv
load_dotenv()

FAL_KEY = os.getenv("FAL_KEY")
JSON2VIDEO_API_KEY = os.getenv("JSON2VIDEO_API_KEY")
FLUX_URL = "https://fal.run/fal-ai/flux-pro"
KLING_URL = "https://fal.run/fal-ai/kling-video/v2/master/image-to-video"
JSON2VIDEO_URL = "https://api.json2video.com/v2/movies"
fal_h = {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}
VOICE_ID = "NgBYGKDDq2Z8Hnhatgma"
SPEED = 0.8

scenes = json.load(open("heaven_scenes.json"))["scenes"]
processed = json.load(open("heaven_progress.json"))
resume_from = len(processed)
print(f"Resuming from scene {resume_from + 1}/{len(scenes)} ({resume_from} already done)\n")

for i in range(resume_from, len(scenes)):
    scene = scenes[i]
    print(f"=== Scene {i+1}/{len(scenes)} ===")

    prompt = scene["imagePrompt"]
    if scene.get("lighting"):
        prompt += f", {scene['lighting']}"
    print(f"  FLUX image...")
    r = requests.post(FLUX_URL, headers=fal_h, json={
        "prompt": prompt, "image_size": "landscape_16_9",
        "num_inference_steps": 28, "num_images": 1,
    }, timeout=120)
    r.raise_for_status()
    img_url = r.json()["images"][0]["url"]
    print(f"  Image: {img_url[:60]}...")

    # Use queue API for Kling to avoid timeout
    print(f"  Kling video (queue mode)...")
    r = requests.post(
        f"https://queue.fal.run/fal-ai/kling-video/v2/master/image-to-video",
        headers=fal_h, json={
            "image_url": img_url,
            "prompt": scene.get("motion", "Slow cinematic camera movement"),
            "duration": "10", "cfg_scale": 0.5,
        }, timeout=30)
    r.raise_for_status()
    request_id = r.json()["request_id"]
    print(f"  Request ID: {request_id}")

    # Poll for completion
    while True:
        time.sleep(10)
        r = requests.get(
            f"https://queue.fal.run/fal-ai/kling-video/v2/master/image-to-video/requests/{request_id}/status",
            headers=fal_h, timeout=15)
        status = r.json().get("status", "unknown")
        print(f"  Kling: {status}")
        if status == "COMPLETED":
            r = requests.get(
                f"https://queue.fal.run/fal-ai/kling-video/v2/master/image-to-video/requests/{request_id}",
                headers=fal_h, timeout=30)
            data = r.json()
            vid_url = data.get("video", {}).get("url") or data["data"]["video"]["url"]
            print(f"  Video: {vid_url[:60]}...")
            break
        elif status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Kling failed for scene {i+1}: {r.json()}")

    processed.append({"narration": scene["narration"], "video_url": vid_url, "image_url": img_url})
    with open("heaven_progress.json", "w") as f:
        json.dump(processed, f, indent=2)
    print(f"  Done ({i+1}/{len(scenes)})\n")

# JSON2Video render
print("=== Submitting to JSON2Video ===")
subtitle_settings = {
    "style": "classic", "font-family": "Oswald Bold", "font-size": 80,
    "position": "bottom-center", "line-color": "#CCCCCC", "word-color": "#FFFF00",
    "outline-color": "#000000", "outline-width": 8, "shadow-color": "#000000",
    "shadow-offset": 6, "max-words-per-line": 4,
}
j2v_scenes = []
for i, s in enumerate(processed, 1):
    elements = [
        {"id": f"scene{i}_bg", "type": "video", "src": s["video_url"], "resize": "cover", "loop": -1, "duration": -2},
    ]
    if s.get("narration", "").strip():
        elements.append({"id": f"scene{i}_voice", "type": "voice", "text": s["narration"], "voice": VOICE_ID, "model": "elevenlabs", "speed": SPEED})
    j2v_scenes.append({"id": f"scene{i}", "comment": f"Scene {i}", "duration": "auto", "elements": elements})

payload = {
    "resolution": "full-hd", "quality": "high",
    "elements": [{"id": "movie_subtitles", "type": "subtitles", "language": "en", "model": "default", "settings": subtitle_settings}],
    "scenes": j2v_scenes,
}

r = requests.post(JSON2VIDEO_URL, headers={"x-api-key": JSON2VIDEO_API_KEY, "Content-Type": "application/json"}, json=payload, timeout=30)
r.raise_for_status()
project_id = r.json().get("project") or r.json().get("id")
print(f"Project: {project_id}\nPolling...")

while True:
    time.sleep(15)
    r = requests.get(JSON2VIDEO_URL, headers={"x-api-key": JSON2VIDEO_API_KEY}, params={"project": project_id}, timeout=30)
    movie = r.json().get("movie", r.json())
    status = movie.get("status", "unknown")
    print(f"  {status}")
    if status == "done":
        print(f"\nDONE! {movie['url']}")
        break
    elif status == "error":
        print(f"\nERROR: {movie.get('message')}")
        break
