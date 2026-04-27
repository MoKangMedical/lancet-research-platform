# Full Capability Map

## 1. Data Foundation
- Raw/bronze/silver/gold layered data directories
- Data catalog generation (`10_data_catalog.py`)
- Data quality reporting (`11_data_quality_report.py`)

## 2. Exploratory Analysis and Visualization
- Automated EDA figure generation (`12_auto_eda.py`)
- Forest plot generation from model output (`31_forest_from_model.py`)
- Subgroup effect forest plot (`32_subgroup_forest.py`)
- Nonlinear spline effect curve (`33_spline_effect_plot.py`)
- Survival plotting and Cox output (`34_survival_km_cox.py`)
- GBD choropleth world map with static export (`35_gbd_choropleth_map.py`)

## 3. Statistical Modeling
- Primary regression pipeline (`30_run_analysis_pipeline.py`)
- Epidemiology templates in Python and R
- Survey, survival, and causal packages preinstalled

## 4. Literature Engine
- Real PubMed references with PMID/DOI (`20`, `21`)
- Topic grouping + recent-5y + high-impact filters (`21`)
- Lancet-style numbered intro and references (`22`)

## 5. Writing System
- Abstract/main text/cover letter templates
- Manuscript skeleton + pandoc DOCX export

## 6. Unified Orchestration
- Single CLI: `analysis/python/99_research_cli.py`
- Make targets via `Makefile`

## 7. Outputs
- `outputs/figures/`
- `outputs/tables/`
- `outputs/references/`
- `outputs/manuscript/`
