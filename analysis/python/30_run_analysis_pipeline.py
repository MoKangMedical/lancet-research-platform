#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
import statsmodels.api as sm

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--out_table', default=str(ROOT / 'outputs' / 'tables' / 'model_primary.csv'))
    p.add_argument('--out_summary', default=str(ROOT / 'outputs' / 'tables' / 'model_primary_summary.txt'))
    p.add_argument('--outcome', required=True)
    p.add_argument('--exposure', required=True)
    p.add_argument('--covars', default='')
    return p.parse_args()


def read_df(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == '.csv':
        return pd.read_csv(path)
    if path.suffix.lower() in {'.parquet', '.pq'}:
        return pd.read_parquet(path)
    raise ValueError('Unsupported input format')


def main() -> None:
    args = parse_args()
    df = read_df(Path(args.input)).copy()

    covars = [x.strip() for x in args.covars.split(',') if x.strip()]
    cols = [args.outcome, args.exposure] + covars
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise ValueError(f'Missing columns: {miss}')

    dat = df[cols].dropna()
    y = dat[args.outcome]
    X = sm.add_constant(dat[[args.exposure] + covars], has_constant='add')

    # Choose model family by binary outcome heuristic.
    uniq = sorted(y.unique().tolist())
    if uniq in ([0, 1], [0], [1]):
        fit = sm.GLM(y, X, family=sm.families.Binomial()).fit(cov_type='HC3')
    else:
        fit = sm.OLS(y, X).fit(cov_type='HC3')

    tab = pd.DataFrame({'term': fit.params.index, 'coef': fit.params.values, 'se': fit.bse.values, 'p': fit.pvalues.values})

    out_table = Path(args.out_table)
    out_table.parent.mkdir(parents=True, exist_ok=True)
    tab.to_csv(out_table, index=False)

    out_summary = Path(args.out_summary)
    out_summary.write_text(str(fit.summary()), encoding='utf-8')

    print(f'Model table: {out_table}')
    print(f'Model summary: {out_summary}')


if __name__ == '__main__':
    main()
