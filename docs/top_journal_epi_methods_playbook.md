# Top-Journal Epidemiology Methods Playbook

## A. Study Design (before modeling)
- Protocol and SAP pre-specification
- DAG-driven covariate set definition
- Target trial emulation for observational designs
- Explicit bias map: selection, information, confounding

## B. Core Analyses
- Descriptive epidemiology + standardized Table 1
- Weighted analyses for complex surveys (e.g., NHANES)
- Time-to-event models (Cox, competing risks)
- Hierarchical/mixed models for clustered data
- Missing data with multiple imputation (MICE)

## C. Causal Inference Layer
- Propensity score matching/weighting (IPTW, overlap weights)
- Doubly robust estimation (AIPW/TMLE where feasible)
- Sensitivity analyses: E-value, unmeasured confounding stress tests

## D. Robustness and Publication Readiness
- Prespecified subgroup and interaction analyses
- Negative/positive control outcomes or exposures
- Reproducible figure/table pipelines from code only
- Transparent model diagnostics and assumptions checks

## E. Dataset-specific notes
- NHANES: strata/PSU/weights must enter all inferential models
- MIMIC: time indexing, immortal-time bias checks, censoring strategy
- GBD/global aging: age-standardization, period/cohort consistency checks

## F. Minimal output set for high-impact submission
- Figure 1: Cohort flowchart
- Figure 2: Main effect plot (forest / spline / KM / CIF)
- Table 1: Baseline characteristics
- Table 2: Main models + sensitivity models
- Supplement: missingness, diagnostics, robustness grid
