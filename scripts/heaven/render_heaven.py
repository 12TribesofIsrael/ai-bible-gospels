"""Render Heaven on Earth: FLUX + Kling + JSON2Video pipeline"""
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
print(f"Loaded {len(scenes)} scenes\n")

processed = []
for i, scene in enumerate(scenes, 1):
    print(f"=== Scene {i}/{len(scenes)} ===")

    # FLUX image
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

    # Kling video
    print(f"  Kling video...")
    r = requests.post(KLING_URL, headers=fal_h, json={
        "image_url": img_url,
        "prompt": scene.get("motion", "Slow cinematic camera movement"),
        "duration": "10", "cfg_scale": 0.5,
    }, timeout=600)
    r.raise_for_status()
    data = r.json()
    vid_url = data.get("video", {}).get("url") or data["data"]["video"]["url"]
    print(f"  Video: {vid_url[:60]}...")

    processed.append({"narration": scene["narration"], "video_url": vid_url, "image_url": img_url})

    # Save progress after each scene
    with open("heaven_progress.json", "w") as f:
        json.dump(processed, f, indent=2)
    print(f"  Done ({i}/{len(scenes)})\n")

# Build JSON2Video payload
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
print(f"Project: {project_id}")
print("Polling...")

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
