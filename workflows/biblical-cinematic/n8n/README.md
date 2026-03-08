# n8n Workflows

## Current Production Workflow

**File:** `Biblical-Video-Workflow-v7.2.json`
**Status:** ✓ Production (proven, tested, stable)

### What It Does
- Takes KJV scripture text input
- Parses with Perplexity sonar-pro → 20 cinematic scene descriptions
- Generates ElevenLabs narration (214 WPM, voice NgBYGKDDq2Z8Hnhatgma)
- Calls JSON2Video to render final video
- Returns download link and real-time progress updates

### How to Use
1. Import this workflow into n8n
2. Set the template ID to `h5yD4ZbxhCPNFQ2WoVUs` in the JSON2Video node (or update if changed)
3. Ensure environment variables are set:
   - `N8N_WEBHOOK_URL` — your n8n webhook endpoint
   - `JSON2VIDEO_API_KEY` — JSON2Video API key
4. Publish/activate the workflow
5. Trigger via webhook or manual execution

### Key Features
- **Field-name-anchored JSON parsing** — 100% reliable (immune to Perplexity's unescaped quotes)
- **120s timeout** on Perplexity call (handles first-run schema compilation)
- **Valid pan values** for zoom-only scenes (pan: "right" or "left" instead of empty string)

### DO NOT MODIFY LIGHTLY
This workflow is stable. If you need to make changes:
1. Duplicate it first as a test version
2. Make changes
3. Test thoroughly before deploying to production
4. Only replace this file after successful testing

## v8.0 — Kling AI Video Motion (NEW)

**File:** `Biblical-Video-Workflow-v8.0.json`
**Status:** Testing (not yet production)

### What It Does
- Same Perplexity scene generation as v7.2
- Generates FLUX Pro images via fal.ai for each scene
- Animates each image with Kling v1.6 Standard (5s video clips)
- Passes video URLs to JSON2Video for assembly (no Ken Burns)
- **Cost:** ~$7.31/video | **Time:** ~35-45 min

### Prerequisites
- `FAL_KEY` environment variable set in n8n
- New JSON2Video template with `video` elements imported
- fal.ai account with sufficient credits

### How to Use
1. Import this workflow into n8n
2. Add fal.ai Header Auth credential: `Authorization: Key YOUR_FAL_KEY`
3. Set `FAL_KEY` in n8n environment variables
4. Import `templates/JSON2Video-Template-v8-Kling.json` to JSON2Video dashboard
5. Update the template ID in the JSON2Video node
6. Test with a short chapter first

## Legacy Workflows

**File:** `Biblical-Video-Workflow-v6.0.2.json`
**Status:** Legacy reference (do not edit or use)

This is v6 baseline, kept for reference only in case you need to understand the old approach.
