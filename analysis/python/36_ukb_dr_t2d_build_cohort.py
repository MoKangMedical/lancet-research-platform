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
    '5890-0.0': 'diabetes_eye_disease',
    '5901-0.0': 'age_eye_disease_dx',
    '30740-0.0': 'glucose',
    '30750-0.0': 'hba1c',
    '30690-0.0': 'cholesterol_total',
    '30760-0.0': 'cholesterol_hdl',
    '40000-0.0': 'death_date',
    '40001-0.0': 'death_cause_icd10',
    '42000-0.0': 'mi_date',
    '42006-0.0': 'stroke_date',
    '131354-0.0': 'hf_date',
    '130706-0.0': 't1d_icd_date',
    '130708-0.0': 't2d_icd_date',
    '131184-0.0': 'retinal_disorder_elsewhere_date',
}

REQUIRED_COLUMNS = list(FIELD_MAP)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Build UK Biobank T2D-retinopathy cohort')
    p.add_argument('--input', default=str(DEFAULT_INPUT))
    p.add_argument(
        '--out_csv',
        default=str(ROOT / 'data/gold/ukb_dr_t2d_analysis.csv'),
    )
    p.add_argument(
        '--out_qc',
        default=str(ROOT / 'outputs/tables/ukb_dr_t2d_build_qc.csv'),
    )
    p.add_argument('--chunksize', type=int, default=20000)
    p.add_argument('--admin-censor-date', default='2023-12-31')
    return p.parse_args()


def read_selected_columns(path: Path, chunksize: int) -> pd.DataFrame:
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
    return df[cols].min(axis=1)


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
        'diabetes_eye_disease',
        'age_eye_disease_dx',
        'glucose',
        'hba1c',
        'cholesterol_total',
        'cholesterol_hdl',
    ]
    date_cols = [
        'baseline_date',
        'lost_to_followup_date',
        'death_date',
        'mi_date',
        'stroke_date',
        'hf_date',
        't1d_icd_date',
        't2d_icd_date',
        'retinal_disorder_elsewhere_date',
    ]
    admin_censor = pd.Timestamp(args.admin_censor_date)
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if out_csv.exists():
        out_csv.unlink()

    qc_counts = {
        'n_total_rows': 0,
        'n_analytic': 0,
        'n_t2d': 0,
        'n_retinopathy': 0,
        'n_joint_0': 0,
        'n_joint_1': 0,
        'n_joint_2': 0,
        'n_joint_3': 0,
        'n_allcause_deaths': 0,
        'n_mace': 0,
        'n_hf': 0,
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

        t2d_by_self_report = df['diabetes_doctor'].eq(1)
        t2d_by_icd = df['t2d_icd_date'].notna()
        t2d_by_hba1c = df['hba1c'].ge(48)
        probable_t1d = (
            df['diabetes_doctor'].eq(1)
            & df['insulin_within_one_year'].eq(1)
            & df['age_diabetes_dx'].lt(30)
            & df['t2d_icd_date'].isna()
        )
        df['t2d'] = ((t2d_by_self_report | t2d_by_icd | t2d_by_hba1c) & ~probable_t1d).astype(int)

        retinopathy_by_self_report = df['diabetes_eye_disease'].fillna(0).gt(0)
        retinopathy_by_age = df['age_eye_disease_dx'].notna()
        retinopathy_by_icd = df['retinal_disorder_elsewhere_date'].notna()
        df['retinopathy'] = (
            retinopathy_by_self_report | retinopathy_by_age | retinopathy_by_icd
        ).astype(int)

        df['joint_group'] = df['t2d'] * 2 + df['retinopathy']
        df['joint_label'] = df['joint_group'].map({
            0: 'No T2D / No retinopathy',
            1: 'No T2D / Retinopathy',
            2: 'T2D / No retinopathy',
            3: 'T2D / Retinopathy',
        })

        censor_candidates = pd.concat(
            [
                df['death_date'],
                df['lost_to_followup_date'],
                pd.Series(admin_censor, index=df.index),
            ],
            axis=1,
        )
        df['censor_date'] = censor_candidates.min(axis=1)

        df['cvd_death'] = df['death_cause_icd10'].fillna('').astype(str).str.startswith('I').astype(int)
        df['mace_date'] = earliest_date(df, ['mi_date', 'stroke_date'])
        cvd_death_date = df['death_date'].where(df['cvd_death'].eq(1))
        df['mace_date'] = pd.concat([df['mace_date'], cvd_death_date], axis=1).min(axis=1)

        df['prev_mi'] = df['mi_date'].lt(df['baseline_date']).astype(int)
        df['prev_stroke'] = df['stroke_date'].lt(df['baseline_date']).astype(int)
        df['prev_hf'] = df['hf_date'].lt(df['baseline_date']).astype(int)
        df['prev_cvd'] = ((df['prev_mi'] == 1) | (df['prev_stroke'] == 1) | (df['prev_hf'] == 1)).astype(int)

        df['event_allcause'] = (
            df['death_date'].notna() & df['death_date'].le(df['censor_date'])
        ).astype(int)
        df['event_mace'] = (
            df['mace_date'].notna()
            & df['mace_date'].ge(df['baseline_date'])
            & df['mace_date'].le(df['censor_date'])
        ).astype(int)
        df['event_hf'] = (
            df['hf_date'].notna()
            & df['hf_date'].ge(df['baseline_date'])
            & df['hf_date'].le(df['censor_date'])
        ).astype(int)

        df['followup_allcause_years'] = (
            (df['death_date'].where(df['event_allcause'].eq(1), df['censor_date']) - df['baseline_date'])
            .dt.days
            .div(365.25)
        )
        df['followup_mace_years'] = (
            (df['mace_date'].where(df['event_mace'].eq(1), df['censor_date']) - df['baseline_date'])
            .dt.days
            .div(365.25)
        )
        df['followup_hf_years'] = (
            (df['hf_date'].where(df['event_hf'].eq(1), df['censor_date']) - df['baseline_date'])
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
            'glucose',
            'hba1c',
            'cholesterol_total',
            'cholesterol_hdl',
            'alcohol_freq',
            'smoking_status',
            'smoking_former',
            'smoking_current',
            't2d',
            'retinopathy',
            'joint_group',
            'joint_label',
            'prev_cvd',
            'cvd_death',
            'event_allcause',
            'event_mace',
            'event_hf',
            'followup_allcause_years',
            'followup_mace_years',
            'followup_hf_years',
            'death_date',
            'mace_date',
            'hf_date',
        ]
        ].copy()

        analytic = analytic[
            analytic['baseline_date'].notna()
            & analytic['age_baseline'].notna()
            & analytic['sex'].notna()
        ].copy()
        analytic = analytic[analytic['followup_allcause_years'].fillna(-1).ge(0)].copy()

        qc_counts['n_analytic'] += len(analytic)
        qc_counts['n_t2d'] += int(analytic['t2d'].sum())
        qc_counts['n_retinopathy'] += int(analytic['retinopathy'].sum())
        qc_counts['n_joint_0'] += int((analytic['joint_group'] == 0).sum())
        qc_counts['n_joint_1'] += int((analytic['joint_group'] == 1).sum())
        qc_counts['n_joint_2'] += int((analytic['joint_group'] == 2).sum())
        qc_counts['n_joint_3'] += int((analytic['joint_group'] == 3).sum())
        qc_counts['n_allcause_deaths'] += int(analytic['event_allcause'].sum())
        qc_counts['n_mace'] += int(analytic['event_mace'].sum())
        qc_counts['n_hf'] += int(analytic['event_hf'].sum())

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
