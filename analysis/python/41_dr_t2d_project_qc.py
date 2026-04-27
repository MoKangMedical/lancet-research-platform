#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='QC report for the DR-T2D project')
    p.add_argument('--ukb-input', default=str(ROOT / 'data/gold/ukb_dr_t2d_analysis.csv'))
    p.add_argument('--ukb-results-dir', default=str(ROOT / 'outputs/ukb_dr_t2d'))
    p.add_argument('--gbd-qc-json', default=str(ROOT / 'outputs/tables/gbd2023_starter_qc.json'))
    p.add_argument('--out-md', default=str(ROOT / 'outputs/tables/dr_t2d_project_qc_report.md'))
    p.add_argument('--out-json', default=str(ROOT / 'outputs/tables/dr_t2d_project_qc_report.json'))
    return p.parse_args()


def float_or_none(value: float) -> float | None:
    if pd.isna(value) or np.isinf(value):
        return None
    return float(value)


def main() -> None:
    warnings.filterwarnings('ignore', category=FutureWarning)
    args = parse_args()
    df = pd.read_csv(args.ukb_input)
    results_dir = Path(args.ukb_results_dir)
    cox_joint = pd.read_csv(results_dir / 'cox_joint_groups.csv')
    cox_interaction = pd.read_csv(results_dir / 'cox_interaction_terms.csv')
    additive = pd.read_csv(results_dir / 'additive_interaction_metrics.csv')
    table1 = pd.read_csv(results_dir / 'table1_joint_groups.csv')
    gbd_qc = json.loads(Path(args.gbd_qc_json).read_text(encoding='utf-8'))

    df['t2d_analysis'] = (
        df['t2d'].fillna(0).eq(1)
        | df['hba1c'].ge(48)
        | df['glucose'].ge(11.1)
    ).astype(int)
    df['joint_group_analysis'] = df['t2d_analysis'] * 2 + df['retinopathy']

    main_df = df[df['prev_cvd'].fillna(0).eq(0)].copy()

    cohort = {
        'rows': int(len(df)),
        'eid_duplicates': int(df['eid'].duplicated().sum()),
        'baseline_missing': int(df['baseline_date'].isna().sum()),
        'negative_followup_allcause': int((df['followup_allcause_years'] < 0).fillna(False).sum()),
        'negative_followup_mace': int((df['followup_mace_years'] < 0).fillna(False).sum()),
        'prev_cvd_rows': int(df['prev_cvd'].sum()),
        'incident_rows': int(len(main_df)),
        'raw_no_t2d_ret_hba1c48': int(((df['t2d'] == 0) & (df['retinopathy'] == 1) & (df['hba1c'] >= 48)).sum()),
        'raw_no_t2d_ret_glucose11_1': int(((df['t2d'] == 0) & (df['retinopathy'] == 1) & (df['glucose'] >= 11.1)).sum()),
        'analysis_no_t2d_ret_hba1c48': int(((df['t2d_analysis'] == 0) & (df['retinopathy'] == 1) & (df['hba1c'] >= 48)).sum()),
        'analysis_no_t2d_ret_glucose11_1': int(((df['t2d_analysis'] == 0) & (df['retinopathy'] == 1) & (df['glucose'] >= 11.1)).sum()),
        'missing_bmi': int(df['bmi'].isna().sum()),
        'missing_sbp': int(df['sbp'].isna().sum()),
        'missing_cholesterol_total': int(df['cholesterol_total'].isna().sum()),
        'missing_hba1c': int(df['hba1c'].isna().sum()),
    }

    group_sizes = (
        main_df['joint_group_analysis']
        .value_counts()
        .reindex([0, 1, 2, 3], fill_value=0)
        .to_dict()
    )

    key_rows = cox_joint[cox_joint['term'].isin(['joint_1', 'joint_2', 'joint_3'])].copy()
    interaction_rows = cox_interaction[
        cox_interaction['term'].isin(['t2d', 'retinopathy', 't2d_x_retinopathy'])
    ].copy()

    allcause_add = additive[additive['outcome'] == 'event_allcause'].set_index('metric')['value'].to_dict()
    mace_add = additive[additive['outcome'] == 'event_mace'].set_index('metric')['value'].to_dict()

    gbd_findings = {
        'mortality_years_available': gbd_qc['mortality']['years'],
        'mortality_duplicate_name_rows': int(gbd_qc['mortality']['name_level_duplicate_rows']),
        'mortality_duplicate_name_locations': gbd_qc['mortality']['name_level_duplicate_locations'],
        'mortality_limitation': gbd_qc['mortality']['limitation'],
    }

    findings = []
    if cohort['raw_no_t2d_ret_hba1c48'] > 0:
        findings.append(
            'Current gold cohort contains discordant participants with retinopathy and diabetic-range HbA1c despite raw t2d=0; manuscript analyses should rely on the analysis-stage T2D definition or rebuild the cohort with a finalized diabetes algorithm.'
        )
    if group_sizes.get(1, 0) < 500:
        findings.append(
            'The incident cohort has a very small No T2D / Retinopathy group, so interaction estimates are unstable and should not be used as the lead claim.'
        )
    if gbd_findings['mortality_duplicate_name_rows'] > 0:
        findings.append(
            'The current GBD starter mortality long table contains duplicated location names across hierarchy levels and only selected years, so it is suitable for exploration but not final disease-specific submission results.'
        )

    summary = {
        'cohort': cohort,
        'incident_group_sizes': group_sizes,
        'gbd': gbd_findings,
        'ukb_joint_model_rows': key_rows.to_dict(orient='records'),
        'ukb_interaction_rows': interaction_rows.to_dict(orient='records'),
        'additive_allcause': {k: float_or_none(v) for k, v in allcause_add.items()},
        'additive_mace': {k: float_or_none(v) for k, v in mace_add.items()},
        'findings': findings,
    }

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    t1_n = int(table1.loc[table1['metric'] == 'n', 'value'].sum())
    md = "\n".join([
        '# DR-T2D Project QC Report',
        '',
        '## Scope',
        '',
        '- UK Biobank cohort table',
        '- UKB joint-effect and interaction outputs',
        '- GBD 2023 starter dataset readiness',
        '',
        '## UKB Integrity Checks',
        '',
        f"- Rows: `{cohort['rows']}`",
        f"- Duplicate `eid`: `{cohort['eid_duplicates']}`",
        f"- Missing baseline date: `{cohort['baseline_missing']}`",
        f"- Negative follow-up (all-cause): `{cohort['negative_followup_allcause']}`",
        f"- Negative follow-up (MACE): `{cohort['negative_followup_mace']}`",
        f"- Prevalent CVD rows excluded from incident models: `{cohort['prev_cvd_rows']}`",
        f"- Incident cohort size used in current Table 1: `{t1_n}`",
        '',
        '## Diabetes Classification QC',
        '',
        f"- Raw cohort discordance: `t2d=0 & retinopathy=1 & HbA1c>=48`: `{cohort['raw_no_t2d_ret_hba1c48']}`",
        f"- Raw cohort discordance: `t2d=0 & retinopathy=1 & glucose>=11.1`: `{cohort['raw_no_t2d_ret_glucose11_1']}`",
        f"- Analysis-stage discordance after protective T2D definition, HbA1c criterion: `{cohort['analysis_no_t2d_ret_hba1c48']}`",
        f"- Analysis-stage discordance after protective T2D definition, glucose criterion: `{cohort['analysis_no_t2d_ret_glucose11_1']}`",
        '',
        '## Missingness',
        '',
        f"- BMI missing: `{cohort['missing_bmi']}`",
        f"- SBP missing: `{cohort['missing_sbp']}`",
        f"- Total cholesterol missing: `{cohort['missing_cholesterol_total']}`",
        f"- HbA1c missing: `{cohort['missing_hba1c']}`",
        '',
        '## Incident Cohort Group Sizes',
        '',
        f"- No T2D / No retinopathy: `{group_sizes.get(0, 0)}`",
        f"- No T2D / Retinopathy: `{group_sizes.get(1, 0)}`",
        f"- T2D / No retinopathy: `{group_sizes.get(2, 0)}`",
        f"- T2D / Retinopathy: `{group_sizes.get(3, 0)}`",
        '',
        '## Current Interpretation Check',
        '',
        '- The joint-risk signal is strongest for MACE and present for all-cause mortality.',
        '- The interaction story is not publication-grade as a headline claim because the No T2D / Retinopathy group is too small and unstable.',
        '- Additive interaction metrics should be interpreted cautiously; negative or unstable synergy-index values are not suitable for headline emphasis.',
        '',
        '## GBD Starter Dataset QC',
        '',
        f"- Mortality starter years available: `{gbd_findings['mortality_years_available']}`",
        f"- Mortality duplicate name-level rows: `{gbd_findings['mortality_duplicate_name_rows']}`",
        f"- Duplicate location names flagged: `{', '.join(gbd_findings['mortality_duplicate_name_locations'])}`",
        f"- Limitation: {gbd_findings['mortality_limitation']}",
        '',
        '## QC Conclusions',
        '',
    ] + [f"- {finding}" for finding in findings])

    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md + '\n', encoding='utf-8')

    print(f'QC markdown: {out_md}')
    print(f'QC json: {out_json}')


if __name__ == '__main__':
    main()
