#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path("/Users/apple/Documents/lancet-research-platform")
MAP_SCRIPT = ROOT / "analysis" / "python" / "35_gbd_choropleth_map.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reusable GBD summary-table, trend-plot, and map outputs from tidy data.")
    parser.add_argument("--input", required=True, help="Tidy CSV/XLSX/Parquet input")
    parser.add_argument("--measure", default="", help="Measure filter, e.g. prevalence, incidence, DALY, YLD, YLL")
    parser.add_argument("--metric", default="", help="Metric filter, e.g. age_standardized_rate or count")
    parser.add_argument("--sex", default="", help="Sex filter")
    parser.add_argument("--location", default="", help="Location filter")
    parser.add_argument("--summary-year", type=int, default=2023)
    parser.add_argument("--top-n", type=int, default=12)
    parser.add_argument("--cause-pattern", action="append", default=[], help="Regex cause filter; repeatable")
    parser.add_argument("--map-cause", default="", help="Cause to use for map output when multiple causes are present")
    parser.add_argument("--value-col", default="mean")
    parser.add_argument("--year-col", default="year_id")
    parser.add_argument("--measure-col", default="measure")
    parser.add_argument("--metric-col", default="metric")
    parser.add_argument("--sex-col", default="sex")
    parser.add_argument("--location-col", default="location_name")
    parser.add_argument("--cause-col", default="cause_name")
    parser.add_argument("--lower-col", default="lower")
    parser.add_argument("--upper-col", default="upper")
    parser.add_argument("--out-prefix", default="", help="Optional explicit output prefix path without extension")
    return parser.parse_args()


def read_df(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input format: {suffix}")


def slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_").replace("__", "_")


def maybe_filter_exact(df: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    if not value or column not in df.columns:
        return df
    return df.loc[df[column].astype(str).str.casefold() == value.casefold()].copy()


def maybe_filter_regex(df: pd.DataFrame, column: str, patterns: list[str]) -> pd.DataFrame:
    if not patterns or column not in df.columns:
        return df
    mask = pd.Series(False, index=df.index)
    for pattern in patterns:
        mask = mask | df[column].astype(str).str.contains(pattern, case=False, regex=True, na=False)
    return df.loc[mask].copy()


def choose_top_causes(df: pd.DataFrame, args: argparse.Namespace) -> tuple[pd.DataFrame, list[str]]:
    if args.cause_col not in df.columns:
        return df, []

    if args.cause_pattern:
        filtered = maybe_filter_regex(df, args.cause_col, args.cause_pattern)
        return filtered, sorted(filtered[args.cause_col].dropna().astype(str).unique().tolist())

    year_df = df.loc[df[args.year_col] == args.summary_year].copy() if args.year_col in df.columns else df.copy()
    if year_df.empty:
        year_df = df.copy()

    candidates = year_df.copy()
    if args.cause_col in candidates.columns and (candidates[args.cause_col] != "All causes").any():
        candidates = candidates.loc[candidates[args.cause_col] != "All causes"].copy()

    if candidates.empty:
        candidates = year_df.copy()

    top_rows = candidates.nlargest(args.top_n, args.value_col)
    causes = top_rows[args.cause_col].dropna().astype(str).tolist()
    if not causes:
        return df, []
    filtered = df.loc[df[args.cause_col].isin(causes)].copy()
    return filtered, causes


def build_summary_table(df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    summary_df = df.loc[df[args.year_col] == args.summary_year].copy() if args.year_col in df.columns else df.copy()
    if summary_df.empty:
        summary_df = df.copy()
    sort_columns = [args.value_col]
    summary_df = summary_df.sort_values(sort_columns, ascending=False).reset_index(drop=True)
    keep = [
        column
        for column in [
            args.location_col,
            args.cause_col,
            args.measure_col,
            args.metric_col,
            args.sex_col,
            args.year_col,
            args.value_col,
            args.lower_col,
            args.upper_col,
        ]
        if column in summary_df.columns
    ]
    return summary_df[keep].copy()


def build_trend_plot(df: pd.DataFrame, args: argparse.Namespace, out_png: Path) -> None:
    if args.year_col not in df.columns or args.value_col not in df.columns:
        raise ValueError("Trend plot requires year and value columns.")

    label_columns = []
    for column in [args.cause_col, args.sex_col, args.location_col]:
        if column in df.columns and df[column].nunique() > 1:
            label_columns.append(column)

    if not label_columns:
        label_columns = [column for column in [args.cause_col, args.sex_col, args.location_col] if column in df.columns][:1]

    trend_df = df.sort_values(args.year_col).copy()
    if label_columns:
        trend_df["series_label"] = trend_df[label_columns].astype(str).agg(" | ".join, axis=1)
    else:
        trend_df["series_label"] = "Series"

    grouped = list(trend_df.groupby("series_label", sort=False))
    fig, ax = plt.subplots(figsize=(9, max(5, len(grouped) * 0.45)))
    for label, frame in grouped:
        ax.plot(frame[args.year_col], frame[args.value_col], marker="o", linewidth=2, label=label)
        if len(grouped) == 1 and args.lower_col in frame.columns and args.upper_col in frame.columns:
            ax.fill_between(frame[args.year_col], frame[args.lower_col], frame[args.upper_col], alpha=0.2)

    title_bits = [bit for bit in [args.measure or "", args.metric or "", "Trend"] if bit]
    ax.set_title(" ".join(title_bits))
    ax.set_xlabel(args.year_col)
    ax.set_ylabel(args.value_col)
    if len(grouped) > 1:
        ax.legend(frameon=False, fontsize=9)
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=220)
    plt.close(fig)


def build_map(df: pd.DataFrame, args: argparse.Namespace, prefix: Path) -> dict[str, object]:
    if args.location_col not in df.columns or df[args.location_col].nunique() <= 1:
        return {"generated": False, "reason": "input is not location-level"}

    map_df = df.copy()
    if args.year_col in map_df.columns:
        year_slice = map_df.loc[map_df[args.year_col] == args.summary_year].copy()
        if not year_slice.empty:
            map_df = year_slice
    if args.cause_col in map_df.columns and map_df[args.cause_col].nunique() > 1:
        if args.map_cause:
            map_df = maybe_filter_exact(map_df, args.cause_col, args.map_cause)
        elif (map_df[args.cause_col] == "All causes").any():
            map_df = map_df.loc[map_df[args.cause_col] == "All causes"].copy()
        else:
            top_cause = (
                map_df.sort_values(args.value_col, ascending=False)[args.cause_col].dropna().astype(str).iloc[0]
            )
            map_df = map_df.loc[map_df[args.cause_col] == top_cause].copy()

    if map_df.empty or map_df[args.location_col].nunique() <= 1:
        return {"generated": False, "reason": "no mappable location-level rows after cause selection"}

    if map_df.duplicated(subset=[args.location_col], keep=False).any():
        map_df = (
            map_df.sort_values(args.value_col, ascending=False)
            .drop_duplicates(subset=[args.location_col], keep="first")
            .copy()
        )

    map_input = prefix.parent.parent / "tables" / f"{prefix.name}_map_input.csv"
    map_input.parent.mkdir(parents=True, exist_ok=True)
    map_df[[args.location_col, args.value_col]].rename(columns={args.location_col: "location_name", args.value_col: "val"}).to_csv(map_input, index=False)

    out_html = prefix.parent / f"{prefix.name}_map.html"
    out_png = prefix.parent / f"{prefix.name}_map.png"
    out_prepped = prefix.parent.parent / "tables" / f"{prefix.name}_map_prepped.csv"

    cmd = [
        str(ROOT / ".." / ".venvs" / "data-analytics" / "bin" / "python"),
        str(MAP_SCRIPT),
        "--input",
        str(map_input),
        "--value_col",
        "val",
        "--location_col",
        "location_name",
        "--title",
        f"{prefix.name} map",
        "--out_html",
        str(out_html),
        "--out_png",
        str(out_png),
        "--out_csv",
        str(out_prepped),
        "--skip_png",
    ]
    subprocess.run(cmd, check=True)
    return {
        "generated": True,
        "input": str(map_input),
        "html": str(out_html),
        "png": str(out_png),
        "prepped": str(out_prepped),
    }


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser()
    df = read_df(input_path).copy()

    df = maybe_filter_exact(df, args.measure_col, args.measure)
    df = maybe_filter_exact(df, args.metric_col, args.metric)
    df = maybe_filter_exact(df, args.sex_col, args.sex)
    df = maybe_filter_exact(df, args.location_col, args.location)

    if df.empty:
        raise ValueError("No rows left after applying filters.")

    focused_df, selected_causes = choose_top_causes(df, args)
    if focused_df.empty:
        raise ValueError("No rows left after selecting causes.")

    summary_df = build_summary_table(focused_df, args)

    prefix = (
        Path(args.out_prefix).expanduser()
        if args.out_prefix
        else ROOT
        / "outputs"
        / "figures"
        / slugify(
            "_".join(
                bit
                for bit in [
                    "gbd_template",
                    args.measure or "all",
                    args.metric or "all",
                    str(args.summary_year),
                    args.sex or "all",
                ]
                if bit
            )
        )
    )
    prefix.parent.mkdir(parents=True, exist_ok=True)

    summary_out = prefix.parent.parent / "tables" / f"{prefix.name}_summary.csv"
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(summary_out, index=False)

    trend_out = prefix.parent / f"{prefix.name}_trend.png"
    build_trend_plot(focused_df, args, trend_out)

    map_payload = build_map(focused_df, args, prefix)
    manifest = {
        "input": str(input_path),
        "summary_table": str(summary_out),
        "trend_figure": str(trend_out),
        "map": map_payload,
        "selected_causes": selected_causes,
        "summary_year": args.summary_year,
        "measure": args.measure,
        "metric": args.metric,
        "sex": args.sex,
        "location": args.location,
    }
    manifest_out = prefix.parent.parent / "tables" / f"{prefix.name}_manifest.json"
    manifest_out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"summary {summary_out}")
    print(f"trend {trend_out}")
    print(f"manifest {manifest_out}")
    if map_payload.get("generated"):
        print(f"map {map_payload['html']}")
    else:
        print(f"map skipped: {map_payload.get('reason', 'unknown')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
