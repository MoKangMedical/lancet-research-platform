#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests


ROOT = Path("/Users/apple/Desktop/lancet-research-platform")
PROJECT_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-针对皮肤病的相关全球流行病和疾病负担研究方案-20分-38万-已收5万+5万"
)
PACKAGE_ROOT = PROJECT_DIR / "lancet_skin_article_package"
AGING_DIR = PACKAGE_ROOT / "aging_analysis_outputs"
OUTPUT_DIR = PACKAGE_ROOT / "apac_results_tool_outputs"
STATE_PATH = ROOT / "output" / "playwright" / "gbdlogin_state_20260309.json"
RESULTS_URL = "https://vizhub.healthdata.org/gbd-results/php/data.php"
VERSION_ID = 8352
CAUSE_ID = 653
YEAR_ID = 2023
MEASURE_MAP = {
    1: "Deaths",
    5: "Prevalence",
    6: "Incidence",
}


def load_state_token(state_path: Path) -> str:
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    for origin in payload.get("origins", []):
        for item in origin.get("localStorage", []):
            if "accesstoken" not in item.get("name", ""):
                continue
            parsed = json.loads(item["value"])
            token = parsed.get("secret", "")
            if token:
                return token
    raise RuntimeError(f"Access token not found in {state_path}")


def fetch_apac_reference() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for region_code, region_label in [("EAS", "East Asia & Pacific"), ("SAS", "South Asia")]:
        url = f"https://api.worldbank.org/v2/region/{region_code}/country?format=json&per_page=500"
        payload = requests.get(url, timeout=30).json()[1]
        for item in payload:
            rows.append(
                {
                    "wb_iso3": item["id"],
                    "apac_region_code": region_code,
                    "apac_region_label": region_label,
                    "apac_name": item["name"],
                }
            )
    return pd.DataFrame(rows).drop_duplicates(subset=["wb_iso3"]).reset_index(drop=True)


def build_apac_location_frame() -> pd.DataFrame:
    country_complete = pd.read_csv(AGING_DIR / "skin_aging_2023_country_complete.csv")
    apac_ref = fetch_apac_reference()
    apac = country_complete.merge(apac_ref, on="wb_iso3", how="inner").copy()
    apac = apac.sort_values(["apac_region_label", "gbd_name"]).reset_index(drop=True)
    if apac["location_id"].isna().any():
        missing = apac.loc[apac["location_id"].isna(), "gbd_name"].tolist()
        raise RuntimeError(f"Missing location_id for APAC rows: {missing}")
    return apac


def fetch_results(access_token: str, location_ids: list[int]) -> dict[str, object]:
    payload: list[tuple[str, object]] = [("version", VERSION_ID)]
    for measure_id in MEASURE_MAP:
        payload.append(("measure[]", measure_id))
    for location_id in location_ids:
        payload.append(("location[]", int(location_id)))
    payload.extend(
        [
            ("sex[]", 3),
            ("age[]", 27),
            ("cause[]", CAUSE_ID),
            ("metric[]", 3),
            ("year[]", YEAR_ID),
            ("population_group", 1),
            ("api_version", "2023.0.0"),
            ("base", "single"),
            ("context", "cause"),
            ("singleOrMult", "single"),
            ("idsOrNames", "ids"),
            ("rows", 500000),
            ("start_year", 1980),
            ("fetch_all_years", "false"),
            ("language", "en"),
        ]
    )
    response = requests.post(
        RESULTS_URL,
        data=payload,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def tidy_results(raw: dict[str, object], apac: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(raw["data"], columns=raw["cols"]).copy()
    df["measure_name"] = df["measure"].map(MEASURE_MAP)
    df["age_name"] = "Age-standardized"
    df["metric_name"] = "Rate"
    df["sex_name"] = "Both"
    df["cause_name"] = "Skin and subcutaneous diseases"
    keep_cols = [
        "location_id",
        "gbd_name",
        "gbd_short_name",
        "wb_iso3",
        "apac_region_label",
        "age65_pct",
        "life_expectancy",
        "old_age_dependency",
    ]
    merged = df.merge(
        apac[keep_cols],
        left_on="location",
        right_on="location_id",
        how="left",
        validate="many_to_one",
    )
    merged["query_source"] = "Official GBD Results Tool"
    merged["query_date"] = "2026-03-09"
    merged = merged[
        [
            "location_id",
            "gbd_name",
            "gbd_short_name",
            "wb_iso3",
            "apac_region_label",
            "measure",
            "measure_name",
            "sex",
            "sex_name",
            "age",
            "age_name",
            "cause",
            "cause_name",
            "metric",
            "metric_name",
            "year",
            "val",
            "lower",
            "upper",
            "age65_pct",
            "life_expectancy",
            "old_age_dependency",
            "query_source",
            "query_date",
        ]
    ].sort_values(["measure", "val"], ascending=[True, False])
    return merged.reset_index(drop=True)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    apac = build_apac_location_frame()
    token = load_state_token(STATE_PATH)
    raw = fetch_results(token, apac["location_id"].astype(int).tolist())
    tidy = tidy_results(raw, apac)

    csv_path = OUTPUT_DIR / "skin_apac_official_asr_2023.csv"
    json_path = OUTPUT_DIR / "skin_apac_official_asr_2023_query.json"
    summary_path = OUTPUT_DIR / "skin_apac_official_asr_2023_summary.json"

    tidy.to_csv(csv_path, index=False)
    json_path.write_text(
        json.dumps(
            {
                "source": "Official GBD Results Tool",
                "endpoint": RESULTS_URL,
                "version": VERSION_ID,
                "cause_id": CAUSE_ID,
                "cause_name": "Skin and subcutaneous diseases",
                "measure_ids": list(MEASURE_MAP.keys()),
                "measure_names": list(MEASURE_MAP.values()),
                "metric_id": 3,
                "metric_name": "Rate",
                "age_id": 27,
                "age_name": "Age-standardized",
                "sex_id": 3,
                "sex_name": "Both",
                "year_id": YEAR_ID,
                "location_count": int(apac["location_id"].nunique()),
                "query_date": "2026-03-09",
                "state_path": str(STATE_PATH),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(
            {
                "rows": int(len(tidy)),
                "locations": int(tidy["location_id"].nunique()),
                "measures": sorted(tidy["measure_name"].unique().tolist()),
                "top_deaths": tidy.loc[tidy["measure_name"] == "Deaths", ["gbd_name", "val"]]
                .head(5)
                .to_dict(orient="records"),
                "top_prevalence": tidy.loc[tidy["measure_name"] == "Prevalence", ["gbd_name", "val"]]
                .head(5)
                .to_dict(orient="records"),
                "top_incidence": tidy.loc[tidy["measure_name"] == "Incidence", ["gbd_name", "val"]]
                .head(5)
                .to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {csv_path}")
    print(f"Rows: {len(tidy)}")
    print(f"Locations: {tidy['location_id'].nunique()}")


if __name__ == "__main__":
    main()
