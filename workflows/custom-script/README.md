# Custom Script → Cinematic Video Pipeline

Takes any script, concept, or idea as plain text — Claude AI breaks it into cinematic scenes with your brand style (dark backgrounds, golden divine light, ethnicity-accurate biblical figures), then generates a full video through FLUX → Kling → JSON2Video. Dynamic scene count — no hardcoded limits.

**Key difference from biblical-cinematic:** You provide a concept/script, Claude interprets it creatively (not word-for-word narration). The AI generates its own powerful narration, image prompts, motion, and lighting.

## Pipeline

1. **Claude AI** (Anthropic) — reads your script, creates N cinematic scenes (narration, image prompts, motion, lighting)
2. **FLUX** (fal.ai) — generates a photorealistic image per scene
3. **Kling** (fal.ai) — adds cinematic motion to each image (15s video clips)
4. **ElevenLabs** (via JSON2Video) — narrates each scene (voice: NgBYGKDDq2Z8Hnhatgma, 214 WPM at 0.9x speed)
5. **JSON2Video** — composites everything with transcription-based subtitles into a final MP4

**No template ID required** — JSON2Video payload is built dynamically in code for any scene count.

## Setup

Required environment variables in `.env` (project root):

```
ANTHROPIC_API_KEY=your_anthropic_key
FAL_KEY=your_fal_api_key
JSON2VIDEO_API_KEY=your_json2video_key
```

Install dependencies:

```bash
pip install requests python-dotenv uvicorn fastapi
```

## Web App (Recommended)

```bash
python workflows/custom-script/server.py
# Opens at http://localhost:8500
```

**Step 1** — Paste your script/concept in the text area, click "Generate Scenes with Claude AI"
**Step 2** — Review and edit scenes (narration, image prompts, motion, lighting). Add or remove scenes as needed.
**Step 3** — Click "Generate Video" — real-time progress shows per-scene FLUX/Kling status
**Step 4** — Download the final MP4

If the pipeline fails mid-way, click **"Retry from Failed Scene"** — it picks up where it left off without re-generating completed scenes.

### Fixing a Scene After Video is Complete

After your video renders, a **"Fix a Scene"** panel appears below the download link:

1. Select the scene number from the dropdown
2. Edit the image prompt, motion, lighting, or narration
3. Click **"Regenerate This Scene"**
4. Only that scene's FLUX image + Kling video is regenerated (~$0.24)
5. All scenes are re-submitted to JSON2Video for a fresh render (~$1.50)
6. Download the updated video

**Common fixes:**
- **AI drew extra limbs** — add "anatomically correct, each figure has exactly two arms" to the image prompt
- **Misspelled text in image** — remove all text/words from the image prompt (let subtitles handle text)
- **Wrong lighting/mood** — edit the lighting field
- **Bad camera motion** — edit the motion field

## CLI Usage

```bash
# Full pipeline: script → scenes → video
python workflows/custom-script/generate.py script.txt

# Preview scenes only (no FLUX/Kling/JSON2Video API calls)
python workflows/custom-script/generate.py script.txt --scenes-only

# Full pipeline + post-production (intro/outro/logo)
python workflows/custom-script/generate.py script.txt --post-produce

# Skip Claude — use pre-built scenes JSON directly
python workflows/custom-script/generate.py scenes.json
```

## Recovery

If the pipeline fails mid-generation, completed Kling videos can be recovered from fal.ai's history API:

```bash
python workflows/custom-script/recover.py
```

This queries fal.ai for completed videos, regenerates only the missing scenes, and submits all to JSON2Video.

## Input

Write your script as a plain text file. It can be:
- A full script with narrator lines and visual directions (like `example-trailer.txt`)
- A rough concept or outline
- A topic description

Claude will interpret it creatively and generate the right number of scenes.

## Output

- `{script_name}_scenes.json` — the generated scenes (saved for review/reuse)
- Final MP4 URL printed to console / shown in web UI
- With `--post-produce`: `output/{name}_final.mp4` with intro/outro/logo

## Important Notes

- **Never put text in FLUX image prompts** — AI image generators misspell words. Let subtitles handle all on-screen text.
- **Subtitles use transcription mode** — exact narration text is provided to JSON2Video, not auto-detected from audio. This ensures correct spelling of biblical names (Judah, Deuteronomy, Ephraim, etc.).
- **Single-scene regeneration** — if one scene needs fixing, regenerate only that scene's FLUX + Kling, then re-submit the full payload to JSON2Video (~$1.50 render cost, no other API costs).

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Web UI on port 8500 — paste script, edit scenes, generate video |
| `generate.py` | CLI pipeline — script → scenes → FLUX → Kling → JSON2Video |
| `recover.py` | Recovery script — fetches completed videos from fal.ai history |
| `example-trailer.txt` | Example input — channel trailer script |
