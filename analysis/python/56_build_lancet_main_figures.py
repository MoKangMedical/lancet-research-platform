#!/usr/bin/env python3
"""Build a Lancet-style figure package for the DR-T2D manuscript."""

from __future__ import annotations

from pathlib import Path

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter
from matplotlib.patches import FancyBboxPatch


PROJECT_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/04_多期刊投稿包/GBD2023_UKB_DR_T2D_2026-03-07/journal_01_eClinicalMedicine/lancet_main_assets"
)
GBD_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/04_多期刊投稿包/GBD2023_UKB_DR_T2D_2026-03-07/journal_01_eClinicalMedicine/gbd_2023_results"
)
UKB_DATA = Path("/Users/apple/Desktop/lancet-research-platform/data/gold/ukb_dr_t2d_analysis.csv")
UKB_RESULTS = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/02_UKB结果/ukb_dr_t2d"
)

COLORS = {
    "ink": "#222222",
    "muted": "#666666",
    "grid": "#d9d9d9",
    "t2d": "#b85c38",
    "t2d_fill": "#efd7cf",
    "vision": "#3f6f8c",
    "vision_fill": "#d8e6ef",
    "ref": "#b0b0b0",
    "ret_only": "#8d8d8d",
    "t2d_only": "#bc6c25",
    "both": "#355070",
    "accent": "#6b8f71",
}


def apply_lancet_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "figure.dpi": 180,
        "savefig.dpi": 320,
        "axes.facecolor": "white",
        "figure.facecolor": "white",
        "axes.edgecolor": COLORS["ink"],
        "axes.linewidth": 0.8,
        "axes.labelcolor": COLORS["ink"],
        "xtick.color": COLORS["ink"],
        "ytick.color": COLORS["ink"],
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 8,
    })


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(-0.13, 1.06, label, transform=ax.transAxes, fontsize=12, fontweight="bold", va="top", ha="left")


def style_axis(ax: plt.Axes, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis=grid_axis, color=COLORS["grid"], linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)


def save_figure(fig: plt.Figure, basename: str) -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(PROJECT_DIR / f"{basename}.png", bbox_inches="tight")
    fig.savefig(PROJECT_DIR / f"{basename}.pdf", bbox_inches="tight")
    plt.close(fig)


def load_gbd_series(filename: str, entity: str, measure: str, metric: str) -> pd.DataFrame:
    df = pd.read_csv(GBD_DIR / filename)
    scope_mask = df.get("location_scope", pd.Series(index=df.index, dtype=object)).eq("global")
    if "location_name" in df.columns:
        scope_mask = scope_mask | df["location_name"].astype(str).eq("Global")
    keep = (
        (df["entity_label"] == entity)
        & (df["measure_name"] == measure)
        & (df["metric_name"] == metric)
        & scope_mask
        & (df["sex_name"] == "Both")
    )
    return df.loc[keep].sort_values("year").copy()


def load_ukb_complete_case() -> pd.DataFrame:
    df = pd.read_csv(UKB_DATA, parse_dates=["baseline_date", "censor_date", "death_date", "mace_date", "hf_date"])
    df["t2d_analysis"] = (
        (df["t2d"] == 1)
        | (df["hba1c"].fillna(-1) >= 48)
        | (df["glucose"].fillna(-1) >= 11.1)
    ).astype(int)
    df["joint_analysis"] = df["t2d_analysis"] * 2 + df["retinopathy"]
    df["joint_label_analysis"] = df["joint_analysis"].map({
        0: "No T2D / No retinopathy",
        1: "No T2D / Retinopathy",
        2: "T2D / No retinopathy",
        3: "T2D / Retinopathy",
    })
    covars = [
        "age_baseline", "sex", "white_ethnicity", "townsend", "bmi", "sbp",
        "cholesterol_total", "hba1c", "smoking_former", "smoking_current",
    ]
    df = df[df["prev_cvd"] == 0].copy()
    df = df[df[covars + ["followup_allcause_years", "followup_mace_years", "event_allcause", "event_mace"]].notna().all(axis=1)].copy()
    df = df[(df["followup_allcause_years"] > 0) & (df["followup_mace_years"] > 0)].copy()
    return df


def draw_box(ax: plt.Axes, xy: tuple[float, float], width: float, height: float, title: str, body: list[str], fc: str) -> None:
    x0, y0 = xy
    patch = FancyBboxPatch(
        (x0, y0),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=0.9,
        edgecolor=COLORS["ink"],
        facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x0 + 0.02, y0 + height - 0.04, title, fontsize=11, fontweight="bold", ha="left", va="top", color=COLORS["ink"])
    ax.text(x0 + 0.02, y0 + height - 0.10, "\n".join(body), fontsize=8.8, ha="left", va="top", color=COLORS["ink"], linespacing=1.35)


def build_figure_1() -> None:
    apply_lancet_style()
    fig = plt.figure(figsize=(13.5, 7.4))
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.01, 0.98, "Figure 1. Dual-source study design and analytical profile", fontsize=14, fontweight="bold", ha="left", va="top")

    draw_box(
        ax,
        (0.03, 0.59),
        0.42,
        0.28,
        "Global burden arm: GBD 2023",
        [
            "Official Results Tool extraction",
            "1990-2023, global + 21 regions + 204 countries/territories",
            "T2D prevalence and DALYs",
            "T2D-related blindness and vision loss as the public retinal-burden proxy",
        ],
        COLORS["vision_fill"],
    )
    draw_box(
        ax,
        (0.03, 0.20),
        0.42,
        0.28,
        "Participant-level arm: UK Biobank",
        [
            "502,409 adults in source extract",
            "20,147 excluded for prevalent myocardial infarction, stroke, or heart failure",
            "482,262 participants in incident cohort",
            "Adjusted survival models for all-cause mortality and MACE",
        ],
        "#f2ece8",
    )
    draw_box(
        ax,
        (0.54, 0.59),
        0.40,
        0.28,
        "GBD outputs used in the main manuscript",
        [
            "Global temporal trends with uncertainty intervals",
            "EAPC of age-standardised burden",
            "Regional, country, sex, and severity heterogeneity",
            "Interpretation limited to ecological burden, not participant-level causation",
        ],
        "#f6f6f6",
    )
    draw_box(
        ax,
        (0.54, 0.20),
        0.40,
        0.28,
        "UK Biobank outputs used in the main manuscript",
        [
            "Joint exposure groups: no T2D/no retinal disease, retinal disease only, T2D only, T2D plus retinal disease",
            "119,237 complete-case participants for all-cause mortality",
            "119,235 complete-case participants for MACE",
            "Lead claim: joint prognostic enrichment, not strong statistical interaction",
        ],
        "#f6f6f6",
    )

    ax.annotate("", xy=(0.50, 0.73), xytext=(0.45, 0.73), arrowprops=dict(arrowstyle="->", lw=1.0, color=COLORS["ink"]))
    ax.annotate("", xy=(0.50, 0.34), xytext=(0.45, 0.34), arrowprops=dict(arrowstyle="->", lw=1.0, color=COLORS["ink"]))
    ax.text(
        0.50,
        0.53,
        "Integrated interpretation:\nRising global burden plus a clinically high-risk subgroup",
        ha="center",
        va="center",
        fontsize=9.4,
        fontweight="bold",
        color=COLORS["ink"],
    )

    ax.text(
        0.03,
        0.06,
        "Public GBD 2023 access did not expose diabetic retinopathy as a stand-alone cause at extraction. "
        "The burden arm therefore uses blindness and vision loss attributable to type 2 diabetes as the closest public proxy for diabetes-related retinal burden.",
        fontsize=8.5,
        color=COLORS["muted"],
        ha="left",
        va="bottom",
    )
    save_figure(fig, "Figure_1_Study_Design_Lancet")


def build_figure_2() -> None:
    apply_lancet_style()
    fig = plt.figure(figsize=(13.2, 8.8))
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.30, wspace=0.20)

    specs = [
        ("A", "gbd2023_t2d_prevalence_asr_global_region_country.csv", "Type 2 diabetes", "Prevalence", "Rate", "Age-standardised prevalence", COLORS["t2d"], COLORS["t2d_fill"], "EAPC 1.27%"),
        ("B", "gbd2023_t2d_dalys_asr_global_region_country.csv", "Type 2 diabetes", "DALYs", "Rate", "Age-standardised DALYs", COLORS["t2d"], COLORS["t2d_fill"], "EAPC 0.94%"),
        ("C", "gbd2023_t2d_visionloss_global_core.csv", "T2D-related vision loss", "Prevalence", "Rate", "Age-standardised prevalence", COLORS["vision"], COLORS["vision_fill"], "EAPC 2.13%"),
        ("D", "gbd2023_t2d_visionloss_global_core.csv", "T2D-related vision loss", "YLDs", "Rate", "Age-standardised YLDs", COLORS["vision"], COLORS["vision_fill"], "EAPC 2.10%"),
    ]

    for i, (lab, filename, entity, measure, metric, title, line_c, fill_c, eapc_text) in enumerate(specs):
        ax = fig.add_subplot(gs[i // 2, i % 2])
        df = load_gbd_series(filename, entity, measure, metric)
        ax.fill_between(df["year"], df["lower"], df["upper"], color=fill_c, alpha=0.9, linewidth=0)
        ax.plot(df["year"], df["val"], color=line_c, linewidth=2.4)
        style_axis(ax, "y")
        panel_label(ax, lab)
        ax.set_title(title, loc="left", pad=8)
        ax.set_xlabel("Year")
        ax.set_ylabel("Rate per 100,000")
        start = df.iloc[0]
        end = df.iloc[-1]
        ax.scatter([start["year"], end["year"]], [start["val"], end["val"]], color=line_c, s=18, zorder=3)
        ax.text(start["year"] + 0.5, start["val"], f"1990: {start['val']:.1f}", fontsize=8.5, va="bottom", color=COLORS["ink"])
        ax.text(end["year"] - 6.2, end["val"], f"2023: {end['val']:.1f}", fontsize=8.5, va="bottom", color=COLORS["ink"])
        ax.text(0.98, 0.10, eapc_text, transform=ax.transAxes, ha="right", fontsize=9, color=COLORS["muted"])

    fig.suptitle("Figure 2. Global age-standardised burden trends from GBD 2023", x=0.02, y=0.99, ha="left", fontsize=14, fontweight="bold")
    save_figure(fig, "Figure_2_GBD_Trends_Lancet")


def errorbar_rank(ax: plt.Axes, df: pd.DataFrame, label_col: str, title: str, color: str, panel: str) -> None:
    df = df.copy().sort_values("val", ascending=True)
    y = np.arange(len(df))
    xerr = np.vstack([df["val"] - df["lower"], df["upper"] - df["val"]])
    ax.errorbar(df["val"], y, xerr=xerr, fmt="none", ecolor=COLORS["muted"], elinewidth=1.0, capsize=2)
    ax.scatter(df["val"], y, color=color, s=28, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(df[label_col])
    ax.set_xlabel("Rate per 100,000")
    ax.set_title(title, loc="left", pad=8)
    style_axis(ax, "x")
    panel_label(ax, panel)


def build_figure_3() -> None:
    apply_lancet_style()
    region = pd.read_csv(GBD_DIR / "gbd2023_region_2023_prevalence_asr.csv")
    country = pd.read_csv(GBD_DIR / "gbd2023_country_top10_2023_prevalence_asr.csv")
    sex = pd.read_csv(GBD_DIR / "gbd2023_global_sex_2023_prevalence_asr.csv")
    severity = pd.read_csv(GBD_DIR / "gbd2023_t2d_visionloss_severity_prevalence_asr_global_2023.csv")

    fig = plt.figure(figsize=(13.4, 9.2))
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.34)

    ax1 = fig.add_subplot(gs[0, 0])
    errorbar_rank(
        ax1,
        region[region["entity_label"] == "Type 2 diabetes"].head(8),
        "location_short_name",
        "Top regional age-standardised prevalence of type 2 diabetes in 2023",
        COLORS["t2d"],
        "A",
    )

    ax2 = fig.add_subplot(gs[0, 1])
    errorbar_rank(
        ax2,
        region[region["entity_label"] == "T2D-related vision loss"].head(8),
        "location_short_name",
        "Top regional age-standardised prevalence of T2D-related vision loss in 2023",
        COLORS["vision"],
        "B",
    )

    ax3 = fig.add_subplot(gs[1, 0])
    country_vis = country[country["entity_label"] == "T2D-related vision loss"].copy().head(10).sort_values("val", ascending=True)
    y = np.arange(len(country_vis))
    ax3.hlines(y, 0, country_vis["val"], color=COLORS["vision_fill"], linewidth=2.5)
    ax3.scatter(country_vis["val"], y, color=COLORS["vision"], s=30)
    ax3.set_yticks(y)
    ax3.set_yticklabels(country_vis["location_name"])
    ax3.set_xlabel("Rate per 100,000")
    ax3.set_title("Top country age-standardised prevalence of T2D-related vision loss in 2023", loc="left", pad=8)
    style_axis(ax3, "x")
    panel_label(ax3, "C")

    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis("off")
    panel_label(ax4, "D")
    ax4.set_title("Sex contrast and severity structure in 2023", loc="left", pad=8)
    sex_t2d = sex[sex["entity_label"] == "Type 2 diabetes"].set_index("sex_name")["val"]
    sex_vis = sex[sex["entity_label"] == "T2D-related vision loss"].set_index("sex_name")["val"]
    sev_both = severity[severity["sex_name"] == "Both"].copy().sort_values("val", ascending=True)

    sex_ax = ax4.inset_axes([0.02, 0.57, 0.92, 0.33])
    ratios = pd.Series({
        "Type 2 diabetes": sex_t2d["Female"] / sex_t2d["Male"],
        "T2D-related vision loss": sex_vis["Female"] / sex_vis["Male"],
    }).sort_values()
    sex_y = np.arange(len(ratios))
    sex_ax.barh(sex_y, ratios.values, color=[COLORS["t2d"], COLORS["vision"]])
    sex_ax.set_yticks(sex_y)
    sex_ax.set_yticklabels(ratios.index)
    sex_ax.axvline(1.0, color=COLORS["muted"], linestyle="--", linewidth=0.9)
    sex_ax.set_xlabel("Female-to-male rate ratio")
    sex_ax.set_xlim(0, 1.5)
    style_axis(sex_ax, "x")
    sex_ax.spines["left"].set_visible(False)
    for yi, val in zip(sex_y, ratios.values):
        sex_ax.text(val + 0.03, yi, f"{val:.2f}", va="center", fontsize=8.5)

    sev_ax = ax4.inset_axes([0.02, 0.08, 0.92, 0.33])
    sev_y = np.arange(len(sev_both))
    sev_ax.barh(sev_y, sev_both["val"], color=COLORS["accent"])
    sev_ax.set_yticks(sev_y)
    sev_ax.set_yticklabels(sev_both["rei_name"])
    sev_ax.set_xlabel("Rate per 100,000")
    style_axis(sev_ax, "x")
    sev_ax.spines["left"].set_visible(False)
    for yi, val in zip(sev_y, sev_both["val"]):
        sev_ax.text(val + 0.5, yi, f"{val:.1f}", va="center", fontsize=8.5)

    fig.suptitle("Figure 3. Geographic, sex, and severity heterogeneity in GBD 2023", x=0.02, y=0.99, ha="left", fontsize=14, fontweight="bold")
    save_figure(fig, "Figure_3_GBD_Heterogeneity_Lancet")


def plot_km(ax: plt.Axes, df: pd.DataFrame, duration_col: str, event_col: str, title: str, panel: str) -> None:
    groups = [
        (0, "No T2D / No retinopathy", COLORS["ref"], "-"),
        (1, "No T2D / Retinopathy", COLORS["ret_only"], (0, (2, 1))),
        (2, "T2D / No retinopathy", COLORS["t2d_only"], "-"),
        (3, "T2D / Retinopathy", COLORS["both"], "-"),
    ]
    kmfs = []
    for group_id, label, color, ls in groups:
        g = df[df["joint_analysis"] == group_id]
        kmf = KaplanMeierFitter()
        kmf.fit(g[duration_col], event_observed=g[event_col], label=f"{label} (n={len(g):,})")
        kmf.plot_survival_function(ax=ax, ci_show=False, color=color, linestyle=ls, linewidth=2.1 if group_id in [0, 2, 3] else 1.6)
        kmfs.append(kmf)
    style_axis(ax, "y")
    panel_label(ax, panel)
    ax.set_title(title, loc="left", pad=8)
    ax.set_xlabel("Follow-up (years)")
    ax.set_ylabel("Survival probability")
    ax.set_xlim(0, 16)
    ax.set_ylim(0.72 if event_col == "event_allcause" else 0.80, 1.01)
    ax.legend(frameon=False, loc="lower left")
    ax.text(0.99, 0.03, "Retinopathy-only group is sparse", transform=ax.transAxes, ha="right", va="bottom", fontsize=7.8, color=COLORS["muted"])


def build_figure_4() -> None:
    apply_lancet_style()
    df = load_ukb_complete_case()
    cox = pd.read_csv(UKB_RESULTS / "cox_joint_groups.csv")
    cox = cox[cox["term"].isin(["joint_1", "joint_2", "joint_3"])].copy()

    group_map = {
        "joint_1": "No T2D / Retinopathy",
        "joint_2": "T2D / No retinopathy",
        "joint_3": "T2D / Retinopathy",
    }
    outcome_map = {"event_allcause": "All-cause mortality", "event_mace": "MACE"}
    cox["group_label"] = cox["term"].map(group_map)
    cox["outcome_label"] = cox["outcome"].map(outcome_map)

    fig = plt.figure(figsize=(13.4, 10.8))
    gs = gridspec.GridSpec(2, 2, height_ratios=[1, 1.15], hspace=0.48, wspace=0.28)

    ax1 = fig.add_subplot(gs[0, 0])
    plot_km(ax1, df, "followup_allcause_years", "event_allcause", "All-cause mortality", "A")

    ax2 = fig.add_subplot(gs[0, 1])
    plot_km(ax2, df, "followup_mace_years", "event_mace", "Major adverse cardiovascular events", "B")

    ax3 = fig.add_subplot(gs[1, :])
    order = [
        ("All-cause mortality", "No T2D / Retinopathy"),
        ("All-cause mortality", "T2D / No retinopathy"),
        ("All-cause mortality", "T2D / Retinopathy"),
        ("MACE", "No T2D / Retinopathy"),
        ("MACE", "T2D / No retinopathy"),
        ("MACE", "T2D / Retinopathy"),
    ]
    plot_df = pd.DataFrame(order, columns=["outcome_label", "group_label"]).merge(cox, on=["outcome_label", "group_label"], how="left")
    y = np.arange(len(plot_df))[::-1]
    colors = [COLORS["both"] if "Retinopathy" in g and "No T2D" not in g else COLORS["t2d_only"] if "T2D / No retinopathy" in g else COLORS["ret_only"] for g in plot_df["group_label"]]
    ax3.errorbar(
        plot_df["exp(coef)"],
        y,
        xerr=np.vstack([
            plot_df["exp(coef)"] - plot_df["exp(coef) lower 95%"],
            plot_df["exp(coef) upper 95%"] - plot_df["exp(coef)"],
        ]),
        fmt="none",
        ecolor=COLORS["muted"],
        elinewidth=1.3,
        capsize=2.5,
        zorder=2,
    )
    ax3.scatter(plot_df["exp(coef)"], y, c=colors, s=40, zorder=3)
    ax3.axvline(1.0, color=COLORS["muted"], linestyle="--", linewidth=1.0)
    ax3.set_yticks(y)
    ax3.set_yticklabels([f"{o} | {g}" for o, g in zip(plot_df["outcome_label"], plot_df["group_label"])])
    ax3.set_xlabel("Adjusted hazard ratio")
    ax3.set_title("Adjusted associations versus the no T2D and no retinopathy reference group", loc="left", pad=8)
    style_axis(ax3, "x")
    panel_label(ax3, "C")
    ax3.set_xlim(0, 6.6)
    for yi, hr, lo, hi in zip(y, plot_df["exp(coef)"], plot_df["exp(coef) lower 95%"], plot_df["exp(coef) upper 95%"]):
        ax3.text(6.72, yi, f"{hr:.2f} ({lo:.2f}-{hi:.2f})", fontsize=8.5, va="center")
    ax3.text(0.0, -0.18, "Models adjusted for age, sex, white ethnicity, Townsend deprivation, BMI, systolic blood pressure, total cholesterol, HbA1c, former smoking, and current smoking.", transform=ax3.transAxes, fontsize=8.3, color=COLORS["muted"])

    fig.suptitle("Figure 4. UK Biobank outcome panels for joint T2D-retinal disease status", x=0.02, y=0.99, ha="left", fontsize=14, fontweight="bold")
    save_figure(fig, "Figure_4_UKB_Outcomes_Lancet")


def main() -> None:
    build_figure_1()
    build_figure_2()
    build_figure_3()
    build_figure_4()
    print(f"Lancet-style figures saved to {PROJECT_DIR}")


if __name__ == "__main__":
    main()
