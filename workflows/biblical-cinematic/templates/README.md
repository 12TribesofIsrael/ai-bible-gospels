# JSON2Video Templates

## Current Production Template

**File:** `JSON2Video-Template-v7-Phase1_no_card.json`
**Template ID:** `h5yD4ZbxhCPNFQ2WoVUs`
**Status:** ✓ Production (proven, tested, stable)

### What It Does
- 20 biblical scenes with ElevenLabs narration
- Variable Ken Burns motion (zoom-in, zoom-out, ken-burns, pan-right, pan-left)
- HD 1920×1080 output
- ~8–13 minute final video

### How to Use
1. Update this file in JSON2Video dashboard under Templates
2. Configure the template ID in n8n workflow (if needed)
3. Run renders

### DO NOT MODIFY
This template is stable and proven. If you need changes, create a new test template instead. See `archive/ARCHIVE_README.md` for why.

## v8.0 — Kling AI Video Motion Template (NEW)

**File:** `JSON2Video-Template-v8-Kling.json`
**Status:** Testing (not yet production)

### What It Does
- 20 biblical scenes with Kling AI video clips (real motion, not Ken Burns)
- ElevenLabs narration
- HD 1920×1080 output
- Uses `type: "video"` elements with `src` URLs from fal.ai Kling

### Variables per scene
- `sceneN_videoUrl` — Kling video clip URL
- `sceneN_voiceOverText` — narration text
- `sceneN_overlaidText` — subtitle text

## Old Templates

All old/broken templates have been moved to `archive/`. Do not use them.

## Source Baseline

The structure of this template is copied from `archive/references/v7-working-baseline/h5.json`, which is the proven working baseline from the last successful render (March 7, 18:42).
