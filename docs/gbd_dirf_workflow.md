# GBD DIRF Workflow

Use this workflow to turn the downloaded GBD 2023 DIRF appendix tables into a reusable tidy dataset and submission-oriented outputs.

## What this covers

- incidence
- prevalence
- DALY
- YLD
- YLL

The parser currently targets the core global supplementary appendix tables:

- prevalence age-standardized rates
- incidence age-standardized rates
- DALY counts and age-standardized rates
- YLD counts and age-standardized rates
- YLL counts and age-standardized rates

## Commands

```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
cd /Users/apple/Documents/lancet-research-platform

make gbd-dirf-parse
```

This writes:

- `data/silver/gbd/gbd2023_dirf_global_core_tidy.csv`
- `outputs/tables/gbd2023_dirf_global_core_qc.json`

## Output templates

Create a summary table plus trend figure from the parsed global DIRF dataset:

```bash
make gbd-template \
  INPUT=/Users/apple/Documents/lancet-research-platform/data/silver/gbd/gbd2023_dirf_global_core_tidy.csv \
  MEASURE=DALY \
  METRIC=age_standardized_rate \
  SEX=Both \
  YEAR=2023
```

Create a map from any location-level tidy GBD dataset:

```bash
make gbd-template \
  INPUT=/path/to/location_level_tidy.csv \
  MEASURE=prevalence \
  SEX=Both \
  YEAR=2023 \
  MAP_CAUSE='All causes'
```

## Notes

- The core DIRF appendix tables parsed here are `Global`, so trend and summary outputs are directly supported but maps are skipped unless the input dataset is location-level.
- For publication-grade disease maps, use a `GBD Results` export or another location-level tidy dataset with stable geographic identifiers.
- The template script writes a manifest JSON so each figure and table can be reproduced.
