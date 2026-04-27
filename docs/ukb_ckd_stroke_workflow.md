# UKB CKD-Stroke Workflow

## Study intent

- Project: `长沙湘雅医院-UKB-CKD-Stroke`
- Design: UK Biobank prospective cohort
- Primary exposure: baseline CKD
- Primary outcome: incident stroke
- Secondary outcomes: incident ischaemic stroke, all-cause mortality

## Input

- UK Biobank main table:
  `/Users/apple/Desktop/所有数据/UKB数据/ukb669219.csv`
- Local data dictionary:
  `/Users/apple/Desktop/所有数据/UKB数据/Data_Dictionary_Showcase.csv`

## Implemented scripts

- Cohort builder:
  `/Users/apple/Documents/lancet-research-platform/analysis/python/49_ukb_ckd_stroke_build_cohort.py`
- Analysis:
  `/Users/apple/Documents/lancet-research-platform/analysis/python/50_ukb_ckd_stroke_analysis.py`

## Main fields

- Baseline date: `53-0.0`
- Loss to follow-up: `191-0.0`
- Sex: `31-0.0`
- Ethnicity: `21000-0.0`
- Age at assessment: `21003-0.0`
- Townsend deprivation: `189-0.0`
- BMI: `21001-0.0`
- Systolic blood pressure: `4080-0.0`, fallback `93-0.0`
- Smoking: `1239-0.0`, `1249-0.0`
- Alcohol frequency: `1558-0.0`
- Diabetes self-report: `2443-0.0`
- Age diabetes diagnosed: `2976-0.0`
- Insulin within one year: `2986-0.0`
- Serum creatinine: `30700-0.0`
- Cystatin C: `30720-0.0`
- Urine microalbumin: `30500-0.0`
- Urine creatinine: `30510-0.0`
- Total cholesterol: `30690-0.0`
- HDL cholesterol: `30760-0.0`
- Date of death: `40000-0.0`
- Cause of death ICD10: `40001-0.0`
- Date of stroke: `42006-0.0`
- Date of ischaemic stroke: `42008-0.0`
- Date of end-stage renal disease report: `42026-0.0`
- Date E10 first reported: `130706-0.0`
- Date E11 first reported: `130708-0.0`
- Date N18 first reported: `132032-0.0`
- Date N19 first reported: `132034-0.0`

## Core definitions

- eGFR: CKD-EPI 2021 creatinine equation
- UACR: `urine microalbumin (mg/L) * 1000 / urine creatinine (umol/L)`, unit `mg/mmol`
- Baseline CKD:
  - clinical CKD history before baseline (`N18`, `N19`, or ESRD date before baseline)
  - or `eGFR < 60 mL/min/1.73m2`
  - or `UACR >= 3 mg/mmol`
- Incident stroke:
  - earliest of `42006` and fatal stroke death date (`I60-I64`)
- Incident ischaemic stroke:
  - earliest of `42008` and fatal ischaemic stroke death date (`I63`)
- Censoring:
  - earliest of death, loss to follow-up, and admin censor date

## Commands

```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
cd /Users/apple/Documents/lancet-research-platform

python analysis/python/49_ukb_ckd_stroke_build_cohort.py \
  --input '/Users/apple/Desktop/所有数据/UKB数据/ukb669219.csv' \
  --out_csv data/gold/ukb_ckd_stroke_analysis.csv \
  --out_qc outputs/tables/ukb_ckd_stroke_build_qc.csv \
  --chunksize 10000 \
  --admin-censor-date 2023-12-31

python analysis/python/50_ukb_ckd_stroke_analysis.py \
  --input data/gold/ukb_ckd_stroke_analysis.csv \
  --outdir outputs/ukb_ckd_stroke
```

## Outputs

- Cohort table:
  `/Users/apple/Documents/lancet-research-platform/data/gold/ukb_ckd_stroke_analysis.csv`
- Build QC:
  `/Users/apple/Documents/lancet-research-platform/outputs/tables/ukb_ckd_stroke_build_qc.csv`
- Analysis tables and figures:
  `/Users/apple/Documents/lancet-research-platform/outputs/ukb_ckd_stroke`

## Current analysis package

- Table 1 by CKD status
- Multivariable Cox models for CKD and:
  - incident stroke
  - incident ischaemic stroke
  - all-cause mortality
- Category analyses for eGFR and UACR
- Joint kidney-marker models (`eGFR<60` and `UACR>=3`)
- Interaction terms and additive interaction metrics
- KM curves by baseline CKD status

## Recommended next upgrades

- Add spline models for continuous eGFR and log-UACR
- Add sex, diabetes, and age-stratified subgroup analyses
- Add competing-risk models for non-stroke death
- Add manuscript shell and journal-targeted results framing
