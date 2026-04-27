# PubMed Real-Reference Workflow

## Goal
Generate verifiable references from PubMed with PMID and DOI where available.

## Command
```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
python /Users/apple/Documents/lancet-research-platform/analysis/python/20_pubmed_real_refs.py \
  --query "(NHANES) AND (all-cause mortality)" \
  --retmax 30 \
  --outdir /Users/apple/Documents/lancet-research-platform/outputs/references
```

## Outputs
- `pubmed_references.csv`
- `pubmed_references.json`
- `pubmed_references.bib`

## Notes
- Every record is tied to a PubMed URL via PMID.
- DOI is parsed from PubMed first; if missing, it tries Crossref title matching.
- Use the `.bib` file directly in manuscript reference managers.
