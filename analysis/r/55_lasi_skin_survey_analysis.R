suppressPackageStartupMessages({
  library(haven)
  library(survey)
  library(dplyr)
  library(ggplot2)
  library(jsonlite)
})

project_root <- "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-针对皮肤病的相关全球流行病和疾病负担研究方案-20分-38万-已收5万+5万"
package_root <- file.path(project_root, "lasi_skin_followup_package_20260312")
table_dir <- file.path(package_root, "outputs", "tables")
figure_dir <- file.path(package_root, "outputs", "figures")
manuscript_dir <- file.path(package_root, "outputs", "manuscript")
lasi_path <- "/Users/apple/Desktop/所有数据/global aging data数据/LASI_印度/Harmonized LASI A.3_SPSS/H_LASI_a3.sav"

dir.create(table_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(figure_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(manuscript_dir, recursive = TRUE, showWarnings = FALSE)

options(survey.lonely.psu = "adjust")

keep_binary <- function(x) ifelse(x %in% c(0, 1), x, NA_real_)

fmt_p <- function(x) {
  ifelse(is.na(x), "", ifelse(x < 0.001, "<0.001", sprintf("%.3f", x)))
}

make_design <- function(df) {
  svydesign(ids = ~hhid, strata = ~hh1state, weights = ~r1wtresp, data = df, nest = TRUE)
}

prop_row <- function(df, label) {
  if (nrow(df) == 0) {
    return(data.frame(
      Group = label,
      Unweighted_n = 0,
      Prevalence = NA_real_,
      CI_low = NA_real_,
      CI_high = NA_real_
    ))
  }
  des <- make_design(df)
  est <- suppressWarnings(svyciprop(~r1skindise, des, method = "logit", na.rm = TRUE))
  ci <- confint(est)
  data.frame(
    Group = label,
    Unweighted_n = nrow(df),
    Prevalence = as.numeric(unname(coef(est))),
    CI_low = as.numeric(ci[1]),
    CI_high = as.numeric(ci[2])
  )
}

survey_prop <- function(df, variable) {
  sub <- df[!is.na(df[[variable]]), , drop = FALSE]
  if (nrow(sub) == 0) return(NA_real_)
  des <- make_design(sub)
  unname(coef(svymean(as.formula(paste0("~", variable)), des, na.rm = TRUE)))[1] * 100
}

survey_mean <- function(df, variable) {
  sub <- df[!is.na(df[[variable]]), , drop = FALSE]
  if (nrow(sub) == 0) return(NA_real_)
  des <- make_design(sub)
  unname(coef(svymean(as.formula(paste0("~", variable)), des, na.rm = TRUE)))[1]
}

or_table <- function(model, term, label, n, col_name = "Label") {
  s <- coef(summary(model))
  ci <- confint(model)
  data.frame(
    Label = label,
    OR = exp(s[term, "Estimate"]),
    CI_low = exp(ci[term, 1]),
    CI_high = exp(ci[term, 2]),
    p_value = s[term, "Pr(>|t|)"],
    Analytic_n = n
  ) |>
    rename(!!col_name := Label)
}

read_cols <- c(
  "prim_key", "hhid", "hh1state", "r1wtresp", "r1proxy", "r1agey", "ragender",
  "raeduc_l", "hh1rural", "r1skindise", "r1adlaa", "r1iadlaa", "r1mobilca",
  "r1painfr", "r1cesd10dep", "r1fallslp", "r1vgactx", "r1mdactx", "r1mbmi"
)

raw <- read_sav(lasi_path, col_select = all_of(read_cols))

analysis <- raw |>
  mutate(
    across(c(r1skindise, r1adlaa, r1iadlaa, r1mobilca, r1painfr, r1cesd10dep, r1proxy), keep_binary),
    female = ifelse(ragender == 2, 1, ifelse(ragender == 1, 0, NA_real_)),
    rural = ifelse(hh1rural == 1, 1, ifelse(hh1rural == 0, 0, NA_real_)),
    sleep_problem = ifelse(r1fallslp %in% c(1, 2), 1, ifelse(r1fallslp == 3, 0, NA_real_)),
    vig_inactive = ifelse(r1vgactx == 5, 1, ifelse(r1vgactx %in% c(1, 2, 3, 4), 0, NA_real_)),
    mod_inactive = ifelse(r1mdactx == 5, 1, ifelse(r1mdactx %in% c(1, 2, 3, 4), 0, NA_real_)),
    age_group = cut(r1agey, breaks = c(44, 59, 74, 120), labels = c("45-59", "60-74", "75+")),
    age75plus = ifelse(r1agey >= 75, 1, ifelse(r1agey >= 45, 0, NA_real_)),
    education_group = cut(raeduc_l, breaks = c(-0.1, 0.1, 2.1, 9.1), labels = c("No schooling", "Primary", "Secondary+")),
    education_secondary_plus = ifelse(raeduc_l >= 3, 1, ifelse(raeduc_l %in% 0:2, 0, NA_real_)),
    bmi_group = cut(r1mbmi, breaks = c(0, 18.5, 25, 100), labels = c("Underweight", "Normal BMI", "Overweight or obese")),
    bmi_over = ifelse(r1mbmi >= 25, 1, ifelse(r1mbmi > 0, 0, NA_real_))
  ) |>
  filter(r1agey >= 45, !is.na(r1wtresp), r1skindise %in% c(0, 1), !is.na(hhid), !is.na(hh1state))

primary_design <- make_design(analysis)
no_proxy_df <- analysis |> filter(r1proxy == 0)
no_proxy_design <- make_design(no_proxy_df)

main_prev_specs <- list(
  list(label = "Overall", df = analysis),
  list(label = "Age 45-59", df = analysis |> filter(age_group == "45-59")),
  list(label = "Age 60-74", df = analysis |> filter(age_group == "60-74")),
  list(label = "Age 75+", df = analysis |> filter(age_group == "75+")),
  list(label = "Men", df = analysis |> filter(female == 0)),
  list(label = "Women", df = analysis |> filter(female == 1)),
  list(label = "Urban", df = analysis |> filter(rural == 0)),
  list(label = "Rural", df = analysis |> filter(rural == 1))
)

supp_prev_specs <- list(
  list(label = "No schooling", df = analysis |> filter(education_group == "No schooling")),
  list(label = "Primary", df = analysis |> filter(education_group == "Primary")),
  list(label = "Secondary+", df = analysis |> filter(education_group == "Secondary+")),
  list(label = "Underweight", df = analysis |> filter(bmi_group == "Underweight")),
  list(label = "Normal BMI", df = analysis |> filter(bmi_group == "Normal BMI")),
  list(label = "Overweight or obese", df = analysis |> filter(bmi_group == "Overweight or obese")),
  list(label = "Vigorously inactive", df = analysis |> filter(vig_inactive == 1)),
  list(label = "Not vigorously inactive", df = analysis |> filter(vig_inactive == 0)),
  list(label = "Moderately inactive", df = analysis |> filter(mod_inactive == 1)),
  list(label = "Not moderately inactive", df = analysis |> filter(mod_inactive == 0)),
  list(label = "Proxy respondent", df = analysis |> filter(r1proxy == 1)),
  list(label = "Self respondent", df = analysis |> filter(r1proxy == 0))
)

table2_prevalence_main <- bind_rows(lapply(main_prev_specs, \(x) prop_row(x$df, x$label))) |>
  mutate(
    Prevalence_pct = round(Prevalence * 100, 2),
    CI_low_pct = round(CI_low * 100, 2),
    CI_high_pct = round(CI_high * 100, 2)
  )

tableS2_prevalence_additional <- bind_rows(lapply(supp_prev_specs, \(x) prop_row(x$df, x$label))) |>
  mutate(
    Prevalence_pct = round(Prevalence * 100, 2),
    CI_low_pct = round(CI_low * 100, 2),
    CI_high_pct = round(CI_high * 100, 2)
  )

table1_characteristics <- bind_rows(
  data.frame(Characteristic = "Participants, n"),
  data.frame(Characteristic = "Mean age, years"),
  data.frame(Characteristic = "Women, %"),
  data.frame(Characteristic = "Rural residence, %"),
  data.frame(Characteristic = "No schooling, %"),
  data.frame(Characteristic = "Secondary education or above, %"),
  data.frame(Characteristic = "Underweight, %"),
  data.frame(Characteristic = "Overweight or obese, %"),
  data.frame(Characteristic = "Any ADL limitation, %"),
  data.frame(Characteristic = "Any IADL limitation, %"),
  data.frame(Characteristic = "Any mobility limitation, %"),
  data.frame(Characteristic = "Frequent pain, %"),
  data.frame(Characteristic = "Depressive symptoms, %"),
  data.frame(Characteristic = "Sleep problems, %")
) |>
  mutate(
    Total = c(
      nrow(analysis),
      survey_mean(analysis, "r1agey"),
      survey_prop(analysis, "female"),
      survey_prop(analysis, "rural"),
      survey_prop(transform(analysis, no_school = ifelse(education_group == "No schooling", 1, ifelse(is.na(education_group), NA, 0))), "no_school"),
      survey_prop(analysis, "education_secondary_plus"),
      survey_prop(transform(analysis, underweight = ifelse(bmi_group == "Underweight", 1, ifelse(is.na(bmi_group), NA, 0))), "underweight"),
      survey_prop(transform(analysis, overweight = ifelse(bmi_group == "Overweight or obese", 1, ifelse(is.na(bmi_group), NA, 0))), "overweight"),
      survey_prop(analysis, "r1adlaa"),
      survey_prop(analysis, "r1iadlaa"),
      survey_prop(analysis, "r1mobilca"),
      survey_prop(analysis, "r1painfr"),
      survey_prop(analysis, "r1cesd10dep"),
      survey_prop(analysis, "sleep_problem")
    ),
    No_skin_disease = c(
      nrow(filter(analysis, r1skindise == 0)),
      survey_mean(filter(analysis, r1skindise == 0), "r1agey"),
      survey_prop(filter(analysis, r1skindise == 0), "female"),
      survey_prop(filter(analysis, r1skindise == 0), "rural"),
      survey_prop(transform(filter(analysis, r1skindise == 0), no_school = ifelse(education_group == "No schooling", 1, ifelse(is.na(education_group), NA, 0))), "no_school"),
      survey_prop(filter(analysis, r1skindise == 0), "education_secondary_plus"),
      survey_prop(transform(filter(analysis, r1skindise == 0), underweight = ifelse(bmi_group == "Underweight", 1, ifelse(is.na(bmi_group), NA, 0))), "underweight"),
      survey_prop(transform(filter(analysis, r1skindise == 0), overweight = ifelse(bmi_group == "Overweight or obese", 1, ifelse(is.na(bmi_group), NA, 0))), "overweight"),
      survey_prop(filter(analysis, r1skindise == 0), "r1adlaa"),
      survey_prop(filter(analysis, r1skindise == 0), "r1iadlaa"),
      survey_prop(filter(analysis, r1skindise == 0), "r1mobilca"),
      survey_prop(filter(analysis, r1skindise == 0), "r1painfr"),
      survey_prop(filter(analysis, r1skindise == 0), "r1cesd10dep"),
      survey_prop(filter(analysis, r1skindise == 0), "sleep_problem")
    ),
    Skin_disease = c(
      nrow(filter(analysis, r1skindise == 1)),
      survey_mean(filter(analysis, r1skindise == 1), "r1agey"),
      survey_prop(filter(analysis, r1skindise == 1), "female"),
      survey_prop(filter(analysis, r1skindise == 1), "rural"),
      survey_prop(transform(filter(analysis, r1skindise == 1), no_school = ifelse(education_group == "No schooling", 1, ifelse(is.na(education_group), NA, 0))), "no_school"),
      survey_prop(filter(analysis, r1skindise == 1), "education_secondary_plus"),
      survey_prop(transform(filter(analysis, r1skindise == 1), underweight = ifelse(bmi_group == "Underweight", 1, ifelse(is.na(bmi_group), NA, 0))), "underweight"),
      survey_prop(transform(filter(analysis, r1skindise == 1), overweight = ifelse(bmi_group == "Overweight or obese", 1, ifelse(is.na(bmi_group), NA, 0))), "overweight"),
      survey_prop(filter(analysis, r1skindise == 1), "r1adlaa"),
      survey_prop(filter(analysis, r1skindise == 1), "r1iadlaa"),
      survey_prop(filter(analysis, r1skindise == 1), "r1mobilca"),
      survey_prop(filter(analysis, r1skindise == 1), "r1painfr"),
      survey_prop(filter(analysis, r1skindise == 1), "r1cesd10dep"),
      survey_prop(filter(analysis, r1skindise == 1), "sleep_problem")
    )
  ) |>
  mutate(
    across(c(Total, No_skin_disease, Skin_disease), \(x) round(x, 2))
  )

predictor_df <- analysis |>
  filter(!is.na(r1agey), !is.na(female), !is.na(rural), !is.na(education_secondary_plus))
predictor_model <- svyglm(r1skindise ~ r1agey + female + rural + education_secondary_plus, design = make_design(predictor_df), family = quasibinomial())
table3_predictors <- bind_rows(
  or_table(predictor_model, "r1agey", "Age (per year)", nrow(predictor_df), "Predictor"),
  or_table(predictor_model, "female", "Women vs men", nrow(predictor_df), "Predictor"),
  or_table(predictor_model, "rural", "Rural vs urban", nrow(predictor_df), "Predictor"),
  or_table(predictor_model, "education_secondary_plus", "Secondary education or above vs less", nrow(predictor_df), "Predictor")
)

outcome_specs <- list(
  list(var = "r1adlaa", label = "Any ADL limitation"),
  list(var = "r1iadlaa", label = "Any IADL limitation"),
  list(var = "r1mobilca", label = "Any mobility limitation"),
  list(var = "r1painfr", label = "Frequent pain"),
  list(var = "r1cesd10dep", label = "Depressive symptoms"),
  list(var = "sleep_problem", label = "Sleep problems")
)

fit_outcome_table <- function(df, add_terms = NULL) {
  bind_rows(lapply(outcome_specs, function(spec) {
    model_df <- df |>
      filter(!is.na(.data[[spec$var]]), !is.na(r1agey), !is.na(female), !is.na(rural), !is.na(education_secondary_plus))
    if (!is.null(add_terms)) {
      for (v in add_terms) model_df <- model_df |> filter(!is.na(.data[[v]]))
    }
    rhs <- paste(c("r1skindise", "r1agey", "female", "rural", "education_secondary_plus", add_terms), collapse = " + ")
    model <- svyglm(as.formula(paste0(spec$var, " ~ ", rhs)), design = make_design(model_df), family = quasibinomial())
    or_table(model, "r1skindise", spec$label, nrow(model_df), "Outcome")
  }))
}

table4_outcomes <- fit_outcome_table(analysis)
tableS3_outcomes_no_proxy <- fit_outcome_table(no_proxy_df)
tableS4_outcomes_extended <- fit_outcome_table(analysis, c("vig_inactive", "mod_inactive", "bmi_over"))

interaction_rows <- bind_rows(lapply(outcome_specs, function(spec) {
  base_df <- analysis |>
    filter(!is.na(.data[[spec$var]]), !is.na(r1agey), !is.na(female), !is.na(rural), !is.na(education_secondary_plus), !is.na(age75plus))
  sex_model <- svyglm(
    as.formula(paste0(spec$var, " ~ r1skindise * female + r1agey + rural + education_secondary_plus")),
    design = make_design(base_df),
    family = quasibinomial()
  )
  rural_model <- svyglm(
    as.formula(paste0(spec$var, " ~ r1skindise * rural + r1agey + female + education_secondary_plus")),
    design = make_design(base_df),
    family = quasibinomial()
  )
  age_model <- svyglm(
    as.formula(paste0(spec$var, " ~ r1skindise * age75plus + r1agey + female + rural + education_secondary_plus")),
    design = make_design(base_df),
    family = quasibinomial()
  )
  data.frame(
    Outcome = spec$label,
    Sex_interaction_p = coef(summary(sex_model))["r1skindise:female", "Pr(>|t|)"],
    Rural_interaction_p = coef(summary(rural_model))["r1skindise:rural", "Pr(>|t|)"],
    Age75plus_interaction_p = coef(summary(age_model))["r1skindise:age75plus", "Pr(>|t|)"]
  )
}))

stratified_effects <- bind_rows(
  {
    men_df <- analysis |> filter(female == 0, !is.na(sleep_problem), !is.na(r1agey), !is.na(rural), !is.na(education_secondary_plus))
    women_df <- analysis |> filter(female == 1, !is.na(sleep_problem), !is.na(r1agey), !is.na(rural), !is.na(education_secondary_plus))
    men_model <- svyglm(sleep_problem ~ r1skindise + r1agey + rural + education_secondary_plus, design = make_design(men_df), family = quasibinomial())
    women_model <- svyglm(sleep_problem ~ r1skindise + r1agey + rural + education_secondary_plus, design = make_design(women_df), family = quasibinomial())
    bind_rows(
      or_table(men_model, "r1skindise", "Men", nrow(men_df), "Stratum") |> mutate(Modifier = "Sex", Outcome = "Sleep problems"),
      or_table(women_model, "r1skindise", "Women", nrow(women_df), "Stratum") |> mutate(Modifier = "Sex", Outcome = "Sleep problems")
    )
  },
  {
    urban_df <- analysis |> filter(rural == 0, !is.na(r1mobilca), !is.na(r1agey), !is.na(female), !is.na(education_secondary_plus))
    rural_df <- analysis |> filter(rural == 1, !is.na(r1mobilca), !is.na(r1agey), !is.na(female), !is.na(education_secondary_plus))
    urban_model <- svyglm(r1mobilca ~ r1skindise + r1agey + female + education_secondary_plus, design = make_design(urban_df), family = quasibinomial())
    rural_model <- svyglm(r1mobilca ~ r1skindise + r1agey + female + education_secondary_plus, design = make_design(rural_df), family = quasibinomial())
    bind_rows(
      or_table(urban_model, "r1skindise", "Urban", nrow(urban_df), "Stratum") |> mutate(Modifier = "Residence", Outcome = "Any mobility limitation"),
      or_table(rural_model, "r1skindise", "Rural", nrow(rural_df), "Stratum") |> mutate(Modifier = "Residence", Outcome = "Any mobility limitation")
    )
  }
) |>
  select(Modifier, Outcome, Stratum, OR, CI_low, CI_high, p_value, Analytic_n)

tableS1_variable_defs <- data.frame(
  Domain = c(
    "Exposure", "Weight", "Design proxy", "Design proxy", "Demographic", "Demographic", "Socioeconomic",
    "Functional outcome", "Functional outcome", "Functional outcome", "Symptom outcome", "Psychological outcome",
    "Sleep outcome", "Behavioural context", "Behavioural context", "Anthropometric", "Sensitivity variable"
  ),
  Variable = c(
    "r1skindise", "r1wtresp", "hhid", "hh1state", "r1agey", "ragender", "raeduc_l",
    "r1adlaa", "r1iadlaa", "r1mobilca", "r1painfr", "r1cesd10dep", "r1fallslp",
    "r1vgactx", "r1mdactx", "r1mbmi", "r1proxy"
  ),
  Construct = c(
    "Self-reported skin disease", "Respondent weight", "Household cluster proxy", "State stratification proxy", "Age in years", "Sex",
    "Education level", "Any ADL limitation", "Any IADL limitation", "Any mobility limitation", "Frequent pain",
    "Depressive symptoms", "Sleep problems", "Vigorous physical inactivity", "Moderate physical inactivity",
    "Body-mass index", "Proxy interview"
  ),
  Operational_definition = c(
    "Binary harmonized LASI respondent-level skin disease variable.",
    "Post-stratified respondent analysis weight released in the harmonized file.",
    "Used as the primary clustering unit because public harmonized LASI does not release PSU identifiers.",
    "Used as a conservative stratification proxy because public harmonized LASI does not release design strata.",
    "Restricted to respondents aged 45 years or older.",
    "Recoded as women vs men.",
    "Used for grouped prevalence and adjusted models.",
    "Binary indicator of any activity of daily living limitation.",
    "Binary indicator of any instrumental activity of daily living limitation.",
    "Binary indicator of any mobility difficulty.",
    "Binary indicator of frequent pain.",
    "Binary indicator from harmonized LASI depression measure.",
    "Recoded as frequent or occasional problems vs rare or never.",
    "Recoded as inactive vs any vigorous activity frequency.",
    "Recoded as inactive vs any moderate activity frequency.",
    "Used for extended-adjustment sensitivity analysis.",
    "Used to exclude proxy interviews in sensitivity analysis."
  )
)

write.csv(table1_characteristics, file.path(table_dir, "table1_survey_weighted_characteristics.csv"), row.names = FALSE)
write.csv(table2_prevalence_main, file.path(table_dir, "table2_survey_prevalence_main.csv"), row.names = FALSE)
write.csv(table3_predictors, file.path(table_dir, "table3_survey_predictors.csv"), row.names = FALSE)
write.csv(table4_outcomes, file.path(table_dir, "table4_survey_outcomes.csv"), row.names = FALSE)
write.csv(tableS1_variable_defs, file.path(table_dir, "tableS1_survey_variable_definitions.csv"), row.names = FALSE)
write.csv(tableS2_prevalence_additional, file.path(table_dir, "tableS2_survey_prevalence_additional.csv"), row.names = FALSE)
write.csv(tableS3_outcomes_no_proxy, file.path(table_dir, "tableS3_survey_outcomes_no_proxy.csv"), row.names = FALSE)
write.csv(tableS4_outcomes_extended, file.path(table_dir, "tableS4_survey_outcomes_extended_adjustment.csv"), row.names = FALSE)
write.csv(interaction_rows, file.path(table_dir, "tableS5_survey_interaction_tests.csv"), row.names = FALSE)
write.csv(stratified_effects, file.path(table_dir, "tableS6_survey_stratified_effects.csv"), row.names = FALSE)

fig1_df <- table2_prevalence_main |>
  filter(Group != "Overall") |>
  mutate(Group = factor(Group, levels = rev(Group)))

theme_journal <- theme_minimal(base_family = "sans") +
  theme(
    plot.title = element_text(face = "bold", size = 12, colour = "#163A63"),
    axis.title = element_text(size = 10, colour = "#163A63"),
    axis.text = element_text(size = 9, colour = "#1F1F1F"),
    panel.grid.minor = element_blank(),
    panel.grid.major.y = element_blank()
  )

fig1 <- ggplot(fig1_df, aes(x = Prevalence_pct, y = Group, xmin = CI_low_pct, xmax = CI_high_pct)) +
  geom_errorbar(width = 0.15, orientation = "y", colour = "#5B9AA0", linewidth = 0.8) +
  geom_point(size = 2.8, colour = "#163A63") +
  labs(
    title = NULL,
    x = "Prevalence (%)",
    y = NULL
  ) +
  theme_journal

ggsave(file.path(figure_dir, "figure1_survey_weighted_prevalence.png"), fig1, width = 7, height = 4.8, dpi = 320)
ggsave(file.path(figure_dir, "figure1_survey_weighted_prevalence.pdf"), fig1, width = 7, height = 4.8)

fig2_df <- table4_outcomes |>
  mutate(Outcome = factor(Outcome, levels = rev(Outcome)))

fig2 <- ggplot(fig2_df, aes(x = OR, y = Outcome, xmin = CI_low, xmax = CI_high)) +
  geom_vline(xintercept = 1, linetype = 2, colour = "#D96B5F") +
  geom_errorbar(width = 0.15, orientation = "y", colour = "#5B9AA0", linewidth = 0.8) +
  geom_point(size = 2.8, colour = "#163A63") +
  labs(
    title = NULL,
    x = "Adjusted odds ratio",
    y = NULL
  ) +
  theme_journal

ggsave(file.path(figure_dir, "figure2_survey_weighted_outcome_forest.png"), fig2, width = 7.2, height = 4.8, dpi = 320)
ggsave(file.path(figure_dir, "figure2_survey_weighted_outcome_forest.pdf"), fig2, width = 7.2, height = 4.8)

figS1_df <- stratified_effects |>
  mutate(
    Label = paste0(Outcome, " - ", Stratum),
    Label = factor(Label, levels = rev(Label))
  )

figS1 <- ggplot(figS1_df, aes(x = OR, y = Label, xmin = CI_low, xmax = CI_high, colour = Modifier)) +
  geom_vline(xintercept = 1, linetype = 2, colour = "#D96B5F") +
  geom_errorbar(width = 0.15, orientation = "y", linewidth = 0.8) +
  geom_point(size = 2.8) +
  scale_colour_manual(values = c("Sex" = "#D96B5F", "Residence" = "#2F7E79")) +
  labs(
    title = NULL,
    x = "Adjusted odds ratio",
    y = NULL,
    colour = NULL
  ) +
  theme_journal

ggsave(file.path(figure_dir, "figureS1_survey_stratified_interactions.png"), figS1, width = 7.2, height = 4.6, dpi = 320)
ggsave(file.path(figure_dir, "figureS1_survey_stratified_interactions.pdf"), figS1, width = 7.2, height = 4.6)

sensitivity_compare <- table4_outcomes |>
  select(Outcome, Primary_OR = OR, Primary_low = CI_low, Primary_high = CI_high) |>
  left_join(tableS3_outcomes_no_proxy |> select(Outcome, No_proxy_OR = OR, No_proxy_low = CI_low, No_proxy_high = CI_high), by = "Outcome") |>
  left_join(tableS4_outcomes_extended |> select(Outcome, Extended_OR = OR, Extended_low = CI_low, Extended_high = CI_high), by = "Outcome")

figS2_df <- bind_rows(
  sensitivity_compare |>
    transmute(Outcome, Model = "Primary survey model", OR = Primary_OR, CI_low = Primary_low, CI_high = Primary_high),
  sensitivity_compare |>
    transmute(Outcome, Model = "Exclude proxy respondents", OR = No_proxy_OR, CI_low = No_proxy_low, CI_high = No_proxy_high),
  sensitivity_compare |>
    transmute(Outcome, Model = "Extended adjustment", OR = Extended_OR, CI_low = Extended_low, CI_high = Extended_high)
) |>
  mutate(
    Label = factor(paste0(Outcome, " - ", Model), levels = rev(unique(paste0(Outcome, " - ", Model))))
  )

figS2 <- ggplot(figS2_df, aes(x = OR, y = Label, xmin = CI_low, xmax = CI_high, colour = Model)) +
  geom_vline(xintercept = 1, linetype = 2, colour = "#D96B5F") +
  geom_errorbar(width = 0.12, orientation = "y", linewidth = 0.7) +
  geom_point(size = 2.3) +
  scale_colour_manual(values = c("Primary survey model" = "#163A63", "Exclude proxy respondents" = "#D96B5F", "Extended adjustment" = "#2F7E79")) +
  labs(
    title = NULL,
    x = "Adjusted odds ratio",
    y = NULL,
    colour = NULL
  ) +
  theme_journal +
  theme(axis.text.y = element_text(size = 7.6))

ggsave(file.path(figure_dir, "figureS2_survey_sensitivity_comparison.png"), figS2, width = 8.2, height = 7.4, dpi = 320)
ggsave(file.path(figure_dir, "figureS2_survey_sensitivity_comparison.pdf"), figS2, width = 8.2, height = 7.4)

overall_prev <- table2_prevalence_main |> filter(Group == "Overall")
sleep_sex_p <- interaction_rows |> filter(Outcome == "Sleep problems") |> pull(Sex_interaction_p)
mobility_rural_p <- interaction_rows |> filter(Outcome == "Any mobility limitation") |> pull(Rural_interaction_p)

summary_json <- list(
  design_note = "Survey-weighted analysis using household clustering and state stratification proxy because the public harmonized LASI file releases respondent weights but not PSU or design strata variables.",
  analytic_n = nrow(analysis),
  households = dplyr::n_distinct(analysis$hhid),
  states = dplyr::n_distinct(analysis$hh1state),
  weighted_prevalence_pct = round(overall_prev$Prevalence_pct[[1]], 2),
  weighted_prevalence_ci = c(round(overall_prev$CI_low_pct[[1]], 2), round(overall_prev$CI_high_pct[[1]], 2)),
  top_outcome = table4_outcomes |> arrange(desc(OR)) |> slice(1) |> pull(Outcome),
  top_outcome_or = round(table4_outcomes |> arrange(desc(OR)) |> slice(1) |> pull(OR), 3),
  significant_interactions = list(
    sex_sleep_problem_p = round(sleep_sex_p, 5),
    rural_mobility_p = round(mobility_rural_p, 5)
  ),
  files = list(
    main_tables = c("table1_survey_weighted_characteristics.csv", "table2_survey_prevalence_main.csv", "table3_survey_predictors.csv", "table4_survey_outcomes.csv"),
    supplementary_tables = c("tableS1_survey_variable_definitions.csv", "tableS2_survey_prevalence_additional.csv", "tableS3_survey_outcomes_no_proxy.csv", "tableS4_survey_outcomes_extended_adjustment.csv", "tableS5_survey_interaction_tests.csv", "tableS6_survey_stratified_effects.csv"),
    figures = c("figure1_survey_weighted_prevalence.png", "figure2_survey_weighted_outcome_forest.png", "figureS1_survey_stratified_interactions.png", "figureS2_survey_sensitivity_comparison.png")
  )
)

write_json(summary_json, file.path(manuscript_dir, "lasi_skin_survey_summary_20260312.json"), pretty = TRUE, auto_unbox = TRUE)
cat(toJSON(summary_json, pretty = TRUE, auto_unbox = TRUE))
