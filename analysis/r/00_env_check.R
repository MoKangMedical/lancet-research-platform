pkgs <- c(
  "tidyverse", "data.table", "arrow", "duckdb", "DBI", "RPostgres",
  "janitor", "survey", "srvyr", "mice", "gtsummary", "gt",
  "tableone", "survival", "survminer", "cmprsk", "MatchIt",
  "WeightIt", "cobalt", "fixest", "lme4", "broom", "targets"
)

for (p in pkgs) {
  ok <- requireNamespace(p, quietly = TRUE)
  cat(if (ok) "OK:" else "MISS:", p, "\n")
}
