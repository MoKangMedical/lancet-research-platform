VENV_PY=/Users/apple/Documents/.venvs/data-analytics/bin/python
ROOT=/Users/apple/Documents/lancet-research-platform
CLI=$(ROOT)/analysis/python/99_research_cli.py

.PHONY: env-check catalog quality eda model forest subgroup spline survival gbd-map gbd-download gbd-unpack gbd-starter gbd-dirf-parse gbd-template gbd-results-export gbd-asthma-u40-analysis gbd-asthma-u40-phase3 gbd-asthma-u40-phase4 gbd-asthma-u40-phase5 gbd-asthma-u40-qc refs lancet-intro audit package manuscript ukb-dr-build ukb-dr-analyze ukb-dr-qc ukb-ckd-stroke-build ukb-ckd-stroke-analyze all

env-check:
	@$(VENV_PY) $(ROOT)/analysis/python/00_env_check.py
	@Rscript $(ROOT)/analysis/r/00_env_check.R

catalog:
	@$(VENV_PY) $(CLI) catalog

quality:
	@echo "Usage: make quality INPUT=/abs/path/data.csv"
	@$(VENV_PY) $(CLI) quality --input $(INPUT)

eda:
	@echo "Usage: make eda INPUT=/abs/path/data.csv"
	@$(VENV_PY) $(CLI) eda --input $(INPUT)

model:
	@echo "Usage: make model INPUT=... OUTCOME=... EXPOSURE=... COVARS=age,sex,bmi"
	@$(VENV_PY) $(CLI) model --input $(INPUT) --outcome $(OUTCOME) --exposure $(EXPOSURE) --covars $(COVARS)

forest:
	@$(VENV_PY) $(CLI) forest

subgroup:
	@echo "Usage: make subgroup INPUT=... OUTCOME=... EXPOSURE=... SUBGROUP=sex COVARS=age,bmi"
	@$(VENV_PY) $(CLI) subgroup --input $(INPUT) --outcome $(OUTCOME) --exposure $(EXPOSURE) --subgroup $(SUBGROUP) --covars $(COVARS)

spline:
	@echo "Usage: make spline INPUT=... OUTCOME=... EXPOSURE=bmi COVARS=age,sex DFSPLINE=4"
	@$(VENV_PY) $(CLI) spline --input $(INPUT) --outcome $(OUTCOME) --exposure $(EXPOSURE) --covars $(COVARS) --df_spline $(DFSPLINE)

survival:
	@echo "Usage: make survival INPUT=... TIME=followup EVENT=death EXPOSURE=exposure_var COVARS=age,sex,bmi"
	@$(VENV_PY) $(CLI) survival --input $(INPUT) --time $(TIME) --event $(EVENT) --exposure $(EXPOSURE) --covars $(COVARS)

gbd-map:
	@echo "Usage: make gbd-map INPUT=... VALUE=val LOCATION=location_name FACET=year TITLE='GBD Map'"
	@$(VENV_PY) $(CLI) gbd-map --input "$(INPUT)" --value_col "$(VALUE)" --location_col "$(LOCATION)" --iso3_col "$(ISO3)" --facet_col "$(FACET)" --title "$(TITLE)" --color_scale "$(SCALE)"

gbd-download:
	@echo "Usage: make gbd-download PRESET=gbd2023-core-1990-2023 LIST_ONLY=1"
	@$(VENV_PY) $(CLI) gbd-download --preset "$(if $(PRESET),$(PRESET),gbd2023-core-1990-2023)" $(foreach r,$(RECORD),--record "$(r)") $(foreach p,$(FILENAME_PATTERN),--filename_pattern "$(p)") $(foreach p,$(LABEL_PATTERN),--label_pattern "$(p)") $(if $(RECORD_URL),--record_url "$(RECORD_URL)",) $(if $(RECORD_HTML),--record_html "$(RECORD_HTML)",) --dest "$(if $(DEST),$(DEST),$(ROOT)/data/raw/gbd)" --year_span "$(if $(YEAR_SPAN),$(YEAR_SPAN),1990-2023)" $(if $(LIST_ONLY),--list_only,) $(if $(MANIFEST_OUT),--manifest_out "$(MANIFEST_OUT)",) $(if $(COOKIE_HEADER),--cookie_header "$(COOKIE_HEADER)",) $(if $(COOKIE_FILE),--cookie_file "$(COOKIE_FILE)",) $(if $(SAVE_HTML),--save_html,) $(if $(FORCE),--force,) --timeout "$(if $(TIMEOUT),$(TIMEOUT),60)"

gbd-unpack:
	@echo "Usage: make gbd-unpack INPUT_ROOT=$(ROOT)/data/raw/gbd"
	@$(VENV_PY) $(CLI) gbd-unpack --input_root "$(if $(INPUT_ROOT),$(INPUT_ROOT),$(ROOT)/data/raw/gbd)" --dest_root "$(if $(DEST_ROOT),$(DEST_ROOT),$(ROOT)/data/bronze/gbd/gbd2023)" --catalog_out "$(if $(CATALOG_OUT),$(CATALOG_OUT),$(ROOT)/outputs/tables/gbd2023_extracted_catalog.csv)" --summary_out "$(if $(SUMMARY_OUT),$(SUMMARY_OUT),$(ROOT)/outputs/tables/gbd2023_extracted_summary.json)" $(if $(FORCE),--force,)

gbd-starter:
	@echo "Usage: make gbd-starter BRONZE_ROOT=$(ROOT)/data/bronze/gbd/gbd2023"
	@$(VENV_PY) $(CLI) gbd-starter --bronze_root "$(if $(BRONZE_ROOT),$(BRONZE_ROOT),$(ROOT)/data/bronze/gbd/gbd2023)" --silver_root "$(if $(SILVER_ROOT),$(SILVER_ROOT),$(ROOT)/data/silver/gbd)" --notebook_out "$(if $(NOTEBOOK_OUT),$(NOTEBOOK_OUT),$(ROOT)/notebooks/gbd2023_starter_analysis.ipynb)" --qc_out "$(if $(QC_OUT),$(QC_OUT),$(ROOT)/outputs/tables/gbd2023_starter_qc.json)" $(if $(FORCE),--force,)

gbd-dirf-parse:
	@echo "Usage: make gbd-dirf-parse DIRF_ROOT=$(ROOT)/data/bronze/gbd/gbd2023/dirf-2023"
	@$(VENV_PY) $(CLI) gbd-dirf-parse --dirf_root "$(if $(DIRF_ROOT),$(DIRF_ROOT),$(ROOT)/data/bronze/gbd/gbd2023/dirf-2023)" --out_csv "$(if $(OUT_CSV),$(OUT_CSV),$(ROOT)/data/silver/gbd/gbd2023_dirf_global_core_tidy.csv)" --qc_out "$(if $(QC_OUT),$(QC_OUT),$(ROOT)/outputs/tables/gbd2023_dirf_global_core_qc.json)"

gbd-template:
	@echo "Usage: make gbd-template INPUT=... MEASURE=DALY METRIC=age_standardized_rate SEX=Both YEAR=2023"
	@$(VENV_PY) $(CLI) gbd-template --input "$(INPUT)" --measure "$(MEASURE)" --metric "$(METRIC)" --sex "$(SEX)" --location "$(LOCATION)" --summary_year "$(if $(YEAR),$(YEAR),2023)" --top_n "$(if $(TOP_N),$(TOP_N),12)" --value_col "$(if $(VALUE_COL),$(VALUE_COL),mean)" --year_col "$(if $(YEAR_COL),$(YEAR_COL),year_id)" --measure_col "$(if $(MEASURE_COL),$(MEASURE_COL),measure)" --metric_col "$(if $(METRIC_COL),$(METRIC_COL),metric)" --sex_col "$(if $(SEX_COL),$(SEX_COL),sex)" --location_col "$(if $(LOCATION_COL),$(LOCATION_COL),location_name)" --cause_col "$(if $(CAUSE_COL),$(CAUSE_COL),cause_name)" --lower_col "$(if $(LOWER_COL),$(LOWER_COL),lower)" --upper_col "$(if $(UPPER_COL),$(UPPER_COL),upper)" $(foreach p,$(CAUSE_PATTERN),--cause_pattern "$(p)") $(if $(MAP_CAUSE),--map_cause "$(MAP_CAUSE)",) $(if $(OUT_PREFIX),--out_prefix "$(OUT_PREFIX)",)

gbd-results-export:
	@echo "Usage: make gbd-results-export SPEC=/abs/path/spec.json PACKAGE=all"
	@$(VENV_PY) $(CLI) gbd-results-export --spec "$(SPEC)" --package "$(if $(PACKAGE),$(PACKAGE),all)" $(if $(STORAGE_STATE),--storage_state "$(STORAGE_STATE)",) $(if $(FORCE_LOGIN),--force_login,)

gbd-asthma-u40-analysis:
	@echo "Usage: make gbd-asthma-u40-analysis STUDY_ROOT=/abs/path/study"
	@$(VENV_PY) $(CLI) gbd-asthma-u40-analysis --study_root "$(STUDY_ROOT)"

gbd-asthma-u40-phase3:
	@echo "Usage: make gbd-asthma-u40-phase3 STUDY_ROOT=/abs/path/study"
	@$(VENV_PY) $(CLI) gbd-asthma-u40-phase3 --study_root "$(STUDY_ROOT)"

gbd-asthma-u40-phase4:
	@echo "Usage: make gbd-asthma-u40-phase4 STUDY_ROOT=/abs/path/study"
	@$(VENV_PY) $(CLI) gbd-asthma-u40-phase4 --study_root "$(STUDY_ROOT)"

gbd-asthma-u40-phase5:
	@echo "Usage: make gbd-asthma-u40-phase5 STUDY_ROOT=/abs/path/study"
	@$(VENV_PY) $(CLI) gbd-asthma-u40-phase5 --study_root "$(STUDY_ROOT)"

gbd-asthma-u40-qc:
	@echo "Usage: make gbd-asthma-u40-qc STUDY_ROOT=/abs/path/study"
	@$(VENV_PY) $(CLI) gbd-asthma-u40-qc --study_root "$(STUDY_ROOT)"

refs:
	@echo "Usage: make refs QUERY='(NHANES) AND (mortality)' PROJECT='Study name'"
	@$(VENV_PY) $(CLI) refs --query "$(QUERY)" --project_name "$(PROJECT)"

lancet-intro:
	@echo "Usage: make lancet-intro PROJECT='Study name'"
	@$(VENV_PY) $(CLI) lancet-intro --project_name "$(PROJECT)"

audit:
	@echo "Usage: make audit MANUSCRIPT=/abs/path/file.md DESIGN=cohort DATA_TYPE=standard"
	@$(VENV_PY) $(CLI) audit --manuscript "$(MANUSCRIPT)" --design "$(DESIGN)" --data_type "$(DATA_TYPE)"

package:
	@echo "Usage: make package PROJECT='submission_name'"
	@$(VENV_PY) $(CLI) package --project_name "$(PROJECT)"

ukb-dr-build:
	@echo "Usage: make ukb-dr-build INPUT=/abs/path/ukb.csv"
	@$(VENV_PY) $(CLI) ukb-dr-build --input "$(INPUT)" --out_csv "$(OUT_CSV)" --out_qc "$(OUT_QC)" --chunksize "$(CHUNKSIZE)" --admin_censor_date "$(ADMIN_CENSOR_DATE)"

ukb-dr-analyze:
	@echo "Usage: make ukb-dr-analyze INPUT=/abs/path/ukb_dr_t2d_analysis.csv"
	@$(VENV_PY) $(CLI) ukb-dr-analyze --input "$(INPUT)" --outdir "$(OUTDIR)"

ukb-dr-qc:
	@echo "Usage: make ukb-dr-qc INPUT=/abs/path/ukb_dr_t2d_analysis.csv"
	@$(VENV_PY) $(CLI) ukb-dr-qc --ukb_input "$(if $(INPUT),$(INPUT),$(ROOT)/data/gold/ukb_dr_t2d_analysis.csv)" --ukb_results_dir "$(if $(OUTDIR),$(OUTDIR),$(ROOT)/outputs/ukb_dr_t2d)" --gbd_qc_json "$(if $(GBD_QC_JSON),$(GBD_QC_JSON),$(ROOT)/outputs/tables/gbd2023_starter_qc.json)" --out_md "$(if $(OUT_MD),$(OUT_MD),$(ROOT)/outputs/tables/dr_t2d_project_qc_report.md)" --out_json "$(if $(OUT_JSON),$(OUT_JSON),$(ROOT)/outputs/tables/dr_t2d_project_qc_report.json)"

ukb-ckd-stroke-build:
	@echo "Usage: make ukb-ckd-stroke-build INPUT=/abs/path/ukb.csv"
	@$(VENV_PY) $(CLI) ukb-ckd-stroke-build --input "$(INPUT)" --out_csv "$(OUT_CSV)" --out_qc "$(OUT_QC)" --chunksize "$(CHUNKSIZE)" --admin_censor_date "$(ADMIN_CENSOR_DATE)"

ukb-ckd-stroke-analyze:
	@echo "Usage: make ukb-ckd-stroke-analyze INPUT=/abs/path/ukb_ckd_stroke_analysis.csv"
	@$(VENV_PY) $(CLI) ukb-ckd-stroke-analyze --input "$(INPUT)" --outdir "$(OUTDIR)"

manuscript:
	@$(VENV_PY) $(ROOT)/analysis/python/90_build_manuscript_skeleton.py
	@pandoc $(ROOT)/outputs/manuscript/draft_manuscript.md -o $(ROOT)/outputs/manuscript/draft_manuscript.docx

all:
	@echo "Run selected targets with required args (quality/eda/model/refs need params)."
