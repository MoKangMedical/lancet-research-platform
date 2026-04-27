# GBD Starter Workflow

Use this workflow after the official 1990-2023 GBD 2023 files have already been downloaded into `data/raw/gbd/`.

## What it does

1. Extract every official zip archive into the bronze layer.
2. Build reusable starter datasets in the silver layer.
3. Generate a starter notebook for immediate inspection and figure drafting.

## Quick start

Activate the environment and move into the repo:

```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
cd /Users/apple/Documents/lancet-research-platform
```

Extract all downloaded GBD 2023 archives into `data/bronze/gbd/gbd2023`:

```bash
make gbd-unpack
```

Build starter datasets and the notebook:

```bash
make gbd-starter
```

## Outputs

Bronze extraction root:

- `data/bronze/gbd/gbd2023/`

Starter datasets:

- `data/silver/gbd/gbd2023_mortality_s7_both_sex_long.csv`
- `data/silver/gbd/gbd2023_high_bmi_global_adult_bmi_long.csv`
- `data/silver/gbd/gbd2023_high_bmi_prevalence_locations_long.csv`

Starter notebook:

- `notebooks/gbd2023_starter_analysis.ipynb`

Catalog and QC:

- `outputs/tables/gbd2023_extracted_catalog.csv`
- `outputs/tables/gbd2023_extracted_summary.json`
- `outputs/tables/gbd2023_starter_qc.json`

## Notes

- The mortality starter dataset tidies official Appendix Table S7 into a long format with parsed point estimates and uncertainty intervals.
- Because Appendix Table S7 does not carry stable `location_id` fields, a few location names are ambiguous across hierarchy levels. Treat the mortality starter as an exploratory scaffold, not the final publication dataset for country or subnational inference.
- The adult-BMI starter dataset keeps the official `HIGH_BMI_IN_ADULTS` series at the `Global` level.
- The prevalence starter dataset keeps official obesity and overweight prevalence series for all available locations, filtered to `Both` sex for a compact but still reusable starter table.
- For final journal analyses that need exact geographic identifiers, export the target dataset from the official `GBD Results` tool and keep `location_id` in the analytic table.
- The notebook is meant to be a stable starting point, not the final journal analysis plan. For disease-specific work, build a dedicated extraction after you pick the outcome, risk, location scope, and stratification plan.
