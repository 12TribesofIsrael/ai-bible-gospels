# Biblical Cinematic — Build Error Log

Running log of bugs hit during development. Kept here so we don't fix the same issue twice.
Archive this file when the app reaches full production.

---

## [2026-03-07] JSON2Video rejects rectangle elements in scenes

**Symptom:** Title card fails with `Object [movie/scenes[0]/elements[1]] does not match any of possible schemas: rectangle`

**Root cause:** JSON2Video does not support `type: "rectangle"` inside scene elements. The title_overlay and title_divider elements caused the entire scene to be rejected.

**Fix:** Removed both rectangle elements. Text readability maintained via heavy `shadow-offset` on text elements + enforcing a dark background in the FLUX image prompt.

**Prevention:** Do not use `type: "rectangle"` in JSON2Video scene elements. For overlays/dividers, rely on image prompt darkness and text shadows instead.

---

## [2026-03-07] Template zoom/pan variables mismatched with n8n output

**Symptom:** All Ken Burns motion on scenes 1–20 was silently ignored — images rendered static.

**Root cause:** Template referenced `scene1_zoomStart`, `scene1_zoomEnd`, `scene1_panStart`, `scene1_panEnd` but n8n sets `scene1_zoom` (integer) and `scene1_pan` (string). Variables never resolved so zoom/pan defaulted to no motion.

**Fix:** Updated template to use `{{scene1_zoom}}`, `{{scene1_pan}}`, `{{scene1_panDistance}}` matching what n8n actually outputs.

**Prevention:** When changing n8n variable names, always cross-check against the JSON2Video template variable block.

---

## [2026-03-02] Ghost server blocking port 8000

**Symptom:** New server wouldn't bind to port 8000. `taskkill /F /PID <pid>` returned "process not found" but port was still occupied and serving old content.

**Root cause:** The server process was orphaned — its parent shell exited (context window ended) but the process kept running. Windows `taskkill` can't kill processes that have been orphaned from their original session in some cases.

**Fix:**
```powershell
# Kill specific PID via PowerShell (more reliable than taskkill):
Stop-Process -Id <pid> -Force

# Nuclear option — kill all Python:
Get-Process python | Stop-Process -Force
```

**Prevention:** Always use PowerShell `Stop-Process` when `taskkill` fails.

---

## [2026-03-02] Server serving stale HTML after code update

**Symptom:** After rewriting `app.py`, the server kept returning the old HTML even after restarting with a fresh `__pycache__`.

**Root cause:** `uvicorn.run("app:app", reload=True)` uses `multiprocessing.spawn` on Windows to create worker processes. The spawned worker imported a cached/old version of the module instead of reading the updated file.

**Fix:** Changed to `uvicorn.run(app, reload=False)` — no multiprocessing spawn, single process, always reads what's on disk at startup.

**Prevention:** Never use `reload=True` on Windows for this project. Restart manually after editing `app.py`.

---

## [2026-03-02] JSON2Video API key not loading — `realtime: false`

**Symptom:** `/api/status` kept returning `realtime: false`. Direct API calls to JSON2Video returned auth errors.

**Root cause:** `.env` had two entries for `JSON2VIDEO_API_KEY` — the placeholder on line 22 and the real key on line 28. `python-dotenv` uses the **first** occurrence, so the placeholder won (`your-json2video-api-key`). The server printed "✓ configured" anyway because a non-empty string is truthy.

**Fix:** Removed the duplicate placeholder line. `.env` now has one clean entry:
```
JSON2VIDEO_API_KEY=2CcHHheoC8loYYgL6TuAnpmgDJAhPfG9C7fwpdpY
```

**Prevention:** Only one entry per key in `.env`. If you need to update a key, edit the existing line — don't append a new one.

---

## [2026-02-XX] n8n generating "undefined" chapter content

**Symptom:** Perplexity received a prompt with "undefined" instead of the scripture text. Output scenes described "undefined chapter" content.

**Root cause:** The `Bible Chapter Text Input` Set node in n8n had `{{ $json.body.text }}` typed into the **field NAME** box instead of the **field VALUE** box. This created a weirdly-named field, and the downstream JS expression `$('Bible Chapter Text Input').item.json.inputText` returned `undefined`.

**Fix:** In the Set node:
- Field NAME = `inputText` (literal text, not an expression)
- Field VALUE = `{{ $json.body.text }}` (expression mode ON)

**Prevention:** In n8n Set nodes, always double-check which box (name vs value) you're typing expressions into. The expression toggle must be ON for the VALUE, not the NAME.

---

## [2026-03-07] Perplexity JSON parse failure — unescaped quotes in string values

**Symptom:** "Enhanced Format for 16:9 Template" node throws `Expected ',' or ']' after array element in JSON at position 20371`. Fails ~30-50% of runs, especially on chapters with dialogue (Matthew 12, etc.).

**Root cause:** Perplexity sonar-pro returns JSON with unescaped double quotes inside string values — e.g. `"the so-called "Pharisees" confronted him"`. The `"` around `Pharisees` breaks `JSON.parse()` because JSON requires `\"` for quotes inside strings.

**Why 7 previous fixes failed:** Heuristic quote repair cannot reliably distinguish structural quotes (`"key": "value"`) from embedded quotes (`"text with "quotes" inside"`). The patterns are identical without schema awareness.

**What was tried and failed (v7.1):** Added `response_format: { type: "json_schema" }` to the Perplexity request + rewrote `repairJson()` with charCode-based state machine. Still failed — Perplexity's `json_schema` requires Tier-3 access ($500+ spend) and is **silently ignored** on lower tiers. The state machine repair accumulates errors across 20 scenes and can't reliably distinguish structural from embedded quotes.

**Definitive fix (v7.2 — CONFIRMED WORKING):**
Field-name-anchored extraction — skips `JSON.parse()` for the fallback path entirely. The 4 field names (`overlaidText`, `voiceOverText`, `imagePrompt`, `motionDescription`) are guaranteed to never appear inside biblical text or image prompt values. Using `indexOf('"fieldName"')` as structural boundaries is therefore 100% reliable. Walks backwards from the next field name occurrence to find the closing quote of each value.

Two-pass flow:
1. Try `JSON.parse()` first (fast path, works ~50% of runs)
2. On failure → `extractScenes()` field-name-anchored extraction (immune to unescaped quotes)

**Prevention:** For any LLM that may return unescaped quotes inside JSON string values, use field-name `indexOf` anchoring rather than quote-state-machine repair. Heuristic repair of quote context is fundamentally unreliable.

---

## Archive note

When the app is fully in production (YouTube auto-upload working, stable for 30+ days), move this file to:
`workflows/biblical-cinematic/archive/ERRORS-build-phase.md`
