#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import warnings
import pandas as pd
from lifelines import KaplanMeierFitter, CoxPHFitter
import matplotlib.pyplot as plt

from lib.plot_style import apply_pub_style

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--time', required=True)
    p.add_argument('--event', required=True)
    p.add_argument('--exposure', required=True)
    p.add_argument('--covars', default='')
    p.add_argument('--out_km', default=str(ROOT / 'outputs/figures/km_curve.png'))
    p.add_argument('--out_cox', default=str(ROOT / 'outputs/tables/cox_summary.csv'))
    return p.parse_args()


def read_df(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == '.csv':
        return pd.read_csv(path)
    if path.suffix.lower() in {'.parquet', '.pq'}:
        return pd.read_parquet(path)
    raise ValueError('Unsupported format')


def main() -> None:
    warnings.filterwarnings('ignore', category=FutureWarning)
    args = parse_args()
    covars = [x.strip() for x in args.covars.split(',') if x.strip()]
    req = [args.time, args.event, args.exposure] + covars

    df = read_df(Path(args.input))[req].dropna().copy()

    apply_pub_style()
    kmf = KaplanMeierFitter()
    plt.figure(figsize=(8.2, 5.2))
    groups = sorted(df[args.exposure].unique().tolist())
    for g in groups:
        d = df[df[args.exposure] == g]
        if len(d) < 20:
            continue
        kmf.fit(d[args.time], d[args.event], label=f'{args.exposure}={g}')
        kmf.plot_survival_function(ci_show=False)
    plt.title('Kaplan-Meier Survival Curve')
    plt.xlabel('Follow-up Time')
    plt.ylabel('Survival Probability')
    plt.tight_layout()
    out_km = Path(args.out_km)
    out_km.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_km)
    plt.close()

    cph = CoxPHFitter()
    cph.fit(df[[args.time, args.event, args.exposure] + covars], duration_col=args.time, event_col=args.event)
    tab = cph.summary.reset_index().rename(columns={'index': 'term'})
    out_cox = Path(args.out_cox)
    out_cox.parent.mkdir(parents=True, exist_ok=True)
    tab.to_csv(out_cox, index=False)

    print(f'KM curve: {out_km}')
    print(f'Cox summary: {out_cox}')


if __name__ == '__main__':
    main()
