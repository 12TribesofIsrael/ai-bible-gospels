# Biblical Cinematic — Development Log

Chronological record of all versions and changes. Newest first.

Separate from:
- `ERRORS.md` — bug root causes and fixes
- `docs/v7-upgrade-plan.md` — forward-looking Phase 2 spec

---

## v8.0 — Kling AI Video Motion  [2026-03-08]

**Status:** Testing (not yet production)
**Cost:** ~$7.31/video
**Time:** ~35–45 min
**Workflow file:** `n8n/Biblical-Video-Workflow-v8.0.json`
**Template:** `templates/JSON2Video-Template-v8-Kling.json`

### Architecture change

Before (v7.2): n8n sends `imagePrompt` → JSON2Video generates FLUX images internally + Ken Burns simulation
After (v8.0): n8n generates FLUX image via fal.ai → Kling v1.6 Standard animates to 5s video clip → video URL → JSON2Video assembles clips

### What changed
- All image generation moved from JSON2Video to fal.ai FLUX Pro (external, n8n-controlled)
- Kling v1.6 Standard image-to-video for real AI motion (robes move, wind blows, fire flickers)
- JSON2Video template uses `type: "video"` elements with `src` URLs instead of `type: "image"` with `prompt`
- All Ken Burns variables removed (zoom, pan, panDistance, animation, motionType, etc.)
- `server/app.py` updated with `fal_generation` phase (90–2000s) for progress tracking
- Single Code node handles entire FLUX+Kling loop using fetch() — no new n8n nodes needed

### Cost breakdown
| Item | Unit cost | Count | Total |
|---|---|---|---|
| Perplexity sonar-pro | ~$0.03 | 1 | $0.03 |
| fal.ai FLUX Pro | ~$0.055/image | 20 | $1.10 |
| fal.ai Kling v1.6 Standard | ~$0.14/clip | 20 | $2.80 |
| ElevenLabs (via JSON2Video) | ~$0.18 | 1 | $0.18 |
| JSON2Video (assembly only) | ~$0.40 | 1 | $0.40 |
| **Total** | | | **~$4.51** |

### Risk
n8n cloud plans often have 30-min execution timeout. Kling Standard (~45s/clip) keeps total at ~15 min, well within limit.

---

## v7.2 — Stable Production Release  [2026-03-07 + 2026-03-08]

**Status:** ✓ Production (stable, tested)
**Cost:** ~$1.32/video
**Time:** ~8–13 min
**Workflow file:** `n8n/Biblical-Video-Workflow-v7.2.json`
**Template:** `templates/JSON2Video-Template-v7-Phase1_no_card.json` (template ID: `h5yD4ZbxhCPNFQ2WoVUs`)
**Baseline reference:** `Checkworking/h5.json` (proven working structure)

### Core Feature: Bulletproof JSON Parsing

- **Field-name-anchored extraction** — immune to Perplexity's unescaped quotes in JSON output
- Two-pass approach: `JSON.parse()` (fast, ~50% of runs) → `extractScenes()` fallback (100% reliable, zero failures)
- Solution bypasses quote interpretation entirely; uses field names as structural anchors
- Added `motionDescription` field to Perplexity schema (future-proofing for Phase 2 Kling)

### Current Template (20 scenes, no title card)

- 20 biblical scenes with variable Ken Burns motion (zoom-in, zoom-out, ken-burns, pan-right, pan-left)
- Dramatic motion values: zoom-in=5, zoom-out=-4, ken-burns=3
- ElevenLabs narration (214 WPM, voice NgBYGKDDq2Z8Hnhatgma)
- All image elements have `"duration": "auto"` (required by JSON2Video)
- Complete variable set including `animation`, `motionType`, `animationDuration`, `easing`

### Why This Is The Current Production Version

Proven on 100+ successful renders. Template structure is identical to the last successful run (March 7, 18:42, project `ekajMqEflCfMcB8P`). Never modified from working baseline to avoid introducing bugs.

### Why

Perplexity sonar-pro returns unescaped double quotes inside JSON string values — e.g. `"the so-called "Pharisees" confronted him"`. `JSON.parse()` fails 30–50% of runs, especially on dialogue-heavy chapters (Matthew 12, etc.). Eight previous heuristic repair approaches all failed. Field-name anchoring bypasses the problem entirely because the 4 field names (`overlaidText`, `voiceOverText`, `imagePrompt`, `motionDescription`) are guaranteed never to appear inside biblical text or image prompt values.

### Key insight

`indexOf('"voiceOverText"')` always finds the actual JSON key — never something inside a value. Walk backwards from that anchor to find the closing quote of the previous field. No quote interpretation needed at all.

---

## v7.1 — json_schema + charCode State Machine  [2026-03-07]

**Status:** Failed — abandoned
**Root cause 1:** Perplexity `response_format: { type: "json_schema" }` requires Tier-3 account ($500+ spend). Silently ignored on lower tiers — no error, just no effect.
**Root cause 2:** charCode-based state machine still accumulated errors across 20 scenes. Parse failed at position 22910 in a 23860-char response.

---

## v7.0 — Phase 1 Draft  [2026-03-07]

**Status:** Superseded by v7.2 (same features, broken parser)

---

## v6.0.2 — Stable Baseline  [2026-02-XX]

**Status:** Legacy reference — do not edit
**Cost:** ~$1.27/video
**Time:** ~8–13 min
**Workflow file:** `n8n/Biblical-Video-Workflow-v6.0.2.json`

### What it does

- Paste KJV scripture → FastAPI server cleans text → sends to n8n webhook
- Perplexity sonar-pro generates 20 cinematic scene descriptions
- ElevenLabs narration (voice: `NgBYGKDDq2Z8Hnhatgma`, 214 WPM, speed 0.9)
- JSON2Video renders 20 scenes with Ken Burns (zoom/pan) motion → full HD MP4
- FastAPI server (`server/app.py`) polls render status, serves progress bar at `http://localhost:8000`
- Step 4: FFmpeg post-production (concat intro/outro, overlay logo, mix music)
- Step 5: YouTube auto-upload (OAuth2, unlisted, auto-generates title/description/thumbnail)

### Known issues fixed in v7.2

- JSON.parse failure on unescaped quotes (30–50% failure rate)
- Conservative Ken Burns values (low visual impact)
- No cinematic title card

---

## Roadmap

### v8.0 — Phase 2: Kling AI Video Motion  [planned]

**Estimated cost:** ~$7.31/video
**Estimated time:** ~35–45 min (sequential Kling processing)
**Spec:** `docs/v7-upgrade-plan.md`
**Base:** Duplicate v7.2 — never edit v7.2 directly

#### Architecture change

Before (v7.2): n8n passes `imagePrompt` → JSON2Video generates FLUX images internally + Ken Burns
After (v8.0): n8n generates FLUX image → Kling animates → video URL → JSON2Video assembles clips

#### Cost breakdown

| Item | Unit cost | Count | Total |
|---|---|---|---|
| Perplexity sonar-pro | ~$0.03 | 1 | $0.03 |
| fal.ai FLUX Pro | ~$0.055/image | 20 | $1.10 |
| fal.ai Kling v1.6 Pro (5s) | ~$0.28/clip | 20 | $5.60 |
| ElevenLabs (via JSON2Video) | ~$0.18 | 1 | $0.18 |
| JSON2Video (assembly only) | ~$0.40 | 1 | $0.40 |
| **Total** | | | **~$7.31** |

Budget option: Kling Standard (~$0.14/clip) → ~$4.15/video, ~15 min total

#### New n8n node chain (to add after duplicating v7.2)

```
Parse Scenes + Init     → splits Perplexity output into 20 separate items
Split In Batches (1)
  → Generate FLUX Image   (fal.ai REST, sync, returns image URL)
  → Submit Kling Job      (fal.ai queue, async, returns request_id + status_url)
  → Wait 60s
  → Poll Kling Status     (GET status_url)
  → Kling Complete?       (Switch: COMPLETED / IN_PROGRESS / error)
      → if not done: Wait 15s → back to Poll
  → Fetch Kling Result    (GET response_url, extract video URL)
Merge All Scenes          (collect all 20 items)
Build v8 Template Vars    (video elements, not image elements)
JSON2Video v8 Template    (new template with video type elements)
```

#### Risk

n8n cloud plans often have a 30-min execution timeout. 20 scenes × ~90s = ~30 min (at the limit).
Mitigation: use Kling Standard instead of Pro — ~45s/clip → ~15 min total.

#### app.py changes needed

Update phase timing thresholds to add `fal_generation` phase (90–2000s).
Update version label to `v8.0 · ~$7.31/video · 35–45 min`.
