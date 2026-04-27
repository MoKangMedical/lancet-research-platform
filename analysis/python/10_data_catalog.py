#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import pandas as pd

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--raw_dir', default=str(ROOT / 'data'))
    p.add_argument('--out_csv', default=str(ROOT / 'outputs' / 'tables' / 'data_catalog.csv'))
    return p.parse_args()


def count_rows(path: Path) -> int | None:
    suf = path.suffix.lower()
    try:
        if suf == '.csv':
            return sum(1 for _ in path.open('r', encoding='utf-8', errors='ignore')) - 1
        if suf in {'.parquet', '.pq'}:
            return len(pd.read_parquet(path))
        if suf in {'.xlsx', '.xls'}:
            return len(pd.read_excel(path, nrows=2000000))
    except Exception:
        return None
    return None


def main() -> None:
    args = parse_args()
    raw = Path(args.raw_dir)
    rows = []
    for p in sorted(raw.rglob('*')):
        if p.is_file():
            rows.append({
                'path': str(p),
                'size_mb': round(p.stat().st_size / 1024 / 1024, 3),
                'suffix': p.suffix.lower(),
                'row_count_est': count_rows(p),
            })
    out = Path(args.out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f'Catalog written: {out} ({len(rows)} files)')


if __name__ == '__main__':
    main()
