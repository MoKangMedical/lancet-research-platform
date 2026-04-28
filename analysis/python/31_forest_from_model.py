#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--model_csv', default=str(ROOT / 'outputs' / 'tables' / 'model_primary.csv'))
    p.add_argument('--out_png', default=str(ROOT / 'outputs' / 'figures' / 'forest_primary.png'))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.model_csv)
    df = df[df['term'] != 'const'].copy()
    if df.empty:
        raise ValueError('No non-intercept terms to plot.')

    df.loc[:, 'lcl'] = df['coef'] - 1.96 * df['se']
    df.loc[:, 'ucl'] = df['coef'] + 1.96 * df['se']

    y = np.arange(len(df))
    plt.figure(figsize=(8, max(4, len(df) * 0.45)))
    plt.hlines(y, df['lcl'], df['ucl'], color='gray')
    plt.plot(df['coef'], y, 'o', color='#1f77b4')
    plt.axvline(0, color='red', linestyle='--', linewidth=1)
    plt.yticks(y, df['term'])
    plt.xlabel('Coefficient (95% CI)')
    plt.title('Primary Model Forest Plot')
    plt.tight_layout()

    out = Path(args.out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=220)
    plt.close()
    print(f'Forest plot: {out}')


if __name__ == '__main__':
    main()
