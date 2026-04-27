#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile

import numpy as np
import pandas as pd
from PIL import Image, ImageStat

AGGREGATE_LABEL = "East Asia study-scope aggregate"
MANUSCRIPT_HEADINGS = [
    "# Summary",
    "# Panel: Research in context",
    "# Introduction",
    "# Methods",
    "# Results",
    "# Discussion",
    "# Declarations",
    "# Figure legends",
    "# Table titles",
    "# References",
]
MAIN_FIGURES = [
    "asthma_east_asia_female_u40_figure_1_counts_trends",
    "asthma_east_asia_female_u40_figure_2_pooled_rate_trends",
    "asthma_east_asia_female_u40_figure_3_age_specific_rates",
    "asthma_east_asia_female_u40_figure_4_risk_rankings",
    "asthma_east_asia_female_u40_figure_5_risk_trends",
]
MAIN_TABLES = [
    "asthma_east_asia_female_u40_table_1_2023_burden_and_rates.csv",
    "asthma_east_asia_female_u40_table_2_pooled_rate_eapc.csv",
    "asthma_east_asia_female_u40_table_3_peak_age_patterns_2023.csv",
    "asthma_east_asia_female_u40_table_4_risk_attribution_2023.csv",
    "asthma_east_asia_female_u40_table_5_risk_change_1990_2023.csv",
]


@dataclass
class Finding:
    severity: str
    domain: str
    title: str
    detail: str
    path: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full-package QC for the East Asia female under-40 asthma study."
    )
    parser.add_argument("--study-root", required=True)
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def add_finding(
    findings: list[Finding],
    severity: str,
    domain: str,
    title: str,
    detail: str,
    path: Path | None = None,
) -> None:
    findings.append(
        Finding(
            severity=severity,
            domain=domain,
            title=title,
            detail=detail,
            path=str(path) if path else "",
        )
    )


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def extract_section(text: str, heading: str, next_heading: str | None) -> str:
    start_match = re.search(rf"^{re.escape(heading)}$", text, flags=re.MULTILINE)
    if not start_match:
        return ""
    start = start_match.end()
    if next_heading is None:
        return text[start:]
    end_match = re.search(rf"^{re.escape(next_heading)}$", text[start:], flags=re.MULTILINE)
    if not end_match:
        return text[start:]
    return text[start : start + end_match.start()]


def expand_citation_token(token: str) -> list[int]:
    values: list[int] = []
    for part in token.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "-" in piece:
            left, right = piece.split("-", 1)
            values.extend(range(int(left), int(right) + 1))
        else:
            values.append(int(piece))
    return values


def extract_citation_numbers(text: str) -> list[int]:
    values: list[int] = []
    for token in re.findall(r"\[([0-9,\-\s]+)\]", text):
        values.extend(expand_citation_token(token))
    return sorted(set(values))


def compute_eapc(series: pd.DataFrame) -> float:
    years = series["year_id"].to_numpy(dtype=float)
    rates = series["pooled_rate"].to_numpy(dtype=float)
    beta = np.polyfit(years, np.log(rates), 1)[0]
    return 100.0 * (math.exp(beta) - 1.0)


def severity_rank(severity: str) -> int:
    order = {"major": 0, "warning": 1, "minor": 2, "info": 3}
    return order.get(severity, 99)


def bool_to_status(value: bool) -> str:
    return "PASS" if value else "FAIL"


def validate_asset(path: Path) -> tuple[bool, str]:
    suffix = path.suffix.lower()
    try:
        if suffix in {".csv", ".tsv"}:
            pd.read_csv(path, nrows=1)
            return True, "tabular_ok"
        if suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
            return True, "json_ok"
        if suffix == ".png":
            with Image.open(path) as img:
                img.verify()
            return True, "png_ok"
        if suffix == ".pdf":
            return path.read_bytes().startswith(b"%PDF-"), "pdf_ok"
        if suffix == ".html":
            text = path.read_text(encoding="utf-8", errors="ignore")
            return bool(text.strip()), "html_ok"
        if suffix == ".docx":
            with ZipFile(path) as zf:
                return "word/document.xml" in zf.namelist(), "docx_ok"
        if suffix in {".md", ".txt"}:
            return bool(path.read_text(encoding="utf-8", errors="ignore").strip()), "text_ok"
        return True, "skipped"
    except Exception as exc:  # pragma: no cover
        return False, f"{type(exc).__name__}: {exc}"


def main() -> None:
    args = parse_args()
    study_root = Path(args.study_root)
    data_root = study_root / "data" / "derived"
    outputs_root = study_root / "outputs"
    figures_root = outputs_root / "figures"
    tables_root = outputs_root / "tables"
    manuscript_root = outputs_root / "manuscript"
    refs_root = outputs_root / "references" / "curated_submission"
    specs_root = study_root / "specs"

    report_path = manuscript_root / "submission_package_qc_report.md"
    summary_path = manuscript_root / "submission_package_qc_summary.json"

    findings: list[Finding] = []
    checks: list[dict[str, object]] = []

    manifest_path = manuscript_root / "submission_package_manifest.json"
    manuscript_path = manuscript_root / "submission_manuscript_5000plus.md"
    docx_path = manuscript_root / "submission_manuscript_5000plus.docx"
    html_path = manuscript_root / "submission_manuscript_5000plus.html"
    refs_path = refs_root / "references_curated_36.csv"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manuscript_text = manuscript_path.read_text(encoding="utf-8")

    core = pd.read_csv(data_root / "asthma_east_asia_female_u40_core_clean.csv")
    under40_counts = pd.read_csv(data_root / "asthma_east_asia_female_u40_under40_counts.csv")
    pooled_rates = pd.read_csv(data_root / "asthma_east_asia_female_u40_pooled_rates.csv")
    age_specific_2023 = pd.read_csv(data_root / "asthma_east_asia_female_u40_age_specific_2023.csv")
    risk_deaths = pd.read_csv(data_root / "asthma_east_asia_female_u40_risk_deaths_clean.csv")
    risk_dalys = pd.read_csv(data_root / "asthma_east_asia_female_u40_risk_dalys_clean.csv")
    risk_deaths_scope = pd.read_csv(data_root / "asthma_east_asia_female_u40_risk_deaths_study_scope_counts.csv")
    risk_dalys_scope = pd.read_csv(data_root / "asthma_east_asia_female_u40_risk_dalys_study_scope_counts.csv")

    table1 = pd.read_csv(tables_root / MAIN_TABLES[0])
    table2 = pd.read_csv(tables_root / MAIN_TABLES[1])
    table3 = pd.read_csv(tables_root / MAIN_TABLES[2])
    table4 = pd.read_csv(tables_root / MAIN_TABLES[3])
    table5 = pd.read_csv(tables_root / MAIN_TABLES[4])
    references = pd.read_csv(refs_path)

    metrics = {
        "core_rows": int(len(core)),
        "under40_counts_rows": int(len(under40_counts)),
        "pooled_rates_rows": int(len(pooled_rates)),
        "age_specific_rows": int(len(age_specific_2023)),
        "risk_deaths_rows": int(len(risk_deaths)),
        "risk_dalys_rows": int(len(risk_dalys)),
        "manuscript_word_count": word_count(manuscript_text),
        "manifest_word_count": int(manifest["word_count"]),
        "reference_count": int(len(references)),
        "main_figure_count_manifest": int(manifest["main_figure_count"]),
        "main_table_count_manifest": int(manifest["main_table_count"]),
    }

    # Core data checks.
    core_key = [
        "population_group_id",
        "measure_id",
        "location_id",
        "sex_id",
        "age_id",
        "cause_id",
        "metric_id",
        "year_id",
    ]
    core_duplicates = int(core.duplicated(subset=core_key).sum())
    core_ui_invalid = int(((core["lower"] > core["val"]) | (core["val"] > core["upper"])).sum())
    core_missing = int(core[core_key + ["val", "lower", "upper"]].isna().sum().sum())
    expected_core_rows = 6 * 8 * 4 * 2 * 34
    core_scope_ok = (
        core["measure_id"].nunique() == 4
        and sorted(core["metric_name"].unique().tolist()) == ["Number", "Rate"]
        and sorted(core["sex_name"].unique().tolist()) == ["Female"]
        and sorted(core["cause_name"].unique().tolist()) == ["Asthma"]
        and core["location_id"].nunique() == 6
        and core["age_id"].nunique() == 8
        and core["year_id"].nunique() == 34
    )
    checks.append(
        {
            "name": "core_clean_shape_and_scope",
            "status": bool_to_status(
                metrics["core_rows"] == expected_core_rows
                and core_duplicates == 0
                and core_ui_invalid == 0
                and core_missing == 0
                and core_scope_ok
            ),
            "details": {
                "rows": metrics["core_rows"],
                "expected_rows": expected_core_rows,
                "duplicates": core_duplicates,
                "ui_invalid": core_ui_invalid,
                "missing_cells": core_missing,
            },
        }
    )
    if metrics["core_rows"] != expected_core_rows or core_duplicates or core_ui_invalid or core_missing or not core_scope_ok:
        add_finding(
            findings,
            "major",
            "data",
            "Core burden dataset failed scope validation",
            (
                f"core_clean has rows={metrics['core_rows']} expected={expected_core_rows}, "
                f"duplicates={core_duplicates}, ui_invalid={core_ui_invalid}, missing_cells={core_missing}."
            ),
            data_root / "asthma_east_asia_female_u40_core_clean.csv",
        )

    pooled_duplicates = int(pooled_rates.duplicated(subset=["measure_short", "location_id", "year_id"]).sum())
    pooled_nonpositive = int(((pooled_rates["population_est"] <= 0) | (pooled_rates["pooled_rate"] <= 0)).sum())
    expected_pooled_rows = 7 * 4 * 34
    pooled_ok = (
        len(pooled_rates) == expected_pooled_rows
        and pooled_duplicates == 0
        and pooled_nonpositive == 0
        and pooled_rates["location_name"].nunique() == 7
    )
    checks.append(
        {
            "name": "pooled_rates_shape_and_positivity",
            "status": bool_to_status(pooled_ok),
            "details": {
                "rows": int(len(pooled_rates)),
                "expected_rows": expected_pooled_rows,
                "duplicates": pooled_duplicates,
                "nonpositive_rows": pooled_nonpositive,
            },
        }
    )
    if not pooled_ok:
        add_finding(
            findings,
            "major",
            "data",
            "Pooled-rate dataset failed validation",
            (
                f"pooled_rates has rows={len(pooled_rates)} expected={expected_pooled_rows}, "
                f"duplicates={pooled_duplicates}, nonpositive_rows={pooled_nonpositive}."
            ),
            data_root / "asthma_east_asia_female_u40_pooled_rates.csv",
        )

    for risk_name, risk_df in [
        ("risk_deaths", risk_deaths),
        ("risk_dalys", risk_dalys),
    ]:
        risk_key = core_key[:-1] + ["rei_id", "metric_id", "year_id"]
        dup_count = int(risk_df.duplicated(subset=risk_key).sum())
        ui_invalid = int(((risk_df["lower"] > risk_df["val"]) | (risk_df["val"] > risk_df["upper"])).sum())
        missing = int(risk_df[risk_key + ["val", "lower", "upper"]].isna().sum().sum())
        ok = dup_count == 0 and ui_invalid == 0 and missing == 0
        checks.append(
            {
                "name": f"{risk_name}_integrity",
                "status": bool_to_status(ok),
                "details": {"duplicates": dup_count, "ui_invalid": ui_invalid, "missing_cells": missing},
            }
        )
        if not ok:
            add_finding(
                findings,
                "major",
                "data",
                f"{risk_name} dataset failed integrity checks",
                f"duplicates={dup_count}, ui_invalid={ui_invalid}, missing_cells={missing}.",
                data_root / f"asthma_east_asia_female_u40_{risk_name.replace('risk_', 'risk_')}_clean.csv",
            )

    # Table checks.
    table1_constituent = table1.loc[table1["location_type"] == "constituent_location"].copy()
    table1_aggregate = table1.loc[table1["location_name"] == AGGREGATE_LABEL].copy()
    table1_sum = (
        table1_constituent.groupby("measure_short", as_index=False)["count_2023"].sum().rename(columns={"count_2023": "sum_count"})
    )
    table1_compare = table1_aggregate.merge(table1_sum, on="measure_short", how="left")
    table1_diff = (table1_compare["count_2023"] - table1_compare["sum_count"]).abs().max()
    pooled_2023 = pooled_rates.loc[
        (pooled_rates["location_name"] == AGGREGATE_LABEL) & (pooled_rates["year_id"] == 2023),
        ["measure_short", "pooled_rate"],
    ]
    table1_rate_compare = table1_aggregate.merge(pooled_2023, on="measure_short", suffixes=("_table", "_source"))
    table1_rate_diff = (table1_rate_compare["pooled_rate_table"] - table1_rate_compare["pooled_rate_source"]).abs().max()
    table1_ok = len(table1) == 28 and float(table1_diff) < 1e-6 and float(table1_rate_diff) < 1e-9
    checks.append(
        {
            "name": "table1_matches_derived_inputs",
            "status": bool_to_status(table1_ok),
            "details": {
                "rows": int(len(table1)),
                "max_count_diff": float(table1_diff),
                "max_rate_diff": float(table1_rate_diff),
            },
        }
    )
    if not table1_ok:
        add_finding(
            findings,
            "major",
            "tables",
            "Table 1 does not reconcile to the derived inputs",
            f"Max count diff={float(table1_diff):.6f}; max pooled-rate diff={float(table1_rate_diff):.12f}.",
            tables_root / MAIN_TABLES[0],
        )

    recomputed_eapc_rows = []
    for (measure_short, location_name), group in pooled_rates.groupby(["measure_short", "location_name"]):
        recomputed_eapc_rows.append(
            {
                "measure_short": measure_short,
                "location_name": location_name,
                "eapc_recomputed": compute_eapc(group.sort_values("year_id")),
            }
        )
    recomputed_eapc = pd.DataFrame(recomputed_eapc_rows)
    table2_compare = table2.merge(recomputed_eapc, on=["measure_short", "location_name"], how="left")
    table2_max_diff = (table2_compare["eapc"] - table2_compare["eapc_recomputed"]).abs().max()
    table2_ok = len(table2) == 28 and float(table2_max_diff) < 1e-9
    checks.append(
        {
            "name": "table2_eapc_reproducibility",
            "status": bool_to_status(table2_ok),
            "details": {"rows": int(len(table2)), "max_abs_diff": float(table2_max_diff)},
        }
    )
    if not table2_ok:
        add_finding(
            findings,
            "major",
            "tables",
            "Table 2 EAPC values are not reproducible from pooled rates",
            f"Max absolute EAPC difference={float(table2_max_diff):.12f}.",
            tables_root / MAIN_TABLES[1],
        )

    rate_2023 = age_specific_2023.loc[age_specific_2023["metric_name"] == "Rate"].copy()
    count_2023 = age_specific_2023.loc[age_specific_2023["metric_name"] == "Number"].copy()
    idx = rate_2023.groupby(["measure_name", "location_name"])["val"].idxmax()
    peak_expected = rate_2023.loc[idx, ["measure_short", "location_name", "age_name", "val"]].rename(
        columns={"age_name": "peak_age_group", "val": "rate_2023"}
    )
    peak_counts = count_2023[["measure_short", "location_name", "age_name", "val"]].rename(
        columns={"age_name": "peak_age_group", "val": "count_2023"}
    )
    peak_expected = peak_expected.merge(
        peak_counts[["measure_short", "location_name", "peak_age_group", "count_2023"]],
        on=["measure_short", "location_name", "peak_age_group"],
        how="left",
    )
    total_counts = (
        count_2023.groupby(["measure_short", "location_name"], as_index=False)["val"].sum().rename(
            columns={"val": "total_count"}
        )
    )
    peak_expected = peak_expected.merge(total_counts, on=["measure_short", "location_name"], how="left")
    peak_expected = peak_expected.copy()
    peak_expected.loc[:, "count_share_pct"] = 100.0 * peak_expected["count_2023"] / peak_expected["total_count"]
    table3_compare = table3.merge(
        peak_expected[["measure_short", "location_name", "peak_age_group", "rate_2023", "count_2023", "count_share_pct"]],
        on=["measure_short", "location_name"],
        suffixes=("_table", "_source"),
    )
    table3_ok = (
        len(table3) == 24
        and (table3_compare["peak_age_group_table"] == table3_compare["peak_age_group_source"]).all()
        and (table3_compare["rate_2023_table"] - table3_compare["rate_2023_source"]).abs().max() < 1e-9
        and (table3_compare["count_2023_table"] - table3_compare["count_2023_source"]).abs().max() < 1e-9
    )
    checks.append(
        {
            "name": "table3_age_peak_reproducibility",
            "status": bool_to_status(table3_ok),
            "details": {"rows": int(len(table3))},
        }
    )
    if not table3_ok:
        add_finding(
            findings,
            "major",
            "tables",
            "Table 3 peak age patterns do not match the 2023 age-specific dataset",
            "At least one location-measure peak cell did not reconcile exactly.",
            tables_root / MAIN_TABLES[2],
        )

    scope_totals_2023 = (
        under40_counts.loc[under40_counts["year_id"] == 2023]
        .groupby("measure_short", as_index=False)["under40_count"]
        .sum()
        .rename(columns={"under40_count": "study_total_2023"})
    )
    table4_expected = pd.concat(
        [
            risk_deaths.loc[(risk_deaths["year_id"] == 2023) & (risk_deaths["metric_name"] == "Number")]
            .groupby("rei_name", as_index=False)[["val", "lower", "upper"]]
            .sum()
            .assign(measure_short="Deaths"),
            risk_dalys.loc[(risk_dalys["year_id"] == 2023) & (risk_dalys["metric_name"] == "Number")]
            .groupby("rei_name", as_index=False)[["val", "lower", "upper"]]
            .sum()
            .assign(measure_short="DALYs"),
        ],
        ignore_index=True,
    ).rename(columns={"val": "attributable_count_2023", "lower": "lower_sum", "upper": "upper_sum"})
    table4_expected = table4_expected.merge(scope_totals_2023, on="measure_short", how="left")
    table4_expected = table4_expected.copy()
    table4_expected.loc[:, "share_of_total_pct"] = 100.0 * table4_expected["attributable_count_2023"] / table4_expected["study_total_2023"]
    table4_expected.loc[:, "rank_2023"] = (
        table4_expected.groupby("measure_short")["share_of_total_pct"].rank(method="first", ascending=False).astype(int)
    )
    table4_expected = table4_expected.sort_values(["measure_short", "rank_2023", "rei_name"]).reset_index(drop=True)
    table4_sorted = table4.sort_values(["measure_short", "rank_2023", "rei_name"]).reset_index(drop=True)
    table4_compare = table4_sorted.merge(
        table4_expected[["rei_name", "measure_short", "attributable_count_2023", "share_of_total_pct", "rank_2023", "lower_sum", "upper_sum"]],
        on=["rei_name", "measure_short", "rank_2023"],
        suffixes=("_table", "_source"),
    )
    table4_ok = (
        len(table4) == len(table4_expected)
        and (table4_compare["attributable_count_2023_table"] - table4_compare["attributable_count_2023_source"]).abs().max() < 1e-9
        and (table4_compare["share_of_total_pct_table"] - table4_compare["share_of_total_pct_source"]).abs().max() < 1e-9
    )
    checks.append(
        {
            "name": "table4_risk_ranking_reproducibility",
            "status": bool_to_status(table4_ok),
            "details": {"rows": int(len(table4))},
        }
    )
    if not table4_ok:
        add_finding(
            findings,
            "major",
            "tables",
            "Table 4 risk attribution values do not reconcile to the source risk files",
            "At least one attributable count or share did not match the recomputed 2023 study-scope totals.",
            tables_root / MAIN_TABLES[3],
        )

    scope_totals_all_years = (
        under40_counts.groupby(["measure_short", "year_id"], as_index=False)["under40_count"].sum().rename(
            columns={"under40_count": "study_total"}
        )
    )
    risk_deaths_scope = risk_deaths_scope.copy()
    risk_dalys_scope = risk_dalys_scope.copy()
    risk_deaths_scope.loc[:, "measure_short"] = "Deaths"
    risk_dalys_scope.loc[:, "measure_short"] = "DALYs"
    scope_risk_all_years = pd.concat([risk_deaths_scope, risk_dalys_scope], ignore_index=True)
    table5_expected = scope_risk_all_years.loc[scope_risk_all_years["year_id"].isin([1990, 2023])].copy()
    table5_expected = table5_expected.merge(scope_totals_all_years, on=["measure_short", "year_id"], how="left")
    table5_expected = table5_expected.rename(columns={"study_scope_count": "attributable_count"})
    table5_expected.loc[:, "share_pct"] = 100.0 * table5_expected["attributable_count"] / table5_expected["study_total"]
    pivot = table5_expected.pivot_table(
        index=["rei_name", "measure_short"],
        columns="year_id",
        values=["attributable_count", "share_pct"],
    )
    pivot.columns = [f"{left}_{right}" for left, right in pivot.columns]
    pivot = pivot.reset_index().rename(
        columns={
            "attributable_count_1990": "count_1990",
            "attributable_count_2023": "count_2023",
            "share_pct_1990": "share_1990_pct",
            "share_pct_2023": "share_2023_pct",
        }
    )
    pivot = pivot.copy()
    pivot.loc[:, "absolute_change"] = pivot["count_2023"] - pivot["count_1990"]
    pivot.loc[:, "percent_change"] = 100.0 * pivot["absolute_change"] / pivot["count_1990"]
    pivot.loc[:, "share_change_pct_points"] = pivot["share_2023_pct"] - pivot["share_1990_pct"]
    top5_2023 = (
        pivot.sort_values(["measure_short", "count_2023"], ascending=[True, False])
        .groupby("measure_short", as_index=False)
        .head(5)
    )
    table5_expected = top5_2023.sort_values(["measure_short", "count_2023"], ascending=[True, False]).reset_index(drop=True)
    table5_sorted = table5.sort_values(["measure_short", "count_2023"], ascending=[True, False]).reset_index(drop=True)
    table5_compare = table5_sorted.merge(
        table5_expected,
        on=["rei_name", "measure_short"],
        suffixes=("_table", "_source"),
    )
    table5_ok = (
        len(table5) == len(table5_expected)
        and (table5_compare["count_1990_table"] - table5_compare["count_1990_source"]).abs().max() < 1e-9
        and (table5_compare["count_2023_table"] - table5_compare["count_2023_source"]).abs().max() < 1e-9
        and (table5_compare["share_1990_pct_table"] - table5_compare["share_1990_pct_source"]).abs().max() < 1e-9
        and (table5_compare["share_2023_pct_table"] - table5_compare["share_2023_pct_source"]).abs().max() < 1e-9
    )
    checks.append(
        {
            "name": "table5_risk_change_reproducibility",
            "status": bool_to_status(table5_ok),
            "details": {"rows": int(len(table5))},
        }
    )
    if not table5_ok:
        add_finding(
            findings,
            "major",
            "tables",
            "Table 5 longitudinal risk change values do not reconcile to the source risk files",
            "At least one 1990/2023 attributable count or share could not be reproduced.",
            tables_root / MAIN_TABLES[4],
        )

    no2_row = table4.loc[(table4["measure_short"] == "DALYs") & (table4["rei_name"] == "Nitrogen dioxide pollution")]
    no2_caveat_present = bool(
        re.search(
            r"nitrogen dioxide pollution.*cross(?:ed|es) zero.*caut",
            manuscript_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    no2_lower = None
    if not no2_row.empty:
        no2_lower = float(no2_row.iloc[0]["lower_sum"])
        if no2_lower < 0 and not no2_caveat_present:
            add_finding(
                findings,
                "warning",
                "interpretation",
                "NO2-attributable DALY estimate crosses zero",
                (
                    "Nitrogen dioxide pollution is discussed as a meaningful DALY contributor, "
                    f"but its 2023 summed lower bound is {no2_lower:.1f}, which crosses zero. "
                    "The Results/Discussion text should add uncertainty caveating before submission."
                ),
                tables_root / MAIN_TABLES[3],
            )

    # Figure checks.
    figure_metrics: list[dict[str, object]] = []
    figure_ok = True
    for stem in MAIN_FIGURES:
        png_path = figures_root / f"{stem}.png"
        pdf_path = figures_root / f"{stem}.pdf"
        png_exists = png_path.exists()
        pdf_exists = pdf_path.exists()
        png_width = png_height = 0
        grayscale_std = 0.0
        png_size = pdf_size = 0
        pdf_valid = False
        if png_exists:
            png_size = png_path.stat().st_size
            with Image.open(png_path) as img:
                png_width, png_height = img.width, img.height
                grayscale_std = float(ImageStat.Stat(img.convert("L")).stddev[0])
        if pdf_exists:
            pdf_size = pdf_path.stat().st_size
            pdf_valid = pdf_path.read_bytes().startswith(b"%PDF-")
        row_ok = png_exists and pdf_exists and png_width >= 1000 and png_height >= 1000 and grayscale_std > 2 and pdf_valid
        figure_ok = figure_ok and row_ok
        figure_metrics.append(
            {
                "stem": stem,
                "png_exists": png_exists,
                "pdf_exists": pdf_exists,
                "png_width": png_width,
                "png_height": png_height,
                "png_size": png_size,
                "pdf_size": pdf_size,
                "grayscale_std": round(grayscale_std, 3),
                "pdf_valid": pdf_valid,
                "status": bool_to_status(row_ok),
            }
        )
        if not row_ok:
            add_finding(
                findings,
                "major",
                "figures",
                f"Main figure asset failed validation: {stem}",
                (
                    f"png_exists={png_exists}, pdf_exists={pdf_exists}, size={png_width}x{png_height}, "
                    f"grayscale_std={grayscale_std:.3f}, pdf_valid={pdf_valid}."
                ),
                png_path if png_exists else pdf_path,
            )
    checks.append(
        {
            "name": "main_figures_render_and_export",
            "status": bool_to_status(figure_ok),
            "details": figure_metrics,
        }
    )

    # Manuscript checks.
    heading_missing = [heading for heading in MANUSCRIPT_HEADINGS if heading not in manuscript_text]
    placeholders = re.findall(r"\[To be completed by authors\]", manuscript_text)
    linguistic_sign_errors = re.findall(r"\b(?:increase|increased|increases|increasing)\s+by\s+-\d[\d,\.]*", manuscript_text, flags=re.IGNORECASE)
    negative_phrase_snippet = linguistic_sign_errors[0] if linguistic_sign_errors else ""
    manuscript_ref_lines = re.findall(r"^\d+\.\s", manuscript_text.split("# References", 1)[1], flags=re.MULTILINE) if "# References" in manuscript_text else []
    section_intro = extract_section(manuscript_text, "# Introduction", "# Methods")
    section_methods = extract_section(manuscript_text, "# Methods", "# Results")
    section_discussion = extract_section(manuscript_text, "# Discussion", "# Declarations")
    intro_citations = extract_citation_numbers(section_intro)
    methods_citations = extract_citation_numbers(section_methods)
    discussion_citations = extract_citation_numbers(section_discussion)
    section_distribution_ok = (
        intro_citations == list(range(1, 13))
        and methods_citations == list(range(13, 25))
        and discussion_citations == list(range(25, 37))
    )
    manuscript_ok = (
        metrics["manuscript_word_count"] >= 5000
        and not heading_missing
        and len(manuscript_ref_lines) == 36
        and section_distribution_ok
    )
    checks.append(
        {
            "name": "manuscript_structure_and_references",
            "status": bool_to_status(manuscript_ok),
            "details": {
                "word_count": metrics["manuscript_word_count"],
                "heading_missing": heading_missing,
                "placeholders": len(placeholders),
                "reference_lines": len(manuscript_ref_lines),
                "intro_citations": intro_citations,
                "methods_citations": methods_citations,
                "discussion_citations": discussion_citations,
            },
        }
    )
    if heading_missing:
        add_finding(
            findings,
            "major",
            "manuscript",
            "Required manuscript sections are missing",
            "Missing headings: " + ", ".join(heading_missing),
            manuscript_path,
        )
    if placeholders:
        add_finding(
            findings,
            "major",
            "manuscript",
            "Submission-critical placeholders remain in the manuscript",
            f"The manuscript still contains {len(placeholders)} '[To be completed by authors]' placeholders for authorship, funding, or declarations.",
            manuscript_path,
        )
    if linguistic_sign_errors:
        add_finding(
            findings,
            "major",
            "manuscript",
            "Narrative sign error in longitudinal risk wording",
            (
                f"The manuscript contains wording like '{negative_phrase_snippet}', "
                "which reverses directionality and should be rewritten before submission."
            ),
            manuscript_path,
        )
    if not section_distribution_ok:
        add_finding(
            findings,
            "warning",
            "references",
            "Citation ranges are not confined to the intended section allocations",
            (
                f"Introduction citations={intro_citations}, Methods citations={methods_citations}, "
                f"Discussion citations={discussion_citations}."
            ),
            manuscript_path,
        )

    # Reference checks.
    duplicate_pmids = references.loc[references["pmid"].duplicated(), "pmid"].astype(str).tolist()
    duplicate_dois = references.loc[references["doi"].duplicated(), "doi"].astype(str).tolist()
    section_counts = references["section"].value_counts().to_dict()
    contiguous_refs = references["ref_no"].tolist() == list(range(1, len(references) + 1))
    reference_ok = (
        len(references) == 36
        and contiguous_refs
        and not duplicate_pmids
        and not duplicate_dois
        and section_counts == {"introduction": 12, "methods": 12, "discussion": 12}
    )
    checks.append(
        {
            "name": "reference_table_integrity",
            "status": bool_to_status(reference_ok),
            "details": {
                "rows": int(len(references)),
                "contiguous": contiguous_refs,
                "duplicate_pmids": duplicate_pmids,
                "duplicate_dois": duplicate_dois,
                "section_counts": section_counts,
            },
        }
    )
    if not reference_ok:
        add_finding(
            findings,
            "major",
            "references",
            "Curated reference table failed integrity checks",
            (
                f"rows={len(references)}, contiguous={contiguous_refs}, "
                f"duplicate_pmids={duplicate_pmids}, duplicate_dois={duplicate_dois}, section_counts={section_counts}."
            ),
            refs_path,
        )

    # Package hygiene and submission-safety checks.
    storage_state_path = specs_root / "gbd_results_storage_state.json"
    ds_store_path = outputs_root / ".DS_Store"
    login_probe_path = figures_root / "login_probe.png"
    post_login_probe_path = figures_root / "post_login_probe.png"
    if storage_state_path.exists():
        add_finding(
            findings,
            "warning",
            "package_hygiene",
            "Authentication storage state is retained inside the study package",
            "The Playwright storage-state JSON should be excluded from any shared or archived submission package because it may contain reusable login state.",
            storage_state_path,
        )
    if ds_store_path.exists():
        add_finding(
            findings,
            "minor",
            "package_hygiene",
            "Finder metadata file is present in outputs",
            "`.DS_Store` is harmless scientifically but should be removed from a clean submission bundle.",
            ds_store_path,
        )
    for extra_path in [login_probe_path, post_login_probe_path]:
        if extra_path.exists():
            add_finding(
                findings,
                "minor",
                "package_hygiene",
                "Debug browser screenshot is retained in the figures directory",
                "Operational probe screenshots should not be kept in the final submission asset folder.",
                extra_path,
            )

    docx_ok = bool(manifest.get("docx_result", {}).get("ok")) and docx_path.exists()
    html_ok = bool(manifest.get("html_result", {}).get("ok")) and html_path.exists()
    docx_has_document_xml = False
    if docx_path.exists():
        with ZipFile(docx_path) as zf:
            docx_has_document_xml = "word/document.xml" in zf.namelist()
    checks.append(
        {
            "name": "rendered_manuscript_assets",
            "status": bool_to_status(docx_ok and html_ok and docx_has_document_xml),
            "details": {
                "docx_ok": docx_ok,
                "html_ok": html_ok,
                "docx_has_document_xml": docx_has_document_xml,
            },
        }
    )

    # Whole-package asset inventory.
    asset_records: list[dict[str, object]] = []
    unreadable_assets: list[dict[str, str]] = []
    for path in sorted(p for p in study_root.rglob("*") if p.is_file()):
        ok, note = validate_asset(path)
        asset_records.append(
            {
                "path": str(path),
                "suffix": path.suffix.lower(),
                "size": path.stat().st_size,
                "status": "PASS" if ok else "FAIL",
                "note": note,
            }
        )
        if not ok:
            unreadable_assets.append({"path": str(path), "note": note})
    checks.append(
        {
            "name": "whole_package_asset_readability",
            "status": bool_to_status(not unreadable_assets),
            "details": {
                "file_count": len(asset_records),
                "unreadable_count": len(unreadable_assets),
            },
        }
    )
    if unreadable_assets:
        add_finding(
            findings,
            "major",
            "package_hygiene",
            "One or more package assets could not be parsed or opened",
            json.dumps(unreadable_assets[:5], ensure_ascii=False),
            Path(unreadable_assets[0]["path"]),
        )

    findings.sort(key=lambda item: (severity_rank(item.severity), item.domain, item.title))
    severity_counts = {
        severity: sum(1 for item in findings if item.severity == severity)
        for severity in ["major", "warning", "minor", "info"]
    }
    if severity_counts["major"] > 0:
        overall_status = "FAIL"
    elif severity_counts["warning"] > 0:
        overall_status = "CONDITIONAL PASS"
    else:
        overall_status = "PASS"

    report_lines = [
        "# Submission Package QC Report",
        "",
        f"- Study root: `{study_root}`",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Overall status: `{overall_status}`",
        f"- Word count: `{metrics['manuscript_word_count']}`",
        f"- References: `{metrics['reference_count']}`",
        f"- Main tables: `{metrics['main_table_count_manifest']}`",
        f"- Main figures: `{metrics['main_figure_count_manifest']}`",
        "",
        "## Executive Summary",
        "",
        f"- Major findings: `{severity_counts['major']}`",
        f"- Warnings: `{severity_counts['warning']}`",
        f"- Minor hygiene findings: `{severity_counts['minor']}`",
        "",
    ]

    if findings:
        report_lines.extend(["## Findings", ""])
        for idx, item in enumerate(findings, start=1):
            report_lines.append(f"{idx}. [{item.severity.upper()}] {item.domain}: {item.title}")
            report_lines.append(f"   - Detail: {item.detail}")
            if item.path:
                report_lines.append(f"   - Path: `{item.path}`")
            report_lines.append("")
    else:
        report_lines.extend(["## Findings", "", "No findings.", ""])

    report_lines.extend(["## Check Matrix", ""])
    for check in checks:
        report_lines.append(f"- {check['name']}: `{check['status']}`")
    report_lines.append("")
    report_lines.extend(["## Figure Assets", ""])
    for item in figure_metrics:
        report_lines.append(
            (
                f"- {item['stem']}: `{item['status']}`; png={item['png_width']}x{item['png_height']}, "
                f"png_size={item['png_size']}, pdf_size={item['pdf_size']}, grayscale_std={item['grayscale_std']}"
            )
        )
    report_lines.append("")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study_root": str(study_root),
        "overall_status": overall_status,
        "metrics": metrics,
        "severity_counts": severity_counts,
        "findings": [item.__dict__ for item in findings],
        "checks": checks,
        "figure_assets": figure_metrics,
        "manuscript": {
            "path": str(manuscript_path),
            "word_count": metrics["manuscript_word_count"],
            "placeholders": len(placeholders),
            "section_citations": {
                "introduction": intro_citations,
                "methods": methods_citations,
                "discussion": discussion_citations,
            },
        },
        "references": {
            "path": str(refs_path),
            "count": int(len(references)),
            "section_counts": section_counts,
            "duplicate_pmids": duplicate_pmids,
            "duplicate_dois": duplicate_dois,
        },
        "asset_inventory": {
            "file_count": len(asset_records),
            "unreadable_count": len(unreadable_assets),
            "sample": asset_records[:20],
        },
    }

    ensure_dir(report_path.parent)
    report_path.write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"QC report: {report_path}")
    print(f"QC summary: {summary_path}")
    print(f"Overall status: {overall_status}")
    print(f"Findings: {len(findings)}")


if __name__ == "__main__":
    main()
