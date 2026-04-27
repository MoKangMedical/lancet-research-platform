#!/usr/bin/env python3
"""Build supplementary tables and sensitivity analyses for the DR-T2D Lancet package."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter


PROJECT_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/04_多期刊投稿包/GBD2023_UKB_DR_T2D_2026-03-07/journal_01_eClinicalMedicine"
)
UKB_PATH = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/02_UKB结果/ukb_dr_t2d_analysis.csv"
)
GBD_DIR = PROJECT_DIR / "gbd_2023_results"
OUTDIR = PROJECT_DIR / "supplementary_tables"

FULL_COVARS = [
    "age_baseline",
    "sex",
    "white_ethnicity",
    "townsend",
    "bmi",
    "sbp",
    "cholesterol_total",
    "hba1c",
    "smoking_former",
    "smoking_current",
]
MINIMAL_COVARS = [
    "age_baseline",
    "sex",
    "white_ethnicity",
    "bmi",
    "sbp",
    "smoking_former",
    "smoking_current",
]
AGE_SEX_COVARS = ["age_baseline", "sex"]
KEY_VARIABLES = [
    "age_baseline",
    "sex",
    "white_ethnicity",
    "townsend",
    "bmi",
    "sbp",
    "cholesterol_total",
    "hba1c",
    "glucose",
    "smoking_former",
    "smoking_current",
]
JOINT_LABELS = {
    0: "No T2D / No retinopathy",
    1: "No T2D / Retinopathy",
    2: "T2D / No retinopathy",
    3: "T2D / Retinopathy",
}
OUTCOME_MAP = {
    "event_allcause": "All-cause mortality",
    "event_mace": "MACE",
    "event_hf": "Heart failure",
}
DURATION_MAP = {
    "event_allcause": "followup_allcause_years",
    "event_mace": "followup_mace_years",
    "event_hf": "followup_hf_years",
}


def summarize_cox(cph: CoxPHFitter) -> pd.DataFrame:
    out = cph.summary.reset_index()
    if "covariate" in out.columns:
        out = out.rename(columns={"covariate": "term"})
    elif "index" in out.columns:
        out = out.rename(columns={"index": "term"})
    return out


def p_value_display(value: float) -> str:
    return "<0.001" if value < 0.001 else f"{value:.3f}"


def estimate_display(hr: float, lower: float, upper: float) -> tuple[str, str]:
    if any(not np.isfinite(v) for v in [hr, lower, upper]) or upper > 100:
        return "Not estimable", "Not estimable"
    return f"{hr:.2f}", f"{lower:.2f}-{upper:.2f}"


def add_analysis_t2d(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["t2d_analysis"] = (
        out["t2d"].fillna(0).eq(1)
        | out["hba1c"].ge(48)
        | out["glucose"].ge(11.1)
    ).astype(int)
    return out


def incident_cohort() -> pd.DataFrame:
    df = pd.read_csv(UKB_PATH)
    df = add_analysis_t2d(df)
    df = df[df["prev_cvd"].fillna(0).eq(0)].copy()
    return df


def missingness_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    n = len(df)
    for variable in KEY_VARIABLES:
        missing = int(df[variable].isna().sum())
        rows.append(
            {
                "Variable": variable,
                "Missing n": missing,
                "Missing %": round(missing / n * 100, 2),
                "Non-missing n": int(n - missing),
            }
        )
    return pd.DataFrame(rows)


def event_rate_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    df = df.copy()
    df["joint_group_analysis"] = df["t2d_analysis"] * 2 + df["retinopathy"]
    for outcome_col, outcome_label in OUTCOME_MAP.items():
        duration_col = DURATION_MAP[outcome_col]
        for group, group_df in df.groupby("joint_group_analysis", sort=True):
            person_years = float(group_df[duration_col].fillna(0).sum())
            events = int(group_df[outcome_col].sum())
            rate = (events / person_years * 1000) if person_years > 0 else np.nan
            rows.append(
                {
                    "Outcome": outcome_label,
                    "Exposure group": JOINT_LABELS[group],
                    "Participants n": int(len(group_df)),
                    "Events n": events,
                    "Person-years": round(person_years, 2),
                    "Rate per 1000 person-years": round(rate, 2),
                }
            )
    return pd.DataFrame(rows)


def fit_joint_model(
    df: pd.DataFrame,
    *,
    duration_col: str,
    event_col: str,
    exposure_col: str,
    covars: list[str],
    analysis_label: str,
    subgroup_label: str = "Overall",
) -> pd.DataFrame:
    dat = df[[duration_col, event_col, exposure_col, "retinopathy"] + covars].dropna().copy()
    dat = dat[dat[duration_col].gt(0)].copy()
    dat["joint_group"] = dat[exposure_col] * 2 + dat["retinopathy"]
    dat["joint_1"] = dat["joint_group"].eq(1).astype(int)
    dat["joint_2"] = dat["joint_group"].eq(2).astype(int)
    dat["joint_3"] = dat["joint_group"].eq(3).astype(int)
    fit_cols = [duration_col, event_col, "joint_1", "joint_2", "joint_3"] + covars
    cph = CoxPHFitter()
    cph.fit(dat[fit_cols], duration_col=duration_col, event_col=event_col)
    summary = summarize_cox(cph)
    summary = summary.loc[summary["term"].isin(["joint_1", "joint_2", "joint_3"])].copy()
    term_map = {
        "joint_1": "No T2D / Retinopathy",
        "joint_2": "T2D / No retinopathy",
        "joint_3": "T2D / Retinopathy",
    }
    summary["Outcome"] = OUTCOME_MAP[event_col]
    summary["Model"] = analysis_label
    summary["Subgroup"] = subgroup_label
    summary["Exposure group"] = summary["term"].map(term_map)
    summary["Sample n"] = len(dat)
    summary["Events n"] = int(dat[event_col].sum())
    summary["Adjusted HR raw"] = summary["exp(coef)"]
    summary["CI lower raw"] = summary["exp(coef) lower 95%"]
    summary["CI upper raw"] = summary["exp(coef) upper 95%"]
    displays = summary.apply(
        lambda row: estimate_display(
            float(row["Adjusted HR raw"]),
            float(row["CI lower raw"]),
            float(row["CI upper raw"]),
        ),
        axis=1,
        result_type="expand",
    )
    summary["Adjusted HR"] = displays[0]
    summary["95% CI"] = displays[1]
    summary["p value"] = summary["p"].map(p_value_display)
    return summary[
        [
            "Outcome",
            "Subgroup",
            "Model",
            "Exposure group",
            "Sample n",
            "Events n",
            "Adjusted HR raw",
            "CI lower raw",
            "CI upper raw",
            "Adjusted HR",
            "95% CI",
            "p value",
        ]
    ]


def model_hierarchy_table(df: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("Unadjusted", [], "t2d_analysis"),
        ("Age-sex adjusted", AGE_SEX_COVARS, "t2d_analysis"),
        ("Minimal-adjusted", MINIMAL_COVARS, "t2d_analysis"),
        ("Primary full model", FULL_COVARS, "t2d_analysis"),
    ]
    frames = []
    for model_name, covars, exposure_col in specs:
        for event_col, duration_col in DURATION_MAP.items():
            frames.append(
                fit_joint_model(
                    df,
                    duration_col=duration_col,
                    event_col=event_col,
                    exposure_col=exposure_col,
                    covars=covars,
                    analysis_label=model_name,
                )
            )
    return pd.concat(frames, ignore_index=True)


def raw_t2d_sensitivity_table(df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for model_name, exposure_col in [
        ("Primary full model", "t2d_analysis"),
        ("Raw T2D definition sensitivity", "t2d"),
    ]:
        for event_col, duration_col in [
            ("event_allcause", "followup_allcause_years"),
            ("event_mace", "followup_mace_years"),
        ]:
            frames.append(
                fit_joint_model(
                    df,
                    duration_col=duration_col,
                    event_col=event_col,
                    exposure_col=exposure_col,
                    covars=FULL_COVARS,
                    analysis_label=model_name,
                )
            )
    return pd.concat(frames, ignore_index=True)


def sex_stratified_table(df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    sex_map = {0: "Female", 1: "Male"}
    covars = [col for col in FULL_COVARS if col != "sex"]
    for sex_value, sex_label in sex_map.items():
        sex_df = df[df["sex"] == sex_value].copy()
        for event_col, duration_col in [
            ("event_allcause", "followup_allcause_years"),
            ("event_mace", "followup_mace_years"),
        ]:
            frames.append(
                fit_joint_model(
                    sex_df,
                    duration_col=duration_col,
                    event_col=event_col,
                    exposure_col="t2d_analysis",
                    covars=covars,
                    analysis_label="Primary full model",
                    subgroup_label=sex_label,
                )
            )
    return pd.concat(frames, ignore_index=True)


def heart_failure_table(model_hierarchy: pd.DataFrame) -> pd.DataFrame:
    return model_hierarchy[model_hierarchy["Outcome"] == "Heart failure"].copy()


def display_table(df: pd.DataFrame) -> pd.DataFrame:
    drop_cols = ["Adjusted HR raw", "CI lower raw", "CI upper raw"]
    keep_cols = [col for col in df.columns if col not in drop_cols]
    return df[keep_cols].copy()


def build_gbd_tables() -> dict[str, pd.DataFrame]:
    eapc = pd.read_csv(GBD_DIR / "Table_3_GBD_2023_EAPC.csv").rename(
        columns={
            "entity_label": "Entity",
            "measure_name": "Measure",
            "year_start": "Start year",
            "year_end": "End year",
            "eapc": "EAPC",
            "eapc_lower_95": "EAPC lower 95%",
            "eapc_upper_95": "EAPC upper 95%",
        }
    )
    eapc["EAPC (95% CI)"] = eapc.apply(
        lambda row: f"{row['EAPC']:.2f} ({row['EAPC lower 95%']:.2f} to {row['EAPC upper 95%']:.2f})",
        axis=1,
    )
    eapc = eapc[["Entity", "Measure", "Start year", "End year", "EAPC (95% CI)"]]

    region = pd.read_csv(GBD_DIR / "gbd2023_region_2023_prevalence_asr.csv").rename(
        columns={
            "entity_label": "Entity",
            "location_name": "Region",
            "val": "ASR per 100,000",
            "lower": "Lower 95% UI",
            "upper": "Upper 95% UI",
        }
    )
    region = region[["Entity", "Region", "ASR per 100,000", "Lower 95% UI", "Upper 95% UI"]]
    region["ASR per 100,000"] = region["ASR per 100,000"].round(2)
    region["Lower 95% UI"] = region["Lower 95% UI"].round(2)
    region["Upper 95% UI"] = region["Upper 95% UI"].round(2)

    country = pd.read_csv(GBD_DIR / "gbd2023_country_top10_2023_prevalence_asr.csv").rename(
        columns={
            "entity_label": "Entity",
            "location_name": "Country or territory",
            "val": "ASR per 100,000",
            "lower": "Lower 95% UI",
            "upper": "Upper 95% UI",
        }
    )
    country = country[["Entity", "Country or territory", "ASR per 100,000", "Lower 95% UI", "Upper 95% UI"]]
    country["ASR per 100,000"] = country["ASR per 100,000"].round(2)
    country["Lower 95% UI"] = country["Lower 95% UI"].round(2)
    country["Upper 95% UI"] = country["Upper 95% UI"].round(2)

    severity = pd.read_csv(GBD_DIR / "gbd2023_t2d_visionloss_severity_prevalence_asr_global_2023.csv").rename(
        columns={
            "sex_name": "Sex",
            "rei_name": "Severity",
            "val": "ASR per 100,000",
            "lower": "Lower 95% UI",
            "upper": "Upper 95% UI",
        }
    )
    severity = severity[["Sex", "Severity", "ASR per 100,000", "Lower 95% UI", "Upper 95% UI"]]
    severity["ASR per 100,000"] = severity["ASR per 100,000"].round(2)
    severity["Lower 95% UI"] = severity["Lower 95% UI"].round(2)
    severity["Upper 95% UI"] = severity["Upper 95% UI"].round(2)

    sex = pd.read_csv(GBD_DIR / "gbd2023_global_sex_2023_prevalence_asr.csv").rename(
        columns={
            "entity_label": "Entity",
            "sex_name": "Sex",
            "val": "ASR per 100,000",
            "lower": "Lower 95% UI",
            "upper": "Upper 95% UI",
        }
    )
    sex = sex[["Entity", "Sex", "ASR per 100,000", "Lower 95% UI", "Upper 95% UI"]]
    sex["ASR per 100,000"] = sex["ASR per 100,000"].round(2)
    sex["Lower 95% UI"] = sex["Lower 95% UI"].round(2)
    sex["Upper 95% UI"] = sex["Upper 95% UI"].round(2)

    return {
        "Supplementary_Table_S7_GBD_EAPC.csv": eapc,
        "Supplementary_Table_S8_GBD_Regional_Prevalence_ASR_2023.csv": region,
        "Supplementary_Table_S9_GBD_Country_Top10_VisionLoss_ASR_2023.csv": country,
        "Supplementary_Table_S10_GBD_Severity_Split_2023.csv": severity,
        "Supplementary_Table_S11_GBD_Global_Sex_ASR_2023.csv": sex,
    }


def write_overview(highlights: dict[str, object]) -> None:
    lines = [
        "# Supplementary Asset Overview",
        "",
        "## UK Biobank robustness highlights",
        "",
        f"- Incident cohort size: `{highlights['incident_n']:,}`",
        f"- Primary full-model sample size for all-cause mortality: `{highlights['full_allcause_n']:,}`",
        f"- Minimal-adjusted sample size for all-cause mortality: `{highlights['minimal_allcause_n']:,}`",
        f"- Primary full-model HR for T2D and retinopathy versus reference, all-cause mortality: `{highlights['full_allcause_both_hr']}`",
        f"- Primary full-model HR for T2D and retinopathy versus reference, MACE: `{highlights['full_mace_both_hr']}`",
        f"- Minimal-adjusted HR for T2D and retinopathy versus reference, all-cause mortality: `{highlights['minimal_allcause_both_hr']}`",
        f"- Minimal-adjusted HR for T2D and retinopathy versus reference, MACE: `{highlights['minimal_mace_both_hr']}`",
        f"- Primary full-model HR for T2D and retinopathy versus reference, heart failure: `{highlights['full_hf_both_hr']}`",
        f"- Raw T2D definition sensitivity HR for T2D and retinopathy versus reference, MACE: `{highlights['raw_t2d_mace_both_hr']}`",
        "",
        "## Files generated",
        "",
        "- `Supplementary_Table_S1_UKB_Missingness_Incident_Cohort.csv`",
        "- `Supplementary_Table_S2_UKB_Event_Rates_Per1000PY.csv`",
        "- `Supplementary_Table_S3_UKB_Model_Hierarchy.csv`",
        "- `Supplementary_Table_S4_UKB_T2D_Definition_Sensitivity.csv`",
        "- `Supplementary_Table_S5_UKB_Sex_Stratified_Full_Models.csv`",
        "- `Supplementary_Table_S6_UKB_Heart_Failure_Associations.csv`",
        "- `Supplementary_Table_S7_GBD_EAPC.csv`",
        "- `Supplementary_Table_S8_GBD_Regional_Prevalence_ASR_2023.csv`",
        "- `Supplementary_Table_S9_GBD_Country_Top10_VisionLoss_ASR_2023.csv`",
        "- `Supplementary_Table_S10_GBD_Severity_Split_2023.csv`",
        "- `Supplementary_Table_S11_GBD_Global_Sex_ASR_2023.csv`",
        "",
    ]
    (OUTDIR / "00_SUPPLEMENTARY_TABLE_OVERVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    (OUTDIR / "supplementary_highlights.json").write_text(
        json.dumps(highlights, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def ci_lookup(df: pd.DataFrame, *, outcome: str, model: str, exposure_group: str, subgroup: str = "Overall") -> str:
    row = df[
        (df["Outcome"] == outcome)
        & (df["Model"] == model)
        & (df["Exposure group"] == exposure_group)
        & (df["Subgroup"] == subgroup)
    ].iloc[0]
    return f"{row['Adjusted HR raw']:.2f} ({float(row['CI lower raw']):.2f}-{float(row['CI upper raw']):.2f})"


def main() -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    df = incident_cohort()

    s1 = missingness_table(df)
    s2 = event_rate_table(df)
    s3 = model_hierarchy_table(df)
    s4 = raw_t2d_sensitivity_table(df)
    s5 = sex_stratified_table(df)
    s6 = heart_failure_table(s3)
    gbd_tables = build_gbd_tables()

    s1.to_csv(OUTDIR / "Supplementary_Table_S1_UKB_Missingness_Incident_Cohort.csv", index=False)
    s2.to_csv(OUTDIR / "Supplementary_Table_S2_UKB_Event_Rates_Per1000PY.csv", index=False)
    display_table(s3).to_csv(OUTDIR / "Supplementary_Table_S3_UKB_Model_Hierarchy.csv", index=False)
    display_table(s4).to_csv(OUTDIR / "Supplementary_Table_S4_UKB_T2D_Definition_Sensitivity.csv", index=False)
    display_table(s5).to_csv(OUTDIR / "Supplementary_Table_S5_UKB_Sex_Stratified_Full_Models.csv", index=False)
    display_table(s6).to_csv(OUTDIR / "Supplementary_Table_S6_UKB_Heart_Failure_Associations.csv", index=False)
    for filename, table in gbd_tables.items():
        table.to_csv(OUTDIR / filename, index=False)

    highlights = {
        "incident_n": int(len(df)),
        "full_allcause_n": int(
            s3[(s3["Outcome"] == "All-cause mortality") & (s3["Model"] == "Primary full model")]["Sample n"].iloc[0]
        ),
        "minimal_allcause_n": int(
            s3[(s3["Outcome"] == "All-cause mortality") & (s3["Model"] == "Minimal-adjusted")]["Sample n"].iloc[0]
        ),
        "full_allcause_both_hr": ci_lookup(
            s3,
            outcome="All-cause mortality",
            model="Primary full model",
            exposure_group="T2D / Retinopathy",
        ),
        "full_mace_both_hr": ci_lookup(
            s3,
            outcome="MACE",
            model="Primary full model",
            exposure_group="T2D / Retinopathy",
        ),
        "minimal_allcause_both_hr": ci_lookup(
            s3,
            outcome="All-cause mortality",
            model="Minimal-adjusted",
            exposure_group="T2D / Retinopathy",
        ),
        "minimal_mace_both_hr": ci_lookup(
            s3,
            outcome="MACE",
            model="Minimal-adjusted",
            exposure_group="T2D / Retinopathy",
        ),
        "full_hf_both_hr": ci_lookup(
            s3,
            outcome="Heart failure",
            model="Primary full model",
            exposure_group="T2D / Retinopathy",
        ),
        "raw_t2d_mace_both_hr": ci_lookup(
            s4,
            outcome="MACE",
            model="Raw T2D definition sensitivity",
            exposure_group="T2D / Retinopathy",
        ),
    }
    write_overview(highlights)

    print(f"Saved supplementary assets to {OUTDIR}")


if __name__ == "__main__":
    main()
