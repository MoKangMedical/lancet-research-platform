#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests

from lib.plot_style import apply_pub_style


ROOT = Path("/Users/apple/Desktop/lancet-research-platform")
DEFAULT_STATE_PATH = ROOT / "output/playwright/gbdlogin_state_20260309.json"
RESULTS_URL = "https://vizhub.healthdata.org/gbd-results/php/data.php"
VERSION_ID = 8352
T2D_CAUSE_ID = 976
SEX_MAP = {1: "Male", 2: "Female", 3: "Both"}
REI_MAP = {200: "Blindness and vision loss", 229: "Moderate vision loss", 230: "Severe vision loss", 231: "Blindness"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build GBD manuscript assets for the DR-T2D eClinicalMedicine package")
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    return parser.parse_args()


def load_access_token(state_path: Path) -> str:
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    for origin in payload.get("origins", []):
        for item in origin.get("localStorage", []):
            if "accesstoken" not in item.get("name", "").lower():
                continue
            secret = json.loads(item["value"]).get("secret", "")
            if secret:
                return secret
    raise RuntimeError(f"Access token not found in {state_path}")


def post_results(token: str, payload: list[tuple[str, object]]) -> pd.DataFrame:
    response = requests.post(
        RESULTS_URL,
        data=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    return pd.DataFrame(body["data"], columns=body["cols"])


def fetch_global_series(
    token: str,
    context: str,
    measure_id: int,
    metric_id: int,
    age_id: int,
    rei_ids: list[int] | None,
    years: list[int],
    sexes: list[int],
) -> pd.DataFrame:
    payload: list[tuple[str, object]] = [
        ("version", VERSION_ID),
        ("context", context),
        ("cause[]", T2D_CAUSE_ID),
        ("measure[]", measure_id),
        ("metric[]", metric_id),
        ("age[]", age_id),
        ("location[]", 1),
        ("population_group", 1),
        ("api_version", "2023.0.0"),
        ("base", "single"),
        ("singleOrMult", "single"),
        ("idsOrNames", "ids"),
        ("rows", 500000),
        ("start_year", 1980),
        ("fetch_all_years", "false"),
        ("language", "en"),
    ]
    for year in years:
        payload.append(("year[]", year))
    for sex in sexes:
        payload.append(("sex[]", sex))
    for rei_id in rei_ids or []:
        payload.append(("rei[]", rei_id))
    return post_results(token, payload)


def compute_eapc(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (entity_label, measure_name), group in df.groupby(["entity_label", "measure_name"]):
        subset = group.sort_values("year")
        xs = subset["year"].astype(float).tolist()
        ys = [math.log(float(v)) for v in subset["val"].tolist()]
        n = len(xs)
        x_bar = sum(xs) / n
        y_bar = sum(ys) / n
        ss_xx = sum((x - x_bar) ** 2 for x in xs)
        ss_xy = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys))
        slope = ss_xy / ss_xx
        intercept = y_bar - slope * x_bar
        residual_sum = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
        variance = residual_sum / (n - 2)
        slope_se = math.sqrt(variance / ss_xx)
        rows.append(
            {
                "entity_label": entity_label,
                "measure_name": measure_name,
                "n_years": n,
                "year_start": int(xs[0]),
                "year_end": int(xs[-1]),
                "eapc": 100.0 * (math.exp(slope) - 1.0),
                "eapc_lower_95": 100.0 * (math.exp(slope - 1.96 * slope_se) - 1.0),
                "eapc_upper_95": 100.0 * (math.exp(slope + 1.96 * slope_se) - 1.0),
            }
        )
    return pd.DataFrame(rows).sort_values(["entity_label", "measure_name"]).reset_index(drop=True)


def one_row(df: pd.DataFrame, entity_label: str, measure_name: str, metric_name: str) -> pd.Series:
    return df[
        (df["entity_label"] == entity_label)
        & (df["measure_name"] == measure_name)
        & (df["metric_name"] == metric_name)
    ].iloc[0]


def build_global_summary(t2d_core: pd.DataFrame, vis_core: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for frame in [t2d_core, vis_core]:
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    rows: list[dict[str, object]] = []
    for (entity_label, measure_name, metric_name), group in combined.groupby(["entity_label", "measure_name", "metric_name"]):
        base = group[group["year"] == 1990].iloc[0]
        last = group[group["year"] == 2023].iloc[0]
        rows.append(
            {
                "entity_label": entity_label,
                "measure_name": measure_name,
                "metric_name": metric_name,
                "value_1990": base["val"],
                "lower_1990": base["lower"],
                "upper_1990": base["upper"],
                "value_2023": last["val"],
                "lower_2023": last["lower"],
                "upper_2023": last["upper"],
                "absolute_change": last["val"] - base["val"],
                "pct_change_1990_2023": ((last["val"] - base["val"]) / base["val"]) * 100.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["entity_label", "measure_name", "metric_name"]).reset_index(drop=True)


def make_figure_1(t2d_core: pd.DataFrame, vis_core: pd.DataFrame, out_path: Path) -> None:
    apply_pub_style()
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    figure_frames = [
        (t2d_core[(t2d_core["measure_name"] == "Prevalence") & (t2d_core["metric_name"] == "Number")], axes[0, 0], "Global T2D prevalence counts", "Cases"),
        (t2d_core[(t2d_core["measure_name"] == "Prevalence") & (t2d_core["metric_name"] == "Rate")], axes[0, 1], "Global T2D prevalence ASR", "ASR per 100,000"),
        (vis_core[(vis_core["measure_name"] == "Prevalence") & (vis_core["metric_name"] == "Number")], axes[1, 0], "Global T2D-related vision loss counts", "Cases"),
        (vis_core[(vis_core["measure_name"] == "Prevalence") & (vis_core["metric_name"] == "Rate")], axes[1, 1], "Global T2D-related vision loss ASR", "ASR per 100,000"),
    ]
    for frame, ax, title, ylab in figure_frames:
        for sex_name in ["Both", "Male", "Female"]:
            sub = frame[frame["sex_name"] == sex_name].sort_values("year")
            ax.plot(sub["year"], sub["val"], label=sex_name, linewidth=2.4 if sex_name == "Both" else 1.8)
        ax.set_title(title)
        ax.set_xlabel("Year")
        ax.set_ylabel(ylab)
        ax.legend(frameon=False)
    fig.suptitle("GBD 2023 global burden trends", fontsize=16, y=1.02)
    fig.savefig(out_path)
    plt.close(fig)


def make_figure_2(region_2023: pd.DataFrame, sex_2023: pd.DataFrame, severity_2023: pd.DataFrame, out_path: Path) -> None:
    apply_pub_style()
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True)
    for entity_label, ax, title in [
        ("Type 2 diabetes", axes[0, 0], "2023 regional T2D prevalence ASR"),
        ("T2D-related vision loss", axes[0, 1], "2023 regional T2D-related vision loss prevalence ASR"),
    ]:
        sub = region_2023[region_2023["entity_label"] == entity_label].sort_values("val", ascending=True)
        ax.barh(sub["location_name"], sub["val"], color="#c47f3c" if entity_label == "Type 2 diabetes" else "#3a7ca5")
        ax.set_title(title)
        ax.set_xlabel("ASR per 100,000")

    pivot = sex_2023.pivot(index="sex_name", columns="entity_label", values="val").reindex(["Male", "Female"])
    pivot.plot(kind="bar", ax=axes[1, 0], color=["#c47f3c", "#3a7ca5"])
    axes[1, 0].set_title("2023 global sex-specific prevalence ASR")
    axes[1, 0].set_ylabel("ASR per 100,000")
    axes[1, 0].set_xlabel("")
    axes[1, 0].legend(frameon=False, title="")
    axes[1, 0].tick_params(axis="x", rotation=0)

    sev = severity_2023[severity_2023["sex_name"] == "Both"].sort_values("val", ascending=True)
    axes[1, 1].barh(sev["rei_name"], sev["val"], color="#7a9e7e")
    axes[1, 1].set_title("2023 global severity distribution of T2D-related vision loss")
    axes[1, 1].set_xlabel("ASR per 100,000")

    fig.suptitle("GBD 2023 heterogeneity in 2023", fontsize=16, y=1.02)
    fig.savefig(out_path)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    token = load_access_token(Path(args.state_path))

    t2d_prev_asr = pd.read_csv(outdir / "gbd2023_t2d_prevalence_asr_global_region_country.csv")
    t2d_prev_num = pd.read_csv(outdir / "gbd2023_t2d_prevalence_number_global_region_country.csv")
    vis_prev_asr = pd.read_csv(outdir / "gbd2023_t2d_visionloss_prevalence_asr_global_region_country.csv")

    t2d_core = pd.concat(
        [
            t2d_prev_asr[(t2d_prev_asr["location_name"] == "Global") & (t2d_prev_asr["sex_name"].isin(["Male", "Female", "Both"]))],
            t2d_prev_num[(t2d_prev_num["location_name"] == "Global") & (t2d_prev_num["sex_name"].isin(["Male", "Female", "Both"]))],
            pd.read_csv(outdir / "gbd2023_t2d_dalys_asr_global_region_country.csv").query("location_name == 'Global' and sex_name in ['Male', 'Female', 'Both']"),
            pd.read_csv(outdir / "gbd2023_t2d_dalys_number_global_region_country.csv").query("location_name == 'Global' and sex_name in ['Male', 'Female', 'Both']"),
        ],
        ignore_index=True,
    )
    t2d_core.to_csv(outdir / "gbd2023_t2d_global_core.csv", index=False)

    vis_core_path = outdir / "gbd2023_t2d_visionloss_global_core.csv"
    severity_path = outdir / "gbd2023_t2d_visionloss_severity_prevalence_asr_global_2023.csv"
    if vis_core_path.exists():
        vis_core = pd.read_csv(vis_core_path)
    else:
        frames = [vis_prev_asr[(vis_prev_asr["location_name"] == "Global") & (vis_prev_asr["sex_name"].isin(["Male", "Female", "Both"]))].copy()]
        for measure_id, metric_id, age_id in [(5, 1, 22), (3, 3, 27), (3, 1, 22)]:
            raw = fetch_global_series(
                token,
                context="impairment",
                measure_id=measure_id,
                metric_id=metric_id,
                age_id=age_id,
                rei_ids=[200],
                years=list(range(1990, 2024)),
                sexes=[1, 2, 3],
            )
            raw["entity_label"] = "T2D-related vision loss"
            raw["measure_name"] = {5: "Prevalence", 3: "YLDs"}[measure_id]
            raw["metric_name"] = {1: "Number", 3: "Rate"}[metric_id]
            raw["age_name"] = {22: "All ages", 27: "Age-standardized"}[age_id]
            raw["sex_name"] = raw["sex"].map(SEX_MAP)
            raw["location_name"] = "Global"
            raw["rei_name"] = "Blindness and vision loss"
            frames.append(
                raw[
                    ["entity_label", "measure_name", "metric_name", "age_name", "sex", "sex_name", "year", "val", "lower", "upper", "location_name", "rei_name"]
                ]
            )
        vis_core = pd.concat(frames, ignore_index=True)
        vis_core.to_csv(vis_core_path, index=False)

    if severity_path.exists():
        severity_2023 = pd.read_csv(severity_path)
    else:
        raw = fetch_global_series(
            token,
            context="impairment",
            measure_id=5,
            metric_id=3,
            age_id=27,
            rei_ids=[229, 230, 231],
            years=[2023],
            sexes=[1, 2, 3],
        )
        raw["sex_name"] = raw["sex"].map(SEX_MAP)
        raw["rei_name"] = raw["rei"].map(REI_MAP)
        raw["location_name"] = "Global"
        severity_2023 = raw[["sex", "sex_name", "year", "rei", "rei_name", "val", "lower", "upper", "location_name"]].copy()
        severity_2023.to_csv(severity_path, index=False)

    global_summary = build_global_summary(
        t2d_core[t2d_core["sex_name"] == "Both"].copy(),
        vis_core[vis_core["sex_name"] == "Both"].copy(),
    )
    global_summary.to_csv(outdir / "Table_2_GBD_2023_Global_Summary.csv", index=False)

    eapc = compute_eapc(
        pd.concat(
            [
                t2d_core[(t2d_core["metric_name"] == "Rate") & (t2d_core["age_name"] == "Age-standardized") & (t2d_core["sex_name"] == "Both")],
                vis_core[(vis_core["metric_name"] == "Rate") & (vis_core["age_name"] == "Age-standardized") & (vis_core["sex_name"] == "Both")],
            ],
            ignore_index=True,
        )
    )
    eapc.to_csv(outdir / "Table_3_GBD_2023_EAPC.csv", index=False)

    region_2023 = pd.concat(
        [
            t2d_prev_asr[(t2d_prev_asr["location_scope"] == "region") & (t2d_prev_asr["sex_name"] == "Both") & (t2d_prev_asr["year"] == 2023)],
            vis_prev_asr[(vis_prev_asr["location_scope"] == "region") & (vis_prev_asr["sex_name"] == "Both") & (vis_prev_asr["year"] == 2023)],
        ],
        ignore_index=True,
    ).sort_values(["entity_label", "val"], ascending=[True, False])
    region_2023.to_csv(outdir / "gbd2023_region_2023_prevalence_asr.csv", index=False)

    country_2023 = pd.concat(
        [
            t2d_prev_asr[(t2d_prev_asr["location_scope"] == "country") & (t2d_prev_asr["sex_name"] == "Both") & (t2d_prev_asr["year"] == 2023)],
            vis_prev_asr[(vis_prev_asr["location_scope"] == "country") & (vis_prev_asr["sex_name"] == "Both") & (vis_prev_asr["year"] == 2023)],
        ],
        ignore_index=True,
    ).sort_values(["entity_label", "val"], ascending=[True, False]).groupby("entity_label").head(10).reset_index(drop=True)
    country_2023.to_csv(outdir / "gbd2023_country_top10_2023_prevalence_asr.csv", index=False)

    sex_2023 = pd.concat(
        [
            t2d_core[(t2d_core["measure_name"] == "Prevalence") & (t2d_core["metric_name"] == "Rate") & (t2d_core["age_name"] == "Age-standardized") & (t2d_core["year"] == 2023) & (t2d_core["sex_name"].isin(["Male", "Female"]))],
            vis_core[(vis_core["measure_name"] == "Prevalence") & (vis_core["metric_name"] == "Rate") & (vis_core["age_name"] == "Age-standardized") & (vis_core["year"] == 2023) & (vis_core["sex_name"].isin(["Male", "Female"]))],
        ],
        ignore_index=True,
    )[["entity_label", "sex_name", "val", "lower", "upper"]]
    sex_2023.to_csv(outdir / "gbd2023_global_sex_2023_prevalence_asr.csv", index=False)

    make_figure_1(t2d_core, vis_core, outdir / "Figure_1_GBD_Global_Trends.png")
    make_figure_2(region_2023, sex_2023, severity_2023, outdir / "Figure_2_GBD_Heterogeneity_2023.png")

    summary_md = f"""# GBD 2023 Summary For eClinicalMedicine Draft

- Global type 2 diabetes prevalence increased from {one_row(global_summary, 'Type 2 diabetes', 'Prevalence', 'Number')['value_1990'] / 1_000_000:.1f} million in 1990 to {one_row(global_summary, 'Type 2 diabetes', 'Prevalence', 'Number')['value_2023'] / 1_000_000:.1f} million in 2023.
- Global T2D-related vision loss prevalence increased from {one_row(global_summary, 'T2D-related vision loss', 'Prevalence', 'Number')['value_1990'] / 1_000_000:.2f} million in 1990 to {one_row(global_summary, 'T2D-related vision loss', 'Prevalence', 'Number')['value_2023'] / 1_000_000:.2f} million in 2023.
- In 2023, the highest regional age-standardized prevalence rate for type 2 diabetes was in {region_2023[region_2023['entity_label'] == 'Type 2 diabetes'].iloc[0]['location_name']}.
- In 2023, the highest regional age-standardized prevalence rate for T2D-related vision loss was in {region_2023[region_2023['entity_label'] == 'T2D-related vision loss'].iloc[0]['location_name']}.
- Public GBD 2023 access does not expose diabetic retinopathy as a stand-alone public cause. This package therefore uses blindness and vision loss attributable to type 2 diabetes in the impairment context as the closest public GBD 2023 analogue for diabetes-related retinal burden.
"""
    (outdir / "GBD_2023_SUMMARY.md").write_text(summary_md, encoding="utf-8")

    print(f"Wrote manuscript assets to {outdir}")
    print(f"Global summary rows: {len(global_summary)}")
    print(f"EAPC rows: {len(eapc)}")


if __name__ == "__main__":
    main()
