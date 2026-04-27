#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path('/Users/apple/Documents/lancet-research-platform')
PY = '/Users/apple/Documents/.venvs/data-analytics/bin/python'


def run(cmd: list[str]) -> None:
    print('>>', ' '.join(cmd))
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Unified research CLI')
    sub = p.add_subparsers(dest='cmd', required=True)

    sub.add_parser('catalog')

    q = sub.add_parser('quality')
    q.add_argument('--input', required=True)

    e = sub.add_parser('eda')
    e.add_argument('--input', required=True)

    m = sub.add_parser('model')
    m.add_argument('--input', required=True)
    m.add_argument('--outcome', required=True)
    m.add_argument('--exposure', required=True)
    m.add_argument('--covars', default='')

    f = sub.add_parser('forest')
    f.add_argument('--model_csv', default=str(ROOT / 'outputs' / 'tables' / 'model_primary.csv'))

    sg = sub.add_parser('subgroup')
    sg.add_argument('--input', required=True)
    sg.add_argument('--outcome', required=True)
    sg.add_argument('--exposure', required=True)
    sg.add_argument('--subgroup', required=True)
    sg.add_argument('--covars', default='')

    sp = sub.add_parser('spline')
    sp.add_argument('--input', required=True)
    sp.add_argument('--outcome', required=True)
    sp.add_argument('--exposure', required=True)
    sp.add_argument('--covars', default='')
    sp.add_argument('--df_spline', type=int, default=4)

    sv = sub.add_parser('survival')
    sv.add_argument('--input', required=True)
    sv.add_argument('--time', required=True)
    sv.add_argument('--event', required=True)
    sv.add_argument('--exposure', required=True)
    sv.add_argument('--covars', default='')

    gm = sub.add_parser('gbd-map')
    gm.add_argument('--input', required=True)
    gm.add_argument('--value_col', default='val')
    gm.add_argument('--location_col', default='location_name')
    gm.add_argument('--iso3_col', default='')
    gm.add_argument('--facet_col', default='')
    gm.add_argument('--color_scale', default='YlOrRd')
    gm.add_argument('--title', default='GBD Choropleth Map')

    gd = sub.add_parser('gbd-download')
    gd.add_argument('--preset', default='gbd2023-core-1990-2023')
    gd.add_argument('--record', action='append')
    gd.add_argument('--record_url', default='')
    gd.add_argument('--record_html', default='')
    gd.add_argument('--dest', default=str(ROOT / 'data' / 'raw' / 'gbd'))
    gd.add_argument('--filename_pattern', action='append', default=[])
    gd.add_argument('--label_pattern', action='append', default=[])
    gd.add_argument('--year_span', default='1990-2023')
    gd.add_argument('--list_only', action='store_true')
    gd.add_argument('--manifest_out', default='')
    gd.add_argument('--cookie_header', default='')
    gd.add_argument('--cookie_file', default='')
    gd.add_argument('--save_html', action='store_true')
    gd.add_argument('--force', action='store_true')
    gd.add_argument('--timeout', type=int, default=60)

    gu = sub.add_parser('gbd-unpack')
    gu.add_argument('--input_root', default=str(ROOT / 'data' / 'raw' / 'gbd'))
    gu.add_argument('--dest_root', default=str(ROOT / 'data' / 'bronze' / 'gbd' / 'gbd2023'))
    gu.add_argument('--catalog_out', default=str(ROOT / 'outputs' / 'tables' / 'gbd2023_extracted_catalog.csv'))
    gu.add_argument('--summary_out', default=str(ROOT / 'outputs' / 'tables' / 'gbd2023_extracted_summary.json'))
    gu.add_argument('--force', action='store_true')

    gs = sub.add_parser('gbd-starter')
    gs.add_argument('--bronze_root', default=str(ROOT / 'data' / 'bronze' / 'gbd' / 'gbd2023'))
    gs.add_argument('--silver_root', default=str(ROOT / 'data' / 'silver' / 'gbd'))
    gs.add_argument('--notebook_out', default=str(ROOT / 'notebooks' / 'gbd2023_starter_analysis.ipynb'))
    gs.add_argument('--qc_out', default=str(ROOT / 'outputs' / 'tables' / 'gbd2023_starter_qc.json'))
    gs.add_argument('--force', action='store_true')

    gp = sub.add_parser('gbd-dirf-parse')
    gp.add_argument('--dirf_root', default=str(ROOT / 'data' / 'bronze' / 'gbd' / 'gbd2023' / 'dirf-2023'))
    gp.add_argument('--out_csv', default=str(ROOT / 'data' / 'silver' / 'gbd' / 'gbd2023_dirf_global_core_tidy.csv'))
    gp.add_argument('--qc_out', default=str(ROOT / 'outputs' / 'tables' / 'gbd2023_dirf_global_core_qc.json'))

    gt = sub.add_parser('gbd-template')
    gt.add_argument('--input', required=True)
    gt.add_argument('--measure', default='')
    gt.add_argument('--metric', default='')
    gt.add_argument('--sex', default='')
    gt.add_argument('--location', default='')
    gt.add_argument('--summary_year', type=int, default=2023)
    gt.add_argument('--top_n', type=int, default=12)
    gt.add_argument('--cause_pattern', action='append', default=[])
    gt.add_argument('--map_cause', default='')
    gt.add_argument('--out_prefix', default='')
    gt.add_argument('--value_col', default='mean')
    gt.add_argument('--year_col', default='year_id')
    gt.add_argument('--measure_col', default='measure')
    gt.add_argument('--metric_col', default='metric')
    gt.add_argument('--sex_col', default='sex')
    gt.add_argument('--location_col', default='location_name')
    gt.add_argument('--cause_col', default='cause_name')
    gt.add_argument('--lower_col', default='lower')
    gt.add_argument('--upper_col', default='upper')

    ge = sub.add_parser('gbd-results-export')
    ge.add_argument('--spec', required=True)
    ge.add_argument('--storage_state', default='')
    ge.add_argument('--package', default='all')
    ge.add_argument('--force_login', action='store_true')

    ga = sub.add_parser('gbd-asthma-u40-analysis')
    ga.add_argument('--study_root', required=True)

    g3 = sub.add_parser('gbd-asthma-u40-phase3')
    g3.add_argument('--study_root', required=True)

    g4 = sub.add_parser('gbd-asthma-u40-phase4')
    g4.add_argument('--study_root', required=True)

    g5 = sub.add_parser('gbd-asthma-u40-phase5')
    g5.add_argument('--study_root', required=True)

    gq = sub.add_parser('gbd-asthma-u40-qc')
    gq.add_argument('--study_root', required=True)

    r = sub.add_parser('refs')
    r.add_argument('--query', required=True)
    r.add_argument('--retmax', type=int, default=80)
    r.add_argument('--project_name', default='Unnamed Study')

    l = sub.add_parser('lancet-intro')
    l.add_argument('--project_name', default='Unnamed Study')
    l.add_argument('--max_refs', type=int, default=30)

    a = sub.add_parser('audit')
    a.add_argument('--manuscript', required=True)
    a.add_argument('--design', default='cohort')
    a.add_argument('--data_type', default='standard')

    s = sub.add_parser('package')
    s.add_argument('--project_name', default='submission')

    ub = sub.add_parser('ukb-dr-build')
    ub.add_argument('--input', default='/Users/apple/Desktop/所有数据/UKB数据/ukb669219.csv')
    ub.add_argument('--out_csv', default=str(ROOT / 'data/gold/ukb_dr_t2d_analysis.csv'))
    ub.add_argument('--out_qc', default=str(ROOT / 'outputs/tables/ukb_dr_t2d_build_qc.csv'))
    ub.add_argument('--chunksize', type=int, default=20000)
    ub.add_argument('--admin_censor_date', default='2023-12-31')

    ua = sub.add_parser('ukb-dr-analyze')
    ua.add_argument('--input', default=str(ROOT / 'data/gold/ukb_dr_t2d_analysis.csv'))
    ua.add_argument('--outdir', default=str(ROOT / 'outputs/ukb_dr_t2d'))

    uq = sub.add_parser('ukb-dr-qc')
    uq.add_argument('--ukb_input', default=str(ROOT / 'data/gold/ukb_dr_t2d_analysis.csv'))
    uq.add_argument('--ukb_results_dir', default=str(ROOT / 'outputs/ukb_dr_t2d'))
    uq.add_argument('--gbd_qc_json', default=str(ROOT / 'outputs/tables/gbd2023_starter_qc.json'))
    uq.add_argument('--out_md', default=str(ROOT / 'outputs/tables/dr_t2d_project_qc_report.md'))
    uq.add_argument('--out_json', default=str(ROOT / 'outputs/tables/dr_t2d_project_qc_report.json'))

    kb = sub.add_parser('ukb-ckd-stroke-build')
    kb.add_argument('--input', default='/Users/apple/Desktop/所有数据/UKB数据/ukb669219.csv')
    kb.add_argument('--out_csv', default=str(ROOT / 'data/gold/ukb_ckd_stroke_analysis.csv'))
    kb.add_argument('--out_qc', default=str(ROOT / 'outputs/tables/ukb_ckd_stroke_build_qc.csv'))
    kb.add_argument('--chunksize', type=int, default=20000)
    kb.add_argument('--admin_censor_date', default='2023-12-31')

    ka = sub.add_parser('ukb-ckd-stroke-analyze')
    ka.add_argument('--input', default=str(ROOT / 'data/gold/ukb_ckd_stroke_analysis.csv'))
    ka.add_argument('--outdir', default=str(ROOT / 'outputs/ukb_ckd_stroke'))

    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.cmd == 'catalog':
        run([PY, str(ROOT / 'analysis/python/10_data_catalog.py')])
    elif args.cmd == 'quality':
        run([PY, str(ROOT / 'analysis/python/11_data_quality_report.py'), '--input', args.input])
    elif args.cmd == 'eda':
        run([PY, str(ROOT / 'analysis/python/12_auto_eda.py'), '--input', args.input])
    elif args.cmd == 'model':
        run([
            PY,
            str(ROOT / 'analysis/python/30_run_analysis_pipeline.py'),
            '--input', args.input,
            '--outcome', args.outcome,
            '--exposure', args.exposure,
            '--covars', args.covars,
        ])
    elif args.cmd == 'forest':
        run([PY, str(ROOT / 'analysis/python/31_forest_from_model.py'), '--model_csv', args.model_csv])
    elif args.cmd == 'subgroup':
        run([
            PY,
            str(ROOT / 'analysis/python/32_subgroup_forest.py'),
            '--input', args.input,
            '--outcome', args.outcome,
            '--exposure', args.exposure,
            '--subgroup', args.subgroup,
            '--covars', args.covars,
        ])
    elif args.cmd == 'spline':
        run([
            PY,
            str(ROOT / 'analysis/python/33_spline_effect_plot.py'),
            '--input', args.input,
            '--outcome', args.outcome,
            '--exposure', args.exposure,
            '--covars', args.covars,
            '--df_spline', str(args.df_spline),
        ])
    elif args.cmd == 'survival':
        run([
            PY,
            str(ROOT / 'analysis/python/34_survival_km_cox.py'),
            '--input', args.input,
            '--time', args.time,
            '--event', args.event,
            '--exposure', args.exposure,
            '--covars', args.covars,
        ])
    elif args.cmd == 'gbd-map':
        run([
            PY,
            str(ROOT / 'analysis/python/35_gbd_choropleth_map.py'),
            '--input', args.input,
            '--value_col', args.value_col,
            '--location_col', args.location_col,
            '--iso3_col', args.iso3_col,
            '--facet_col', args.facet_col,
            '--color_scale', args.color_scale,
            '--title', args.title,
        ])
    elif args.cmd == 'gbd-download':
        cmd = [
            PY,
            str(ROOT / 'analysis/python/38_gbd_download.py'),
            '--preset', args.preset,
            '--dest', args.dest,
            '--year-span', args.year_span,
            '--timeout', str(args.timeout),
        ]
        for value in args.record or []:
            cmd.extend(['--record', value])
        for value in args.filename_pattern:
            cmd.extend(['--filename-pattern', value])
        for value in args.label_pattern:
            cmd.extend(['--label-pattern', value])
        if args.record_url:
            cmd.extend(['--record-url', args.record_url])
        if args.record_html:
            cmd.extend(['--record-html', args.record_html])
        if args.list_only:
            cmd.append('--list-only')
        if args.manifest_out:
            cmd.extend(['--manifest-out', args.manifest_out])
        if args.cookie_header:
            cmd.extend(['--cookie-header', args.cookie_header])
        if args.cookie_file:
            cmd.extend(['--cookie-file', args.cookie_file])
        if args.save_html:
            cmd.append('--save-html')
        if args.force:
            cmd.append('--force')
        run(cmd)
    elif args.cmd == 'gbd-unpack':
        cmd = [
            PY,
            str(ROOT / 'analysis/python/39_gbd_unpack_archives.py'),
            '--input-root', args.input_root,
            '--dest-root', args.dest_root,
            '--catalog-out', args.catalog_out,
            '--summary-out', args.summary_out,
        ]
        if args.force:
            cmd.append('--force')
        run(cmd)
    elif args.cmd == 'gbd-starter':
        cmd = [
            PY,
            str(ROOT / 'analysis/python/40_gbd_build_starter_datasets.py'),
            '--bronze-root', args.bronze_root,
            '--silver-root', args.silver_root,
            '--notebook-out', args.notebook_out,
            '--qc-out', args.qc_out,
        ]
        if args.force:
            cmd.append('--force')
        run(cmd)
    elif args.cmd == 'gbd-dirf-parse':
        run([
            PY,
            str(ROOT / 'analysis/python/41_gbd_parse_dirf_tables.py'),
            '--dirf-root', args.dirf_root,
            '--out-csv', args.out_csv,
            '--qc-out', args.qc_out,
        ])
    elif args.cmd == 'gbd-template':
        cmd = [
            PY,
            str(ROOT / 'analysis/python/42_gbd_make_templates.py'),
            '--input', args.input,
            '--measure', args.measure,
            '--metric', args.metric,
            '--sex', args.sex,
            '--location', args.location,
            '--summary-year', str(args.summary_year),
            '--top-n', str(args.top_n),
            '--value-col', args.value_col,
            '--year-col', args.year_col,
            '--measure-col', args.measure_col,
            '--metric-col', args.metric_col,
            '--sex-col', args.sex_col,
            '--location-col', args.location_col,
            '--cause-col', args.cause_col,
            '--lower-col', args.lower_col,
            '--upper-col', args.upper_col,
        ]
        for value in args.cause_pattern:
            cmd.extend(['--cause-pattern', value])
        if args.map_cause:
            cmd.extend(['--map-cause', args.map_cause])
        if args.out_prefix:
            cmd.extend(['--out-prefix', args.out_prefix])
        run(cmd)
    elif args.cmd == 'gbd-results-export':
        cmd = [
            'node',
            str(ROOT / 'analysis/node/44_gbd_results_export.js'),
            '--spec', args.spec,
            '--package', args.package,
        ]
        if args.storage_state:
            cmd.extend(['--storage-state', args.storage_state])
        if args.force_login:
            cmd.append('--force-login')
        run(cmd)
    elif args.cmd == 'gbd-asthma-u40-analysis':
        run([
            PY,
            str(ROOT / 'analysis/python/45_gbd_asthma_east_asia_u40_analysis.py'),
            '--study-root', args.study_root,
        ])
    elif args.cmd == 'gbd-asthma-u40-phase3':
        run([
            PY,
            str(ROOT / 'analysis/python/46_gbd_asthma_east_asia_u40_phase3.py'),
            '--study-root', args.study_root,
        ])
    elif args.cmd == 'gbd-asthma-u40-phase4':
        run([
            PY,
            str(ROOT / 'analysis/python/47_gbd_asthma_east_asia_u40_phase4_manuscript.py'),
            '--study-root', args.study_root,
        ])
    elif args.cmd == 'gbd-asthma-u40-phase5':
        run([
            PY,
            str(ROOT / 'analysis/python/48_gbd_asthma_east_asia_u40_phase5_submission_package.py'),
            '--study-root', args.study_root,
        ])
    elif args.cmd == 'gbd-asthma-u40-qc':
        run([
            PY,
            str(ROOT / 'analysis/python/49_gbd_asthma_east_asia_u40_qc_report.py'),
            '--study-root', args.study_root,
        ])
    elif args.cmd == 'refs':
        run([
            PY,
            str(ROOT / 'analysis/python/21_pubmed_lit_review_pipeline.py'),
            '--query', args.query,
            '--retmax', str(args.retmax),
            '--project_name', args.project_name,
            '--outdir', str(ROOT / 'outputs/references'),
        ])
    elif args.cmd == 'lancet-intro':
        run([
            PY,
            str(ROOT / 'analysis/python/22_build_lancet_intro_refs.py'),
            '--in_csv', str(ROOT / 'outputs/references/pubmed_references_advanced.csv'),
            '--project_name', args.project_name,
            '--max_refs', str(args.max_refs),
            '--outdir', str(ROOT / 'outputs/references'),
        ])
    elif args.cmd == 'audit':
        run([
            PY,
            str(ROOT / 'analysis/python/24_manuscript_audit.py'),
            '--manuscript', args.manuscript,
            '--design', args.design,
            '--data_type', args.data_type,
        ])
    elif args.cmd == 'package':
        run([
            PY,
            str(ROOT / 'analysis/python/25_submission_packager.py'),
            '--project', args.project_name,
        ])
    elif args.cmd == 'ukb-dr-build':
        run([
            PY,
            str(ROOT / 'analysis/python/36_ukb_dr_t2d_build_cohort.py'),
            '--input', args.input,
            '--out_csv', args.out_csv,
            '--out_qc', args.out_qc,
            '--chunksize', str(args.chunksize),
            '--admin-censor-date', args.admin_censor_date,
        ])
    elif args.cmd == 'ukb-dr-analyze':
        run([
            PY,
            str(ROOT / 'analysis/python/37_ukb_dr_t2d_interaction_analysis.py'),
            '--input', args.input,
            '--outdir', args.outdir,
        ])
    elif args.cmd == 'ukb-dr-qc':
        run([
            PY,
            str(ROOT / 'analysis/python/41_dr_t2d_project_qc.py'),
            '--ukb-input', args.ukb_input,
            '--ukb-results-dir', args.ukb_results_dir,
            '--gbd-qc-json', args.gbd_qc_json,
            '--out-md', args.out_md,
            '--out-json', args.out_json,
        ])
    elif args.cmd == 'ukb-ckd-stroke-build':
        run([
            PY,
            str(ROOT / 'analysis/python/49_ukb_ckd_stroke_build_cohort.py'),
            '--input', args.input,
            '--out_csv', args.out_csv,
            '--out_qc', args.out_qc,
            '--chunksize', str(args.chunksize),
            '--admin-censor-date', args.admin_censor_date,
        ])
    elif args.cmd == 'ukb-ckd-stroke-analyze':
        run([
            PY,
            str(ROOT / 'analysis/python/50_ukb_ckd_stroke_analysis.py'),
            '--input', args.input,
            '--outdir', args.outdir,
        ])


if __name__ == '__main__':
    main()
