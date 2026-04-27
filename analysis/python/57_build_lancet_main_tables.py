#!/usr/bin/env python3
"""Build Lancet-main table assets for the DR-T2D manuscript."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/04_多期刊投稿包/GBD2023_UKB_DR_T2D_2026-03-07/journal_01_eClinicalMedicine/lancet_main_tables"
)
UKB_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/02_UKB结果/ukb_dr_t2d"
)
GBD_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/04_多期刊投稿包/GBD2023_UKB_DR_T2D_2026-03-07/journal_01_eClinicalMedicine/gbd_2023_results"
)


def fmt_mean(value: float) -> str:
    return f"{value:.1f}"


def fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def fmt_int(value: float) -> str:
    return f"{int(round(value)):,}"


def fmt_rate(value: float) -> str:
    return f"{value:.1f}"


def build_table_1() -> pd.DataFrame:
    raw = pd.read_csv(UKB_DIR / "table1_joint_groups.csv")
    wide = raw.pivot(index="metric", columns="group", values="value")
    col_order = [
        "No T2D / No retinopathy",
        "No T2D / Retinopathy",
        "T2D / No retinopathy",
        "T2D / Retinopathy",
    ]
    wide = wide[col_order]
    rows = [
        ("Participants, n", "n", fmt_int),
        ("Age at baseline, years", "age_mean", fmt_mean),
        ("Women, %", "female_pct", fmt_pct),
        ("Body-mass index, kg/m2", "bmi_mean", fmt_mean),
        ("HbA1c, mmol/mol", "hba1c_mean", fmt_mean),
        ("Systolic blood pressure, mm Hg", "sbp_mean", fmt_mean),
        ("Current smoking, %", "smoking_current_pct", fmt_pct),
        ("All-cause deaths, n", "allcause_events", fmt_int),
        ("MACE events, n", "mace_events", fmt_int),
    ]
    out = []
    for label, metric, formatter in rows:
        vals = [formatter(float(wide.loc[metric, col])) for col in col_order]
        out.append([label, *vals])
    return pd.DataFrame(out, columns=["Characteristic", *col_order])


def build_table_2() -> pd.DataFrame:
    raw = pd.read_csv(GBD_DIR / "Table_2_GBD_2023_Global_Summary.csv")
    entity_map = {
        "Type 2 diabetes": "Type 2 diabetes",
        "T2D-related vision loss": "T2D-related vision loss",
    }
    metric_map = {
        ("Prevalence", "Number"): "Prevalence, number",
        ("Prevalence", "Rate"): "Prevalence, ASR per 100,000",
        ("DALYs", "Number"): "DALYs, number",
        ("DALYs", "Rate"): "DALYs, ASR per 100,000",
        ("YLDs", "Number"): "YLDs, number",
        ("YLDs", "Rate"): "YLDs, ASR per 100,000",
    }
    rows = []
    for entity in ["Type 2 diabetes", "T2D-related vision loss"]:
        sub = raw[raw["entity_label"] == entity]
        for _, r in sub.iterrows():
            label = metric_map[(r["measure_name"], r["metric_name"])]
            value_1990 = fmt_int(r["value_1990"]) if r["metric_name"] == "Number" else fmt_rate(r["value_1990"])
            value_2023 = fmt_int(r["value_2023"]) if r["metric_name"] == "Number" else fmt_rate(r["value_2023"])
            pct = f"{r['pct_change_1990_2023']:.1f}%"
            rows.append([entity_map[entity], label, value_1990, value_2023, pct])
    return pd.DataFrame(rows, columns=["Entity", "Measure", "1990", "2023", "% change"])


def build_table_3() -> pd.DataFrame:
    raw = pd.read_csv(UKB_DIR / "cox_joint_groups.csv")
    raw = raw[raw["term"].isin(["joint_1", "joint_2", "joint_3"])].copy()
    term_map = {
        "joint_1": "No T2D / Retinopathy",
        "joint_2": "T2D / No retinopathy",
        "joint_3": "T2D / Retinopathy",
    }
    outcome_map = {
        "event_allcause": "All-cause mortality",
        "event_mace": "MACE",
    }
    rows = []
    for outcome in ["event_allcause", "event_mace"]:
        sub = raw[raw["outcome"] == outcome].copy()
        sub["Exposure group"] = sub["term"].map(term_map)
        sub["Outcome"] = outcome_map[outcome]
        for _, r in sub.iterrows():
            rows.append(
                [
                    r["Outcome"],
                    r["Exposure group"],
                    f"{r['exp(coef)']:.2f}",
                    f"{r['exp(coef) lower 95%']:.2f}-{r['exp(coef) upper 95%']:.2f}",
                    f"{r['p']:.3g}",
                ]
            )
    return pd.DataFrame(rows, columns=["Outcome", "Exposure group", "Adjusted HR", "95% CI", "p value"])


def build_table_3_main() -> pd.DataFrame:
    raw = build_table_3().copy()
    return raw.drop(columns=["p value"])


def build_appendix_table_3() -> pd.DataFrame:
    joint = pd.read_csv(UKB_DIR / "cox_joint_groups.csv")
    inter = pd.read_csv(UKB_DIR / "cox_interaction_terms.csv")
    add = pd.read_csv(UKB_DIR / "additive_interaction_metrics.csv")

    joint = joint[joint["term"].isin(["joint_1", "joint_2", "joint_3"])].copy()
    joint["model_block"] = "Joint exposure model"
    inter = inter[inter["term"].isin(["t2d", "retinopathy", "t2d_x_retinopathy"])].copy()
    inter["model_block"] = "Interaction model"

    outcome_map = {
        "event_allcause": "All-cause mortality",
        "event_mace": "MACE",
    }
    term_map = {
        "joint_1": "No T2D / Retinopathy",
        "joint_2": "T2D / No retinopathy",
        "joint_3": "T2D / Retinopathy",
        "t2d": "T2D main effect",
        "retinopathy": "Retinopathy main effect",
        "t2d_x_retinopathy": "T2D x retinopathy",
    }

    rows = []
    for frame in [joint, inter]:
        for _, r in frame.iterrows():
            rows.append(
                {
                    "Section": r["model_block"],
                    "Outcome": outcome_map[r["outcome"]],
                    "Term": term_map[r["term"]],
                    "Adjusted HR": f"{r['exp(coef)']:.2f}",
                    "95% CI": f"{r['exp(coef) lower 95%']:.2f}-{r['exp(coef) upper 95%']:.2f}",
                    "p value": f"{r['p']:.3g}",
                }
            )
    add_rows = []
    metric_map = {
        "HR_01": "HR for retinopathy without T2D",
        "HR_10": "HR for T2D without retinopathy",
        "HR_11": "HR for T2D with retinopathy",
        "RERI": "Relative excess risk due to interaction",
        "AP": "Attributable proportion",
        "S": "Synergy index",
    }
    for _, r in add.iterrows():
        add_rows.append(
            {
                "Section": "Additive interaction metrics",
                "Outcome": outcome_map[r["outcome"]],
                "Term": metric_map[r["metric"]],
                "Adjusted HR": f"{r['value']:.3f}" if abs(r["value"]) < 10 else f"{r['value']:.2f}",
                "95% CI": "",
                "p value": "",
            }
        )
    return pd.DataFrame(rows + add_rows, columns=["Section", "Outcome", "Term", "Adjusted HR", "95% CI", "p value"])


def build_table_notes() -> str:
    return (
        "# Lancet Main Table System\n\n"
        "## Table 1\n"
        "Baseline profile and crude event counts of the incident UK Biobank cohort by joint T2D-retinal disease status.\n\n"
        "## Table 2\n"
        "Global 1990 and 2023 burden summary for type 2 diabetes and T2D-related vision loss from GBD 2023.\n\n"
        "## Table 3 main-text version\n"
        "Adjusted associations of joint T2D-retinal disease status with all-cause mortality and MACE in UK Biobank.\n\n"
        "## Appendix Table 3 version\n"
        "Expanded joint, interaction, and additive interaction estimates.\n\n"
        "## Supplementary table candidates\n"
        "- Interaction terms and additive interaction metrics.\n"
        "- Region and country rankings.\n"
        "- Severity split of T2D-related vision loss.\n"
    )


def main() -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    table_1 = build_table_1()
    table_2 = build_table_2()
    table_3 = build_table_3()
    table_3_main = build_table_3_main()
    appendix_table_3 = build_appendix_table_3()
    table_1.to_csv(PROJECT_DIR / "Table_1_UKB_Cohort_Profile_Lancet.csv", index=False)
    table_2.to_csv(PROJECT_DIR / "Table_2_GBD_Global_Burden_Lancet.csv", index=False)
    table_3.to_csv(PROJECT_DIR / "Table_3_UKB_Adjusted_Associations_Lancet_detailed.csv", index=False)
    table_3_main.to_csv(PROJECT_DIR / "Table_3_UKB_Adjusted_Associations_Lancet_main.csv", index=False)
    appendix_table_3.to_csv(PROJECT_DIR / "Appendix_Table_3_UKB_Interaction_and_Full_Models_Lancet.csv", index=False)
    (PROJECT_DIR / "00_TABLE_SYSTEM_OVERVIEW.md").write_text(build_table_notes(), encoding="utf-8")
    print(f"Saved Lancet-main tables to {PROJECT_DIR}")


if __name__ == "__main__":
    main()
