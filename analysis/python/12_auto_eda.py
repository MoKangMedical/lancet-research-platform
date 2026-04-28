#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--outdir', default=str(ROOT / 'outputs' / 'figures' / 'eda'))
    p.add_argument('--max_num_cols', type=int, default=8)
    return p.parse_args()


def read_df(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == '.csv':
        return pd.read_csv(path)
    if path.suffix.lower() in {'.parquet', '.pq'}:
        return pd.read_parquet(path)
    raise ValueError('Unsupported input format')


def main() -> None:
    args = parse_args()
    df = read_df(Path(args.input))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    num_cols = df.select_dtypes(include='number').columns.tolist()[: args.max_num_cols]
    if num_cols:
        corr = df[num_cols].corr(numeric_only=True)
        plt.figure(figsize=(10, 8))
        sns.heatmap(corr, cmap='coolwarm', center=0)
        plt.title('Correlation Heatmap')
        plt.tight_layout()
        plt.savefig(outdir / 'corr_heatmap.png', dpi=200)
        plt.close()

        for c in num_cols[:4]:
            plt.figure(figsize=(7, 4))
            sns.histplot(df[c].dropna(), kde=True)
            plt.title(f'Distribution: {c}')
            plt.tight_layout()
            plt.savefig(outdir / f'dist_{c}.png', dpi=200)
            plt.close()

    print(f'EDA figures generated in: {outdir}')


if __name__ == '__main__':
    main()
