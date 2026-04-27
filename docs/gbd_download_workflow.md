# GBD Download Workflow

Use this workflow for official GBD 2023 files covering 1990-2023 that are published through GHDx record pages.

## Download mode matrix

Keep these modes in descending order of stability.

1. `GHDx record files with authenticated session`
This is the default for official appendix tables, information sheets, and bundled exposure archives attached to a GHDx record.

2. `GBD Results Tool browser export`
This is the default for custom cause-risk-location-age-sex-year CSV extracts.

3. `GBD Results Tool programmatic endpoints`
The public tool exposes stable bootstrap endpoints for settings, versions, metadata, hierarchies, and default data. The same frontend bundle also references `php/download.php` and `php/get_download_result.php?taskID=...`, which suggests an asynchronous export queue. Treat this as an undocumented integration path: usable for research automation, but not the first-choice production path.

4. `Browser automation`
Use Playwright only when a reproducible API-level path is unavailable or the task needs authenticated UI export behavior.

## What this workflow covers

- Cause-specific mortality 1990-2023
- YLD, DALY, HALE, and risk-attributable burden 1990-2023
- Risk exposure estimates 1990-2023

These are official GHDx record files, not ad hoc CSV exports from the `GBD Results Tool`.

## Why authentication matters

GHDx record pages list files publicly, but actual file downloads require a logged-in session. When unauthenticated, file links resolve to `download-access/login`.

The local downloader detects that state and stops with a clear error instead of pretending the download succeeded.

## Results Tool programmatic surface

As of March 7, 2026, these public endpoints are directly reachable without login and are useful for building reproducible download payloads:

- `https://vizhub.healthdata.org/gbd-results/php/app_settings.php`
- `https://vizhub.healthdata.org/gbd-results/php/version/`
- `https://vizhub.healthdata.org/gbd-results/php/toolUrls/`
- `https://vizhub.healthdata.org/gbd-results/php/metadata/?language=English`
- `https://vizhub.healthdata.org/gbd-results/php/hierarchy/`
- `https://vizhub.healthdata.org/gbd-results/php/default_data.php?start_year=1990&version=8352`

These let you fix:

- the active GBD round and version ids
- the tool audience
- the allowed dimensions and hierarchy ids
- the default table structure and column names

They are suitable for metadata bootstrapping, validation, and script preparation.

## Undocumented export queue mode

The current official Results Tool frontend bundle references:

- `https://vizhub.healthdata.org/gbd-results/php/download.php`
- `https://vizhub.healthdata.org/gbd-results/php/get_download_result.php?taskID=...`

It also contains logic for:

- `CAP_EXCEEDED`
- `TOO_MANY_REQUESTS`
- `DUPLICATE_REQUEST`
- `TIMEOUT`
- 7-day task availability on the download-result page

This is strong evidence that the official UI submits asynchronous export jobs. However, because the payload contract is undocumented and empty test posts return `401` with `Unable to parse authentication token`, do not treat this as the primary supported path. Keep it as an advanced fallback for reverse-engineered automation only.

## Quick start

Activate the environment and move into the repo:

```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
cd /Users/apple/Documents/lancet-research-platform
```

List the current 1990-2023 manifest from the cached record pages:

```bash
make gbd-download PRESET=gbd2023-core-1990-2023 LIST_ONLY=1 DEST=/Users/apple/Documents/lancet-research-platform/data/raw/gbd YEAR_SPAN=1990-2023 TIMEOUT=60
```

Download after you have an authenticated GHDx cookie:

```bash
export GHDX_COOKIE='cookie_name=cookie_value; another_cookie=another_value'
make gbd-download PRESET=gbd2023-core-1990-2023 DEST=/Users/apple/Documents/lancet-research-platform/data/raw/gbd YEAR_SPAN=1990-2023 TIMEOUT=60
```

Refresh the local HTML cache from the live record pages while authenticated:

```bash
make gbd-download PRESET=gbd2023-core-1990-2023 LIST_ONLY=1 SAVE_HTML=1 DEST=/Users/apple/Documents/lancet-research-platform/data/raw/gbd YEAR_SPAN=1990-2023 TIMEOUT=60
```

## Narrow the download

Only mortality appendix tables:

```bash
python /Users/apple/Documents/lancet-research-platform/analysis/python/38_gbd_download.py \
  --record mortality-2023 \
  --filename-pattern 'TABLES\\.zip' \
  --year-span 1990-2023 \
  --dest /Users/apple/Documents/lancet-research-platform/data/raw/gbd
```

Only high-BMI risk exposure files:

```bash
python /Users/apple/Documents/lancet-research-platform/analysis/python/38_gbd_download.py \
  --record risk-exposure-2023 \
  --filename-pattern 'HIGH_BMI' \
  --year-span 1990-2023 \
  --dest /Users/apple/Documents/lancet-research-platform/data/raw/gbd
```

Write a manifest snapshot for reproducibility:

```bash
python /Users/apple/Documents/lancet-research-platform/analysis/python/38_gbd_download.py \
  --preset gbd2023-core-1990-2023 \
  --list-only \
  --manifest-out /Users/apple/Documents/lancet-research-platform/data/raw/gbd/gbd2023_manifest.json
```

## Output layout

Files are written under:

- `data/raw/gbd/mortality-2023/`
- `data/raw/gbd/dirf-2023/`
- `data/raw/gbd/risk-exposure-2023/`

After download, move straight into the reproducible post-download workflow:

```bash
make gbd-unpack
make gbd-starter
```

That will expand the archives into `data/bronze/gbd/gbd2023/`, build starter datasets in `data/silver/gbd/`, and generate `notebooks/gbd2023_starter_analysis.ipynb`.

## Limits

- This workflow does not automate custom exports from the `GBD Results Tool`.
- The public Results Tool metadata endpoints are stable enough to use for discovery, but the export queue endpoints are undocumented and may change without notice.
- For custom location-cause-measure extracts, use the official Results Tool and then run the `gbd-research` skill validation workflow on the exported CSV.
- If the authenticated record page still returns login links, refresh the browser session and export a new cookie header or cookie file.
