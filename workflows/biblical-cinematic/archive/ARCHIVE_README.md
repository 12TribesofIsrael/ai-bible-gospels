# Archive — Old and Broken Files

This folder contains old, broken, or superseded versions of workflows and templates. **Do not use these files.**

## Folder Structure

### `releases/`
Historical releases and versions. Reference only.

#### `v6.0.2/`
Legacy stable v6.0.2 baseline (working, but slower Perplexity JSON parsing). Do not use.

#### `v7.1-broken/`
Failed v7.1 attempt (attempted json_schema but requires Tier-3 Perplexity account, silently ignored). Do not use.

#### `v7.2-broken-templates/`
Broken v7.2 templates that caused 8 consecutive render failures:
- `JSON2Video-Template-v7-Phase1.json` — had missing `duration`, unsupported elements, stripped variables
Do not use.

### `references/`
Reference files that may be useful for understanding the baseline structure.

#### `v7-working-baseline/`
Proven working baseline from the last successful render (March 7, 18:42):
- `h5.json` — **Source of truth for valid template structure.** This is the template that was copied to `templates/JSON2Video-Template-v7-Phase1_no_card.json`
- `Biblical-Video-Workflow-v7-Phase1 (1).json` — Old workflow reference
Use `h5.json` ONLY as a structural reference if you need to understand what the template should look like.

## Current Production Files

**Do not archive or move these:**

| File | Location |
|---|---|
| Workflow | `n8n/Biblical-Video-Workflow-v7.2.json` |
| Template | `templates/JSON2Video-Template-v7-Phase1_no_card.json` |

These are the ONLY files you should use for production renders.

## Rule for Future Changes

**Never modify a working template.** Create a new test template first. Only move it to production after successful testing. Archive the old template only after confirming the new one works reliably.

See `ERRORS.md` [2026-03-08] for full details on the 8-failure incident and why reverting to baseline was the solution.
