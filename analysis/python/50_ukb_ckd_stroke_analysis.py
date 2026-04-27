#!/usr/bin/env python3
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter

from lib.common import write_json
from lib.plot_style import apply_pub_style

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Run UKB CKD-stroke analyses')
    p.add_argument(
        '--input',
        default=str(ROOT / 'data/gold/ukb_ckd_stroke_analysis.csv'),
    )
    p.add_argument(
        '--outdir',
        default=str(ROOT / 'outputs/ukb_ckd_stroke'),
    )
    return p.parse_args()


def summarize_cox(cph: CoxPHFitter) -> pd.DataFrame:
    out = cph.summary.reset_index()
    if 'term' in out.columns:
        return out
    if 'covariate' in out.columns:
        return out.rename(columns={'covariate': 'term'})
    return out.rename(columns={out.columns[0]: 'term'})


def build_table1(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group_value, group_label in [(0, 'No CKD'), (1, 'CKD')]:
        gdf = df[df['ckd'] == group_value].copy()
        if gdf.empty:
            continue
        rows.extend(
            [
                {'group': group_label, 'metric': 'n', 'value': len(gdf)},
                {'group': group_label, 'metric': 'age_mean', 'value': gdf['age_baseline'].mean()},
                {'group': group_label, 'metric': 'female_pct', 'value': gdf['sex'].eq(0).mean() * 100},
                {'group': group_label, 'metric': 'bmi_mean', 'value': gdf['bmi'].mean()},
                {'group': group_label, 'metric': 'sbp_mean', 'value': gdf['sbp'].mean()},
                {'group': group_label, 'metric': 'egfr_mean', 'value': gdf['egfr_creatinine_2021'].mean()},
                {'group': group_label, 'metric': 'uacr_median', 'value': gdf['uacr_mg_mmol'].median()},
                {'group': group_label, 'metric': 'diabetes_pct', 'value': gdf['diabetes'].mean() * 100},
                {'group': group_label, 'metric': 'smoking_current_pct', 'value': gdf['smoking_current'].mean() * 100},
                {'group': group_label, 'metric': 'stroke_events', 'value': gdf['event_stroke'].sum()},
                {'group': group_label, 'metric': 'ischemic_stroke_events', 'value': gdf['event_ischemic_stroke'].sum()},
                {'group': group_label, 'metric': 'allcause_deaths', 'value': gdf['event_allcause'].sum()},
            ]
        )
    return pd.DataFrame(rows)


def cox_from_design(
    design: pd.DataFrame,
    duration_col: str,
    event_col: str,
    exposure_terms: list[str],
    covars: list[str],
    model_name: str,
) -> pd.DataFrame:
    cols = [duration_col, event_col] + exposure_terms + covars
    dat = design[cols].dropna().copy()
    dat = dat[dat[duration_col].gt(0)].copy()
    if dat.empty or int(dat[event_col].sum()) == 0:
        return pd.DataFrame()
    cph = CoxPHFitter()
    cph.fit(dat, duration_col=duration_col, event_col=event_col)
    out = summarize_cox(cph)
    out['outcome'] = event_col
    out['model'] = model_name
    out['n'] = len(dat)
    out['events'] = int(dat[event_col].sum())
    return out


def cox_binary_exposure(
    df: pd.DataFrame,
    duration_col: str,
    event_col: str,
    exposure_col: str,
    covars: list[str],
) -> pd.DataFrame:
    dat = df[[duration_col, event_col, exposure_col] + covars].dropna().copy()
    dat[exposure_col] = dat[exposure_col].astype(int)
    return cox_from_design(
        dat,
        duration_col=duration_col,
        event_col=event_col,
        exposure_terms=[exposure_col],
        covars=covars,
        model_name=f'binary_{exposure_col}',
    )


def cox_categorical_exposure(
    df: pd.DataFrame,
    duration_col: str,
    event_col: str,
    exposure_col: str,
    categories: list[str],
    covars: list[str],
    prefix: str,
) -> pd.DataFrame:
    dat = df[[duration_col, event_col, exposure_col] + covars].dropna().copy()
    if dat.empty:
        return pd.DataFrame()
    dat[exposure_col] = pd.Categorical(dat[exposure_col], categories=categories, ordered=True)
    dat = dat[dat[exposure_col].notna()].copy()
    dummies = pd.get_dummies(dat[exposure_col], prefix=prefix, drop_first=True)
    if dummies.empty:
        return pd.DataFrame()
    design = pd.concat([dat[[duration_col, event_col] + covars], dummies], axis=1)
    return cox_from_design(
        design,
        duration_col=duration_col,
        event_col=event_col,
        exposure_terms=dummies.columns.tolist(),
        covars=covars,
        model_name=f'categorical_{exposure_col}',
    )


def cox_joint_markers(
    df: pd.DataFrame,
    duration_col: str,
    event_col: str,
    covars: list[str],
) -> pd.DataFrame:
    dat = df[[duration_col, event_col, 'kidney_marker_joint_group'] + covars].dropna().copy()
    if dat.empty:
        return pd.DataFrame()
    dat['kidney_marker_joint_group'] = dat['kidney_marker_joint_group'].astype(int)
    dummies = pd.get_dummies(dat['kidney_marker_joint_group'], prefix='joint', drop_first=True)
    if dummies.empty:
        return pd.DataFrame()
    design = pd.concat([dat[[duration_col, event_col] + covars], dummies], axis=1)
    return cox_from_design(
        design,
        duration_col=duration_col,
        event_col=event_col,
        exposure_terms=dummies.columns.tolist(),
        covars=covars,
        model_name='joint_kidney_markers',
    )


def interaction_term_model(
    df: pd.DataFrame,
    duration_col: str,
    event_col: str,
    covars: list[str],
) -> pd.DataFrame:
    dat = df[[duration_col, event_col, 'egfr_lt60', 'albuminuria_ge3'] + covars].dropna().copy()
    if dat.empty:
        return pd.DataFrame()
    dat['egfr_lt60'] = dat['egfr_lt60'].astype(int)
    dat['albuminuria_ge3'] = dat['albuminuria_ge3'].astype(int)
    dat['egfr_x_albuminuria'] = dat['egfr_lt60'] * dat['albuminuria_ge3']
    return cox_from_design(
        dat,
        duration_col=duration_col,
        event_col=event_col,
        exposure_terms=['egfr_lt60', 'albuminuria_ge3', 'egfr_x_albuminuria'],
        covars=covars,
        model_name='interaction_egfr_albuminuria',
    )


def additive_interaction_from_joint(cox_df: pd.DataFrame) -> pd.DataFrame:
    hr = {}
    for term in ['joint_1', 'joint_2', 'joint_3']:
        sub = cox_df.loc[cox_df['term'] == term, 'exp(coef)']
        hr[term] = float(sub.iloc[0]) if len(sub) else np.nan
    hr01 = hr['joint_1']
    hr10 = hr['joint_2']
    hr11 = hr['joint_3']
    reri = hr11 - hr10 - hr01 + 1
    ap = reri / hr11 if pd.notna(hr11) and hr11 != 0 else np.nan
    denom = (hr10 - 1) + (hr01 - 1)
    synergy_index = (hr11 - 1) / denom if pd.notna(denom) and denom != 0 else np.nan
    return pd.DataFrame(
        {
            'metric': ['HR_01', 'HR_10', 'HR_11', 'RERI', 'AP', 'S'],
            'value': [hr01, hr10, hr11, reri, ap, synergy_index],
        }
    )


def draw_km_binary(
    df: pd.DataFrame,
    duration_col: str,
    event_col: str,
    group_col: str,
    out_path: Path,
    title: str,
) -> None:
    apply_pub_style()
    plt.figure(figsize=(8.6, 5.4))
    kmf = KaplanMeierFitter()
    label_map = {0: 'No CKD', 1: 'CKD'}
    for group in [0, 1]:
        gdf = df.loc[df[group_col] == group, [duration_col, event_col]].dropna()
        gdf = gdf[gdf[duration_col].gt(0)]
        if len(gdf) < 50:
            continue
        kmf.fit(gdf[duration_col], gdf[event_col], label=label_map[group])
        kmf.plot_survival_function(ci_show=False)
    plt.title(title)
    plt.xlabel('Follow-up years')
    plt.ylabel('Survival probability')
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path)
    plt.close()


def main() -> None:
    warnings.filterwarnings('ignore', category=FutureWarning)
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(
        args.input,
        parse_dates=[
            'baseline_date',
            'censor_date',
            'clinical_ckd_date',
            'stroke_date',
            'ischemic_stroke_date',
            'stroke_death_date',
            'fatal_ischemic_stroke_date',
            'any_stroke_date',
            'any_ischemic_stroke_date',
            'death_date',
        ],
    )

    table1 = build_table1(df)
    table1.to_csv(outdir / 'table1_ckd_status.csv', index=False)

    stroke_free_df = df[df['prev_stroke'].fillna(0).eq(0)].copy()
    covars = [
        'age_baseline',
        'sex',
        'white_ethnicity',
        'townsend',
        'bmi',
        'sbp',
        'cholesterol_total',
        'diabetes',
        'smoking_former',
        'smoking_current',
    ]
    outcomes = [
        ('followup_stroke_years', 'event_stroke'),
        ('followup_ischemic_stroke_years', 'event_ischemic_stroke'),
        ('followup_allcause_years', 'event_allcause'),
    ]

    binary_outputs = []
    egfr_outputs = []
    acr_outputs = []
    joint_outputs = []
    interaction_outputs = []
    additive_outputs = []
    event_summary = []

    egfr_categories = ['G1 >=90', 'G2 60-89', 'G3a 45-59', 'G3b 30-44', 'G4-5 <30']
    uacr_categories = ['A1 <3', 'A2 3-29.9', 'A3 >=30']

    for duration_col, event_col in outcomes:
        event_summary.append(
            {
                'outcome': event_col,
                'n': int(stroke_free_df[[duration_col, event_col]].dropna().shape[0]),
                'events': int(stroke_free_df[event_col].fillna(0).sum()),
            }
        )

        binary_df = cox_binary_exposure(stroke_free_df, duration_col, event_col, 'ckd', covars)
        if not binary_df.empty:
            binary_outputs.append(binary_df)

        egfr_df = cox_categorical_exposure(
            stroke_free_df,
            duration_col,
            event_col,
            'egfr_category',
            egfr_categories,
            covars,
            'egfr',
        )
        if not egfr_df.empty:
            egfr_outputs.append(egfr_df)

        acr_df = cox_categorical_exposure(
            stroke_free_df,
            duration_col,
            event_col,
            'uacr_category',
            uacr_categories,
            covars,
            'uacr',
        )
        if not acr_df.empty:
            acr_outputs.append(acr_df)

        joint_df = cox_joint_markers(stroke_free_df, duration_col, event_col, covars)
        if not joint_df.empty:
            joint_outputs.append(joint_df)
            additive = additive_interaction_from_joint(joint_df)
            additive['outcome'] = event_col
            additive_outputs.append(additive)

        interaction_df = interaction_term_model(stroke_free_df, duration_col, event_col, covars)
        if not interaction_df.empty:
            interaction_outputs.append(interaction_df)

    if binary_outputs:
        pd.concat(binary_outputs, ignore_index=True).to_csv(outdir / 'cox_ckd_binary.csv', index=False)
    if egfr_outputs:
        pd.concat(egfr_outputs, ignore_index=True).to_csv(outdir / 'cox_egfr_categories.csv', index=False)
    if acr_outputs:
        pd.concat(acr_outputs, ignore_index=True).to_csv(outdir / 'cox_uacr_categories.csv', index=False)
    if joint_outputs:
        pd.concat(joint_outputs, ignore_index=True).to_csv(outdir / 'cox_joint_kidney_markers.csv', index=False)
    if interaction_outputs:
        pd.concat(interaction_outputs, ignore_index=True).to_csv(outdir / 'cox_interaction_terms.csv', index=False)
    if additive_outputs:
        pd.concat(additive_outputs, ignore_index=True).to_csv(outdir / 'additive_interaction_metrics.csv', index=False)

    draw_km_binary(
        stroke_free_df[stroke_free_df['ckd'].isin([0, 1])].copy(),
        'followup_stroke_years',
        'event_stroke',
        'ckd',
        outdir / 'km_stroke_ckd.png',
        'Incident stroke by baseline CKD status',
    )
    draw_km_binary(
        stroke_free_df[stroke_free_df['ckd'].isin([0, 1])].copy(),
        'followup_ischemic_stroke_years',
        'event_ischemic_stroke',
        'ckd',
        outdir / 'km_ischemic_stroke_ckd.png',
        'Incident ischaemic stroke by baseline CKD status',
    )
    draw_km_binary(
        stroke_free_df[stroke_free_df['ckd'].isin([0, 1])].copy(),
        'followup_allcause_years',
        'event_allcause',
        'ckd',
        outdir / 'km_allcause_ckd.png',
        'All-cause survival by baseline CKD status',
    )

    summary = {
        'input': args.input,
        'analysis_population_n': int(len(df)),
        'stroke_free_population_n': int(len(stroke_free_df)),
        'baseline_ckd_n': int(df['ckd'].fillna(0).sum()),
        'event_summary': event_summary,
        'outdir': str(outdir),
    }
    write_json(outdir / 'analysis_summary.json', summary)

    print(f'Analysis outputs written to: {outdir}')


if __name__ == '__main__':
    main()
