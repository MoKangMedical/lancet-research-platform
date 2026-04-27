#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import warnings
from contextlib import contextmanager
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build derived datasets, summary tables, and first-pass figures for the East Asia female under-40 asthma study."
    )
    parser.add_argument("--study-root", required=True)
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def attach_display_fields(df: pd.DataFrame) -> pd.DataFrame:
    measure_map = {
        "DALYs (Disability-Adjusted Life Years)": "DALYs",
        "Deaths": "Deaths",
        "Incidence": "Incidence",
        "Prevalence": "Prevalence",
    }
    age_order = [
        "<5 years",
        "5-9 years",
        "10-14 years",
        "15-19 years",
        "20-24 years",
        "25-29 years",
        "30-34 years",
        "35-39 years",
    ]
    location_order = [
        "China",
        "Japan",
        "Mongolia",
        "Democratic People's Republic of Korea",
        "Republic of Korea",
        "Taiwan",
    ]
    out = df.copy()
    out = out.assign(
        measure_short=lambda frame: frame["measure_name"].map(measure_map).fillna(frame["measure_name"]),
        age_name=lambda frame: pd.Categorical(frame["age_name"], categories=age_order, ordered=True),
        location_name=lambda frame: pd.Categorical(
            frame["location_name"], categories=location_order, ordered=True
        ),
    )
    return out


def build_core_derived(core: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    core = attach_display_fields(core)
    counts = core[core["metric_name"] == "Number"].copy()
    rates = core[core["metric_name"] == "Rate"].copy()

    under40_counts = (
        counts.groupby(["measure_short", "location_name", "year_id"], observed=True)[["val", "lower", "upper"]]
        .sum()
        .reset_index()
        .rename(
            columns={
                "val": "under40_count",
                "lower": "under40_count_lower_sum",
                "upper": "under40_count_upper_sum",
            }
        )
    )
    under40_counts["ui_note"] = "Lower and upper bounds are arithmetic sums across age groups."

    age_specific_2023 = (
        core[core["year_id"] == 2023]
        .sort_values(["measure_short", "metric_name", "location_name", "age_name"])
        .reset_index(drop=True)
    )
    return under40_counts, age_specific_2023


def build_2023_summary_table(under40_counts: pd.DataFrame) -> pd.DataFrame:
    summary_2023 = under40_counts[under40_counts["year_id"] == 2023].copy()
    summary_2023 = summary_2023.assign(
        under40_count_fmt=lambda frame: frame["under40_count"].map(lambda value: f"{value:,.1f}"),
        under40_count_ui_fmt=lambda frame: frame.apply(
            lambda row: (
                f"{row['under40_count']:,.1f} "
                f"({row['under40_count_lower_sum']:,.1f}-{row['under40_count_upper_sum']:,.1f})"
            ),
            axis=1,
        ),
    )
    return summary_2023.sort_values(["measure_short", "under40_count"], ascending=[True, False]).reset_index(drop=True)


def build_change_table(under40_counts: pd.DataFrame) -> pd.DataFrame:
    wide = (
        under40_counts[under40_counts["year_id"].isin([1990, 2023])]
        .pivot_table(
            index=["measure_short", "location_name"],
            columns="year_id",
            values="under40_count",
            aggfunc="first",
            observed=False,
        )
        .reset_index()
        .rename(columns={1990: "count_1990", 2023: "count_2023"})
    )
    wide = wide.assign(
        absolute_change=lambda frame: frame["count_2023"] - frame["count_1990"],
        percent_change=lambda frame: (frame["absolute_change"] / frame["count_1990"]) * 100.0,
    )
    return wide.sort_values(["measure_short", "percent_change"]).reset_index(drop=True)


def build_risk_summary(df: pd.DataFrame, measure_label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = attach_display_fields(df)
    counts = out[out["metric_name"] == "Number"].copy()
    study_total = (
        counts.groupby(["rei_name", "year_id"], observed=True)[["val", "lower", "upper"]]
        .sum()
        .reset_index()
        .rename(columns={"val": "study_scope_count", "lower": "lower_sum", "upper": "upper_sum"})
    )
    summary_2023 = (
        study_total[study_total["year_id"] == 2023]
        .sort_values("study_scope_count", ascending=False)
        .reset_index(drop=True)
    )
    summary_2023 = summary_2023.assign(measure_short=measure_label)
    return study_total, summary_2023


@contextmanager
def suppress_seaborn_future_warnings():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=".*ChainedAssignmentError.*",
            category=FutureWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=".*observed=False is deprecated.*",
            category=FutureWarning,
        )
        yield


def save_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=False)


def plot_measure_trends(under40_counts: pd.DataFrame, out_path: Path) -> None:
    ensure_dir(out_path.parent)
    sns.set_theme(style="whitegrid")
    measures = ["Incidence", "Prevalence", "Deaths", "DALYs"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True)
    axes = axes.flatten()
    with suppress_seaborn_future_warnings():
        for ax, measure in zip(axes, measures):
            subset = under40_counts[under40_counts["measure_short"] == measure]
            sns.lineplot(
                data=subset,
                x="year_id",
                y="under40_count",
                hue="location_name",
                ax=ax,
                linewidth=2,
            )
            ax.set_title(measure)
            ax.set_xlabel("Year")
            ax.set_ylabel("Under-40 summed count")
            ax.legend(title="Location", fontsize=8, title_fontsize=9)
    fig.suptitle("Asthma burden trends in East Asia females under 40 years, 1990-2023", fontsize=14)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_age_heatmap(age_specific_2023: pd.DataFrame, out_path: Path) -> None:
    ensure_dir(out_path.parent)
    sns.set_theme(style="white")
    subset = age_specific_2023[
        (age_specific_2023["measure_short"] == "DALYs") & (age_specific_2023["metric_name"] == "Rate")
    ].copy()
    pivot = subset.pivot(index="location_name", columns="age_name", values="val")
    fig, ax = plt.subplots(figsize=(12, 4.5))
    with suppress_seaborn_future_warnings():
        sns.heatmap(
            pivot,
            cmap="YlOrRd",
            annot=True,
            fmt=".1f",
            linewidths=0.5,
            cbar_kws={"label": "Rate"},
            ax=ax,
        )
    ax.set_title("2023 DALY rates by age group and location")
    ax.set_xlabel("Age group")
    ax.set_ylabel("Location")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_risk_bars(risk_deaths_2023: pd.DataFrame, risk_dalys_2023: pd.DataFrame, out_path: Path) -> None:
    ensure_dir(out_path.parent)
    sns.set_theme(style="whitegrid")
    left = risk_deaths_2023[["rei_name", "study_scope_count"]].copy()
    left = left.assign(measure_short="Deaths")
    right = risk_dalys_2023[["rei_name", "study_scope_count"]].copy()
    right = right.assign(measure_short="DALYs")
    combined = pd.concat([left, right], ignore_index=True)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    with suppress_seaborn_future_warnings():
        for ax, measure in zip(axes, ["Deaths", "DALYs"]):
            subset = combined[combined["measure_short"] == measure].sort_values("study_scope_count", ascending=True)
            sns.barplot(data=subset, x="study_scope_count", y="rei_name", color="#c44e52", ax=ax)
            ax.set_title(f"2023 attributable {measure.lower()} counts")
            ax.set_xlabel("Study-scope summed count")
            ax.set_ylabel("")
    fig.suptitle("Leading attributable risk factors for asthma burden in East Asia females under 40 years, 2023", fontsize=14)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def build_qc(core: pd.DataFrame, risk_deaths: pd.DataFrame, risk_dalys: pd.DataFrame) -> dict:
    return {
        "core_rows": int(len(core)),
        "risk_deaths_rows": int(len(risk_deaths)),
        "risk_dalys_rows": int(len(risk_dalys)),
        "locations": sorted(core["location_name"].dropna().unique().tolist()),
        "age_groups": sorted(core["age_name"].dropna().unique().tolist()),
        "measures": sorted(core["measure_name"].dropna().unique().tolist()),
        "risk_deaths_reis": sorted(risk_deaths["rei_name"].dropna().unique().tolist()),
        "risk_dalys_reis": sorted(risk_dalys["rei_name"].dropna().unique().tolist()),
        "duplicate_rows": {
            "core": int(
                core.duplicated(["measure_id", "location_id", "sex_id", "age_id", "metric_id", "year_id"]).sum()
            ),
            "risk_deaths": int(
                risk_deaths.duplicated(
                    ["measure_id", "location_id", "sex_id", "age_id", "metric_id", "year_id", "rei_id"]
                ).sum()
            ),
            "risk_dalys": int(
                risk_dalys.duplicated(
                    ["measure_id", "location_id", "sex_id", "age_id", "metric_id", "year_id", "rei_id"]
                ).sum()
            ),
        },
    }


def main() -> None:
    warnings.filterwarnings(
        "ignore",
        message=".*ChainedAssignmentError.*",
        category=FutureWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=".*observed=False is deprecated.*",
        category=FutureWarning,
    )
    args = parse_args()
    study_root = Path(args.study_root)
    raw_root = study_root / "data" / "raw_results"
    derived_root = study_root / "data" / "derived"
    figures_root = study_root / "outputs" / "figures"
    tables_root = study_root / "outputs" / "tables"

    core = load_csv(raw_root / "asthma_east_asia_female_u40_core_1990_2023.csv")
    risk_deaths = load_csv(raw_root / "asthma_east_asia_female_u40_risk_deaths_1990_2023.csv")
    risk_dalys = load_csv(raw_root / "asthma_east_asia_female_u40_risk_dalys_1990_2023.csv")

    under40_counts, age_specific_2023 = build_core_derived(core)
    summary_2023 = build_2023_summary_table(under40_counts)
    change_table = build_change_table(under40_counts)
    risk_deaths_total, risk_deaths_2023 = build_risk_summary(risk_deaths, "Deaths")
    risk_dalys_total, risk_dalys_2023 = build_risk_summary(risk_dalys, "DALYs")

    save_csv(core, derived_root / "asthma_east_asia_female_u40_core_clean.csv")
    save_csv(under40_counts, derived_root / "asthma_east_asia_female_u40_under40_counts.csv")
    save_csv(age_specific_2023, derived_root / "asthma_east_asia_female_u40_age_specific_2023.csv")
    save_csv(risk_deaths, derived_root / "asthma_east_asia_female_u40_risk_deaths_clean.csv")
    save_csv(risk_dalys, derived_root / "asthma_east_asia_female_u40_risk_dalys_clean.csv")
    save_csv(risk_deaths_total, derived_root / "asthma_east_asia_female_u40_risk_deaths_study_scope_counts.csv")
    save_csv(risk_dalys_total, derived_root / "asthma_east_asia_female_u40_risk_dalys_study_scope_counts.csv")

    save_csv(summary_2023, tables_root / "asthma_east_asia_female_u40_table_2023_summary.csv")
    save_csv(change_table, tables_root / "asthma_east_asia_female_u40_table_1990_2023_change.csv")
    save_csv(risk_deaths_2023, tables_root / "asthma_east_asia_female_u40_table_2023_risk_deaths.csv")
    save_csv(risk_dalys_2023, tables_root / "asthma_east_asia_female_u40_table_2023_risk_dalys.csv")

    plot_measure_trends(under40_counts, figures_root / "asthma_east_asia_female_u40_trends_counts.png")
    plot_age_heatmap(age_specific_2023, figures_root / "asthma_east_asia_female_u40_2023_daly_rate_heatmap.png")
    plot_risk_bars(
        risk_deaths_2023,
        risk_dalys_2023,
        figures_root / "asthma_east_asia_female_u40_2023_risk_rankings.png",
    )

    qc = build_qc(core, risk_deaths, risk_dalys)
    qc_path = tables_root / "asthma_east_asia_female_u40_analysis_qc.json"
    ensure_dir(qc_path.parent)
    qc_path.write_text(json.dumps(qc, indent=2), encoding="utf-8")

    print(f"Wrote derived datasets to {derived_root}")
    print(f"Wrote tables to {tables_root}")
    print(f"Wrote figures to {figures_root}")
    print(f"Wrote QC to {qc_path}")


if __name__ == "__main__":
    main()
