# biscore-addon

Focused Python tooling for downloading Wowhead TBC guides and extracting structured BiS/gems/enchants data.

This repository intentionally excludes addon runtime, scoring pipeline, schema/calibration, and packaging flows.

## Requirements

- Python 3.9+

## Setup

```bash
python3 -m pip install -r requirements.txt
```

## Scripts

Run scripts as modules from repo root:

```bash
python3 -m scripts.download_missing_guides --help
python3 -m scripts.download_missing_gems_enchants --help
python3 -m scripts.extract_wowhead_items --help
python3 -m scripts.batch_extract_and_report --help
python3 -m scripts.report_batch_items --help
```

## Typical Flow

1. Download missing BiS guides based on current coverage JSON.

```bash
python3 -m scripts.download_missing_guides \
  --coverage-json scripts/batch_extracted_items.json \
  --dest-dir scripts
```

2. Download missing gems/enchants guides.

```bash
python3 -m scripts.download_missing_gems_enchants \
  --coverage-json scripts/batch_extracted_items.json \
  --dest-dir scripts
```

3. Batch extract all local HTML guides and write JSON/report outputs.

```bash
python3 -m scripts.batch_extract_and_report \
  --input-dir scripts \
  --output-json scripts/batch_extracted_items.json \
  --output-report scripts/coverage_report.md
```

4. Review extracted summary.

```bash
python3 -m scripts.report_batch_items scripts/batch_extracted_items.json
```

## Outputs

- `scripts/batch_extracted_items.json`
- `scripts/coverage_report.md`
- Optional local HTML guide files in `scripts/` (not committed)

## Intentionally Out Of Scope

- WoW addon runtime/UI code
- Data scoring pipeline and release packaging
- Calibration docs, schema validation system, and vendor sync logic
