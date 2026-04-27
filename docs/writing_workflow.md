# Writing Workflow (Pandoc-first)

1. Update analysis outputs in `outputs/figures` and `outputs/tables`.
2. Run manuscript skeleton builder:
   - `source /Users/apple/Documents/.venvs/data-analytics/bin/activate`
   - `python /Users/apple/Documents/lancet-research-platform/analysis/python/90_build_manuscript_skeleton.py`
3. Fill templates in `outputs/manuscript/templates/`.
4. Merge into `outputs/manuscript/draft_manuscript.md`.
5. Export with pandoc:
   - `pandoc outputs/manuscript/draft_manuscript.md -o outputs/manuscript/draft_manuscript.docx`
   - `pandoc outputs/manuscript/draft_manuscript.md -o outputs/manuscript/draft_manuscript.html`

If Quarto CLI is installed later, migrate to `.qmd` for cross-reference and journal rendering.
