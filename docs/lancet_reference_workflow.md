# Lancet-Style Numbered Reference Workflow

## Step 1: Build/refresh PubMed advanced dataset
```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
python /Users/apple/Documents/lancet-research-platform/analysis/python/21_pubmed_lit_review_pipeline.py \
  --query "(NHANES OR MIMIC OR GBD) AND (mortality OR cardiovascular)" \
  --retmax 120 \
  --project_name "Your Study" \
  --outdir /Users/apple/Documents/lancet-research-platform/outputs/references
```

## Step 2: Generate Lancet-style numbered intro + references
```bash
python /Users/apple/Documents/lancet-research-platform/analysis/python/22_build_lancet_intro_refs.py \
  --in_csv /Users/apple/Documents/lancet-research-platform/outputs/references/pubmed_references_advanced.csv \
  --outdir /Users/apple/Documents/lancet-research-platform/outputs/references \
  --project_name "Your Study" \
  --max_refs 30
```

## Outputs
- `lancet_intro_numbered.md`
- `lancet_references_numbered.md`
- `lancet_citations_map.csv`
