# Lancet Research Platform

A complete local research operating system for top-tier epidemiology studies (NHANES, MIMIC, GBD, global aging).

## Core Capabilities
- Data architecture: `raw -> bronze -> silver -> gold`
- Data catalog and quality diagnostics
- Automated EDA and publication-oriented figures
- Advanced plotting: subgroup forest, spline effect, KM survival curve, GBD choropleth map
- Auth-aware GBD 2023 downloader for official 1990-2023 GHDx files
- Post-download GBD 2023 unpacking, starter dataset build, and starter notebook generation
- DIRF appendix parser for prevalence, incidence, DALY, YLD, and YLL plus reusable figure/table templates
- Regression/survival/causal-method templates
- PubMed real-reference engine (PMID/DOI verified)
- Lancet-style numbered introduction + references
- Reporting-guideline manuscript audit (STROBE/RECORD/GATHER/TRIPOD/ICMJE/Lancet-core)
- Submission package auto-builder
- Manuscript skeleton and DOCX export
- Unified CLI + Makefile orchestration

## Project Structure
- `analysis/python/` scripts for data, modeling, literature, writing
- `analysis/r/` R templates for survey/survival/causal analysis
- `data/` layered data storage
- `outputs/` figures, tables, references, manuscript artifacts
- `docs/` protocol, methods, and workflows
- `sql/templates/` reusable SQL templates

## Environment
```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
cd /Users/apple/Documents/lancet-research-platform
```

## One-Command Entry Points
```bash
make env-check
make catalog
make quality INPUT=/absolute/path/data.csv
make eda INPUT=/absolute/path/data.csv
make model INPUT=/absolute/path/data.csv OUTCOME=death EXPOSURE=exposure_var COVARS=age,sex,bmi
make forest
make subgroup INPUT=/absolute/path/data.csv OUTCOME=death EXPOSURE=exposure_var SUBGROUP=sex COVARS=age,bmi
make spline INPUT=/absolute/path/data.csv OUTCOME=death EXPOSURE=bmi COVARS=age,sex,exposure_var DFSPLINE=4
make survival INPUT=/absolute/path/data.csv TIME=followup EVENT=event EXPOSURE=exposure_var COVARS=age,sex,bmi
make gbd-map INPUT=/absolute/path/gbd.csv VALUE=val LOCATION=location_name FACET=year TITLE='GBD Global Map'
make gbd-download PRESET=gbd2023-core-1990-2023 LIST_ONLY=1
make gbd-unpack
make gbd-starter
make gbd-dirf-parse
make gbd-template INPUT=/absolute/path/gbd_tidy.csv MEASURE=DALY METRIC=age_standardized_rate SEX=Both YEAR=2023
make refs QUERY='(NHANES OR MIMIC) AND (mortality)' PROJECT='Your Study'
make lancet-intro PROJECT='Your Study'
make audit MANUSCRIPT=/absolute/path/manuscript.md DESIGN=cohort DATA_TYPE=standard
make package PROJECT='YourStudySubmission'
make manuscript
```

## Unified CLI
```bash
python /Users/apple/Documents/lancet-research-platform/analysis/python/99_research_cli.py --help
```

## Key Workflows
- End-to-end execution: `docs/quickstart_end_to_end.md`
- Full capability map: `docs/full_capability_map.md`
- GBD mapping workflow: `docs/gbd_mapping_workflow.md`
- GBD download workflow: `docs/gbd_download_workflow.md`
- GBD starter workflow: `docs/gbd_starter_workflow.md`
- GBD DIRF workflow: `docs/gbd_dirf_workflow.md`
- PubMed advanced workflow: `docs/pubmed_workflow_advanced.md`
- Lancet numbering workflow: `docs/lancet_reference_workflow.md`
- Standards and sources: `docs/top_epi_paper_standards_and_sources.md`

## Notes
- Quarto CLI is optional; current writing path uses Pandoc and is already functional.
- For database-backed pipelines (PostgreSQL/DuckDB), keep credentials outside git and use local env vars.
