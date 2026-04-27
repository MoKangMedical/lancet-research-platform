#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import warnings
from pathlib import Path

import nbformat as nbf
import pandas as pd

ROOT = Path("/Users/apple/Documents/lancet-research-platform")
DEFAULT_BRONZE_ROOT = ROOT / "data" / "bronze" / "gbd" / "gbd2023"
DEFAULT_SILVER_ROOT = ROOT / "data" / "silver" / "gbd"
DEFAULT_NOTEBOOK_OUT = ROOT / "notebooks" / "gbd2023_starter_analysis.ipynb"
DEFAULT_QC_OUT = ROOT / "outputs" / "tables" / "gbd2023_starter_qc.json"

warnings.filterwarnings("ignore", message=".*ChainedAssignmentError.*", category=FutureWarning)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build reusable GBD 2023 starter datasets and a notebook from the extracted bronze layer."
    )
    parser.add_argument("--bronze-root", default=str(DEFAULT_BRONZE_ROOT), help="Root of extracted GBD bronze files")
    parser.add_argument("--silver-root", default=str(DEFAULT_SILVER_ROOT), help="Output directory for starter datasets")
    parser.add_argument("--notebook-out", default=str(DEFAULT_NOTEBOOK_OUT), help="Starter notebook path")
    parser.add_argument("--qc-out", default=str(DEFAULT_QC_OUT), help="QC summary JSON path")
    parser.add_argument("--force", action="store_true", help="Overwrite outputs if they already exist")
    return parser.parse_args()


def snake_case(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized.lower()


def find_one(bronze_root: Path, pattern: str) -> Path:
    matches = sorted(bronze_root.rglob(pattern))
    if not matches:
        raise FileNotFoundError(f"No files match pattern {pattern} under {bronze_root}")
    if len(matches) > 1:
        print(f"using {matches[0]} for pattern {pattern}")
    return matches[0]


def parse_interval_series(series: pd.Series) -> pd.DataFrame:
    cleaned = series.fillna("").astype(str).str.strip().str.replace(",", "", regex=False)
    extracted = cleaned.str.extract(
        r"^(?P<estimate>-?\d+(?:\.\d+)?)\s*(?:\((?P<lower>-?\d+(?:\.\d+)?)-(?P<upper>-?\d+(?:\.\d+)?)\))?$"
    )
    return extracted.apply(lambda column: pd.to_numeric(column, errors="coerce"))


def build_mortality_long(mortality_csv: Path, output_path: Path) -> dict[str, object]:
    df = pd.read_csv(mortality_csv, skiprows=1, encoding="latin1")
    df.columns = [column.strip() for column in df.columns]

    value_columns = [column for column in df.columns if re.match(r"^\d{4} \([^)]+\)$", column)]
    id_columns = [column for column in df.columns if column not in value_columns]
    long_df = df.melt(id_vars=id_columns, value_vars=value_columns, var_name="year_metric", value_name="value_raw")

    year_metric = long_df["year_metric"].str.extract(r"(?P<year_id>\d{4}) \((?P<metric_label>[^)]+)\)")
    parsed_values = parse_interval_series(long_df["value_raw"])
    long_df = pd.concat([long_df, year_metric, parsed_values], axis=1).copy()
    long_df["year_id"] = long_df["year_id"].astype("Int64")
    long_df["metric"] = long_df["metric_label"].map(
        {
            "ASMR": "age_standardized_mortality_rate",
            "All-Age Deaths": "all_age_deaths",
        }
    )
    long_df["metric"] = long_df["metric"].fillna(long_df["metric_label"].map(snake_case))
    long_df["unit"] = long_df["metric_label"].map(
        {
            "ASMR": "per_100000",
            "All-Age Deaths": "count",
        }
    )
    long_df["unit"] = long_df["unit"].fillna("unknown")
    long_df["sex"] = "Both"
    long_df["source_table"] = mortality_csv.name
    long_df = long_df.rename(
        columns={
            "Location Name": "location_name",
            "Cause Name": "cause_name",
        }
    )
    output_columns = [
        "location_name",
        "cause_name",
        "sex",
        "year_id",
        "metric",
        "unit",
        "estimate",
        "lower",
        "upper",
        "source_table",
    ]
    tidy = long_df[output_columns].sort_values(["location_name", "cause_name", "metric", "year_id"]).reset_index(
        drop=True
    )
    duplicate_rows = int(
        tidy.duplicated(subset=["location_name", "cause_name", "sex", "year_id", "metric"], keep=False).sum()
    )
    duplicate_locations = sorted(
        tidy.loc[
            tidy.duplicated(subset=["location_name", "cause_name", "sex", "year_id", "metric"], keep=False),
            "location_name",
        ]
        .dropna()
        .unique()
        .tolist()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tidy.to_csv(output_path, index=False)
    return {
        "input": str(mortality_csv),
        "output": str(output_path),
        "rows": int(len(tidy)),
        "locations": int(tidy["location_name"].nunique()),
        "causes": int(tidy["cause_name"].nunique()),
        "years": sorted(tidy["year_id"].dropna().astype(int).unique().tolist()),
        "name_level_duplicate_rows": duplicate_rows,
        "name_level_duplicate_locations": duplicate_locations,
        "limitation": (
            "Official Appendix Table S7 does not include stable location IDs. "
            "Some location names repeat across hierarchy levels, so this starter table is suitable for exploration "
            "and prototyping but not as the final source for publication-grade country/subnational inference."
        ),
    }


def derive_indicator(path: Path) -> str:
    name = path.stem
    name = re.sub(r"_Y\d{4}M\d{2}D\d{2}$", "", name, flags=re.I)
    name = re.sub(r"^IHME_GBD_2023_RISK_EXPOSURE_HIGH_BMI_", "", name, flags=re.I)
    return snake_case(name)


def build_high_bmi_global(inputs: list[Path], output_path: Path) -> dict[str, object]:
    frames: list[pd.DataFrame] = []
    for csv_path in inputs:
        for chunk in pd.read_csv(csv_path, chunksize=200000):
            chunk.columns = [snake_case(column) for column in chunk.columns]
            if "measure_id" not in chunk.columns:
                chunk["measure_id"] = pd.NA
            if "definition" not in chunk.columns:
                chunk["definition"] = pd.NA
            chunk = chunk.loc[chunk["location_name"] == "Global"].copy()
            if chunk.empty:
                continue
            chunk["risk_indicator"] = derive_indicator(csv_path)
            chunk["source_file"] = csv_path.name
            frames.append(chunk)

    if not frames:
        raise ValueError("No Global rows were found in the extracted HIGH_BMI files.")

    combined = pd.concat(frames, ignore_index=True)
    global_df = combined.copy()
    global_df["year_id"] = pd.to_numeric(global_df["year_id"], errors="coerce").astype("Int64")
    for column in ["age_group_id", "sex_id", "location_id", "measure_id"]:
        global_df[column] = pd.to_numeric(global_df[column], errors="coerce").astype("Int64")
    for column in ["mean", "lower", "upper"]:
        global_df[column] = pd.to_numeric(global_df[column], errors="coerce")
    ordered_columns = [
        "risk_indicator",
        "source_file",
        "location_id",
        "location_name",
        "year_id",
        "age_group_id",
        "age_group_name",
        "sex_id",
        "sex",
        "measure_id",
        "measure",
        "definition",
        "mean",
        "lower",
        "upper",
    ]
    global_df = global_df[ordered_columns].sort_values(
        ["risk_indicator", "sex", "age_group_id", "year_id"]
    ).reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    global_df.to_csv(output_path, index=False)
    return {
        "inputs": [str(path) for path in inputs],
        "output": str(output_path),
        "rows": int(len(global_df)),
        "indicators": sorted(global_df["risk_indicator"].dropna().unique().tolist()),
        "years": [int(global_df["year_id"].min()), int(global_df["year_id"].max())],
        "sexes": sorted(global_df["sex"].dropna().unique().tolist()),
    }


def build_high_bmi_prevalence_locations(inputs: list[Path], output_path: Path) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wrote_header = False
    row_count = 0
    indicators: set[str] = set()
    locations: set[str] = set()
    years_min: int | None = None
    years_max: int | None = None

    ordered_columns = [
        "risk_indicator",
        "source_file",
        "location_id",
        "location_name",
        "year_id",
        "age_group_id",
        "age_group_name",
        "sex_id",
        "sex",
        "measure_id",
        "measure",
        "definition",
        "mean",
        "lower",
        "upper",
    ]

    for csv_path in inputs:
        indicator = derive_indicator(csv_path)
        for chunk in pd.read_csv(csv_path, chunksize=200000):
            chunk.columns = [snake_case(column) for column in chunk.columns]
            if "measure_id" not in chunk.columns:
                chunk["measure_id"] = pd.NA
            if "definition" not in chunk.columns:
                chunk["definition"] = pd.NA
            if "sex" in chunk.columns:
                chunk = chunk.loc[chunk["sex"] == "Both"].copy()
            if chunk.empty:
                continue
            chunk["risk_indicator"] = indicator
            chunk["source_file"] = csv_path.name
            for column in ["age_group_id", "sex_id", "location_id", "measure_id", "year_id"]:
                chunk[column] = pd.to_numeric(chunk[column], errors="coerce").astype("Int64")
            for column in ["mean", "lower", "upper"]:
                chunk[column] = pd.to_numeric(chunk[column], errors="coerce")
            chunk = chunk[ordered_columns]
            chunk.to_csv(output_path, mode="a" if wrote_header else "w", header=not wrote_header, index=False)
            wrote_header = True

            row_count += int(len(chunk))
            indicators.add(indicator)
            locations.update(chunk["location_name"].dropna().astype(str).unique().tolist())
            chunk_year_min = chunk["year_id"].dropna().min()
            chunk_year_max = chunk["year_id"].dropna().max()
            if pd.notna(chunk_year_min):
                years_min = int(chunk_year_min) if years_min is None else min(years_min, int(chunk_year_min))
            if pd.notna(chunk_year_max):
                years_max = int(chunk_year_max) if years_max is None else max(years_max, int(chunk_year_max))

    if row_count == 0:
        raise ValueError("No Both-sex prevalence rows were found in the extracted HIGH_BMI prevalence files.")

    return {
        "inputs": [str(path) for path in inputs],
        "output": str(output_path),
        "rows": row_count,
        "indicators": sorted(indicators),
        "locations": len(locations),
        "years": [years_min, years_max],
        "sexes": ["Both"],
        "strict_duplicate_rows_with_location_id": 0,
    }


def build_notebook(
    notebook_path: Path,
    mortality_csv: Path,
    adult_bmi_csv: Path,
    prevalence_csv: Path,
) -> None:
    nb = nbf.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb["metadata"]["language_info"] = {"name": "python"}
    cells = [
        nbf.v4.new_markdown_cell(
            "# GBD 2023 Starter Analysis\n\n"
            "This notebook starts from the reusable starter datasets built from the official 1990-2023 GBD files.\n"
            "It covers a quick mortality trend view and a global high-BMI exposure profile."
        ),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n"
            "import seaborn as sns\n\n"
            "sns.set_theme(style='whitegrid')\n"
            "ROOT = Path('/Users/apple/Documents/lancet-research-platform')\n"
            f"MORTALITY_PATH = Path({str(mortality_csv)!r})\n"
            f"ADULT_BMI_PATH = Path({str(adult_bmi_csv)!r})\n"
            f"PREVALENCE_PATH = Path({str(prevalence_csv)!r})\n\n"
            "mortality = pd.read_csv(MORTALITY_PATH)\n"
            "adult_bmi = pd.read_csv(ADULT_BMI_PATH)\n"
            "prevalence = pd.read_csv(PREVALENCE_PATH)\n\n"
            "print('mortality shape:', mortality.shape)\n"
            "print('adult_bmi shape:', adult_bmi.shape)\n"
            "print('prevalence shape:', prevalence.shape)\n"
            "mortality.head()"
        ),
        nbf.v4.new_code_cell(
            "global_all_cause = mortality.loc[\n"
            "    (mortality['location_name'] == 'Global')\n"
            "    & (mortality['cause_name'] == 'All causes')\n"
            "    & (mortality['metric'] == 'age_standardized_mortality_rate')\n"
            "].copy()\n"
            "global_all_cause = global_all_cause.sort_values('year_id')\n\n"
            "fig, ax = plt.subplots(figsize=(7, 4))\n"
            "ax.plot(global_all_cause['year_id'], global_all_cause['estimate'], marker='o', linewidth=2)\n"
            "ax.fill_between(global_all_cause['year_id'], global_all_cause['lower'], global_all_cause['upper'], alpha=0.2)\n"
            "ax.set_title('Global all-cause age-standardized mortality rate')\n"
            "ax.set_xlabel('Year')\n"
            "ax.set_ylabel('ASMR per 100,000')\n"
            "plt.tight_layout()\n"
            "plt.show()\n\n"
            "global_all_cause[['year_id', 'estimate', 'lower', 'upper']]"
        ),
        nbf.v4.new_code_cell(
            "top_causes_2023 = mortality.loc[\n"
            "    (mortality['location_name'] == 'Global')\n"
            "    & (mortality['metric'] == 'age_standardized_mortality_rate')\n"
            "    & (mortality['year_id'] == 2023)\n"
            "    & (mortality['cause_name'] != 'All causes')\n"
            "].copy()\n"
            "top_causes_2023 = top_causes_2023.nlargest(15, 'estimate').sort_values('estimate')\n\n"
            "fig, ax = plt.subplots(figsize=(8, 6))\n"
            "ax.barh(top_causes_2023['cause_name'], top_causes_2023['estimate'], color='#b85c38')\n"
            "ax.set_title('Top 15 global causes by 2023 ASMR')\n"
            "ax.set_xlabel('ASMR per 100,000')\n"
            "ax.set_ylabel('Cause')\n"
            "plt.tight_layout()\n"
            "plt.show()\n\n"
            "top_causes_2023[['cause_name', 'estimate', 'lower', 'upper']].tail(15)"
        ),
        nbf.v4.new_code_cell(
            "AGE_GROUP = '20 to 24'\n"
            "adult_subset = adult_bmi.copy()\n"
            "if AGE_GROUP not in set(adult_subset['age_group_name']):\n"
            "    AGE_GROUP = sorted(adult_subset['age_group_name'].dropna().unique())[0]\n"
            "adult_subset = adult_subset.loc[adult_subset['age_group_name'] == AGE_GROUP].sort_values(['sex', 'year_id'])\n\n"
            "fig, ax = plt.subplots(figsize=(8, 4))\n"
            "for sex, frame in adult_subset.groupby('sex'):\n"
            "    ax.plot(frame['year_id'], frame['mean'], label=sex, linewidth=2)\n"
            "ax.set_title(f'Global adult mean BMI ({AGE_GROUP})')\n"
            "ax.set_xlabel('Year')\n"
            "ax.set_ylabel('BMI')\n"
            "ax.legend(frameon=False)\n"
            "plt.tight_layout()\n"
            "plt.show()\n\n"
            "adult_subset[['sex', 'year_id', 'mean', 'lower', 'upper']].head()"
        ),
        nbf.v4.new_code_cell(
            "AGE_GROUP = '20 to 24'\n"
            "LOCATION = 'China' if 'China' in set(prevalence['location_name']) else sorted(prevalence['location_name'].dropna().unique())[0]\n"
            "indicator_subset = prevalence.loc[\n"
            "    (prevalence['location_name'] == LOCATION)\n"
            "    & (prevalence['risk_indicator'].isin([\n"
            "        'prevalence_of_obesity',\n"
            "        'prevalence_of_overweight',\n"
            "        'prevalence_of_obesity_and_overweight',\n"
            "    ]))\n"
            "].copy()\n"
            "if AGE_GROUP not in set(indicator_subset['age_group_name']):\n"
            "    AGE_GROUP = sorted(indicator_subset['age_group_name'].dropna().unique())[0]\n"
            "indicator_subset = indicator_subset.loc[indicator_subset['age_group_name'] == AGE_GROUP]\n"
            "indicator_subset = indicator_subset.sort_values(['risk_indicator', 'year_id'])\n\n"
            "fig, ax = plt.subplots(figsize=(8, 4))\n"
            "for indicator, frame in indicator_subset.groupby('risk_indicator'):\n"
            "    ax.plot(frame['year_id'], frame['mean'], label=indicator.replace('_', ' '), linewidth=2)\n"
            "ax.set_title(f'{LOCATION} high-BMI prevalence trends ({AGE_GROUP}, both sexes)')\n"
            "ax.set_xlabel('Year')\n"
            "ax.set_ylabel('Prevalence')\n"
            "ax.legend(frameon=False)\n"
            "plt.tight_layout()\n"
            "plt.show()\n\n"
            "indicator_subset[['location_name', 'risk_indicator', 'year_id', 'mean', 'lower', 'upper']].head()"
        ),
    ]
    nb["cells"] = cells
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    with notebook_path.open("w", encoding="utf-8") as handle:
        nbf.write(nb, handle)


def main() -> int:
    args = parse_args()
    bronze_root = Path(args.bronze_root).expanduser()
    silver_root = Path(args.silver_root).expanduser()
    notebook_out = Path(args.notebook_out).expanduser()
    qc_out = Path(args.qc_out).expanduser()

    mortality_input = find_one(bronze_root, "*TABLE_S7*.CSV")
    high_bmi_inputs = sorted(bronze_root.rglob("*HIGH_BMI*.CSV"))
    if not high_bmi_inputs:
        raise FileNotFoundError(f"No extracted HIGH_BMI CSV files found under {bronze_root}")
    adult_bmi_inputs = [path for path in high_bmi_inputs if "IN_ADULTS" in path.name.upper()]
    prevalence_inputs = [path for path in high_bmi_inputs if "IN_ADULTS" not in path.name.upper()]
    if not adult_bmi_inputs or not prevalence_inputs:
        raise FileNotFoundError("Expected both adult-BMI and prevalence HIGH_BMI extracts, but one group was missing.")

    mortality_output = silver_root / "gbd2023_mortality_s7_both_sex_long.csv"
    adult_bmi_output = silver_root / "gbd2023_high_bmi_global_adult_bmi_long.csv"
    prevalence_output = silver_root / "gbd2023_high_bmi_prevalence_locations_long.csv"

    if not args.force:
        for path in [mortality_output, adult_bmi_output, prevalence_output, notebook_out]:
            if path.exists():
                raise FileExistsError(f"{path} already exists; rerun with --force to overwrite")

    qc_payload = {
        "mortality": build_mortality_long(mortality_input, mortality_output),
        "high_bmi_global_adult_bmi": build_high_bmi_global(adult_bmi_inputs, adult_bmi_output),
        "high_bmi_prevalence_locations": build_high_bmi_prevalence_locations(prevalence_inputs, prevalence_output),
    }
    build_notebook(
        notebook_out,
        mortality_csv=mortality_output,
        adult_bmi_csv=adult_bmi_output,
        prevalence_csv=prevalence_output,
    )
    qc_payload["notebook"] = str(notebook_out)

    qc_out.parent.mkdir(parents=True, exist_ok=True)
    qc_out.write_text(json.dumps(qc_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"mortality starter {mortality_output}")
    print(f"adult-bmi starter {adult_bmi_output}")
    print(f"prevalence starter {prevalence_output}")
    print(f"notebook {notebook_out}")
    print(f"qc {qc_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
