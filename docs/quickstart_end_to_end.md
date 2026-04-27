# End-to-End Quickstart

```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
cd /Users/apple/Documents/lancet-research-platform

# 1) Environment check
make env-check

# 2) Data catalog
make catalog

# 3) Data quality + EDA
make quality INPUT=/absolute/path/your_analysis_dataset.csv
make eda INPUT=/absolute/path/your_analysis_dataset.csv

# 4) Primary model + forest
make model INPUT=/absolute/path/your_analysis_dataset.csv OUTCOME=death EXPOSURE=exposure_var COVARS=age,sex,bmi
make forest
make subgroup INPUT=/absolute/path/your_analysis_dataset.csv OUTCOME=death EXPOSURE=exposure_var SUBGROUP=sex COVARS=age,bmi
make spline INPUT=/absolute/path/your_analysis_dataset.csv OUTCOME=death EXPOSURE=bmi COVARS=age,sex DFSPLINE=4
make gbd-map INPUT=/absolute/path/gbd.csv VALUE=val LOCATION=location_name FACET=year TITLE='GBD Global Map'

# 5) Literature and numbered intro
make refs QUERY='(NHANES OR MIMIC) AND (mortality)' PROJECT='Your Study'
make lancet-intro PROJECT='Your Study'

# 6) Manuscript skeleton
make manuscript
```
