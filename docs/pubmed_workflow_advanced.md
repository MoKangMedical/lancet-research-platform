# Advanced PubMed Workflow

## Capabilities
- Topic grouping (exposure/outcome/methods/aging/validation)
- Recent-5-year filter
- High-impact-journal subset
- Auto-generated intro literature draft

## Run
```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
python /Users/apple/Documents/lancet-research-platform/analysis/python/21_pubmed_lit_review_pipeline.py \
  --query "(NHANES OR MIMIC OR GBD) AND (mortality OR cardiovascular)" \
  --retmax 80 \
  --project_name "Your Study Title" \
  --outdir /Users/apple/Documents/lancet-research-platform/outputs/references
```

## Outputs
- `pubmed_references_advanced.csv` (master)
- `pubmed_recent5y.csv`
- `pubmed_high_impact.csv`
- `pubmed_grouped.json`
- `intro_lit_review_draft.md`
