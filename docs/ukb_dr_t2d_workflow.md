# UKB DR-T2D Workflow

## Input

- UK Biobank main table:
  `/Users/apple/Desktop/所有数据/UKB数据/ukb669219.csv`
- Local data dictionary:
  `/Users/apple/Desktop/所有数据/UKB数据/Data_Dictionary_Showcase.csv`

## Implemented scripts

- Cohort builder:
  `/Users/apple/Documents/lancet-research-platform/analysis/python/36_ukb_dr_t2d_build_cohort.py`
- Interaction analysis:
  `/Users/apple/Documents/lancet-research-platform/analysis/python/37_ukb_dr_t2d_interaction_analysis.py`

## Main fields

- Baseline date: `53-0.0`
- Sex: `31-0.0`
- Ethnicity: `21000-0.0`
- Age at assessment: `21003-0.0`
- Townsend deprivation: `189-0.0`
- BMI: `21001-0.0`
- Systolic blood pressure: `4080-0.0`, fallback `93-0.0`
- Glucose: `30740-0.0`
- HbA1c: `30750-0.0`
- Total cholesterol: `30690-0.0`
- HDL cholesterol: `30760-0.0`
- Smoking: `1239-0.0`, `1249-0.0`
- Alcohol frequency: `1558-0.0`
- Diabetes self-report: `2443-0.0`
- Age diabetes diagnosed: `2976-0.0`
- Insulin within one year: `2986-0.0`
- Diabetes-related eye disease: `5890-0.0`, `5901-0.0`
- T2D ICD date: `130708-0.0`
- Retinal disorder in diseases classified elsewhere: `131184-0.0`
- Date of death: `40000-0.0`
- Cause of death ICD10: `40001-0.0`
- Date of myocardial infarction: `42000-0.0`
- Date of stroke: `42006-0.0`
- Date of heart failure: `131354-0.0`

## Commands

```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
cd /Users/apple/Documents/lancet-research-platform

python analysis/python/36_ukb_dr_t2d_build_cohort.py \
  --input '/Users/apple/Desktop/所有数据/UKB数据/ukb669219.csv' \
  --out_csv data/gold/ukb_dr_t2d_analysis.csv \
  --out_qc outputs/tables/ukb_dr_t2d_build_qc.csv \
  --chunksize 10000 \
  --admin-censor-date 2023-12-31

python analysis/python/37_ukb_dr_t2d_interaction_analysis.py \
  --input data/gold/ukb_dr_t2d_analysis.csv \
  --outdir outputs/ukb_dr_t2d
```

## Outputs

- Cohort table:
  `/Users/apple/Documents/lancet-research-platform/data/gold/ukb_dr_t2d_analysis.csv`
- Build QC:
  `/Users/apple/Documents/lancet-research-platform/outputs/tables/ukb_dr_t2d_build_qc.csv`
- Analysis tables and figures:
  `/Users/apple/Documents/lancet-research-platform/outputs/ukb_dr_t2d`

## Current analysis note

The analysis script applies a protective T2D definition for modelling:

- existing `t2d` flag from the cohort table
- or `HbA1c >= 48 mmol/mol`
- or `glucose >= 11.1 mmol/L`

This was added because a small number of clear hyperglycaemic participants remained outside the initial T2D flag in the raw extract.
