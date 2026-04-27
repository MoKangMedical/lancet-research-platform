#!/usr/bin/env python3
"""Build manuscript-ready UKB figures for the DR-T2D eClinicalMedicine draft."""

from __future__ import annotations

from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pandas as pd


PROJECT_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/04_多期刊投稿包/GBD2023_UKB_DR_T2D_2026-03-07/journal_01_eClinicalMedicine"
)
UKB_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-基于全球疾病负担(GBD)和英国生物数据银行（UK Biobank）的糖尿病视网膜病变与2型糖尿病（T2D）交互作用-10分以上/"
    "Codex研究产出_2026-03-07/02_UKB结果/ukb_dr_t2d"
)


def build_figure_3() -> Path:
    allcause_img = mpimg.imread(UKB_DIR / "km_allcause_joint_groups.png")
    mace_img = mpimg.imread(UKB_DIR / "km_mace_joint_groups.png")

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), dpi=300)
    for ax, img, title, panel in [
        (axes[0], allcause_img, "All-cause mortality", "A"),
        (axes[1], mace_img, "Major adverse cardiovascular events", "B"),
    ]:
        ax.imshow(img)
        ax.axis("off")
        ax.set_title(f"{panel}. {title}", loc="left", fontsize=12, fontweight="bold")

    fig.suptitle("UK Biobank Kaplan-Meier curves by joint T2D-retinopathy status", fontsize=14, y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.96))

    out = PROJECT_DIR / "Figure_3_UKB_KM.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def build_figure_4() -> Path:
    df = pd.read_csv(UKB_DIR / "cox_joint_groups.csv")
    df = df[df["term"].isin(["joint_1", "joint_2", "joint_3"])].copy()

    outcome_map = {
        "event_allcause": "All-cause mortality",
        "event_mace": "MACE",
    }
    group_map = {
        "joint_1": "No T2D / Retinopathy",
        "joint_2": "T2D / No retinopathy",
        "joint_3": "T2D / Retinopathy",
    }

    df["outcome_label"] = df["outcome"].map(outcome_map)
    df["group_label"] = df["term"].map(group_map)
    df["y_label"] = df["outcome_label"] + " | " + df["group_label"]

    plot_order = [
        "All-cause mortality | No T2D / Retinopathy",
        "All-cause mortality | T2D / No retinopathy",
        "All-cause mortality | T2D / Retinopathy",
        "MACE | No T2D / Retinopathy",
        "MACE | T2D / No retinopathy",
        "MACE | T2D / Retinopathy",
    ]
    df["y_label"] = pd.Categorical(df["y_label"], categories=plot_order, ordered=True)
    df = df.sort_values("y_label", ascending=False).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(9, 5.8), dpi=300)
    y = list(range(len(df)))
    hr = df["exp(coef)"]
    lo = df["exp(coef) lower 95%"]
    hi = df["exp(coef) upper 95%"]
    xerr = [hr - lo, hi - hr]

    colors = ["#7c9f35" if "All-cause" in label else "#b65b3a" for label in df["y_label"].astype(str)]
    ax.errorbar(hr, y, xerr=xerr, fmt="none", ecolor="#555555", elinewidth=1.5, capsize=3, zorder=2)
    ax.scatter(hr, y, s=45, c=colors, zorder=3)
    ax.axvline(1.0, color="#888888", linestyle="--", linewidth=1)

    ax.set_yticks(y)
    ax.set_yticklabels(df["y_label"])
    ax.set_xlabel("Adjusted hazard ratio (95% CI)")
    ax.set_title("Adjusted hazards for mortality and MACE by joint T2D-retinopathy status", loc="left", fontsize=13)
    ax.grid(axis="x", alpha=0.25)
    ax.set_xlim(0, max(6.5, float(hi.max()) + 0.4))

    for yi, hr_i, lo_i, hi_i in zip(y, hr, lo, hi):
        ax.text(float(hi.max()) + 0.1, yi, f"{hr_i:.2f} ({lo_i:.2f}-{hi_i:.2f})", va="center", fontsize=9)

    ax.text(0.01, -0.12, "Reference group: No T2D / No retinopathy", transform=ax.transAxes, fontsize=9)
    fig.tight_layout()

    out = PROJECT_DIR / "Figure_4_UKB_Adjusted_HRs.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    fig3 = build_figure_3()
    fig4 = build_figure_4()
    print(f"Saved: {fig3}")
    print(f"Saved: {fig4}")


if __name__ == "__main__":
    main()
