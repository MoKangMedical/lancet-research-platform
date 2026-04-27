#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path("/Users/apple/Documents/lancet-research-platform")
DEFAULT_DIRF_ROOT = ROOT / "data" / "bronze" / "gbd" / "gbd2023" / "dirf-2023"
DEFAULT_OUT_CSV = ROOT / "data" / "silver" / "gbd" / "gbd2023_dirf_global_core_tidy.csv"
DEFAULT_QC_OUT = ROOT / "outputs" / "tables" / "gbd2023_dirf_global_core_qc.json"

warnings.filterwarnings("ignore", message=".*ChainedAssignmentError.*", category=FutureWarning)


@dataclass(frozen=True)
class TableSpec:
    table_id: int
    filename: str
    measure: str
    metric: str
    unit: str


TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(1, "IHME_GBD_2023_DIRF_1990_2023_APPENDIX_3_TABLE_1_Y2025M09D26.XLSX", "prevalence", "age_standardized_rate", "per_100000"),
    TableSpec(2, "IHME_GBD_2023_DIRF_1990_2023_APPENDIX_3_TABLE_2_Y2025M09D26.XLSX", "incidence", "age_standardized_rate", "per_100000"),
    TableSpec(3, "IHME_GBD_2023_DIRF_1990_2023_APPENDIX_3_TABLE_3_Y2025M09D26.XLSX", "DALY", "count", "count"),
    TableSpec(4, "IHME_GBD_2023_DIRF_1990_2023_APPENDIX_3_TABLE_4_Y2025M09D26.XLSX", "DALY", "age_standardized_rate", "per_100000"),
    TableSpec(5, "IHME_GBD_2023_DIRF_1990_2023_APPENDIX_3_TABLE_5_Y2025M09D26.XLSX", "YLD", "count", "count"),
    TableSpec(6, "IHME_GBD_2023_DIRF_1990_2023_APPENDIX_3_TABLE_6_Y2025M09D26.XLSX", "YLD", "age_standardized_rate", "per_100000"),
    TableSpec(7, "IHME_GBD_2023_DIRF_1990_2023_APPENDIX_3_TABLE_7_Y2025M09D26.XLSX", "YLL", "count", "count"),
    TableSpec(8, "IHME_GBD_2023_DIRF_1990_2023_APPENDIX_3_TABLE_8_Y2025M09D26.XLSX", "YLL", "age_standardized_rate", "per_100000"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse core GBD 2023 DIRF appendix tables into a tidy global dataset.")
    parser.add_argument("--dirf-root", default=str(DEFAULT_DIRF_ROOT), help="Root of extracted DIRF appendix tables")
    parser.add_argument("--out-csv", default=str(DEFAULT_OUT_CSV), help="Output tidy CSV")
    parser.add_argument("--qc-out", default=str(DEFAULT_QC_OUT), help="Output QC JSON")
    return parser.parse_args()


def normalize_sex(value: object) -> str | None:
    text = str(value).strip()
    mapping = {
        "Both Sexes": "Both",
        "Females": "Female",
        "Males": "Male",
    }
    return mapping.get(text)


def normalize_stat(value: object) -> str | None:
    text = str(value).strip().lower()
    if text in {"mean", "lower", "upper"}:
        return text
    return None


def parse_year(value: object) -> int | None:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    match = re.search(r"(19|20)\d{2}", text)
    return int(match.group(0)) if match else None


def parse_number(value: object) -> float | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    text = text.replace(",", "").replace("·", ".")
    try:
        return float(text)
    except ValueError:
        return None


def find_appendix_table(dirf_root: Path, filename: str) -> Path:
    matches = sorted(dirf_root.rglob(filename))
    if not matches:
        raise FileNotFoundError(f"Could not find {filename} under {dirf_root}")
    return matches[0]


def parse_core_table(path: Path, spec: TableSpec) -> list[dict[str, object]]:
    raw = pd.read_excel(path, header=None)
    year_row = raw.iloc[1].ffill()
    sex_row = raw.iloc[2].ffill()
    stat_row = raw.iloc[3]
    data = raw.iloc[4:].reset_index(drop=True)

    records: list[dict[str, object]] = []
    for _, row in data.iterrows():
        cause_name = row.iloc[1]
        if pd.isna(cause_name):
            continue
        cause_name_text = str(cause_name).strip()
        if not cause_name_text:
            continue
        cause_level_value = parse_number(row.iloc[0])
        grouped: dict[tuple[int, str], dict[str, object]] = {}
        for col_idx in range(2, raw.shape[1]):
            year_id = parse_year(year_row.iloc[col_idx])
            sex = normalize_sex(sex_row.iloc[col_idx])
            stat = normalize_stat(stat_row.iloc[col_idx])
            if year_id is None or sex is None or stat is None:
                continue
            key = (year_id, sex)
            if key not in grouped:
                grouped[key] = {
                    "location_name": "Global",
                    "cause_level": int(cause_level_value) if cause_level_value is not None else pd.NA,
                    "cause_name": cause_name_text,
                    "measure": spec.measure,
                    "metric": spec.metric,
                    "unit": spec.unit,
                    "year_id": year_id,
                    "sex": sex,
                    "mean": None,
                    "lower": None,
                    "upper": None,
                    "source_table_id": spec.table_id,
                    "source_table": path.name,
                }
            grouped[key][stat] = parse_number(row.iloc[col_idx])
        records.extend(grouped.values())
    return records


def build_qc(df: pd.DataFrame, inputs: list[str], out_csv: Path) -> dict[str, object]:
    return {
        "inputs": inputs,
        "output": str(out_csv),
        "rows": int(len(df)),
        "measures": sorted(df["measure"].dropna().astype(str).unique().tolist()),
        "metrics": sorted(df["metric"].dropna().astype(str).unique().tolist()),
        "sexes": sorted(df["sex"].dropna().astype(str).unique().tolist()),
        "years": sorted(df["year_id"].dropna().astype(int).unique().tolist()),
        "causes": int(df["cause_name"].nunique()),
        "missing_mean_rows": int(df["mean"].isna().sum()),
        "duplicate_rows": int(df.duplicated(subset=["cause_name", "measure", "metric", "year_id", "sex"], keep=False).sum()),
    }


def main() -> int:
    args = parse_args()
    dirf_root = Path(args.dirf_root).expanduser()
    out_csv = Path(args.out_csv).expanduser()
    qc_out = Path(args.qc_out).expanduser()

    all_records: list[dict[str, object]] = []
    input_paths: list[str] = []
    for spec in TABLE_SPECS:
        path = find_appendix_table(dirf_root, spec.filename)
        print(f"parse {path}")
        input_paths.append(str(path))
        all_records.extend(parse_core_table(path, spec))

    df = pd.DataFrame(all_records).copy()
    df["cause_level"] = pd.to_numeric(df["cause_level"], errors="coerce").astype("Int64")
    df["year_id"] = pd.to_numeric(df["year_id"], errors="coerce").astype("Int64")
    for column in ["mean", "lower", "upper"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.sort_values(["measure", "metric", "cause_level", "cause_name", "sex", "year_id"]).reset_index(drop=True)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    qc_payload = build_qc(df, inputs=input_paths, out_csv=out_csv)
    qc_out.parent.mkdir(parents=True, exist_ok=True)
    qc_out.write_text(json.dumps(qc_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"tidy csv {out_csv}")
    print(f"qc {qc_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
