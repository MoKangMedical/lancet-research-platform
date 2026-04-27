#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests

from lib.plot_style import apply_pub_style


ROOT = Path("/Users/apple/Desktop/lancet-research-platform")
DEFAULT_STATE_PATH = ROOT / "output/playwright/gbdlogin_state_20260309.json"
DEFAULT_OUTDIR = ROOT / "outputs/gbd_dr_t2d_gbd2023"
RESULTS_URL = "https://vizhub.healthdata.org/gbd-results/php/data.php"
METADATA_URL = "https://vizhub.healthdata.org/gbd-results/php/metadata/?language=en"
HIERARCHY_URL = "https://vizhub.healthdata.org/gbd-results/php/hierarchy/"
VERSION_ID = 8352
T2D_CAUSE_ID = 976
VISION_LOSS_REI_ID = 200
VISION_LOSS_DETAIL_REI_IDS = {
    229: "Moderate vision loss",
    230: "Severe vision loss",
    231: "Blindness",
}
SEX_MAP = {1: "Male", 2: "Female", 3: "Both"}
MEASURE_MAP = {2: "DALYs", 3: "YLDs", 5: "Prevalence"}
METRIC_MAP = {1: "Number", 3: "Rate"}
AGE_MAP = {22: "All ages", 27: "Age-standardized"}
YEARS = list(range(1990, 2024))
LOCATION_SCOPE_ORDER = {"global": 0, "region": 1, "country": 2}


@dataclass(frozen=True)
class QuerySpec:
    slug: str
    entity: str
    entity_label: str
    context: str
    measure_id: int
    metric_id: int
    age_id: int
    rei_ids: tuple[int, ...] = ()


MAIN_QUERY_SPECS = [
    QuerySpec(
        slug="gbd2023_t2d_prevalence_asr_global_region_country",
        entity="t2d",
        entity_label="Type 2 diabetes",
        context="cause",
        measure_id=5,
        metric_id=3,
        age_id=27,
    ),
    QuerySpec(
        slug="gbd2023_t2d_prevalence_number_global_region_country",
        entity="t2d",
        entity_label="Type 2 diabetes",
        context="cause",
        measure_id=5,
        metric_id=1,
        age_id=22,
    ),
    QuerySpec(
        slug="gbd2023_t2d_dalys_asr_global_region_country",
        entity="t2d",
        entity_label="Type 2 diabetes",
        context="cause",
        measure_id=2,
        metric_id=3,
        age_id=27,
    ),
    QuerySpec(
        slug="gbd2023_t2d_dalys_number_global_region_country",
        entity="t2d",
        entity_label="Type 2 diabetes",
        context="cause",
        measure_id=2,
        metric_id=1,
        age_id=22,
    ),
    QuerySpec(
        slug="gbd2023_t2d_visionloss_prevalence_asr_global_region_country",
        entity="t2d_related_vision_loss",
        entity_label="T2D-related vision loss",
        context="impairment",
        measure_id=5,
        metric_id=3,
        age_id=27,
        rei_ids=(VISION_LOSS_REI_ID,),
    ),
    QuerySpec(
        slug="gbd2023_t2d_visionloss_prevalence_number_global_region_country",
        entity="t2d_related_vision_loss",
        entity_label="T2D-related vision loss",
        context="impairment",
        measure_id=5,
        metric_id=1,
        age_id=22,
        rei_ids=(VISION_LOSS_REI_ID,),
    ),
    QuerySpec(
        slug="gbd2023_t2d_visionloss_ylds_asr_global_region_country",
        entity="t2d_related_vision_loss",
        entity_label="T2D-related vision loss",
        context="impairment",
        measure_id=3,
        metric_id=3,
        age_id=27,
        rei_ids=(VISION_LOSS_REI_ID,),
    ),
    QuerySpec(
        slug="gbd2023_t2d_visionloss_ylds_number_global_region_country",
        entity="t2d_related_vision_loss",
        entity_label="T2D-related vision loss",
        context="impairment",
        measure_id=3,
        metric_id=1,
        age_id=22,
        rei_ids=(VISION_LOSS_REI_ID,),
    ),
]

SEVERITY_SPEC = QuerySpec(
    slug="gbd2023_t2d_visionloss_severity_prevalence_asr_global_2023",
    entity="t2d_related_vision_loss",
    entity_label="T2D-related vision loss",
    context="impairment",
    measure_id=5,
    metric_id=3,
    age_id=27,
    rei_ids=tuple(VISION_LOSS_DETAIL_REI_IDS),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and summarize GBD 2023 T2D and T2D-related vision loss data")
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--chunk-size", type=int, default=20)
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


def fetch_json(url: str, token: str) -> dict:
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    response.raise_for_status()
    return response.json()


def build_location_frame(token: str) -> pd.DataFrame:
    metadata = fetch_json(METADATA_URL, token)["data"]["location"]
    hierarchy = fetch_json(HIERARCHY_URL, token)["data"]["locations"][0]
    location_lookup = {
        int(item["id"]): {
            "location_name": item["name"],
            "location_short_name": item["short_name"],
        }
        for item in metadata.values()
        if isinstance(item, dict) and str(item.get("id", "")).isdigit()
    }

    rows: list[dict[str, object]] = []
    queue: list[tuple[dict[str, object], int, int | None]] = [(hierarchy, 0, None)]
    while queue:
        node, depth, parent_id = queue.pop(0)
        location_id = int(node["id"])
        info = location_lookup.get(location_id, {})
        scope = None
        if depth == 0:
            scope = "global"
        elif depth == 2:
            scope = "region"
        elif depth == 3:
            scope = "country"
        rows.append(
            {
                "location_id": location_id,
                "location_name": info.get("location_name"),
                "location_short_name": info.get("location_short_name"),
                "depth": depth,
                "parent_id": parent_id,
                "location_scope": scope,
            }
        )
        for child in node.get("children", []) or []:
            queue.append((child, depth + 1, location_id))

    frame = pd.DataFrame(rows)
    frame = frame[frame["location_scope"].isin({"global", "region", "country"})].copy()
    frame["scope_order"] = frame["location_scope"].map(LOCATION_SCOPE_ORDER)
    return frame.sort_values(["scope_order", "location_name"]).reset_index(drop=True)


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


def chunked_results(
    token: str,
    spec: QuerySpec,
    location_ids: list[int],
    years: list[int],
    sexes: list[int],
    chunk_size: int = 20,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for start in range(0, len(location_ids), chunk_size):
        chunk = location_ids[start : start + chunk_size]
        payload = build_payload(spec, location_ids=chunk, years=years, sexes=sexes)
        frames.append(post_results(token, payload))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_payload(spec: QuerySpec, location_ids: list[int], years: list[int], sexes: list[int]) -> list[tuple[str, object]]:
    payload: list[tuple[str, object]] = [
        ("version", VERSION_ID),
        ("context", spec.context),
        ("cause[]", T2D_CAUSE_ID),
        ("measure[]", spec.measure_id),
        ("metric[]", spec.metric_id),
        ("age[]", spec.age_id),
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
    for location_id in location_ids:
        payload.append(("location[]", int(location_id)))
    for year in years:
        payload.append(("year[]", int(year)))
    for sex in sexes:
        payload.append(("sex[]", int(sex)))
    for rei_id in spec.rei_ids:
        payload.append(("rei[]", int(rei_id)))
    return payload


def enrich(df: pd.DataFrame, spec: QuerySpec, locations: pd.DataFrame) -> pd.DataFrame:
    loc_lookup = locations.set_index("location_id")[["location_name", "location_short_name", "location_scope"]]
    out = df.copy()
    out["entity"] = spec.entity
    out["entity_label"] = spec.entity_label
    out["context"] = spec.context
    out["measure_name"] = MEASURE_MAP[spec.measure_id]
    out["metric_name"] = METRIC_MAP[spec.metric_id]
    out["age_name"] = AGE_MAP[spec.age_id]
    out["sex_name"] = out["sex"].map(SEX_MAP)
    out["cause_name"] = "Diabetes mellitus type 2"
    out["rei_name"] = out["rei"].map(VISION_LOSS_DETAIL_REI_IDS).fillna("Blindness and vision loss") if "rei" in out.columns else ""
    out = out.merge(loc_lookup, left_on="location", right_index=True, how="left")
    ordered_cols = [
        "entity",
        "entity_label",
        "context",
        "cause_name",
        "rei_name",
        "measure",
        "measure_name",
        "metric",
        "metric_name",
        "age",
        "age_name",
        "sex",
        "sex_name",
        "location",
        "location_name",
        "location_short_name",
        "location_scope",
        "year",
        "val",
        "lower",
        "upper",
    ]
    for col in ordered_cols:
        if col not in out.columns:
            out[col] = ""
    return out[ordered_cols].sort_values(
        ["entity", "measure_name", "metric_name", "location_scope", "location_name", "sex", "year", "rei_name"]
    ).reset_index(drop=True)


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


def build_global_summary(main_tidy: pd.DataFrame) -> pd.DataFrame:
    subset = main_tidy[
        (main_tidy["location_name"] == "Global")
        & (main_tidy["sex_name"] == "Both")
        & (
            ((main_tidy["metric_name"] == "Rate") & (main_tidy["age_name"] == "Age-standardized"))
            | ((main_tidy["metric_name"] == "Number") & (main_tidy["age_name"] == "All ages"))
        )
    ].copy()
    rows: list[dict[str, object]] = []
    for (entity_label, measure_name, metric_name), group in subset.groupby(["entity_label", "measure_name", "metric_name"]):
        base = group.loc[group["year"] == 1990].iloc[0]
        last = group.loc[group["year"] == 2023].iloc[0]
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


def write_summary_markdown(
    outdir: Path,
    global_summary: pd.DataFrame,
    region_2023: pd.DataFrame,
    country_2023: pd.DataFrame,
    sex_2023: pd.DataFrame,
    eapc: pd.DataFrame,
) -> None:
    def one_row(df: pd.DataFrame, entity: str, measure: str, metric: str) -> pd.Series:
        return df[
            (df["entity_label"] == entity)
            & (df["measure_name"] == measure)
            & (df["metric_name"] == metric)
        ].iloc[0]

    t2d_num = one_row(global_summary, "Type 2 diabetes", "Prevalence", "Number")
    t2d_rate = one_row(global_summary, "Type 2 diabetes", "Prevalence", "Rate")
    vis_num = one_row(global_summary, "T2D-related vision loss", "Prevalence", "Number")
    vis_rate = one_row(global_summary, "T2D-related vision loss", "Prevalence", "Rate")
    top_t2d_region = region_2023[region_2023["entity_label"] == "Type 2 diabetes"].iloc[0]
    top_vis_region = region_2023[region_2023["entity_label"] == "T2D-related vision loss"].iloc[0]
    top_vis_country = country_2023[country_2023["entity_label"] == "T2D-related vision loss"].iloc[0]
    t2d_male = sex_2023[(sex_2023["entity_label"] == "Type 2 diabetes") & (sex_2023["sex_name"] == "Male")].iloc[0]
    t2d_female = sex_2023[(sex_2023["entity_label"] == "Type 2 diabetes") & (sex_2023["sex_name"] == "Female")].iloc[0]
    vis_male = sex_2023[(sex_2023["entity_label"] == "T2D-related vision loss") & (sex_2023["sex_name"] == "Male")].iloc[0]
    vis_female = sex_2023[(sex_2023["entity_label"] == "T2D-related vision loss") & (sex_2023["sex_name"] == "Female")].iloc[0]

    summary = f"""# GBD 2023 Summary For DR-T2D Paper

## Core 2023 findings

- Global type 2 diabetes prevalence reached {t2d_num['value_2023'] / 1_000_000:.1f} million people in 2023, up from {t2d_num['value_1990'] / 1_000_000:.1f} million in 1990.
- The global age-standardized prevalence rate for type 2 diabetes increased from {t2d_rate['value_1990']:.1f} to {t2d_rate['value_2023']:.1f} per 100,000 between 1990 and 2023.
- Global T2D-related vision loss prevalence reached {vis_num['value_2023'] / 1_000_000:.2f} million people in 2023, up from {vis_num['value_1990'] / 1_000_000:.2f} million in 1990.
- The global age-standardized prevalence rate for T2D-related vision loss increased from {vis_rate['value_1990']:.1f} to {vis_rate['value_2023']:.1f} per 100,000 between 1990 and 2023.

## Heterogeneity

- The highest 2023 regional age-standardized prevalence rate for type 2 diabetes was in {top_t2d_region['location_name']} ({top_t2d_region['val']:.1f} per 100,000).
- The highest 2023 regional age-standardized prevalence rate for T2D-related vision loss was in {top_vis_region['location_name']} ({top_vis_region['val']:.1f} per 100,000).
- The highest 2023 country-level age-standardized prevalence rate for T2D-related vision loss was in {top_vis_country['location_name']} ({top_vis_country['val']:.1f} per 100,000).

## Sex pattern in 2023

- Type 2 diabetes age-standardized prevalence was higher in males than females ({t2d_male['val']:.1f} vs {t2d_female['val']:.1f} per 100,000).
- T2D-related vision loss age-standardized prevalence was higher in females than males ({vis_female['val']:.1f} vs {vis_male['val']:.1f} per 100,000).

## EAPC

{eapc.to_markdown(index=False)}

## Important definitional note

- The public GBD 2023 Results Tool does not expose diabetic retinopathy as a stand-alone cause in the public cause list.
- The GBD component in this package therefore uses the public impairment-context estimate for blindness and vision loss attributable to type 2 diabetes as the closest official GBD 2023 analogue for diabetes-related retinal burden.
"""
    (outdir / "GBD_2023_SUMMARY.md").write_text(summary, encoding="utf-8")


def make_figure_1(main_tidy: pd.DataFrame, out_path: Path) -> None:
    apply_pub_style()
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)

    plot_specs = [
        ("Type 2 diabetes", "Prevalence", "Number", "All ages", axes[0, 0], "Prevalent cases"),
        ("Type 2 diabetes", "Prevalence", "Rate", "Age-standardized", axes[0, 1], "ASR per 100,000"),
        ("T2D-related vision loss", "Prevalence", "Number", "All ages", axes[1, 0], "Prevalent cases"),
        ("T2D-related vision loss", "Prevalence", "Rate", "Age-standardized", axes[1, 1], "ASR per 100,000"),
    ]

    for entity_label, measure_name, metric_name, age_name, ax, y_label in plot_specs:
        subset = main_tidy[
            (main_tidy["location_name"] == "Global")
            & (main_tidy["entity_label"] == entity_label)
            & (main_tidy["measure_name"] == measure_name)
            & (main_tidy["metric_name"] == metric_name)
            & (main_tidy["age_name"] == age_name)
            & (main_tidy["sex_name"].isin(["Male", "Female", "Both"]))
        ].copy()
        for sex_name in ["Both", "Male", "Female"]:
            sex_df = subset[subset["sex_name"] == sex_name].sort_values("year")
            if sex_df.empty:
                continue
            ax.plot(sex_df["year"], sex_df["val"], label=sex_name, linewidth=2.4 if sex_name == "Both" else 1.8)
        ax.set_title(f"{entity_label}: {measure_name} ({metric_name})")
        ax.set_xlabel("Year")
        ax.set_ylabel(y_label)
        ax.legend(frameon=False)

    fig.suptitle("GBD 2023 global burden of type 2 diabetes and T2D-related vision loss", fontsize=16, y=1.02)
    fig.savefig(out_path)
    plt.close(fig)


def make_figure_2(main_tidy: pd.DataFrame, severity_2023: pd.DataFrame, out_path: Path) -> None:
    apply_pub_style()
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True)

    panels = [
        ("Type 2 diabetes", axes[0, 0], "2023 regional T2D prevalence ASR"),
        ("T2D-related vision loss", axes[0, 1], "2023 regional T2D-related vision loss prevalence ASR"),
    ]
    for entity_label, ax, title in panels:
        subset = main_tidy[
            (main_tidy["location_scope"] == "region")
            & (main_tidy["entity_label"] == entity_label)
            & (main_tidy["measure_name"] == "Prevalence")
            & (main_tidy["metric_name"] == "Rate")
            & (main_tidy["age_name"] == "Age-standardized")
            & (main_tidy["sex_name"] == "Both")
            & (main_tidy["year"] == 2023)
        ].sort_values("val", ascending=True)
        ax.barh(subset["location_name"], subset["val"], color="#c47f3c" if entity_label == "Type 2 diabetes" else "#3a7ca5")
        ax.set_title(title)
        ax.set_xlabel("ASR per 100,000")

    sex_subset = main_tidy[
        (main_tidy["location_name"] == "Global")
        & (main_tidy["entity_label"].isin(["Type 2 diabetes", "T2D-related vision loss"]))
        & (main_tidy["measure_name"] == "Prevalence")
        & (main_tidy["metric_name"] == "Rate")
        & (main_tidy["age_name"] == "Age-standardized")
        & (main_tidy["sex_name"].isin(["Male", "Female"]))
        & (main_tidy["year"] == 2023)
    ].copy()
    pivot = sex_subset.pivot(index="sex_name", columns="entity_label", values="val").reindex(["Male", "Female"])
    pivot.plot(kind="bar", ax=axes[1, 0], color=["#c47f3c", "#3a7ca5"])
    axes[1, 0].set_title("2023 global sex-specific prevalence ASR")
    axes[1, 0].set_ylabel("ASR per 100,000")
    axes[1, 0].set_xlabel("")
    axes[1, 0].legend(frameon=False, title="")
    axes[1, 0].tick_params(axis="x", rotation=0)

    sev = severity_2023[
        (severity_2023["location_name"] == "Global")
        & (severity_2023["sex_name"] == "Both")
        & (severity_2023["year"] == 2023)
    ].sort_values("val", ascending=True)
    axes[1, 1].barh(sev["rei_name"], sev["val"], color="#7a9e7e")
    axes[1, 1].set_title("2023 global severity pattern of T2D-related vision loss")
    axes[1, 1].set_xlabel("ASR per 100,000")

    fig.suptitle("GBD 2023 regional and sex heterogeneity", fontsize=16, y=1.02)
    fig.savefig(out_path)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    token = load_access_token(Path(args.state_path))
    locations = build_location_frame(token)
    location_ids = locations["location_id"].astype(int).tolist()

    main_frames: list[pd.DataFrame] = []
    raw_exports: dict[str, pd.DataFrame] = {}
    for spec in MAIN_QUERY_SPECS:
        export_path = outdir / f"{spec.slug}.csv"
        if export_path.exists():
            tidy = pd.read_csv(export_path)
        else:
            raw = chunked_results(
                token,
                spec,
                location_ids=location_ids,
                years=YEARS,
                sexes=[1, 2, 3],
                chunk_size=args.chunk_size,
            )
            tidy = enrich(raw, spec, locations)
            tidy.to_csv(export_path, index=False)
        raw_exports[spec.slug] = tidy
        main_frames.append(tidy)

    severity_path = outdir / f"{SEVERITY_SPEC.slug}.csv"
    if severity_path.exists():
        severity_tidy = pd.read_csv(severity_path)
    else:
        severity_raw = chunked_results(
            token,
            SEVERITY_SPEC,
            location_ids=[1],
            years=[2023],
            sexes=[1, 2, 3],
            chunk_size=1,
        )
        severity_tidy = enrich(severity_raw, SEVERITY_SPEC, locations)
        severity_tidy.to_csv(severity_path, index=False)

    main_tidy = pd.concat(main_frames, ignore_index=True)
    main_tidy.to_csv(outdir / "gbd2023_t2d_visionloss_main_tidy.csv", index=False)

    global_summary = build_global_summary(main_tidy)
    global_summary.to_csv(outdir / "Table_2_GBD_2023_Global_Summary.csv", index=False)

    eapc_input = main_tidy[
        (main_tidy["location_name"] == "Global")
        & (main_tidy["sex_name"] == "Both")
        & (main_tidy["metric_name"] == "Rate")
        & (main_tidy["age_name"] == "Age-standardized")
    ].copy()
    eapc = compute_eapc(eapc_input)
    eapc.to_csv(outdir / "Table_3_GBD_2023_EAPC.csv", index=False)

    sex_2023 = main_tidy[
        (main_tidy["location_name"] == "Global")
        & (main_tidy["measure_name"] == "Prevalence")
        & (main_tidy["metric_name"] == "Rate")
        & (main_tidy["age_name"] == "Age-standardized")
        & (main_tidy["year"] == 2023)
        & (main_tidy["sex_name"].isin(["Male", "Female", "Both"]))
    ].copy()
    sex_2023.to_csv(outdir / "gbd2023_global_sex_2023_prevalence_asr.csv", index=False)

    region_2023 = main_tidy[
        (main_tidy["location_scope"] == "region")
        & (main_tidy["measure_name"] == "Prevalence")
        & (main_tidy["metric_name"] == "Rate")
        & (main_tidy["age_name"] == "Age-standardized")
        & (main_tidy["sex_name"] == "Both")
        & (main_tidy["year"] == 2023)
    ].sort_values(["entity_label", "val"], ascending=[True, False]).reset_index(drop=True)
    region_2023.to_csv(outdir / "gbd2023_region_2023_prevalence_asr.csv", index=False)

    country_2023 = main_tidy[
        (main_tidy["location_scope"] == "country")
        & (main_tidy["measure_name"] == "Prevalence")
        & (main_tidy["metric_name"] == "Rate")
        & (main_tidy["age_name"] == "Age-standardized")
        & (main_tidy["sex_name"] == "Both")
        & (main_tidy["year"] == 2023)
    ].sort_values(["entity_label", "val"], ascending=[True, False]).groupby("entity_label").head(10).reset_index(drop=True)
    country_2023.to_csv(outdir / "gbd2023_country_top10_2023_prevalence_asr.csv", index=False)

    make_figure_1(main_tidy, outdir / "Figure_1_GBD_Global_Trends.png")
    make_figure_2(main_tidy, severity_tidy, outdir / "Figure_2_GBD_Heterogeneity_2023.png")
    write_summary_markdown(outdir, global_summary, region_2023, country_2023, sex_2023, eapc)

    manifest = {
        "source": "Official GBD Results Tool API",
        "version_id": VERSION_ID,
        "state_path": str(Path(args.state_path)),
        "cause_id": T2D_CAUSE_ID,
        "cause_name": "Diabetes mellitus type 2",
        "vision_loss_rei_id": VISION_LOSS_REI_ID,
        "vision_loss_detail_rei_ids": VISION_LOSS_DETAIL_REI_IDS,
        "years": [YEARS[0], YEARS[-1]],
        "sexes": SEX_MAP,
        "age_ids": AGE_MAP,
        "location_counts": locations["location_scope"].value_counts().to_dict(),
        "main_queries": [spec.slug for spec in MAIN_QUERY_SPECS],
        "severity_query": SEVERITY_SPEC.slug,
        "note": (
            "The public GBD 2023 Results Tool does not expose diabetic retinopathy as a stand-alone public cause. "
            "The closest official public analogue used here is blindness and vision loss attributable to type 2 diabetes "
            "queried in the impairment context."
        ),
    }
    (outdir / "gbd2023_t2d_visionloss_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote GBD outputs to {outdir}")
    print(f"Rows in main tidy file: {len(main_tidy)}")
    print(f"Rows in severity tidy file: {len(severity_tidy)}")


if __name__ == "__main__":
    main()
