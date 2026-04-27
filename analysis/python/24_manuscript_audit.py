#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import yaml

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--manuscript', required=True, help='Markdown manuscript path')
    p.add_argument('--design', default='cohort', help='cohort/cross_sectional/case_control/prediction_model/gbd/...')
    p.add_argument('--data_type', default='standard', help='standard/routinely_collected_data/health_estimates')
    p.add_argument('--out', default=str(ROOT / 'outputs' / 'manuscript' / 'manuscript_audit.md'))
    return p.parse_args()


def load_cfg() -> dict:
    cfg = ROOT / 'configs' / 'reporting_guidelines.yaml'
    return yaml.safe_load(cfg.read_text(encoding='utf-8'))


def active_guidelines(cfg: dict, design: str, data_type: str) -> list[tuple[str, dict]]:
    out = []
    for name, body in cfg['guidelines'].items():
        applies = set(body.get('applies_to', []))
        if 'all' in applies or design in applies or data_type in applies:
            out.append((name, body))
    return out


def main() -> None:
    args = parse_args()
    text = Path(args.manuscript).read_text(encoding='utf-8').lower()
    cfg = load_cfg()

    acts = active_guidelines(cfg, args.design, args.data_type)

    lines = []
    lines.append('# Manuscript Audit Report')
    lines.append('')
    lines.append(f'- Manuscript: `{args.manuscript}`')
    lines.append(f'- Design: `{args.design}`')
    lines.append(f'- Data Type: `{args.data_type}`')
    lines.append('')

    total_req = 0
    total_hit = 0

    for gname, g in acts:
        reqs = g.get('required_keywords', [])
        hits = [kw for kw in reqs if kw.lower() in text]
        misses = [kw for kw in reqs if kw.lower() not in text]
        total_req += len(reqs)
        total_hit += len(hits)

        lines.append(f'## {gname.upper()}')
        lines.append(f'- Coverage: `{len(hits)}/{len(reqs)}`')
        if misses:
            lines.append('- Missing items:')
            for m in misses:
                lines.append(f'  - {m}')
        else:
            lines.append('- Missing items: none')
        lines.append('')

    score = 100.0 * total_hit / total_req if total_req else 0.0
    lines.insert(4, f'- Overall keyword coverage score: `{score:.1f}%`')

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Audit report: {out}')
    print(f'Overall score: {score:.1f}%')


if __name__ == '__main__':
    main()
