# WoW TBC BiS Downloaded Guide Files

This repository stores downloaded Wowhead TBC guide HTML in:

- `downloads/wowhead_tbc_bis/`

## How To Locate A Spec Guide

Use the **pre-raid HTML filename** as the canonical entry point for each spec.
Files can appear in multiple folders because pages are cross-linked and saved more than once.

### Spec -> Pre-Raid File Mapping

| Spec | Canonical pre-raid filename |
|---|---|
| `druid_balance` | `tbc__guide__classes__druid__balance__dps-bis-gear-pve-pre-raid.html` |
| `druid_feral_dps` | `tbc__guide__classes__druid__feral__dps-bis-gear-pve-pre-raid.html` |
| `druid_feral_tank` | `tbc__guide__classes__druid__feral__tank-bis-gear-pve-pre-raid.html` |
| `druid_restoration` | `tbc__guide__classes__druid__healer-bis-gear-pve-pre-raid.html` |
| `hunter_beast_mastery` | `tbc__guide__classes__hunter__dps-bis-gear-pve-pre-raid.html` |
| `hunter_marksmanship` | `tbc__guide__classes__hunter__marksmanship__dps-bis-gear-pve-pre-raid.html` |
| `hunter_survival` | `tbc__guide__classes__hunter__survival__dps-bis-gear-pve-pre-raid.html` |
| `mage_arcane` | `tbc__guide__classes__mage__arcane__dps-bis-gear-pve-pre-raid.html` |
| `mage_fire` | `tbc__guide__classes__mage__dps-bis-gear-pve-pre-raid.html` |
| `mage_frost` | `tbc__guide__classes__mage__frost__dps-bis-gear-pve-pre-raid.html` |
| `paladin_holy` | `tbc__guide__classes__paladin__holy__healer-bis-gear-pve-pre-raid.html` |
| `paladin_protection` | `tbc__guide__classes__paladin__tank-bis-gear-pve-pre-raid.html` |
| `paladin_retribution` | `tbc__guide__classes__paladin__retribution__dps-bis-gear-pve-pre-raid.html` |
| `priest_discipline` | `tbc__guide__classes__priest__healer-bis-gear-pve-pre-raid.html` (shared) |
| `priest_holy` | `tbc__guide__classes__priest__healer-bis-gear-pve-pre-raid.html` (shared) |
| `priest_shadow` | `tbc__guide__classes__priest__shadow__dps-bis-gear-pve-pre-raid.html` |
| `rogue_assassination` | `tbc__guide__classes__rogue__dps-bis-gear-pve-pre-raid.html` (shared) |
| `rogue_combat` | `tbc__guide__classes__rogue__dps-bis-gear-pve-pre-raid.html` (shared) |
| `rogue_subtlety` | `tbc__guide__classes__rogue__dps-bis-gear-pve-pre-raid.html` (shared) |
| `shaman_elemental` | `tbc__guide__classes__shaman__elemental__dps-bis-gear-pve-pre-raid.html` |
| `shaman_enhancement` | `tbc__guide__classes__shaman__enhancement__dps-bis-gear-pve-pre-raid.html` |
| `shaman_restoration` | `tbc__guide__classes__shaman__healer-bis-gear-pve-pre-raid.html` |
| `warlock_affliction` | `tbc__guide__classes__warlock__affliction__dps-bis-gear-pve-pre-raid.html` |
| `warlock_demonology` | `tbc__guide__classes__warlock__demonology__dps-bis-gear-pve-pre-raid.html` |
| `warlock_destruction` | `tbc__guide__classes__warlock__dps-bis-gear-pve-pre-raid.html` |
| `warrior_arms` | `tbc__guide__classes__warrior__dps-bis-gear-pve-pre-raid.html` (shared) |
| `warrior_fury` | `tbc__guide__classes__warrior__dps-bis-gear-pve-pre-raid.html` (shared) |
| `warrior_protection` | `tbc__guide__classes__warrior__protection__tank-bis-gear-pve-pre-raid.html` |

## Shared-Guide Specs

These specs intentionally resolve to the same guide page:

- `priest_discipline` + `priest_holy` -> priest healer guide
- `rogue_assassination` + `rogue_combat` + `rogue_subtlety` -> rogue DPS guide
- `warrior_arms` + `warrior_fury` -> warrior DPS guide

## Interpretation Rules For Warrior And Rogue

### Warrior (`warrior_arms`, `warrior_fury`)

- Treat `tbc__guide__classes__warrior__dps-bis-gear-pve-pre-raid.html` as the shared baseline for both Arms and Fury.
- For later phases, prefer spec-specific files when present:
- `tbc__guide__classes__warrior__arms__dps-bis-gear-pve-phase-2.html`
- `tbc__guide__classes__warrior__fury__dps-bis-gear-pve-phase-2.html`
- `tbc__guide__arms-warrior-dps-...phase-3/4/5...html`
- `tbc__guide__fury-warrior-dps-...phase-3/4/5...html`
- Practical rule: for `warrior_arms`, prioritize `arms` pages; for `warrior_fury`, prioritize `fury` pages; if a phase-specific page is missing, fall back to shared warrior DPS.

### Rogue (`rogue_assassination`, `rogue_combat`, `rogue_subtlety`)

- Treat `tbc__guide__classes__rogue__dps-bis-gear-pve-pre-raid.html` and phase pages under `rogue-dps` as shared source pages for all three specs.
- Rogue specialization differences are often represented as **notes/recommendations inside the same guide**, not separate per-spec guide files.
- Example: Assassination dagger preference is usually embedded in the shared rogue DPS page text/tables, not split into a distinct `rogue_assassination` HTML guide.
- Practical rule: do not require separate HTML filenames per rogue spec; parse the shared guide content for spec-specific notes.

## How To Search Quickly

Find all copies of a spec's canonical pre-raid file:

```bash
find downloads/wowhead_tbc_bis -name 'tbc__guide__classes__priest__healer-bis-gear-pve-pre-raid.html'
```

Count all downloaded HTML:

```bash
find downloads/wowhead_tbc_bis -type f -name '*.html' | wc -l
```

## Parser Logic (Pseudocode)

```text
INPUT: spec_key (for example "warrior_arms"), phase ("pre_raid"|"phase_1"...|"phase_5"), root_dir

1) Resolve canonical class/spec behavior:
   - If spec_key in {priest_discipline, priest_holy}:
       base = "priest healer shared"
   - If spec_key in {rogue_assassination, rogue_combat, rogue_subtlety}:
       base = "rogue dps shared"
   - If spec_key in {warrior_arms, warrior_fury}:
       base = "warrior dps shared + optional spec-split phases"
   - Else:
       base = "single-spec filename from mapping table"

2) Build candidate filenames in priority order:
   - phase == pre_raid:
       use canonical pre-raid filename from mapping table (shared where applicable)
   - phase == phase_1:
       prefer "*karazhan*"
   - phase in {phase_2..phase_5}:
       for warrior_arms: prefer "*arms*phase-N*" before shared "*warrior*dps*phase-N*"
       for warrior_fury: prefer "*fury*phase-N*" before shared "*warrior*dps*phase-N*"
       for rogue_*: use shared "*rogue*dps*phase-N*"
       otherwise: use spec-specific "*<class>/<spec>*phase-N*" or nearest equivalent

3) Locate files on disk:
   - search recursively under downloads/wowhead_tbc_bis
   - match by basename pattern (folder is not authoritative)
   - if multiple matches exist, pick one deterministic winner (for example lexicographically first path)

4) Enchants/gems + references:
   - load "*enchants-gems*" page for the resolved base guide
   - include linked item/spell/skill pages as supporting context

5) Rogue specialization note handling:
   - do NOT expect separate files for assassination/combat/subtlety
   - parse shared rogue page sections/notes for spec-specific guidance
   - example: dagger recommendations map to assassination logic

6) Fallback behavior:
   - if phase-specific file missing, fall back to pre-raid/shared guide
   - emit warning with spec_key + phase + attempted patterns
```

## How To Interpret Files

- `tbc__guide__classes__...pre-raid.html`: pre-raid BiS page (best entry point per spec)
- `...phase-2/3/4/5...html` or `...karazhan...html`: phase-specific BiS pages
- `...enchants-gems...html`: gems/enchants overview for that spec or role
- `tbc__item=...html`, `tbc__spell=...html`, `tbc__skill=...html`: referenced supporting pages pulled from the guides
- For Warrior DPS, phase files may be split by spec (`arms`/`fury`) even when pre-raid is shared.
- For Rogue DPS, spec distinctions are commonly content-level notes inside shared rogue pages.

## Important Notes

- Folder names are downloader buckets, not guaranteed one-folder-per-spec.
- The same guide can exist in multiple folders due to cross-link discovery.
- Shared specs are not missing data; they intentionally map to one role guide.
