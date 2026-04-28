#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import pandas as pd

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True, help='CSV or Parquet file path')
    p.add_argument('--out_md', default=str(ROOT / 'outputs' / 'tables' / 'data_quality_report.md'))
    return p.parse_args()


def read_df(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == '.csv':
        return pd.read_csv(path)
    if path.suffix.lower() in {'.parquet', '.pq'}:
        return pd.read_parquet(path)
    raise ValueError(f'Unsupported format: {path.suffix}')


def main() -> None:
    args = parse_args()
    p = Path(args.input)
    df = read_df(p)

    missing = df.isna().mean().sort_values(ascending=False)
    n_dups = int(df.duplicated().sum())

    lines = []
    lines.append('# Data Quality Report')
    lines.append('')
    lines.append(f'- File: `{p}`')
    lines.append(f'- Rows: `{len(df)}`')
    lines.append(f'- Columns: `{df.shape[1]}`')
    lines.append(f'- Duplicates (full-row): `{n_dups}`')
    lines.append('')
    lines.append('## Missingness (Top 30)')
    lines.append('')
    lines.append('| column | missing_rate |')
    lines.append('|---|---:|')
    for c, r in missing.head(30).items():
        lines.append(f'| {c} | {r:.4f} |')

    out = Path(args.out_md)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Quality report written: {out}')


if __name__ == '__main__':
    main()
