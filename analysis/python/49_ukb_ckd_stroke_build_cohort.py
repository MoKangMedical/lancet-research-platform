#!/usr/bin/env python3
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('/Users/apple/Documents/lancet-research-platform')
DEFAULT_INPUT = Path('/Users/apple/Desktop/所有数据/UKB数据/ukb669219.csv')


FIELD_MAP = {
    'eid': 'eid',
    '53-0.0': 'baseline_date',
    '191-0.0': 'lost_to_followup_date',
    '31-0.0': 'sex',
    '21000-0.0': 'ethnicity',
    '21003-0.0': 'age_baseline',
    '189-0.0': 'townsend',
    '21001-0.0': 'bmi',
    '93-0.0': 'sbp_manual',
    '4080-0.0': 'sbp_auto',
    '1239-0.0': 'smoking_current_raw',
    '1249-0.0': 'smoking_past_raw',
    '1558-0.0': 'alcohol_freq',
    '2443-0.0': 'diabetes_doctor',
    '2976-0.0': 'age_diabetes_dx',
    '2986-0.0': 'insulin_within_one_year',
    '30500-0.0': 'urine_microalbumin_mg_l',
    '30510-0.0': 'urine_creatinine_umol_l',
    '30690-0.0': 'cholesterol_total',
    '30700-0.0': 'serum_creatinine_umol_l',
    '30720-0.0': 'cystatin_c_mg_l',
    '30760-0.0': 'cholesterol_hdl',
    '40000-0.0': 'death_date',
    '40001-0.0': 'death_cause_icd10',
    '42006-0.0': 'stroke_date',
    '42008-0.0': 'ischemic_stroke_date',
    '42026-0.0': 'esrd_date',
    '130706-0.0': 't1d_icd_date',
    '130708-0.0': 't2d_icd_date',
    '132032-0.0': 'ckd_n18_date',
    '132034-0.0': 'renal_failure_n19_date',
}

REQUIRED_COLUMNS = list(FIELD_MAP)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Build UK Biobank CKD-stroke cohort')
    p.add_argument('--input', default=str(DEFAULT_INPUT))
    p.add_argument(
        '--out_csv',
        default=str(ROOT / 'data/gold/ukb_ckd_stroke_analysis.csv'),
    )
    p.add_argument(
        '--out_qc',
        default=str(ROOT / 'outputs/tables/ukb_ckd_stroke_build_qc.csv'),
    )
    p.add_argument('--chunksize', type=int, default=20000)
    p.add_argument('--admin-censor-date', default='2023-12-31')
    return p.parse_args()


def read_selected_columns(path: Path, chunksize: int):
    return pd.read_csv(
        path,
        usecols=lambda c: c in REQUIRED_COLUMNS,
        chunksize=chunksize,
        low_memory=False,
    )


def clean_numeric(df: pd.DataFrame, cols: list[str]) -> None:
    for col in cols:
        if col not in df.columns:
            continue
        df[col] = pd.to_numeric(df[col], errors='coerce')
        df.loc[df[col] < 0, col] = np.nan


def clean_dates(df: pd.DataFrame, cols: list[str]) -> None:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')


def build_smoking_status(df: pd.DataFrame) -> pd.Series:
    current = df['smoking_current_raw'].fillna(0).eq(1)
    past = df['smoking_past_raw'].fillna(0).eq(1)
    status = pd.Series(np.nan, index=df.index, dtype='float')
    status.loc[~current & ~past] = 0
    status.loc[~current & past] = 1
    status.loc[current] = 2
    return status


def earliest_date(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    present = [col for col in cols if col in df.columns]
    if not present:
        return pd.Series(pd.NaT, index=df.index, dtype='datetime64[ns]')
    return df[present].min(axis=1)


def build_diabetes_flag(df: pd.DataFrame) -> pd.Series:
    t2d_by_self_report = df['diabetes_doctor'].eq(1)
    t2d_by_icd = df['t2d_icd_date'].notna()
    probable_t1d = (
        df['diabetes_doctor'].eq(1)
        & df['insulin_within_one_year'].eq(1)
        & df['age_diabetes_dx'].lt(30)
        & df['t2d_icd_date'].isna()
    )
    return ((t2d_by_self_report | t2d_by_icd) & ~probable_t1d).astype(int)


def estimate_egfr_2021(df: pd.DataFrame) -> pd.Series:
    scr_mg_dl = df['serum_creatinine_umol_l'].div(88.4)
    female = df['sex'].eq(0)
    kappa = np.where(female, 0.7, 0.9)
    alpha = np.where(female, -0.241, -0.302)
    scr_ratio = scr_mg_dl / kappa
    egfr = (
        142
        * np.power(np.minimum(scr_ratio, 1), alpha)
        * np.power(np.maximum(scr_ratio, 1), -1.2)
        * np.power(0.9938, df['age_baseline'])
        * np.where(female, 1.012, 1.0)
    )
    out = pd.Series(egfr, index=df.index, dtype='float')
    valid = scr_mg_dl.notna() & df['age_baseline'].notna() & df['sex'].isin([0, 1])
    return out.where(valid)


def estimate_uacr(df: pd.DataFrame) -> pd.Series:
    valid = (
        df['urine_microalbumin_mg_l'].notna()
        & df['urine_creatinine_umol_l'].notna()
        & df['urine_creatinine_umol_l'].gt(0)
    )
    acr = df['urine_microalbumin_mg_l'] * 1000.0 / df['urine_creatinine_umol_l']
    return acr.where(valid)


def categorize_egfr(egfr: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=egfr.index, dtype='object')
    out.loc[egfr.ge(90)] = 'G1 >=90'
    out.loc[egfr.ge(60) & egfr.lt(90)] = 'G2 60-89'
    out.loc[egfr.ge(45) & egfr.lt(60)] = 'G3a 45-59'
    out.loc[egfr.ge(30) & egfr.lt(45)] = 'G3b 30-44'
    out.loc[egfr.lt(30)] = 'G4-5 <30'
    return out


def categorize_uacr(acr: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=acr.index, dtype='object')
    out.loc[acr.lt(3)] = 'A1 <3'
    out.loc[acr.ge(3) & acr.lt(30)] = 'A2 3-29.9'
    out.loc[acr.ge(30)] = 'A3 >=30'
    return out


def stroke_death_date(df: pd.DataFrame) -> pd.Series:
    codes = df['death_cause_icd10'].fillna('').astype(str).str[:3]
    return df['death_date'].where(codes.isin({'I60', 'I61', 'I62', 'I63', 'I64'}))


def fatal_ischemic_stroke_date(df: pd.DataFrame) -> pd.Series:
    codes = df['death_cause_icd10'].fillna('').astype(str).str[:3]
    return df['death_date'].where(codes.eq('I63'))


def main() -> None:
    warnings.filterwarnings('ignore', category=FutureWarning)
    args = parse_args()
    numeric_cols = [
        'sex',
        'ethnicity',
        'age_baseline',
        'townsend',
        'bmi',
        'sbp_manual',
        'sbp_auto',
        'smoking_current_raw',
        'smoking_past_raw',
        'alcohol_freq',
        'diabetes_doctor',
        'age_diabetes_dx',
        'insulin_within_one_year',
        'urine_microalbumin_mg_l',
        'urine_creatinine_umol_l',
        'cholesterol_total',
        'serum_creatinine_umol_l',
        'cystatin_c_mg_l',
        'cholesterol_hdl',
    ]
    date_cols = [
        'baseline_date',
        'lost_to_followup_date',
        'death_date',
        'stroke_date',
        'ischemic_stroke_date',
        'esrd_date',
        't1d_icd_date',
        't2d_icd_date',
        'ckd_n18_date',
        'renal_failure_n19_date',
    ]
    admin_censor = pd.Timestamp(args.admin_censor_date)
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if out_csv.exists():
        out_csv.unlink()

    qc_counts = {
        'n_total_rows': 0,
        'n_analytic': 0,
        'n_ckd': 0,
        'n_clinical_ckd_history': 0,
        'n_lab_ckd': 0,
        'n_joint_0': 0,
        'n_joint_1': 0,
        'n_joint_2': 0,
        'n_joint_3': 0,
        'n_prev_stroke': 0,
        'n_incident_stroke': 0,
        'n_incident_ischemic_stroke': 0,
        'n_allcause_deaths': 0,
    }
    wrote_header = False

    for raw_chunk in read_selected_columns(Path(args.input), args.chunksize):
        df = raw_chunk.rename(columns=FIELD_MAP)
        qc_counts['n_total_rows'] += len(df)
        clean_numeric(df, numeric_cols)
        clean_dates(df, date_cols)

        df['sbp'] = df['sbp_auto'].combine_first(df['sbp_manual'])
        df['white_ethnicity'] = df['ethnicity'].eq(1001).astype(int)
        df['smoking_status'] = build_smoking_status(df)
        df['smoking_former'] = df['smoking_status'].eq(1).astype(int)
        df['smoking_current'] = df['smoking_status'].eq(2).astype(int)
        df['diabetes'] = build_diabetes_flag(df)

        df['egfr_creatinine_2021'] = estimate_egfr_2021(df)
        df['uacr_mg_mmol'] = estimate_uacr(df)
        df['egfr_category'] = categorize_egfr(df['egfr_creatinine_2021'])
        df['uacr_category'] = categorize_uacr(df['uacr_mg_mmol'])
        df['egfr_lt60'] = df['egfr_creatinine_2021'].lt(60)
        df['albuminuria_ge3'] = df['uacr_mg_mmol'].ge(3)

        df['clinical_ckd_date'] = earliest_date(
            df,
            ['ckd_n18_date', 'renal_failure_n19_date', 'esrd_date'],
        )
        df['clinical_ckd_history'] = (
            df['clinical_ckd_date'].notna()
            & df['baseline_date'].notna()
            & df['clinical_ckd_date'].le(df['baseline_date'])
        )
        df['lab_ckd'] = df['egfr_lt60'] | df['albuminuria_ge3']
        has_ckd_info = (
            df['clinical_ckd_history']
            | df['egfr_creatinine_2021'].notna()
            | df['uacr_mg_mmol'].notna()
        )
        df['ckd'] = np.nan
        df.loc[df['clinical_ckd_history'] | df['lab_ckd'], 'ckd'] = 1
        df.loc[has_ckd_info & ~(df['clinical_ckd_history'] | df['lab_ckd']), 'ckd'] = 0
        df['ckd_label'] = df['ckd'].map({0.0: 'No CKD', 1.0: 'CKD'})

        both_kidney_markers = df['egfr_creatinine_2021'].notna() & df['uacr_mg_mmol'].notna()
        df['kidney_marker_joint_group'] = np.nan
        df.loc[both_kidney_markers, 'kidney_marker_joint_group'] = (
            df.loc[both_kidney_markers, 'egfr_lt60'].astype(int) * 2
            + df.loc[both_kidney_markers, 'albuminuria_ge3'].astype(int)
        )
        df['kidney_marker_joint_label'] = df['kidney_marker_joint_group'].map({
            0.0: 'eGFR>=60 / ACR<3',
            1.0: 'eGFR>=60 / ACR>=3',
            2.0: 'eGFR<60 / ACR<3',
            3.0: 'eGFR<60 / ACR>=3',
        })

        df['stroke_death_date'] = stroke_death_date(df)
        df['fatal_ischemic_stroke_date'] = fatal_ischemic_stroke_date(df)
        df['any_stroke_date'] = earliest_date(df, ['stroke_date', 'stroke_death_date'])
        df['any_ischemic_stroke_date'] = earliest_date(
            df,
            ['ischemic_stroke_date', 'fatal_ischemic_stroke_date'],
        )

        df['prev_stroke'] = (
            df['any_stroke_date'].notna()
            & df['baseline_date'].notna()
            & df['any_stroke_date'].lt(df['baseline_date'])
        ).astype(int)

        censor_candidates = pd.concat(
            [
                df['death_date'],
                df['lost_to_followup_date'],
                pd.Series(admin_censor, index=df.index),
            ],
            axis=1,
        )
        df['censor_date'] = censor_candidates.min(axis=1)

        df['event_allcause'] = (
            df['death_date'].notna()
            & df['baseline_date'].notna()
            & df['death_date'].ge(df['baseline_date'])
            & df['death_date'].le(df['censor_date'])
        ).astype(int)
        df['event_stroke'] = (
            df['any_stroke_date'].notna()
            & df['baseline_date'].notna()
            & df['any_stroke_date'].ge(df['baseline_date'])
            & df['any_stroke_date'].le(df['censor_date'])
        ).astype(int)
        df['event_ischemic_stroke'] = (
            df['any_ischemic_stroke_date'].notna()
            & df['baseline_date'].notna()
            & df['any_ischemic_stroke_date'].ge(df['baseline_date'])
            & df['any_ischemic_stroke_date'].le(df['censor_date'])
        ).astype(int)

        df['followup_allcause_years'] = (
            (
                df['death_date'].where(df['event_allcause'].eq(1), df['censor_date'])
                - df['baseline_date']
            )
            .dt.days
            .div(365.25)
        )
        df['followup_stroke_years'] = (
            (
                df['any_stroke_date'].where(df['event_stroke'].eq(1), df['censor_date'])
                - df['baseline_date']
            )
            .dt.days
            .div(365.25)
        )
        df['followup_ischemic_stroke_years'] = (
            (
                df['any_ischemic_stroke_date'].where(df['event_ischemic_stroke'].eq(1), df['censor_date'])
                - df['baseline_date']
            )
            .dt.days
            .div(365.25)
        )

        analytic = df[
            [
                'eid',
                'baseline_date',
                'censor_date',
                'sex',
                'white_ethnicity',
                'age_baseline',
                'townsend',
                'bmi',
                'sbp',
                'smoking_status',
                'smoking_former',
                'smoking_current',
                'alcohol_freq',
                'diabetes',
                'cholesterol_total',
                'cholesterol_hdl',
                'serum_creatinine_umol_l',
                'cystatin_c_mg_l',
                'urine_microalbumin_mg_l',
                'urine_creatinine_umol_l',
                'egfr_creatinine_2021',
                'uacr_mg_mmol',
                'egfr_category',
                'uacr_category',
                'egfr_lt60',
                'albuminuria_ge3',
                'clinical_ckd_date',
                'clinical_ckd_history',
                'lab_ckd',
                'ckd',
                'ckd_label',
                'kidney_marker_joint_group',
                'kidney_marker_joint_label',
                'prev_stroke',
                'event_stroke',
                'event_ischemic_stroke',
                'event_allcause',
                'followup_stroke_years',
                'followup_ischemic_stroke_years',
                'followup_allcause_years',
                'stroke_date',
                'ischemic_stroke_date',
                'stroke_death_date',
                'fatal_ischemic_stroke_date',
                'any_stroke_date',
                'any_ischemic_stroke_date',
                'death_date',
            ]
        ].copy()

        analytic = analytic[
            analytic['baseline_date'].notna()
            & analytic['age_baseline'].notna()
            & analytic['sex'].isin([0, 1])
        ].copy()
        analytic = analytic[analytic['followup_allcause_years'].fillna(-1).ge(0)].copy()

        qc_counts['n_analytic'] += len(analytic)
        qc_counts['n_ckd'] += int(analytic['ckd'].fillna(0).sum())
        qc_counts['n_clinical_ckd_history'] += int(analytic['clinical_ckd_history'].sum())
        qc_counts['n_lab_ckd'] += int(analytic['lab_ckd'].fillna(False).sum())
        qc_counts['n_joint_0'] += int((analytic['kidney_marker_joint_group'] == 0).sum())
        qc_counts['n_joint_1'] += int((analytic['kidney_marker_joint_group'] == 1).sum())
        qc_counts['n_joint_2'] += int((analytic['kidney_marker_joint_group'] == 2).sum())
        qc_counts['n_joint_3'] += int((analytic['kidney_marker_joint_group'] == 3).sum())
        qc_counts['n_prev_stroke'] += int(analytic['prev_stroke'].sum())
        qc_counts['n_incident_stroke'] += int(analytic['event_stroke'].sum())
        qc_counts['n_incident_ischemic_stroke'] += int(analytic['event_ischemic_stroke'].sum())
        qc_counts['n_allcause_deaths'] += int(analytic['event_allcause'].sum())

        analytic.to_csv(out_csv, index=False, mode='a', header=not wrote_header)
        wrote_header = True

    qc = pd.DataFrame(list(qc_counts.items()), columns=['metric', 'value'])
    out_qc = Path(args.out_qc)
    out_qc.parent.mkdir(parents=True, exist_ok=True)
    qc.to_csv(out_qc, index=False)

    print(f'Built cohort: {out_csv}')
    print(f'QC table: {out_qc}')


if __name__ == '__main__':
    main()
