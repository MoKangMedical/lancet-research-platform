#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
import matplotlib.pyplot as plt

from lib.plot_style import apply_pub_style

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--outcome', required=True)
    p.add_argument('--exposure', required=True)
    p.add_argument('--covars', default='')
    p.add_argument('--df_spline', type=int, default=4)
    p.add_argument('--out_csv', default=str(ROOT / 'outputs/tables/spline_effect_curve.csv'))
    p.add_argument('--out_png', default=str(ROOT / 'outputs/figures/spline_effect_plot.png'))
    return p.parse_args()


def read_df(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == '.csv':
        return pd.read_csv(path)
    if path.suffix.lower() in {'.parquet', '.pq'}:
        return pd.read_parquet(path)
    raise ValueError('Unsupported format')


def main() -> None:
    args = parse_args()
    df = read_df(Path(args.input))
    covars = [x.strip() for x in args.covars.split(',') if x.strip()]
    req = [args.outcome, args.exposure] + covars
    dat = df[req].dropna().copy()

    # binary heuristic
    y_uniq = sorted(dat[args.outcome].unique().tolist())
    rhs = f"bs({args.exposure}, df={args.df_spline})"
    if covars:
        rhs += ' + ' + ' + '.join(covars)
    formula = f"{args.outcome} ~ {rhs}"

    if y_uniq in ([0, 1], [0], [1]):
        fit = smf.glm(formula=formula, data=dat, family=sm.families.Binomial()).fit()
        scale = 'pred_prob'
    else:
        fit = smf.ols(formula=formula, data=dat).fit()
        scale = 'pred_mean'

    xgrid = np.linspace(dat[args.exposure].quantile(0.01), dat[args.exposure].quantile(0.99), 120)
    base = {c: dat[c].median() if pd.api.types.is_numeric_dtype(dat[c]) else dat[c].mode().iloc[0] for c in covars}
    pred_df = pd.DataFrame({args.exposure: xgrid, **base})
    pred = fit.get_prediction(pred_df).summary_frame(alpha=0.05)

    curve = pd.DataFrame({
        args.exposure: xgrid,
        scale: pred['mean'].values,
        'lcl': pred['mean_ci_lower'].values,
        'ucl': pred['mean_ci_upper'].values,
    })

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    curve.to_csv(out_csv, index=False)

    apply_pub_style()
    plt.figure(figsize=(8.3, 5.0))
    plt.plot(curve[args.exposure], curve[scale], color='#005f73', lw=2.5)
    plt.fill_between(curve[args.exposure], curve['lcl'], curve['ucl'], color='#94d2bd', alpha=0.35)
    plt.xlabel(args.exposure)
    plt.ylabel(scale)
    plt.title(f'Nonlinear Spline Effect: {args.exposure} -> {args.outcome}')
    plt.tight_layout()
    out_png = Path(args.out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png)
    plt.close()

    print(f'Spline table: {out_csv}')
    print(f'Spline plot: {out_png}')


if __name__ == '__main__':
    main()
