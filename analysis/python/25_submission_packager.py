#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
from datetime import date

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--project', default='study_submission')
    p.add_argument('--manuscript_md', default=str(ROOT / 'outputs/manuscript/draft_manuscript.md'))
    p.add_argument('--refs_md', default=str(ROOT / 'outputs/references/lancet_references_numbered.md'))
    p.add_argument('--intro_md', default=str(ROOT / 'outputs/references/lancet_intro_numbered.md'))
    p.add_argument('--outdir', default=str(ROOT / 'outputs/submissions'))
    return p.parse_args()


def copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> None:
    args = parse_args()
    stamp = date.today().isoformat()
    pkg = Path(args.outdir) / f"{args.project}_{stamp}"
    pkg.mkdir(parents=True, exist_ok=True)

    copy_if_exists(Path(args.manuscript_md), pkg / '01_manuscript.md')
    copy_if_exists(Path(args.refs_md), pkg / '02_references_numbered.md')
    copy_if_exists(Path(args.intro_md), pkg / '03_intro_numbered.md')

    # Common deliverables if available
    copy_if_exists(ROOT / 'outputs/manuscript/draft_manuscript.docx', pkg / '04_manuscript.docx')
    copy_if_exists(ROOT / 'outputs/references/pubmed_references_advanced.csv', pkg / '05_reference_master.csv')
    copy_if_exists(ROOT / 'outputs/tables/model_primary.csv', pkg / '06_model_primary.csv')
    copy_if_exists(ROOT / 'outputs/figures/forest_primary.png', pkg / '07_forest_primary.png')

    checklist = pkg / 'SUBMISSION_CHECKLIST.md'
    checklist.write_text(
        "\n".join([
            '# Submission Checklist',
            '',
            '- [ ] Manuscript final language pass completed',
            '- [ ] Reporting guideline checklist attached (STROBE/RECORD/GATHER/TRIPOD as applicable)',
            '- [ ] Ethics approval and consent statements verified',
            '- [ ] Conflict of interest statement included',
            '- [ ] Data sharing statement included',
            '- [ ] Funding and role of funder statement included',
            '- [ ] Figure/table numbering cross-checked',
            '- [ ] Reference numbering cross-checked with text citations',
        ]),
        encoding='utf-8',
    )

    print(f'Submission package: {pkg}')


if __name__ == '__main__':
    main()
