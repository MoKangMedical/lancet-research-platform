#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

RATE_SCALE = 100000.0
AGGREGATE_LABEL = "Asia-Pacific aggregate"
MEASURE_MAP = {
    "DALYs (Disability-Adjusted Life Years)": "DALYs",
    "Deaths": "Deaths",
    "Incidence": "Incidence",
}
MEASURE_ORDER = ["Incidence", "Deaths", "DALYs"]
AGE_ORDER = ["<5 years", "5-9 years", "10-14 years"]
SEX_ORDER = ["Both", "Male", "Female"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build derived datasets, figures, tables, and QC outputs for the Asia-Pacific children idiopathic epilepsy GBD 2023 study."
    )
    parser.add_argument("--study-root", required=True)
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=False)


def save_json(payload: dict[str, object], path: Path) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_markdown(text: str, path: Path) -> None:
    ensure_dir(path.parent)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def save_figure(fig: plt.Figure, out_base: Path) -> None:
    ensure_dir(out_base.parent)
    fig.savefig(out_base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(out_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def format_count(value: float) -> str:
    return f"{value:,.1f}"


def format_rate(value: float) -> str:
    return f"{value:,.2f}"


def format_pct(value: float) -> str:
    return f"{value:.2f}%"


def load_config(study_root: Path) -> dict[str, object]:
    return json.loads((study_root / "study_config.json").read_text(encoding="utf-8"))


def build_location_lookup(config: dict[str, object]) -> pd.DataFrame:
    geography = config["geography"]  # type: ignore[index]
    subregions = pd.DataFrame(geography["subregions"])  # type: ignore[index]
    subregions["location_type"] = "subregion"
    subregions["subregion_name"] = subregions["display_name"]
    subregions["subregion_id"] = subregions["location_id"]

    countries = pd.DataFrame(geography["countries"])  # type: ignore[index]
    countries["location_type"] = "country"

    out = pd.concat(
        [
            subregions[["location_id", "display_name", "gbd_name", "location_type", "subregion_name", "subregion_id"]],
            countries[["location_id", "display_name", "gbd_name", "location_type", "subregion_name", "subregion_id"]],
        ],
        ignore_index=True,
    )
    out = out.rename(columns={"display_name": "display_location_name"})
    return out


def attach_metadata(raw: pd.DataFrame, config: dict[str, object]) -> pd.DataFrame:
    location_lookup = build_location_lookup(config)
    out = raw.merge(location_lookup, on="location_id", how="left", validate="many_to_one")
    if out["location_type"].isna().any():
        missing = sorted(out.loc[out["location_type"].isna(), "location_id"].unique().tolist())
        raise ValueError(f"Location metadata missing for IDs: {missing}")

    subregion_order = [item["display_name"] for item in config["geography"]["subregions"]]  # type: ignore[index]
    country_order = [item["display_name"] for item in config["geography"]["countries"]]  # type: ignore[index]

    out["measure_short"] = out["measure_name"].map(MEASURE_MAP).fillna(out["measure_name"])
    out["sex_name"] = pd.Categorical(out["sex_name"], categories=SEX_ORDER, ordered=True)
    out["age_name"] = pd.Categorical(out["age_name"], categories=AGE_ORDER, ordered=True)
    out["measure_short"] = pd.Categorical(out["measure_short"], categories=MEASURE_ORDER, ordered=True)
    out["subregion_name"] = pd.Categorical(out["subregion_name"], categories=subregion_order, ordered=True)

    out.loc[out["location_type"] == "subregion", "display_location_name"] = out.loc[
        out["location_type"] == "subregion", "location_name"
    ]
    out["display_location_name"] = np.where(
        out["location_type"] == "country",
        out["display_location_name"],
        out["location_name"],
    )
    location_categories = [AGGREGATE_LABEL] + subregion_order + country_order
    out["display_location_name"] = pd.Categorical(
        out["display_location_name"], categories=location_categories, ordered=True
    )
    return out


def load_raw_data(study_root: Path, config: dict[str, object]) -> pd.DataFrame:
    raw_path = study_root / "data" / "raw_results" / "epilepsy_apac_children_core_1990_2023.csv"
    raw = pd.read_csv(raw_path)
    return attach_metadata(raw, config)


def reconstruct_population(raw: pd.DataFrame) -> pd.DataFrame:
    counts = raw.loc[raw["metric_name"] == "Number"].copy()
    rates = raw.loc[raw["metric_name"] == "Rate"].copy()
    keys = [
        "population_group_id",
        "population_group_name",
        "measure_id",
        "measure_name",
        "measure_short",
        "location_id",
        "location_name",
        "display_location_name",
        "location_type",
        "subregion_name",
        "subregion_id",
        "sex_id",
        "sex_name",
        "age_id",
        "age_name",
        "cause_id",
        "cause_name",
        "year_id",
    ]
    merged = counts[keys + ["val", "lower", "upper"]].merge(
        rates[keys + ["val", "lower", "upper"]],
        on=keys,
        how="inner",
        suffixes=("_count", "_rate"),
        validate="one_to_one",
    )
    merged = merged.assign(
        population_est=lambda frame: np.where(
            frame["val_rate"] > 0,
            frame["val_count"] / frame["val_rate"] * RATE_SCALE,
            np.nan,
        )
    )
    return merged


def build_official_pooled_rates(reconstructed: pd.DataFrame) -> pd.DataFrame:
    pooled = (
        reconstructed.groupby(
            [
                "measure_short",
                "measure_name",
                "location_id",
                "location_name",
                "display_location_name",
                "location_type",
                "subregion_name",
                "subregion_id",
                "sex_name",
                "year_id",
            ],
            observed=True,
            as_index=False,
        )[["val_count", "population_est"]]
        .sum()
        .rename(columns={"val_count": "count"})
    )
    pooled["pooled_rate"] = pooled["count"] / pooled["population_est"] * RATE_SCALE
    return pooled


def build_apac_aggregate(reconstructed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    country_rows = reconstructed.loc[reconstructed["location_type"] == "country"].copy()

    aggregate_age_sex = (
        country_rows.groupby(
            ["measure_short", "measure_name", "sex_name", "age_name", "year_id"],
            observed=True,
            as_index=False,
        )[["val_count", "lower_count", "upper_count", "population_est"]]
        .sum()
        .rename(columns={"val_count": "count", "lower_count": "lower_count_sum", "upper_count": "upper_count_sum"})
    )
    aggregate_age_sex["rate"] = aggregate_age_sex["count"] / aggregate_age_sex["population_est"] * RATE_SCALE

    aggregate_pooled = (
        country_rows.groupby(["measure_short", "measure_name", "sex_name", "year_id"], observed=True, as_index=False)[
            ["val_count", "population_est"]
        ]
        .sum()
        .rename(columns={"val_count": "count"})
        .assign(
            location_id=-1,
            location_name=AGGREGATE_LABEL,
            display_location_name=AGGREGATE_LABEL,
            location_type="aggregate",
            subregion_name=AGGREGATE_LABEL,
            subregion_id=-1,
        )
    )
    aggregate_pooled["pooled_rate"] = aggregate_pooled["count"] / aggregate_pooled["population_est"] * RATE_SCALE

    aggregate_counts = (
        country_rows.groupby(["measure_short", "measure_name", "sex_name", "year_id"], observed=True, as_index=False)[
            ["val_count", "lower_count", "upper_count"]
        ]
        .sum()
        .rename(columns={"val_count": "count", "lower_count": "lower_count_sum", "upper_count": "upper_count_sum"})
    )

    return aggregate_age_sex, aggregate_pooled, aggregate_counts


def fit_log_linear_rate(year: pd.Series, rate: pd.Series) -> dict[str, float]:
    mask = rate.gt(0) & year.notna()
    x = year.loc[mask].to_numpy(dtype=float)
    y = np.log(rate.loc[mask].to_numpy(dtype=float))
    n = len(x)
    if n < 3:
        raise ValueError("Need at least 3 positive observations to estimate EAPC.")
    x_mean = x.mean()
    y_mean = y.mean()
    sxx = np.sum((x - x_mean) ** 2)
    slope = np.sum((x - x_mean) * (y - y_mean)) / sxx
    intercept = y_mean - slope * x_mean
    fitted = intercept + slope * x
    resid = y - fitted
    sigma2 = np.sum(resid**2) / (n - 2)
    se_slope = np.sqrt(sigma2 / sxx)
    z = 1.96
    return {
        "slope": float(slope),
        "slope_lower": float(slope - z * se_slope),
        "slope_upper": float(slope + z * se_slope),
        "n_obs": float(n),
    }


def build_table_1(
    raw: pd.DataFrame, pooled_all: pd.DataFrame, aggregate_counts: pd.DataFrame, config: dict[str, object]
) -> pd.DataFrame:
    target_subregions = [item["display_name"] for item in config["geography"]["subregions"]]  # type: ignore[index]
    counts = (
        raw.loc[
            (raw["metric_name"] == "Number")
            & (raw["sex_name"] == "Both")
            & (raw["year_id"] == 2023)
            & (raw["location_type"] == "subregion")
        ]
        .groupby(["measure_short", "display_location_name"], observed=True, as_index=False)[["val", "lower", "upper"]]
        .sum()
        .rename(columns={"val": "count_2023", "lower": "lower_sum", "upper": "upper_sum"})
    )
    aggregate_rows = (
        aggregate_counts.loc[(aggregate_counts["sex_name"] == "Both") & (aggregate_counts["year_id"] == 2023)]
        .assign(display_location_name=AGGREGATE_LABEL)
        .rename(columns={"count": "count_2023", "lower_count_sum": "lower_sum", "upper_count_sum": "upper_sum"})[
            ["measure_short", "display_location_name", "count_2023", "lower_sum", "upper_sum"]
        ]
    )
    counts = pd.concat([aggregate_rows, counts], ignore_index=True)

    rates = (
        pooled_all.loc[
            (pooled_all["sex_name"] == "Both")
            & (pooled_all["year_id"] == 2023)
            & (pooled_all["display_location_name"].isin([AGGREGATE_LABEL] + target_subregions))
        ][["measure_short", "display_location_name", "pooled_rate"]]
        .rename(columns={"pooled_rate": "rate_2023"})
    )
    long_table = counts.merge(rates, on=["measure_short", "display_location_name"], how="inner", validate="one_to_one")
    long_table["count_2023_ui"] = long_table.apply(
        lambda row: f"{format_count(row['count_2023'])} ({format_count(row['lower_sum'])}-{format_count(row['upper_sum'])})",
        axis=1,
    )
    long_table["rate_2023_fmt"] = long_table["rate_2023"].map(format_rate)
    long_table["display_location_name"] = pd.Categorical(
        long_table["display_location_name"], categories=[AGGREGATE_LABEL] + target_subregions, ordered=True
    )
    long_table = long_table.sort_values(["display_location_name", "measure_short"]).reset_index(drop=True)

    wide = (
        long_table.pivot(index="display_location_name", columns="measure_short", values=["count_2023_ui", "rate_2023_fmt"])
        .sort_index()
        .reset_index()
    )
    wide.columns = [
        "location_name"
        if col == ("display_location_name", "")
        else f"{col[1].lower()}_{col[0].replace('_fmt', '').replace('_ui', '_ui')}"
        for col in wide.columns
    ]
    return wide


def build_table_2(pooled_all: pd.DataFrame, config: dict[str, object]) -> pd.DataFrame:
    targets = [AGGREGATE_LABEL] + [item["display_name"] for item in config["geography"]["subregions"]]  # type: ignore[index]
    subset = pooled_all.loc[
        (pooled_all["sex_name"] == "Both") & (pooled_all["display_location_name"].isin(targets))
    ].copy()
    rows: list[dict[str, object]] = []
    for (location_name, measure_short), group in subset.groupby(
        ["display_location_name", "measure_short"], observed=True, sort=False
    ):
        fit = fit_log_linear_rate(group["year_id"], group["pooled_rate"])
        rate_1990 = float(group.loc[group["year_id"] == 1990, "pooled_rate"].iloc[0])
        rate_2023 = float(group.loc[group["year_id"] == 2023, "pooled_rate"].iloc[0])
        eapc = 100.0 * (np.exp(fit["slope"]) - 1.0)
        eapc_lower = 100.0 * (np.exp(fit["slope_lower"]) - 1.0)
        eapc_upper = 100.0 * (np.exp(fit["slope_upper"]) - 1.0)
        rows.append(
            {
                "location_name": str(location_name),
                "measure_short": str(measure_short),
                "rate_1990": rate_1990,
                "rate_2023": rate_2023,
                "absolute_rate_change": rate_2023 - rate_1990,
                "percent_rate_change": ((rate_2023 - rate_1990) / rate_1990) * 100.0,
                "eapc": eapc,
                "eapc_lower": eapc_lower,
                "eapc_upper": eapc_upper,
            }
        )
    out = pd.DataFrame(rows)
    out["location_name"] = pd.Categorical(out["location_name"], categories=targets, ordered=True)
    out["measure_short"] = pd.Categorical(out["measure_short"], categories=MEASURE_ORDER, ordered=True)
    return out.sort_values(["measure_short", "location_name"]).reset_index(drop=True)


def build_table_3(aggregate_age_sex: pd.DataFrame) -> pd.DataFrame:
    table = aggregate_age_sex.loc[aggregate_age_sex["year_id"] == 2023].copy()
    table["count_2023_ui"] = table.apply(
        lambda row: f"{format_count(row['count'])} ({format_count(row['lower_count_sum'])}-{format_count(row['upper_count_sum'])})",
        axis=1,
    )
    table["rate_2023_fmt"] = table["rate"].map(format_rate)
    table = table[
        [
            "measure_short",
            "sex_name",
            "age_name",
            "count",
            "rate",
            "count_2023_ui",
            "rate_2023_fmt",
        ]
    ].sort_values(["measure_short", "sex_name", "age_name"])
    return table.reset_index(drop=True)


def build_country_summary(raw: pd.DataFrame, pooled_all: pd.DataFrame) -> pd.DataFrame:
    country_counts = (
        raw.loc[
            (raw["metric_name"] == "Number")
            & (raw["sex_name"] == "Both")
            & (raw["year_id"] == 2023)
            & (raw["location_type"] == "country")
        ]
        .groupby(["display_location_name", "subregion_name", "measure_short"], observed=True, as_index=False)[["val"]]
        .sum()
        .rename(columns={"val": "count_2023"})
    )
    country_rates = (
        pooled_all.loc[
            (pooled_all["sex_name"] == "Both")
            & (pooled_all["year_id"] == 2023)
            & (pooled_all["location_type"] == "country")
        ][["display_location_name", "subregion_name", "measure_short", "pooled_rate"]]
        .rename(columns={"pooled_rate": "rate_2023"})
    )
    merged = country_counts.merge(
        country_rates,
        on=["display_location_name", "subregion_name", "measure_short"],
        how="inner",
        validate="one_to_one",
    )
    wide = merged.pivot(
        index=["display_location_name", "subregion_name"],
        columns="measure_short",
        values=["count_2023", "rate_2023"],
    ).reset_index()
    wide.columns = [
        "location_name"
        if col == ("display_location_name", "")
        else "subregion_name"
        if col == ("subregion_name", "")
        else f"{col[1].lower()}_{col[0].replace('_2023', '')}"
        for col in wide.columns
    ]
    wide = wide.sort_values(["dalys_rate", "deaths_rate"], ascending=[False, False]).reset_index(drop=True)
    wide["daly_rank_2023"] = np.arange(1, len(wide) + 1)
    return wide


def build_key_metrics(
    table1: pd.DataFrame, table2: pd.DataFrame, table3: pd.DataFrame, country_summary: pd.DataFrame
) -> dict[str, object]:
    aggregate_table = table2.loc[table2["location_name"] == AGGREGATE_LABEL].copy()
    aggregate_lookup = aggregate_table.set_index("measure_short").to_dict("index")

    top_daly_country = country_summary.iloc[0].to_dict()
    top_death_country = country_summary.sort_values("deaths_rate", ascending=False).iloc[0].to_dict()

    peak_age_rows = table3.sort_values("rate", ascending=False)
    incidence_peak = peak_age_rows.loc[peak_age_rows["measure_short"] == "Incidence"].iloc[0].to_dict()
    deaths_peak = peak_age_rows.loc[peak_age_rows["measure_short"] == "Deaths"].iloc[0].to_dict()
    dalys_peak = peak_age_rows.loc[peak_age_rows["measure_short"] == "DALYs"].iloc[0].to_dict()

    return {
        "aggregate_eapc": aggregate_lookup,
        "top_daly_country": top_daly_country,
        "top_death_country": top_death_country,
        "incidence_peak": incidence_peak,
        "deaths_peak": deaths_peak,
        "dalys_peak": dalys_peak,
        "table1_locations": table1["location_name"].tolist(),
    }


def plot_aggregate_trends(
    aggregate_counts: pd.DataFrame, aggregate_pooled: pd.DataFrame, figure_root: Path
) -> None:
    sns.set_theme(style="whitegrid")
    counts = aggregate_counts.loc[aggregate_counts["sex_name"] == "Both"].copy()
    rates = aggregate_pooled.loc[aggregate_pooled["sex_name"] == "Both"].copy()

    fig, axes = plt.subplots(3, 2, figsize=(14, 12), sharex=True)
    for row_idx, measure in enumerate(MEASURE_ORDER):
        count_ax = axes[row_idx, 0]
        rate_ax = axes[row_idx, 1]
        count_subset = counts.loc[counts["measure_short"] == measure]
        rate_subset = rates.loc[rates["measure_short"] == measure]

        sns.lineplot(data=count_subset, x="year_id", y="count", ax=count_ax, color="#0b6e4f", linewidth=2.4)
        sns.lineplot(data=rate_subset, x="year_id", y="pooled_rate", ax=rate_ax, color="#c84c09", linewidth=2.4)

        count_ax.set_title(f"{measure}: annual count")
        rate_ax.set_title(f"{measure}: pooled crude rate")
        count_ax.set_ylabel("Count")
        rate_ax.set_ylabel("Rate per 100,000")
        count_ax.set_xlabel("Year")
        rate_ax.set_xlabel("Year")

    fig.suptitle("Asia-Pacific childhood idiopathic epilepsy burden, both sexes, 1990-2023", fontsize=15)
    fig.tight_layout()
    save_figure(fig, figure_root / "figure_1_apac_trends")


def plot_subregion_rate_trends(pooled_all: pd.DataFrame, figure_root: Path, config: dict[str, object]) -> None:
    sns.set_theme(style="whitegrid")
    subset = pooled_all.loc[(pooled_all["sex_name"] == "Both") & (pooled_all["location_type"] == "subregion")].copy()
    palette = ["#0b6e4f", "#2a9d8f", "#4472ca", "#ef476f", "#ff8c42", "#6a4c93"]
    subregion_order = [item["display_name"] for item in config["geography"]["subregions"]]  # type: ignore[index]

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharex=True)
    for ax, measure in zip(axes, MEASURE_ORDER):
        measure_subset = subset.loc[subset["measure_short"] == measure].copy()
        measure_subset["display_location_name"] = pd.Categorical(
            measure_subset["display_location_name"], categories=subregion_order, ordered=True
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=FutureWarning)
            sns.lineplot(
                data=measure_subset,
                x="year_id",
                y="pooled_rate",
                hue="display_location_name",
                hue_order=subregion_order,
                palette=palette,
                linewidth=2,
                ax=ax,
            )
        ax.set_title(measure)
        ax.set_xlabel("Year")
        ax.set_ylabel("Rate per 100,000")
        if ax is axes[0]:
            ax.legend(title="Subregion", fontsize=8, title_fontsize=9)
        else:
            ax.get_legend().remove()

    fig.suptitle("Subregional pooled crude rates of childhood idiopathic epilepsy, both sexes, 1990-2023", fontsize=14)
    fig.tight_layout()
    save_figure(fig, figure_root / "figure_2_subregion_rate_trends")


def plot_age_sex_heatmap(table3: pd.DataFrame, figure_root: Path) -> None:
    sns.set_theme(style="white")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    for ax, measure in zip(axes, MEASURE_ORDER):
        subset = table3.loc[table3["measure_short"] == measure].copy()
        pivot = subset.pivot(index="sex_name", columns="age_name", values="rate")
        sns.heatmap(
            pivot,
            cmap="YlOrRd",
            annot=True,
            fmt=".2f",
            linewidths=0.6,
            cbar_kws={"label": "Rate per 100,000"},
            ax=ax,
        )
        ax.set_title(measure)
        ax.set_xlabel("Age group")
        ax.set_ylabel("Sex")
    fig.suptitle("2023 Asia-Pacific childhood idiopathic epilepsy rates by age and sex", fontsize=14)
    fig.tight_layout()
    save_figure(fig, figure_root / "figure_3_age_sex_heatmap_2023")


def plot_country_rankings(country_summary: pd.DataFrame, figure_root: Path) -> None:
    sns.set_theme(style="whitegrid")
    top20 = country_summary.head(20).iloc[::-1].copy()
    fig, axes = plt.subplots(1, 2, figsize=(14, 7), sharey=True)

    sns.barplot(data=top20, x="dalys_rate", y="location_name", color="#1f77b4", ax=axes[0])
    axes[0].set_title("2023 DALY rate")
    axes[0].set_xlabel("Rate per 100,000")
    axes[0].set_ylabel("")

    sns.barplot(data=top20, x="deaths_rate", y="location_name", color="#d1495b", ax=axes[1])
    axes[1].set_title("2023 mortality rate")
    axes[1].set_xlabel("Rate per 100,000")
    axes[1].set_ylabel("")

    fig.suptitle("Top 20 countries by 2023 DALY rate, both sexes", fontsize=14)
    fig.tight_layout()
    save_figure(fig, figure_root / "figure_4_country_rankings_2023")


def build_qc(raw: pd.DataFrame, reconstructed: pd.DataFrame, pooled_all: pd.DataFrame) -> dict[str, object]:
    key = ["measure_id", "location_id", "sex_id", "age_id", "metric_id", "year_id"]
    return {
        "raw_rows": int(len(raw)),
        "duplicate_rows": int(raw.duplicated(key).sum()),
        "invalid_uncertainty_rows": int(((raw["lower"] > raw["val"]) | (raw["val"] > raw["upper"])).sum()),
        "reconstructed_rows": int(len(reconstructed)),
        "nonpositive_population_rows": int((reconstructed["population_est"] <= 0).sum()),
        "pooled_rate_rows": int(len(pooled_all)),
        "nonpositive_pooled_rate_rows": int((pooled_all["pooled_rate"] <= 0).sum()),
        "locations": int(raw["location_id"].nunique()),
        "years": [int(raw["year_id"].min()), int(raw["year_id"].max())],
        "measures": sorted(raw["measure_name"].unique().tolist()),
        "metrics": sorted(raw["metric_name"].unique().tolist()),
        "sexes": sorted([str(item) for item in raw["sex_name"].dropna().unique().tolist()]),
        "ages": sorted([str(item) for item in raw["age_name"].dropna().unique().tolist()]),
    }


def build_results_draft(
    table1: pd.DataFrame,
    table2: pd.DataFrame,
    table3: pd.DataFrame,
    country_summary: pd.DataFrame,
    key_metrics: dict[str, object],
) -> str:
    agg_row = table1.loc[table1["location_name"] == AGGREGATE_LABEL].iloc[0].to_dict()
    aggregate_eapc = key_metrics["aggregate_eapc"]  # type: ignore[assignment]
    incidence_peak = key_metrics["incidence_peak"]  # type: ignore[assignment]
    deaths_peak = key_metrics["deaths_peak"]  # type: ignore[assignment]
    dalys_peak = key_metrics["dalys_peak"]  # type: ignore[assignment]
    top_daly_country = key_metrics["top_daly_country"]  # type: ignore[assignment]
    top_death_country = key_metrics["top_death_country"]  # type: ignore[assignment]

    subregion_highest_dalys = (
        table2.loc[table2["measure_short"] == "DALYs"]
        .sort_values("rate_2023", ascending=False)
        .iloc[0]
        .to_dict()
    )

    return (
        "# Results Draft\n\n"
        "## Overall burden in 2023\n\n"
        f"In 2023, the Asia-Pacific aggregate recorded {agg_row['incidence_count_2023_ui']} incident cases, "
        f"{agg_row['deaths_count_2023_ui']} deaths, and {agg_row['dalys_count_2023_ui']} DALYs among children aged 0-14 years. "
        f"The corresponding pooled crude rates were {agg_row['incidence_rate_2023']} per 100,000 for incidence, "
        f"{agg_row['deaths_rate_2023']} per 100,000 for mortality, and {agg_row['dalys_rate_2023']} per 100,000 for DALYs.\n\n"
        "## Temporal trends from 1990 to 2023\n\n"
        f"At the Asia-Pacific aggregate level, incidence rose slightly over time, whereas mortality and DALY rates declined. "
        f"The EAPC was {format_pct(aggregate_eapc['Incidence']['eapc'])} for incidence, "
        f"{format_pct(aggregate_eapc['Deaths']['eapc'])} for deaths, and "
        f"{format_pct(aggregate_eapc['DALYs']['eapc'])} for DALYs. "
        f"In 2023, the highest subregional DALY rate was observed in {subregion_highest_dalys['location_name']} "
        f"({format_rate(subregion_highest_dalys['rate_2023'])} per 100,000).\n\n"
        "## Age and sex heterogeneity\n\n"
        f"The highest incidence rate in 2023 was observed among {incidence_peak['sex_name'].lower()} children aged {incidence_peak['age_name']} "
        f"({format_rate(incidence_peak['rate'])} per 100,000). "
        f"The highest mortality rate was observed among {deaths_peak['sex_name'].lower()} children aged {deaths_peak['age_name']} "
        f"({format_rate(deaths_peak['rate'])} per 100,000), and the highest DALY rate was observed among {dalys_peak['sex_name'].lower()} "
        f"children aged {dalys_peak['age_name']} ({format_rate(dalys_peak['rate'])} per 100,000).\n\n"
        "## Country ranking in 2023\n\n"
        f"The country with the highest 2023 DALY rate was {top_daly_country['location_name']} "
        f"({format_rate(top_daly_country['dalys_rate'])} per 100,000), while the highest mortality rate was observed in "
        f"{top_death_country['location_name']} ({format_rate(top_death_country['deaths_rate'])} per 100,000). "
        f"The country ranking table retained all countries and territories in the prespecified Asia-Pacific scope, with the main figure showing the top 20 by DALY rate.\n"
    )


def build_figure_legends() -> str:
    return (
        "# Figure Legends\n\n"
        "## Figure 1\n\n"
        "Asia-Pacific aggregate annual counts and pooled crude rates for incidence, deaths, and DALYs among children aged 0-14 years, both sexes combined, 1990-2023. Counts were derived by summing country-level age-specific numbers. Pooled crude rates were reconstructed from matched GBD counts and rates.\n\n"
        "## Figure 2\n\n"
        "Subregional pooled crude rates for incidence, deaths, and DALYs among children aged 0-14 years, both sexes combined, 1990-2023. Official GBD subregional rows were retained for East Asia, South Asia, Southeast Asia, High-income Asia Pacific, Australasia, and Oceania.\n\n"
        "## Figure 3\n\n"
        "Asia-Pacific aggregate age-specific rates for incidence, deaths, and DALYs by sex in 2023. The heatmaps show pooled crude rates per 100,000 for children aged younger than 5 years, 5-9 years, and 10-14 years.\n\n"
        "## Figure 4\n\n"
        "Top 20 countries and territories ranked by 2023 DALY rate among children aged 0-14 years, both sexes combined. The companion panel shows the mortality rate for the same ranked locations.\n"
    )


def main() -> None:
    args = parse_args()
    study_root = Path(args.study_root).resolve()
    config = load_config(study_root)
    derived_root = study_root / "data" / "derived"
    table_root = study_root / "outputs" / "tables"
    figure_root = study_root / "outputs" / "figures"
    manuscript_root = study_root / "outputs" / "manuscript"

    raw = load_raw_data(study_root, config)
    reconstructed = reconstruct_population(raw)
    official_pooled = build_official_pooled_rates(reconstructed)
    aggregate_age_sex, aggregate_pooled, aggregate_counts = build_apac_aggregate(reconstructed)
    pooled_all = pd.concat([official_pooled, aggregate_pooled], ignore_index=True)
    pooled_all["measure_short"] = pd.Categorical(pooled_all["measure_short"], categories=MEASURE_ORDER, ordered=True)

    table1 = build_table_1(raw, pooled_all, aggregate_counts, config)
    table2 = build_table_2(pooled_all, config)
    table3 = build_table_3(aggregate_age_sex)
    country_summary = build_country_summary(raw, pooled_all)
    key_metrics = build_key_metrics(table1, table2, table3, country_summary)
    qc = build_qc(raw, reconstructed, pooled_all)
    results_draft = build_results_draft(table1, table2, table3, country_summary, key_metrics)
    figure_legends = build_figure_legends()

    save_csv(raw, derived_root / "epilepsy_apac_children_core_clean.csv")
    save_csv(reconstructed, derived_root / "epilepsy_apac_children_population_reconstructed.csv")
    save_csv(aggregate_age_sex, derived_root / "epilepsy_apac_children_apac_age_sex_aggregate.csv")
    save_csv(aggregate_counts, derived_root / "epilepsy_apac_children_apac_count_series.csv")
    save_csv(pooled_all, derived_root / "epilepsy_apac_children_pooled_rates.csv")

    save_csv(table1, table_root / "epilepsy_apac_children_table_1_2023_summary.csv")
    save_csv(table2, table_root / "epilepsy_apac_children_table_2_trend_eapc.csv")
    save_csv(table3, table_root / "epilepsy_apac_children_table_3_age_sex_2023.csv")
    save_csv(country_summary, table_root / "epilepsy_apac_children_table_4_country_ranking_2023.csv")
    save_json(qc, table_root / "epilepsy_apac_children_qc.json")
    save_json(key_metrics, table_root / "epilepsy_apac_children_key_metrics.json")

    plot_aggregate_trends(aggregate_counts, aggregate_pooled, figure_root)
    plot_subregion_rate_trends(pooled_all, figure_root, config)
    plot_age_sex_heatmap(table3, figure_root)
    plot_country_rankings(country_summary, figure_root)

    save_markdown(results_draft, manuscript_root / "results_draft.md")
    save_markdown(figure_legends, manuscript_root / "figure_legends.md")


if __name__ == "__main__":
    main()
