#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

LOCATION_ORDER = [
    "China",
    "Japan",
    "Mongolia",
    "Democratic People's Republic of Korea",
    "Republic of Korea",
    "Taiwan",
]
AGGREGATE_LABEL = "East Asia study-scope aggregate"
MEASURE_ORDER = ["Incidence", "Prevalence", "Deaths", "DALYs"]
MEASURE_MAP = {
    "DALYs (Disability-Adjusted Life Years)": "DALYs",
    "Deaths": "Deaths",
    "Incidence": "Incidence",
    "Prevalence": "Prevalence",
}
AGE_ORDER = [
    "<5 years",
    "5-9 years",
    "10-14 years",
    "15-19 years",
    "20-24 years",
    "25-29 years",
    "30-34 years",
    "35-39 years",
]
RATE_SCALE = 100000.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build manuscript-oriented phase-three outputs for the East Asia female under-40 asthma study."
    )
    parser.add_argument("--study-root", required=True)
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=False)


def save_markdown(text: str, path: Path) -> None:
    ensure_dir(path.parent)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def save_figure(fig: plt.Figure, out_base: Path) -> None:
    ensure_dir(out_base.parent)
    fig.savefig(out_base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(out_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def attach_display_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.assign(
        measure_short=lambda frame: frame["measure_name"].map(MEASURE_MAP).fillna(frame["measure_name"]),
        age_name=lambda frame: pd.Categorical(frame["age_name"], categories=AGE_ORDER, ordered=True),
        location_name=lambda frame: pd.Categorical(frame["location_name"], categories=LOCATION_ORDER, ordered=True),
    )
    return out


def load_inputs(study_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    derived_root = study_root / "data" / "derived"
    tables_root = study_root / "outputs" / "tables"
    core = pd.read_csv(derived_root / "asthma_east_asia_female_u40_core_clean.csv")
    risk_deaths = pd.read_csv(derived_root / "asthma_east_asia_female_u40_risk_deaths_clean.csv")
    risk_dalys = pd.read_csv(derived_root / "asthma_east_asia_female_u40_risk_dalys_clean.csv")
    under40_counts = pd.read_csv(tables_root / "asthma_east_asia_female_u40_table_2023_summary.csv")
    return core, risk_deaths, risk_dalys, under40_counts


def build_pooled_rates(core: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    core = attach_display_fields(core)
    counts = core.loc[core["metric_name"] == "Number"].copy()
    rates = core.loc[core["metric_name"] == "Rate"].copy()
    merge_cols = [
        "population_group_id",
        "population_group_name",
        "measure_id",
        "measure_name",
        "measure_short",
        "location_id",
        "location_name",
        "sex_id",
        "sex_name",
        "age_id",
        "age_name",
        "cause_id",
        "cause_name",
        "year_id",
    ]
    rate_values = rates[merge_cols + ["val"]].rename(columns={"val": "age_specific_rate"})
    merged = counts.merge(rate_values, on=merge_cols, how="inner", validate="one_to_one")
    merged = merged.assign(
        population_est=lambda frame: np.where(
            frame["age_specific_rate"] > 0,
            frame["val"] / frame["age_specific_rate"] * RATE_SCALE,
            np.nan,
        )
    )

    pooled = (
        merged.groupby(
            ["measure_short", "measure_name", "location_id", "location_name", "year_id"],
            observed=True,
            as_index=False,
        )[["val", "population_est"]]
        .sum()
        .rename(columns={"val": "under40_count"})
    )
    pooled = pooled.assign(
        pooled_rate=lambda frame: frame["under40_count"] / frame["population_est"] * RATE_SCALE,
        location_type="constituent_location",
    )

    aggregate = (
        merged.groupby(["measure_short", "measure_name", "year_id"], as_index=False)[["val", "population_est"]]
        .sum()
        .rename(columns={"val": "under40_count"})
        .assign(
            location_id=-1,
            location_name=AGGREGATE_LABEL,
            pooled_rate=lambda frame: frame["under40_count"] / frame["population_est"] * RATE_SCALE,
            location_type="study_scope_aggregate",
        )
    )

    pooled_all = pd.concat([pooled, aggregate], ignore_index=True)
    pooled_all["measure_short"] = pd.Categorical(pooled_all["measure_short"], categories=MEASURE_ORDER, ordered=True)
    pooled_all["location_name"] = pd.Categorical(
        pooled_all["location_name"], categories=LOCATION_ORDER + [AGGREGATE_LABEL], ordered=True
    )

    counts_2023 = pooled_all.loc[pooled_all["year_id"] == 2023].copy()
    counts_2023["pooled_rate_fmt"] = counts_2023["pooled_rate"].map(lambda value: f"{value:,.1f}")
    return merged, pooled_all.sort_values(["measure_short", "location_name", "year_id"]), counts_2023


def fit_log_linear_rate(year: pd.Series, rate: pd.Series) -> dict[str, float]:
    mask = rate.gt(0) & year.notna()
    x = year.loc[mask].to_numpy(dtype=float)
    y = np.log(rate.loc[mask].to_numpy(dtype=float))
    n = len(x)
    if n < 3:
        raise ValueError("Need at least 3 positive yearly rate observations for EAPC.")
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
    slope_lower = slope - z * se_slope
    slope_upper = slope + z * se_slope
    return {
        "n_obs": float(n),
        "slope": slope,
        "slope_lower": slope_lower,
        "slope_upper": slope_upper,
    }


def build_eapc_table(pooled_rates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (measure_short, location_name, location_type), group in pooled_rates.groupby(
        ["measure_short", "location_name", "location_type"], observed=True
    ):
        fit = fit_log_linear_rate(group["year_id"], group["pooled_rate"])
        rate_1990 = group.loc[group["year_id"] == 1990, "pooled_rate"].iloc[0]
        rate_2023 = group.loc[group["year_id"] == 2023, "pooled_rate"].iloc[0]
        eapc = 100.0 * (np.exp(fit["slope"]) - 1.0)
        eapc_lower = 100.0 * (np.exp(fit["slope_lower"]) - 1.0)
        eapc_upper = 100.0 * (np.exp(fit["slope_upper"]) - 1.0)
        rows.append(
            {
                "measure_short": str(measure_short),
                "location_name": str(location_name),
                "location_type": location_type,
                "rate_1990": rate_1990,
                "rate_2023": rate_2023,
                "absolute_rate_change": rate_2023 - rate_1990,
                "percent_rate_change": ((rate_2023 - rate_1990) / rate_1990) * 100.0,
                "eapc": eapc,
                "eapc_lower": eapc_lower,
                "eapc_upper": eapc_upper,
                "n_obs": int(fit["n_obs"]),
                "trend_direction": "increase" if eapc > 0 else "decrease",
            }
        )
    out = pd.DataFrame(rows)
    out["measure_short"] = pd.Categorical(out["measure_short"], categories=MEASURE_ORDER, ordered=True)
    out["location_name"] = pd.Categorical(
        out["location_name"], categories=LOCATION_ORDER + [AGGREGATE_LABEL], ordered=True
    )
    return out.sort_values(["measure_short", "location_type", "location_name"]).reset_index(drop=True)


def build_table1(
    under40_summary_2023: pd.DataFrame,
    pooled_2023: pd.DataFrame,
    pooled_all: pd.DataFrame,
) -> pd.DataFrame:
    counts = under40_summary_2023.copy()
    counts["location_type"] = "constituent_location"
    counts = counts.rename(columns={"under40_count": "count_2023"})
    counts = counts.rename(columns={"under40_count_ui_fmt": "count_2023_ui"})

    aggregate_counts = (
        pooled_all.loc[(pooled_all["year_id"] == 2023) & (pooled_all["location_type"] == "study_scope_aggregate")]
        .copy()
        .assign(
            count_2023=lambda frame: frame["under40_count"],
            count_2023_ui=lambda frame: frame["under40_count"].map(lambda value: f"{value:,.1f}"),
            year_id=2023,
        )[["measure_short", "location_name", "location_type", "year_id", "count_2023", "count_2023_ui"]]
    )

    pooled_subset = pooled_2023[
        ["measure_short", "location_name", "location_type", "population_est", "pooled_rate", "pooled_rate_fmt"]
    ].rename(columns={"population_est": "population_2023"})

    table1 = pd.concat(
        [
            counts[
                ["measure_short", "location_name", "location_type", "year_id", "count_2023", "count_2023_ui"]
            ],
            aggregate_counts,
        ],
        ignore_index=True,
    ).merge(
        pooled_subset,
        on=["measure_short", "location_name", "location_type"],
        how="left",
        validate="one_to_one",
    )
    table1["measure_short"] = pd.Categorical(table1["measure_short"], categories=MEASURE_ORDER, ordered=True)
    table1["location_name"] = pd.Categorical(
        table1["location_name"], categories=[AGGREGATE_LABEL] + LOCATION_ORDER, ordered=True
    )
    return table1.sort_values(["measure_short", "location_name"]).reset_index(drop=True)


def build_age_profile(core: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    core = attach_display_fields(core)
    counts = core.loc[(core["metric_name"] == "Number") & (core["year_id"] == 2023)].copy()
    rates = core.loc[(core["metric_name"] == "Rate") & (core["year_id"] == 2023)].copy()
    merge_cols = [
        "measure_id",
        "measure_name",
        "measure_short",
        "location_id",
        "location_name",
        "age_id",
        "age_name",
        "year_id",
    ]
    age_profile = counts.merge(
        rates[merge_cols + ["val"]].rename(columns={"val": "rate_2023"}),
        on=merge_cols,
        how="inner",
        validate="one_to_one",
    )
    age_profile["count_share_pct"] = (
        age_profile["val"] / age_profile.groupby(["measure_short", "location_name"], observed=True)["val"].transform("sum")
    ) * 100.0
    age_profile = age_profile.rename(columns={"val": "count_2023"})
    peak_age = (
        age_profile.sort_values(["measure_short", "location_name", "rate_2023"], ascending=[True, True, False])
        .groupby(["measure_short", "location_name"], observed=True, as_index=False)
        .first()[
            ["measure_short", "location_name", "age_name", "rate_2023", "count_2023", "count_share_pct"]
        ]
        .rename(columns={"age_name": "peak_age_group"})
    )
    return age_profile.sort_values(["measure_short", "location_name", "age_name"]).reset_index(drop=True), peak_age


def build_risk_table(
    risk_deaths: pd.DataFrame,
    risk_dalys: pd.DataFrame,
    table1: pd.DataFrame,
) -> pd.DataFrame:
    risk_frames = []
    for measure_short, risk_df in [("Deaths", risk_deaths), ("DALYs", risk_dalys)]:
        filtered = attach_display_fields(risk_df)
        filtered = filtered.loc[(filtered["metric_name"] == "Number") & (filtered["year_id"] == 2023)].copy()
        summary = (
            filtered.groupby("rei_name", as_index=False)[["val", "lower", "upper"]]
            .sum()
            .rename(columns={"val": "attributable_count_2023", "lower": "lower_sum", "upper": "upper_sum"})
        )
        total = table1.loc[
            (table1["measure_short"] == measure_short) & (table1["location_name"] == AGGREGATE_LABEL), "count_2023"
        ].iloc[0]
        summary["measure_short"] = measure_short
        summary["share_of_total_pct"] = summary["attributable_count_2023"] / total * 100.0
        summary["rank_2023"] = summary["attributable_count_2023"].rank(method="first", ascending=False).astype(int)
        risk_frames.append(summary)
    risk_table = pd.concat(risk_frames, ignore_index=True)
    risk_table["measure_short"] = pd.Categorical(risk_table["measure_short"], categories=["Deaths", "DALYs"], ordered=True)
    return risk_table.sort_values(["measure_short", "rank_2023"]).reset_index(drop=True)


def format_count(value: float) -> str:
    return f"{value:,.1f}"


def format_rate(value: float) -> str:
    return f"{value:,.1f}"


def format_pct(value: float) -> str:
    return f"{value:.2f}%"


def plot_counts_trends(under40_counts: pd.DataFrame, out_base: Path) -> None:
    sns.set_theme(style="whitegrid")
    palette = dict(zip(LOCATION_ORDER, sns.color_palette("Set2", n_colors=len(LOCATION_ORDER))))
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=True)
    for ax, measure in zip(axes.flatten(), MEASURE_ORDER):
        subset = under40_counts.loc[under40_counts["measure_short"] == measure].copy()
        sns.lineplot(
            data=subset,
            x="year_id",
            y="under40_count",
            hue="location_name",
            hue_order=LOCATION_ORDER,
            palette=palette,
            linewidth=2.2,
            ax=ax,
        )
        ax.set_title(measure)
        ax.set_xlabel("Year")
        ax.set_ylabel("Under-40 summed count")
        ax.legend(title="Location", fontsize=8, title_fontsize=9)
    fig.suptitle("Figure 1. Asthma burden counts in females younger than 40 years across East Asian locations, 1990-2023", fontsize=14)
    fig.tight_layout()
    save_figure(fig, out_base)


def plot_rate_trends(pooled_rates: pd.DataFrame, eapc_table: pd.DataFrame, out_base: Path) -> None:
    sns.set_theme(style="whitegrid")
    palette = dict(zip(LOCATION_ORDER, sns.color_palette("Set2", n_colors=len(LOCATION_ORDER))))
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=True)
    for ax, measure in zip(axes.flatten(), MEASURE_ORDER):
        subset = pooled_rates.loc[
            (pooled_rates["measure_short"] == measure) & (pooled_rates["location_type"] == "constituent_location")
        ].copy()
        aggregate = pooled_rates.loc[
            (pooled_rates["measure_short"] == measure) & (pooled_rates["location_type"] == "study_scope_aggregate")
        ].copy()
        sns.lineplot(
            data=subset,
            x="year_id",
            y="pooled_rate",
            hue="location_name",
            hue_order=LOCATION_ORDER,
            palette=palette,
            linewidth=2.0,
            ax=ax,
            legend=False,
        )
        sns.lineplot(
            data=aggregate,
            x="year_id",
            y="pooled_rate",
            color="black",
            linewidth=2.6,
            linestyle="--",
            ax=ax,
            label=AGGREGATE_LABEL,
        )
        agg_eapc = eapc_table.loc[
            (eapc_table["measure_short"] == measure) & (eapc_table["location_name"] == AGGREGATE_LABEL)
        ].iloc[0]
        ax.text(
            0.02,
            0.98,
            "\n".join(
                [
                    "Study-scope aggregate",
                    f"EAPC {agg_eapc['eapc']:.2f}% ({agg_eapc['eapc_lower']:.2f} to {agg_eapc['eapc_upper']:.2f})",
                ]
            ),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8.5,
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#cccccc"},
        )
        ax.set_title(measure)
        ax.set_xlabel("Year")
        ax.set_ylabel("Pooled crude rate per 100,000")
    handles = [
        plt.Line2D([0], [0], color=palette[name], lw=2.2, label=name)
        for name in LOCATION_ORDER
    ] + [plt.Line2D([0], [0], color="black", lw=2.6, linestyle="--", label=AGGREGATE_LABEL)]
    fig.legend(handles=handles, loc="lower center", ncols=4, bbox_to_anchor=(0.5, -0.02), frameon=False)
    fig.suptitle(
        "Figure 2. Pooled crude asthma rates in females younger than 40 years across East Asia, 1990-2023",
        fontsize=14,
    )
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    save_figure(fig, out_base)


def plot_age_heatmaps(age_profile: pd.DataFrame, out_base: Path) -> None:
    sns.set_theme(style="white")
    fig, axes = plt.subplots(2, 2, figsize=(15, 9))
    for ax, measure in zip(axes.flatten(), MEASURE_ORDER):
        subset = age_profile.loc[age_profile["measure_short"] == measure].copy()
        pivot = subset.pivot(index="location_name", columns="age_name", values="rate_2023")
        sns.heatmap(
            pivot,
            cmap="YlOrRd",
            annot=True,
            fmt=".1f",
            linewidths=0.4,
            cbar_kws={"label": "Rate per 100,000"},
            ax=ax,
        )
        ax.set_title(measure)
        ax.set_xlabel("Age group")
        ax.set_ylabel("Location")
    fig.suptitle(
        "Figure 3. Age-specific asthma rates in 2023 among females younger than 40 years in East Asia",
        fontsize=14,
    )
    fig.tight_layout()
    save_figure(fig, out_base)


def plot_risk_rankings(risk_table: pd.DataFrame, out_base: Path) -> None:
    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), sharex=False)
    for ax, measure in zip(axes, ["Deaths", "DALYs"]):
        subset = risk_table.loc[risk_table["measure_short"] == measure].sort_values("share_of_total_pct", ascending=True)
        sns.barplot(data=subset, x="share_of_total_pct", y="rei_name", color="#c44e52", ax=ax)
        ax.set_title(measure)
        ax.set_xlabel("Attributable share of 2023 study-scope burden (%)")
        ax.set_ylabel("")
        for patch, count in zip(ax.patches, subset["attributable_count_2023"]):
            ax.text(
                patch.get_width() + 0.1,
                patch.get_y() + patch.get_height() / 2,
                f"{count:,.1f}",
                va="center",
                fontsize=8,
            )
    fig.suptitle(
        "Figure 4. Leading attributable risk factors for asthma burden among females younger than 40 years in East Asia, 2023",
        fontsize=14,
    )
    fig.tight_layout()
    save_figure(fig, out_base)


def build_results_draft(
    table1: pd.DataFrame,
    eapc_table: pd.DataFrame,
    peak_age: pd.DataFrame,
    risk_table: pd.DataFrame,
) -> str:
    aggregate_2023 = table1.loc[table1["location_name"] == AGGREGATE_LABEL].copy()
    aggregate_eapc = eapc_table.loc[eapc_table["location_name"] == AGGREGATE_LABEL].copy()
    top_location_2023 = (
        table1.loc[table1["location_type"] == "constituent_location"]
        .sort_values(["measure_short", "count_2023"], ascending=[True, False])
        .groupby("measure_short", as_index=False)
        .first()[["measure_short", "location_name", "count_2023"]]
    )
    lowest_eapc = (
        eapc_table.loc[eapc_table["location_type"] == "constituent_location"]
        .sort_values(["measure_short", "eapc"], ascending=[True, True])
        .groupby("measure_short", as_index=False)
        .first()[["measure_short", "location_name", "eapc", "eapc_lower", "eapc_upper"]]
    )
    positive_eapc = eapc_table.loc[
        (eapc_table["location_type"] == "constituent_location") & (eapc_table["eapc"] > 0)
    ].copy()
    highest_age = peak_age.sort_values("rate_2023", ascending=False).iloc[0]
    top_risks = (
        risk_table.sort_values(["measure_short", "share_of_total_pct"], ascending=[True, False])
        .groupby("measure_short", as_index=False)
        .first()[["measure_short", "rei_name", "attributable_count_2023", "share_of_total_pct"]]
    )

    agg_lookup = aggregate_2023.set_index("measure_short").to_dict("index")
    agg_eapc_lookup = aggregate_eapc.set_index("measure_short").to_dict("index")
    top_lookup = top_location_2023.set_index("measure_short").to_dict("index")
    low_lookup = lowest_eapc.set_index("measure_short").to_dict("index")
    risk_lookup = top_risks.set_index("measure_short").to_dict("index")
    positive_lines = [
        f"{row.measure_short} in {row.location_name} ({format_pct(row.eapc)})"
        for row in positive_eapc.itertuples(index=False)
    ]

    lines = [
        "# Results Draft",
        "",
        "## Burden in 2023",
        dedent(
            f"""
            Across the six East Asian locations included in the study scope, females younger than 40 years experienced an estimated
            {format_count(agg_lookup['Incidence']['count_2023'])} incident asthma cases,
            {format_count(agg_lookup['Prevalence']['count_2023'])} prevalent cases,
            {format_count(agg_lookup['Deaths']['count_2023'])} deaths, and
            {format_count(agg_lookup['DALYs']['count_2023'])} DALYs in 2023. The corresponding pooled crude rates were
            {format_rate(agg_lookup['Incidence']['pooled_rate'])},
            {format_rate(agg_lookup['Prevalence']['pooled_rate'])},
            {format_rate(agg_lookup['Deaths']['pooled_rate'])}, and
            {format_rate(agg_lookup['DALYs']['pooled_rate'])} per 100,000, respectively.
            """
        ).strip(),
        dedent(
            f"""
            China carried the largest absolute burden in 2023 for all four study outcomes, including
            {format_count(top_lookup['Incidence']['count_2023'])} incident cases,
            {format_count(top_lookup['Prevalence']['count_2023'])} prevalent cases,
            {format_count(top_lookup['Deaths']['count_2023'])} deaths, and
            {format_count(top_lookup['DALYs']['count_2023'])} DALYs.
            """
        ).strip(),
        "",
        "## Temporal Trends",
        dedent(
            f"""
            At the study-scope aggregate level, pooled crude rates declined over 1990-2023 for all four outcomes:
            incidence EAPC {format_pct(agg_eapc_lookup['Incidence']['eapc'])},
            prevalence EAPC {format_pct(agg_eapc_lookup['Prevalence']['eapc'])},
            deaths EAPC {format_pct(agg_eapc_lookup['Deaths']['eapc'])}, and
            DALYs EAPC {format_pct(agg_eapc_lookup['DALYs']['eapc'])}.
            """
        ).strip(),
        dedent(
            f"""
            Among constituent locations, the steepest decline in incidence, prevalence, and DALY rates was observed in
            {low_lookup['Incidence']['location_name']} ({format_pct(low_lookup['Incidence']['eapc'])}),
            {low_lookup['Prevalence']['location_name']} ({format_pct(low_lookup['Prevalence']['eapc'])}), and
            {low_lookup['DALYs']['location_name']} ({format_pct(low_lookup['DALYs']['eapc'])}), respectively, whereas the largest
            decline in death rates was observed in {low_lookup['Deaths']['location_name']} ({format_pct(low_lookup['Deaths']['eapc'])}).
            """
        ).strip(),
        "Exceptions to the overall decline were " + ", ".join(positive_lines) + ".",
        "",
        "## Age Pattern in 2023",
        dedent(
            f"""
            Age-specific heterogeneity remained substantial in 2023. The highest location-age cell in the rate profile was observed
            for {highest_age['measure_short']} in {highest_age['location_name']} among the {highest_age['peak_age_group']} group, at
            {format_rate(highest_age['rate_2023'])} per 100,000. Table 3 and Figure 3 provide the age-specific pattern across
            all four outcomes and all six East Asian locations.
            """
        ).strip(),
        "",
        "## Attributable Risks in 2023",
        dedent(
            f"""
            In 2023, the leading attributable risk factor for asthma deaths was {risk_lookup['Deaths']['rei_name']},
            accounting for {format_count(risk_lookup['Deaths']['attributable_count_2023'])} deaths and
            {format_pct(risk_lookup['Deaths']['share_of_total_pct'])} of the study-scope total asthma deaths. The leading
            attributable risk factor for asthma DALYs was {risk_lookup['DALYs']['rei_name']}, accounting for
            {format_count(risk_lookup['DALYs']['attributable_count_2023'])} DALYs and
            {format_pct(risk_lookup['DALYs']['share_of_total_pct'])} of the total asthma DALYs.
            """
        ).strip(),
        dedent(
            """
            High body-mass index, secondhand smoke, and occupational asthmagens dominated the attributable DALY profile,
            whereas occupational asthmagens, high body-mass index, and secondhand smoke were the three leading contributors
            to attributable asthma deaths.
            """
        ).strip(),
        "",
        "## Methods Note",
        dedent(
            """
            Under-40 pooled crude rates were derived by reconstructing age-specific population denominators from matched GBD
            counts and rates, then recomputing population-weighted rates across the eight under-40 age groups. These pooled
            crude rates are suitable for trend description and EAPC estimation, but they should not be described as
            age-standardized rates.
            """
        ).strip(),
    ]
    return "\n".join(lines)


def build_figure_legends() -> str:
    return dedent(
        """
        # Figure Legends

        **Figure 1.** Trends in asthma burden counts among females younger than 40 years in six East Asian locations, 1990-2023. Panels show incident cases, prevalent cases, deaths, and DALYs. Values represent summed age-specific counts across the eight under-40 age groups.

        **Figure 2.** Trends in pooled crude asthma rates among females younger than 40 years in East Asia, 1990-2023. Country lines represent constituent locations, and the dashed black line represents the study-scope aggregate reconstructed from the six included locations. EAPC annotations refer to the aggregate series for each outcome.

        **Figure 3.** Age-specific asthma rates in 2023 among females younger than 40 years across East Asian locations. Heatmaps display location-by-age rate matrices for incidence, prevalence, deaths, and DALYs.

        **Figure 4.** Leading attributable risk factors for asthma burden among females younger than 40 years in East Asia in 2023. Bars show the attributable share of the study-scope total burden for deaths and DALYs separately; text labels indicate attributable counts.
        """
    ).strip()


def build_qc(
    pooled_rates: pd.DataFrame,
    eapc_table: pd.DataFrame,
    age_profile: pd.DataFrame,
    risk_table: pd.DataFrame,
) -> dict[str, object]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pooled_rate_rows": int(len(pooled_rates)),
        "eapc_rows": int(len(eapc_table)),
        "age_profile_rows": int(len(age_profile)),
        "risk_rows": int(len(risk_table)),
        "study_scope_locations": LOCATION_ORDER,
        "includes_study_scope_aggregate": bool((pooled_rates["location_name"] == AGGREGATE_LABEL).any()),
        "measures": sorted({str(value) for value in pooled_rates["measure_short"].dropna().unique().tolist()}),
        "nonpositive_pooled_rates": int((pooled_rates["pooled_rate"] <= 0).sum()),
        "nonpositive_population_estimates": int((pooled_rates["population_est"] <= 0).sum()),
    }


def main() -> None:
    warnings.filterwarnings("ignore", message=".*ChainedAssignmentError.*", category=FutureWarning)
    warnings.filterwarnings("ignore", message=".*observed=False is deprecated.*", category=FutureWarning)
    args = parse_args()
    study_root = Path(args.study_root)
    derived_root = study_root / "data" / "derived"
    figures_root = study_root / "outputs" / "figures"
    tables_root = study_root / "outputs" / "tables"
    manuscript_root = study_root / "outputs" / "manuscript"

    core, risk_deaths, risk_dalys, under40_summary_2023 = load_inputs(study_root)
    under40_counts = pd.read_csv(derived_root / "asthma_east_asia_female_u40_under40_counts.csv")

    _, pooled_rates, pooled_2023 = build_pooled_rates(core)
    eapc_table = build_eapc_table(pooled_rates)
    table1 = build_table1(under40_summary_2023, pooled_2023, pooled_rates)
    age_profile, peak_age = build_age_profile(core)
    risk_table = build_risk_table(risk_deaths, risk_dalys, table1)
    results_draft = build_results_draft(table1, eapc_table, peak_age, risk_table)
    figure_legends = build_figure_legends()
    qc = build_qc(pooled_rates, eapc_table, age_profile, risk_table)

    save_csv(pooled_rates, derived_root / "asthma_east_asia_female_u40_pooled_rates.csv")
    save_csv(age_profile, derived_root / "asthma_east_asia_female_u40_age_profile_2023.csv")
    save_csv(table1, tables_root / "asthma_east_asia_female_u40_table_1_2023_burden_and_rates.csv")
    save_csv(eapc_table, tables_root / "asthma_east_asia_female_u40_table_2_pooled_rate_eapc.csv")
    save_csv(peak_age, tables_root / "asthma_east_asia_female_u40_table_3_peak_age_patterns_2023.csv")
    save_csv(risk_table, tables_root / "asthma_east_asia_female_u40_table_4_risk_attribution_2023.csv")
    save_csv(age_profile, tables_root / "asthma_east_asia_female_u40_table_s1_age_profile_2023.csv")

    plot_counts_trends(under40_counts, figures_root / "asthma_east_asia_female_u40_figure_1_counts_trends")
    plot_rate_trends(pooled_rates, eapc_table, figures_root / "asthma_east_asia_female_u40_figure_2_pooled_rate_trends")
    plot_age_heatmaps(age_profile, figures_root / "asthma_east_asia_female_u40_figure_3_age_specific_rates")
    plot_risk_rankings(risk_table, figures_root / "asthma_east_asia_female_u40_figure_4_risk_rankings")

    save_markdown(results_draft, manuscript_root / "results_draft.md")
    save_markdown(figure_legends, manuscript_root / "figure_legends.md")

    qc_path = tables_root / "asthma_east_asia_female_u40_phase3_qc.json"
    qc_path.write_text(json.dumps(qc, indent=2), encoding="utf-8")

    print(f"Wrote manuscript tables to {tables_root}")
    print(f"Wrote manuscript figures to {figures_root}")
    print(f"Wrote manuscript text to {manuscript_root}")
    print(f"Wrote QC to {qc_path}")


if __name__ == "__main__":
    main()
