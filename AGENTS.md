# AGENTS.md

This file defines repository-specific guidance for coding agents working in this project.

## Project Scope

- Project type: World of Warcraft TBC Classic addon (Lua) plus Python data-generation scripts.
- Addon root: `BiScore/`
- Data/download tooling: `scripts/` and `downloads/wowhead_tbc_bis/`

## Core Philosophy

- Prioritize score stability and predictability over broad refactors.
- Preserve clear boundaries:
  - `BiScore/BiScore.lua`: bootstrap, events, slash commands
  - `BiScore/core/*.lua`: scoring, phase state, inspect queue
  - `BiScore/ui/*.lua`: display and tooltip/inspect hooks
  - `BiScore/data/*.lua`: generated class/profile/phase payloads
- Keep behavior deterministic for unchanged input data.

## Architecture Map

1. Bootstrap and events
- `BiScore/BiScore.lua` registers `ADDON_LOADED`, `PLAYER_LOGIN`, `INSPECT_READY`.
- Initializes modules and triggers first character-score refresh.

2. Phase config and saved defaults
- `BiScore/core/phase.lua` owns phase clamping and defaults in `BiScoreDB` and `BiScoreCharDB`.

3. Scoring engine
- `BiScore/core/scoring.lua` owns profile resolution, slot/EP logic, penalties, and final score output.

4. Inspect queue
- `BiScore/core/inspect.lua` serializes inspect requests and handles async completion.

5. UI integration
- `BiScore/ui/tooltip.lua`, `BiScore/ui/charframe.lua`, `BiScore/ui/inspectframe.lua` show scores safely with loading/N/A fallbacks.

## Coding Conventions

- Use `local addon = BiScore` per module.
- Expose public module methods as `function addon:MethodName(...)`.
- Keep non-shared helpers local.
- Prefer early returns for guard checks in event/UI code.
- Preserve existing method names unless intentionally migrating all call sites.

## Data Contract (Critical)

Runtime scoring expects:

- `BiScoreData["CLASS"]["Profile"][phase]` for phases `1..5`
- Each phase has:
  - `slots` (slot ID keyed)
  - `weights` (stat-key weights)
  - `scoring = { floor = <num>, cap = <num> }`
- Slot IDs must match IDs used by `GetInventoryItemLink(unit, slotID)`.

Do not change data shape without updating runtime consumers in `core/scoring.lua`.

## High-Risk Areas

Treat these as high-impact and validate carefully:

- `SLOT_WEIGHTS` or `SCORE_SLOTS`
- rank caps/floors and phase scalars
- two-hand/offhand weighting behavior
- profile auto-detection logic
- gem/enchant penalty multipliers
- return shape of `GetUnitBiScore`

## Data Pipeline Guidance

- Source docs: `DOC_Downloaded_Guide_files.md`
- Scripts:
  - `scripts/download_tbc_bis_guides.py`
  - `scripts/extract_wowhead_guide_markup.py`
  - `scripts/parse_wowhead_html.py`
  - `scripts/check_suspicious_data.py`

Prefer regenerating `BiScore/data/*.lua` via scripts rather than hand-editing large rank tables.

## Validation Workflow

Run from repo root:

```bash
python3 -m py_compile scripts/*.py
python3 scripts/check_suspicious_data.py
```

For runtime Lua edits, also review changed logic in:

- `BiScore/core/scoring.lua`
- `BiScore/core/phase.lua`
- `BiScore/core/inspect.lua`
- `BiScore/ui/*.lua`

## Change Discipline

- Make minimal, scoped edits.
- Do not mix UI concerns into core scoring logic.
- Do not add parser/downloader behavior to addon runtime code.
- Keep account-wide (`BiScoreDB`) vs character (`BiScoreCharDB`) semantics intact.
- Preserve slash command UX (`/biscore phase`, `/biscore profile`, `/biscore score`, `/biscore debug`) unless explicitly asked to change it.

## Quick Task Routing

- Feature/bug in score math -> `BiScore/core/scoring.lua`
- Phase defaults/controls -> `BiScore/core/phase.lua`
- Inspect timing/queue issues -> `BiScore/core/inspect.lua`
- Tooltip/character/inspect display issue -> `BiScore/ui/*.lua`
- BiS data quality/update -> `scripts/*` + `BiScore/data/*.lua`

