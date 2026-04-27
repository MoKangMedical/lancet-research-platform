#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt

from lib.plot_style import apply_pub_style

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--outcome', required=True)
    p.add_argument('--exposure', required=True)
    p.add_argument('--subgroup', required=True)
    p.add_argument('--covars', default='')
    p.add_argument('--out_csv', default=str(ROOT / 'outputs/tables/subgroup_effects.csv'))
    p.add_argument('--out_png', default=str(ROOT / 'outputs/figures/subgroup_forest.png'))
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

    req = [args.outcome, args.exposure, args.subgroup] + covars
    miss = [c for c in req if c not in df.columns]
    if miss:
        raise ValueError(f'Missing columns: {miss}')

    rows = []
    for g, d in df.groupby(args.subgroup):
        dat = d[req].dropna()
        if len(dat) < 40:
            continue
        y = dat[args.outcome]
        X = sm.add_constant(dat[[args.exposure] + covars], has_constant='add')

        uniq = sorted(y.unique().tolist())
        try:
            if uniq in ([0, 1], [0], [1]):
                fit = sm.GLM(y, X, family=sm.families.Binomial()).fit(cov_type='HC3')
            else:
                fit = sm.OLS(y, X).fit(cov_type='HC3')
        except Exception:
            continue

        b = float(fit.params[args.exposure])
        se = float(fit.bse[args.exposure])
        rows.append({
            'group': str(g),
            'n': int(len(dat)),
            'coef': b,
            'lcl': b - 1.96 * se,
            'ucl': b + 1.96 * se,
            'p': float(fit.pvalues[args.exposure]),
        })

    out = pd.DataFrame(rows).sort_values('coef')
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)

    if out.empty:
        print(f'No valid subgroup result. CSV: {out_csv}')
        return

    apply_pub_style()
    y = np.arange(len(out))
    plt.figure(figsize=(8, max(4.2, 0.45 * len(out))))
    plt.hlines(y, out['lcl'], out['ucl'], color='#7f8c8d', lw=2)
    plt.scatter(out['coef'], y, color='#1f78b4', s=50, zorder=3)
    plt.axvline(0, linestyle='--', color='#c0392b', lw=1.5)
    plt.yticks(y, out['group'])
    plt.xlabel('Exposure Effect (95% CI)')
    plt.title(f'Subgroup Forest: {args.exposure} -> {args.outcome}')
    plt.tight_layout()
    out_png = Path(args.out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png)
    plt.close()

    print(f'Subgroup table: {out_csv}')
    print(f'Subgroup forest: {out_png}')


if __name__ == '__main__':
    main()
