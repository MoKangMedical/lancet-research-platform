#!/usr/bin/env python3
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter

from lib.plot_style import apply_pub_style

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Run UKB T2D-retinopathy interaction analyses')
    p.add_argument(
        '--input',
        default=str(ROOT / 'data/gold/ukb_dr_t2d_analysis.csv'),
    )
    p.add_argument(
        '--outdir',
        default=str(ROOT / 'outputs/ukb_dr_t2d'),
    )
    return p.parse_args()


def summarize_cox(cph: CoxPHFitter) -> pd.DataFrame:
    out = cph.summary.reset_index()
    if 'term' in out.columns:
        return out
    if 'covariate' in out.columns:
        return out.rename(columns={'covariate': 'term'})
    first = out.columns[0]
    return out.rename(columns={first: 'term'})


def cox_table(
    df: pd.DataFrame,
    duration_col: str,
    event_col: str,
    covars: list[str],
) -> pd.DataFrame:
    dat = df[[duration_col, event_col, 'joint_group'] + covars].dropna().copy()
    dat = dat[dat[duration_col].gt(0)].copy()
    dat['joint_1'] = dat['joint_group'].eq(1).astype(int)
    dat['joint_2'] = dat['joint_group'].eq(2).astype(int)
    dat['joint_3'] = dat['joint_group'].eq(3).astype(int)
    cph = CoxPHFitter()
    cph.fit(
        dat[[duration_col, event_col, 'joint_1', 'joint_2', 'joint_3'] + covars],
        duration_col=duration_col,
        event_col=event_col,
    )
    out = summarize_cox(cph)
    out['outcome'] = event_col
    return out


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


def interaction_term_model(
    df: pd.DataFrame,
    duration_col: str,
    event_col: str,
    covars: list[str],
) -> pd.DataFrame:
    exposure_col = 't2d_analysis' if 't2d_analysis' in df.columns else 't2d'
    dat = df[[duration_col, event_col, exposure_col, 'retinopathy'] + covars].dropna().copy()
    dat = dat[dat[duration_col].gt(0)].copy()
    dat = dat.rename(columns={exposure_col: 't2d_analysis'})
    dat['t2d_x_retinopathy'] = dat['t2d_analysis'] * dat['retinopathy']
    cph = CoxPHFitter()
    cph.fit(
        dat[[duration_col, event_col, 't2d_analysis', 'retinopathy', 't2d_x_retinopathy'] + covars],
        duration_col=duration_col,
        event_col=event_col,
    )
    out = summarize_cox(cph)
    out['outcome'] = event_col
    return out


def build_table1(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group, gdf in df.groupby('joint_label', dropna=False):
        rows.extend(
            [
                {'group': group, 'metric': 'n', 'value': len(gdf)},
                {'group': group, 'metric': 'age_mean', 'value': gdf['age_baseline'].mean()},
                {'group': group, 'metric': 'female_pct', 'value': gdf['sex'].eq(0).mean() * 100},
                {'group': group, 'metric': 'bmi_mean', 'value': gdf['bmi'].mean()},
                {'group': group, 'metric': 'hba1c_mean', 'value': gdf['hba1c'].mean()},
                {'group': group, 'metric': 'sbp_mean', 'value': gdf['sbp'].mean()},
                {'group': group, 'metric': 'smoking_current_pct', 'value': gdf['smoking_current'].mean() * 100},
                {'group': group, 'metric': 'allcause_events', 'value': gdf['event_allcause'].sum()},
                {'group': group, 'metric': 'mace_events', 'value': gdf['event_mace'].sum()},
            ]
        )
    return pd.DataFrame(rows)


def draw_km(df: pd.DataFrame, duration_col: str, event_col: str, out_path: Path) -> None:
    apply_pub_style()
    plt.figure(figsize=(8.6, 5.4))
    kmf = KaplanMeierFitter()
    for group in [0, 1, 2, 3]:
        gdf = df.loc[df['joint_group'] == group, [duration_col, event_col]].dropna()
        gdf = gdf[gdf[duration_col].gt(0)]
        if len(gdf) < 50:
            continue
        label = {
            0: 'No T2D / No retinopathy',
            1: 'No T2D / Retinopathy',
            2: 'T2D / No retinopathy',
            3: 'T2D / Retinopathy',
        }[group]
        kmf.fit(gdf[duration_col], gdf[event_col], label=label)
        kmf.plot_survival_function(ci_show=False)
    plt.title('UK Biobank survival by T2D-retinopathy joint exposure')
    plt.xlabel('Follow-up years')
    plt.ylabel('Survival probability')
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path)
    plt.close()


def main() -> None:
    warnings.filterwarnings('ignore', category=FutureWarning)
    args = parse_args()
    df = pd.read_csv(args.input, parse_dates=['baseline_date', 'censor_date', 'death_date', 'mace_date', 'hf_date'])
    df['t2d_analysis'] = (
        df['t2d'].fillna(0).eq(1)
        | df['hba1c'].ge(48)
        | df['glucose'].ge(11.1)
    ).astype(int)
    df['joint_group'] = df['t2d_analysis'] * 2 + df['retinopathy']
    df['joint_label'] = df['joint_group'].map({
        0: 'No T2D / No retinopathy',
        1: 'No T2D / Retinopathy',
        2: 'T2D / No retinopathy',
        3: 'T2D / Retinopathy',
    })

    covars = [
        'age_baseline',
        'sex',
        'white_ethnicity',
        'townsend',
        'bmi',
        'sbp',
        'cholesterol_total',
        'hba1c',
        'smoking_former',
        'smoking_current',
    ]
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    main_df = df[df['prev_cvd'].fillna(0).eq(0)].copy()
    table1 = build_table1(main_df)
    table1.to_csv(outdir / 'table1_joint_groups.csv', index=False)
    outcomes = [
        ('followup_allcause_years', 'event_allcause'),
        ('followup_mace_years', 'event_mace'),
    ]
    cox_outputs = []
    interaction_outputs = []
    additive_outputs = []
    for duration_col, event_col in outcomes:
        cox_df = cox_table(main_df, duration_col, event_col, covars)
        cox_outputs.append(cox_df)
        additive = additive_interaction_from_joint(cox_df)
        additive['outcome'] = event_col
        additive_outputs.append(additive)

        inter_df = interaction_term_model(main_df, duration_col, event_col, covars)
        inter_df['term'] = inter_df['term'].replace({'t2d_analysis': 't2d'})
        interaction_outputs.append(inter_df)

    pd.concat(cox_outputs, ignore_index=True).to_csv(outdir / 'cox_joint_groups.csv', index=False)
    pd.concat(interaction_outputs, ignore_index=True).to_csv(outdir / 'cox_interaction_terms.csv', index=False)
    pd.concat(additive_outputs, ignore_index=True).to_csv(outdir / 'additive_interaction_metrics.csv', index=False)

    draw_km(main_df, 'followup_allcause_years', 'event_allcause', outdir / 'km_allcause_joint_groups.png')
    draw_km(main_df, 'followup_mace_years', 'event_mace', outdir / 'km_mace_joint_groups.png')

    print(f'Analysis outputs written to: {outdir}')


if __name__ == '__main__':
    main()
