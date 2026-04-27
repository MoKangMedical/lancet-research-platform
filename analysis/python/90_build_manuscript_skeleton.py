from pathlib import Path
from datetime import date

base = Path('/Users/apple/Documents/lancet-research-platform/outputs/manuscript')
base.mkdir(parents=True, exist_ok=True)

out = base / 'draft_manuscript.md'

content = f"""# Draft Manuscript ({date.today().isoformat()})

## Auto-imported Results Placeholders
- Figure directory: ../figures
- Table directory: ../tables

## Writing Checklist
- [ ] Title and key message finalized
- [ ] Abstract aligned with primary model
- [ ] Methods exactly reproducible from code
- [ ] Results consistent with tables/figures
- [ ] Limitations and bias discussion complete
- [ ] Data sharing and ethics statements complete

## Inserted Sections

### Abstract
(Use template 01)

### Main Text
(Use template 02)

### Cover Letter Notes
(Use template 03)
"""

out.write_text(content, encoding='utf-8')
print(f'Wrote: {out}')
