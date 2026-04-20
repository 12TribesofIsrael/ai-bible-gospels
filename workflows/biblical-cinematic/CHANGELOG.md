# Changelog

All notable changes to the Biblical Cinematic Generator. Each entry includes what changed, why, and what to do if it breaks.

---

## [v8.1.0] - 2026-04-20
### Added
- ElevenLabs voice picker in both Scripture Mode and Custom Script Mode (Step 2, under the Kling model selector)
- Dropdown of named voices (Pro Narrator default, Young Jamal, Tommy Israel, William J, Hakeem, Lamar Lincoln) plus a "paste your own voice ID" override input for any other ElevenLabs voice
- `GET /v9/api/voices` and `GET /custom/api/voices` — return the catalog + default
- `voice_id` accepted on every render-triggering endpoint (`/generate-video`, `/fix-scene`, `/fix-scenes`, `/preview-scenes`); persisted into `pipeline_state` so retry/resume re-uses the chosen voice
- Voice catalogs declared in `biblical_pipeline.py` and `custom-script/router.py` (kept in sync; documented in the README)

### Fixed
- Custom Script Mode default voice was set to `lSsRWJXY8EgpdEGyqC3f`, which is a JSON2Video template ID — not a real ElevenLabs voice. Both modes now default to `NgBYGKDDq2Z8Hnhatgma` ("Pro Narrator")

### Files Modified
- `server/app.py` (Scripture Mode UI + voice loader JS)
- `server/biblical_pipeline.py` (VOICES catalog, `resolve_voice`, `voice_id` plumbing through pipeline + payload builder)
- `../custom-script/router.py` (mirror of above for Custom Script Mode)
- `README.md` (voice table refreshed, removed Daniel/template-ID row)

### Rollback
- `git revert <commit>` — pure additive change, default voice id is unchanged for Scripture Mode (was already `NgBYGKDDq2Z8Hnhatgma`); Custom Script reverts to the broken template-ID default

---

## [v8.0.3] - 2026-03-08
### Added
- Bible chapter selector dropdown (81 books from KJV+Apocrypha PDF)
- `/api/bible/books` and `/api/bible/chapter` endpoints
- `assets/bible_chapters.json` (1365 chapters pre-parsed from PDF)

### Changed
- Perplexity prompt: ethnicity-aware character depiction (Israelites = Black Hebrew Israelites, other nations = their own ethnicity)
- Text processor: 50+ additional archaic word fixes, generic I→J rule, two-pass cleaning

### Files Modified
- `server/app.py`
- `text_processor/biblical_text_processor_v2.py`
- `n8n/Biblical-Video-Workflow-v7.2.json`
- `n8n/Biblical-Video-Workflow-v8.0.json`

### Rollback
- Restore from `backups/workflows/v8.0-master_2026-03-08.json`

---

## [v8.0.2] - 2026-03-08
### Fixed
- Black screen between scenes: Kling 5s video ended while 15-30s narration continued
- Root cause: video element had no loop/duration properties
- Fix: Added `"loop": -1` + `"duration": -2` to all 20 video elements in template

### Changed
- Template ID: `yia2WweBcQAohYpBbByf` → `cHtpubYegDm2patG2tym`

### Files Modified
- `templates/JSON2Video-Template-v8-Kling.json`
- `n8n/Biblical-Video-Workflow-v8.0.json`

### Rollback
- Template: `backups/templates/v8-Kling-master_2026-03-08.json`
- Workflow: `backups/workflows/v8.0-master_2026-03-08.json`

---

## [v8.0.1] - 2026-03-08
### Fixed
- n8n Cloud: `$env.FAL_KEY` blocked → hardcoded FAL_KEY in HTTP headers
- n8n Cloud: `fetch()` blocked → rebuilt with HTTP Request nodes
- fal.ai 429 rate limit → added Split In Batches (batch size 1)

### Files Modified
- `n8n/Biblical-Video-Workflow-v8.0.json`
- `scripts/rebuild_v8_workflow.py`

---

## [v8.0.0] - 2026-03-08
### Added
- Kling AI video motion (replaces Ken Burns static images)
- FLUX image → Kling image-to-video → JSON2Video assembly
- New template: `JSON2Video-Template-v8-Kling.json`
- New workflow: `Biblical-Video-Workflow-v8.0.json`

### Cost Impact
- v7.2: ~$1.32/video → v8.0: ~$7.31/video
- v7.2: ~10 min → v8.0: ~35-45 min

---

## [v7.2.0] - 2026-03-07
### Stable Production Release
- 20-scene biblical videos with Ken Burns zoom/pan
- Field-name-anchored JSON parsing (immune to Perplexity unescaped quotes)
- Title card auto-extraction
- ~$1.32/video, ~10 min render time
