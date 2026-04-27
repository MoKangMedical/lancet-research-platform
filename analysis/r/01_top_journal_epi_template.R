# Top-journal epidemiology analysis template (R)

suppressPackageStartupMessages({
  library(dplyr)
  library(survey)
  library(survival)
  library(MatchIt)
  library(gtsummary)
})

# 1) Complex survey design example (NHANES-like)
# dsgn <- svydesign(ids = ~psu, strata = ~strata, weights = ~wt, nest = TRUE, data = df)
# fit_svy <- svyglm(outcome ~ exposure + age + sex, design = dsgn, family = quasibinomial())

# 2) Propensity score matching / weighting
# m.out <- matchit(exposure ~ age + sex + bmi + smoke, data = df, method = "nearest")
# mdat <- match.data(m.out)

# 3) Survival model
# fit_cox <- coxph(Surv(fu_time, event) ~ exposure + age + sex, data = df)

# 4) Table 1
# tbl1 <- tbl_summary(df, by = exposure)

cat("Template loaded. Replace placeholder variables with your study variables.\n")
