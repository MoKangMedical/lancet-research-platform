#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph
from scipy.stats import spearmanr


ROOT = Path("/Users/apple/Documents/lancet-research-platform")
PROJECT_DIR = Path(
    "/Users/apple/Desktop/研究方案-赵老师项目/0 研究方案-针对皮肤病的相关全球流行病和疾病负担研究方案-20分-38万-已收5万+5万 2"
)
DEFAULT_MANUSCRIPT = PROJECT_DIR / "1208-Manuscript-全球老年人群常见皮肤病流行病学、疾病负担及趋势.docx"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "aging_analysis_outputs"
DEFAULT_OUTPUT_DOCX = PROJECT_DIR / "1208-Manuscript-全球老年人群常见皮肤病流行病学、疾病负担及趋势-aging-data.docx"
GBD_DIRF_PATH = ROOT / "data" / "silver" / "gbd" / "gbd2023_dirf_global_core_tidy.csv"
GBD_MORTALITY_PATH = ROOT / "data" / "silver" / "gbd" / "gbd2023_mortality_s7_both_sex_long.csv"

WB_INDICATORS = {
    "age65_pct": "SP.POP.65UP.TO.ZS",
    "life_expectancy": "SP.DYN.LE00.IN",
    "old_age_dependency": "SP.POP.DPND.OL",
}

GBD_TO_WB_NAME = {
    "Bahamas": "Bahamas, The",
    "Bolivia (Plurinational State of)": "Bolivia",
    "Congo": "Congo, Rep.",
    "Côte d'Ivoire": "Cote d'Ivoire",
    "Democratic People's Republic of Korea": "Korea, Dem. People's Rep.",
    "Democratic Republic of the Congo": "Congo, Dem. Rep.",
    "Egypt": "Egypt, Arab Rep.",
    "Gambia": "Gambia, The",
    "Iran (Islamic Republic of)": "Iran, Islamic Rep.",
    "Kyrgyzstan": "Kyrgyz Republic",
    "Lao People's Democratic Republic": "Lao PDR",
    "Micronesia (Federated States of)": "Micronesia, Fed. Sts.",
    "Palestine": "West Bank and Gaza",
    "Puerto Rico": "Puerto Rico (US)",
    "Republic of Korea": "Korea, Rep.",
    "Republic of Moldova": "Moldova",
    "Saint Kitts and Nevis": "St. Kitts and Nevis",
    "Saint Lucia": "St. Lucia",
    "Saint Vincent and the Grenadines": "St. Vincent and the Grenadines",
    "Slovakia": "Slovak Republic",
    "Somalia": "Somalia, Fed. Rep.",
    "Türkiye": "Turkiye",
    "United Republic of Tanzania": "Tanzania",
    "United States Virgin Islands": "Virgin Islands (U.S.)",
    "United States of America": "United States",
    "Venezuela (Bolivarian Republic of)": "Venezuela, RB",
    "Yemen": "Yemen, Rep.",
}


@dataclass
class AnalysisBundle:
    country_map: pd.DataFrame
    country_analysis: pd.DataFrame
    country_analysis_complete: pd.DataFrame
    country_correlations: pd.DataFrame
    age65_tertiles: pd.DataFrame
    top_asmr: pd.DataFrame
    global_context: pd.DataFrame
    summary: dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a skin disease aging-ecology module and update the manuscript."
    )
    parser.add_argument("--manuscript", default=str(DEFAULT_MANUSCRIPT), help="Input DOCX manuscript path")
    parser.add_argument("--output-docx", default=str(DEFAULT_OUTPUT_DOCX), help="Output DOCX manuscript path")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for tables and summary files")
    parser.add_argument(
        "--skip-docx",
        action="store_true",
        help="Only build analysis outputs and do not write an updated DOCX copy",
    )
    return parser.parse_args()


def fetch_json(url: str) -> dict | list:
    raw = subprocess.check_output(["curl", "-L", "--silent", url], text=True)
    return json.loads(raw)


def build_gbd_country_lookup() -> pd.DataFrame:
    hierarchy = fetch_json("https://vizhub.healthdata.org/gbd-results/php/hierarchy/")["data"]["locations"]
    metadata = fetch_json("https://vizhub.healthdata.org/gbd-results/php/metadata/?language=English")["data"]["location"]
    levels: dict[int, int] = {}

    def walk(nodes: Iterable[dict], level: int) -> None:
        for node in nodes:
            levels[node["id"]] = level
            walk(node.get("children", []), level + 1)

    walk(hierarchy, 1)

    rows = []
    for location_id, level in levels.items():
        record = metadata.get(str(location_id))
        if record is None or level != 4:
            continue
        rows.append(
            {
                "location_id": location_id,
                "gbd_name": record["name"],
                "gbd_short_name": record.get("short_name"),
            }
        )
    return pd.DataFrame(rows).sort_values("gbd_name").reset_index(drop=True)


def load_world_bank_country_lookup() -> pd.DataFrame:
    data = fetch_json("https://api.worldbank.org/v2/country?format=json&per_page=400")[1]
    rows = [
        {"wb_iso3": item["id"], "wb_name": item["name"]}
        for item in data
        if item["region"]["value"] != "Aggregates"
    ]
    return pd.DataFrame(rows)


def load_world_bank_indicator(indicator_code: str, year: int = 2023) -> pd.DataFrame:
    data = fetch_json(
        f"https://api.worldbank.org/v2/country/all/indicator/{indicator_code}?format=json&per_page=400&date={year}"
    )[1]
    return pd.DataFrame(
        {
            "wb_iso3": item["countryiso3code"],
            "value": item["value"],
        }
        for item in data
        if item["countryiso3code"] and item["value"] is not None
    )


def load_world_bank_world_series() -> pd.DataFrame:
    frames = []
    for label, indicator in WB_INDICATORS.items():
        data = fetch_json(
            f"https://api.worldbank.org/v2/country/WLD/indicator/{indicator}?format=json&per_page=100&date=1990:2023"
        )[1]
        frame = pd.DataFrame(
            {
                "year_id": int(item["date"]),
                label: item["value"],
            }
            for item in data
            if item["value"] is not None
        )
        frames.append(frame)

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="year_id", how="outer")
    return merged.sort_values("year_id").reset_index(drop=True)


def load_gbd_country_mortality() -> pd.DataFrame:
    df = pd.read_csv(GBD_MORTALITY_PATH)
    return (
        df[
            (df["cause_name"] == "Skin and subcutaneous diseases")
            & (df["metric"] == "age_standardized_mortality_rate")
            & (df["year_id"] == 2023)
        ][["location_name", "estimate", "lower", "upper"]]
        .rename(
            columns={
                "location_name": "gbd_name",
                "estimate": "asmr_2023",
                "lower": "asmr_2023_lower",
                "upper": "asmr_2023_upper",
            }
        )
        .copy()
    )


def load_global_gbd_context() -> pd.DataFrame:
    dirf = pd.read_csv(GBD_DIRF_PATH)
    dirf = dirf[
        (dirf["location_name"] == "Global")
        & (dirf["cause_name"] == "Skin and subcutaneous diseases")
        & (dirf["sex"] == "Both")
        & (dirf["year_id"].isin([1990, 2023]))
        & (dirf["measure"].isin(["incidence", "prevalence", "DALY"]))
        & (dirf["metric"].isin(["age_standardized_rate", "count"]))
    ][["year_id", "measure", "metric", "mean", "lower", "upper"]].copy()

    mortality = pd.read_csv(GBD_MORTALITY_PATH)
    mortality = mortality[
        (mortality["location_name"] == "Global")
        & (mortality["cause_name"] == "Skin and subcutaneous diseases")
        & (mortality["year_id"].isin([1990, 2023]))
        & (mortality["metric"].isin(["age_standardized_mortality_rate", "all_age_deaths"]))
    ][["year_id", "metric", "estimate", "lower", "upper"]].copy()
    mortality["measure"] = "Deaths"
    mortality["mean"] = mortality["estimate"]
    mortality = mortality.drop(columns=["estimate"])
    mortality["metric"] = mortality["metric"].map(
        {
            "age_standardized_mortality_rate": "age_standardized_rate",
            "all_age_deaths": "count",
        }
    )

    merged = pd.concat([dirf, mortality], ignore_index=True, sort=False)
    world = load_world_bank_world_series()
    return merged.merge(world, on="year_id", how="left").sort_values(["year_id", "measure", "metric"])


def build_analysis_bundle() -> AnalysisBundle:
    gbd_countries = build_gbd_country_lookup()
    wb_countries = load_world_bank_country_lookup()
    mortality = load_gbd_country_mortality()

    country_map = gbd_countries.copy()
    country_map["wb_name"] = country_map["gbd_name"].map(GBD_TO_WB_NAME).fillna(country_map["gbd_name"])
    country_map = country_map.merge(wb_countries, on="wb_name", how="left")

    indicator_frames = []
    for label, indicator in WB_INDICATORS.items():
        frame = load_world_bank_indicator(indicator)
        indicator_frames.append(frame.rename(columns={"value": label}))

    wb_indicators = indicator_frames[0]
    for frame in indicator_frames[1:]:
        wb_indicators = wb_indicators.merge(frame, on="wb_iso3", how="outer")

    country_analysis = country_map.merge(mortality, on="gbd_name", how="left").merge(
        wb_indicators, on="wb_iso3", how="left"
    )
    country_analysis_complete = country_analysis.dropna(
        subset=["asmr_2023", "age65_pct", "life_expectancy", "old_age_dependency"]
    ).copy()

    correlations = []
    for indicator in ["age65_pct", "life_expectancy", "old_age_dependency"]:
        rho, p_value = spearmanr(country_analysis_complete[indicator], country_analysis_complete["asmr_2023"])
        correlations.append(
            {
                "indicator": indicator,
                "spearman_rho": rho,
                "p_value": p_value,
            }
        )
    country_correlations = pd.DataFrame(correlations)

    country_analysis_complete["age65_tertile"] = pd.qcut(
        country_analysis_complete["age65_pct"], 3, labels=["T1", "T2", "T3"]
    )
    age65_tertiles = (
        country_analysis_complete.groupby("age65_tertile", observed=False)["asmr_2023"]
        .agg(["count", "median", "mean", "min", "max"])
        .reset_index()
    )
    top_asmr = country_analysis_complete.sort_values("asmr_2023", ascending=False).head(20).copy()
    global_context = load_global_gbd_context()

    summary = summarize_results(
        country_map=country_map,
        country_analysis_complete=country_analysis_complete,
        country_correlations=country_correlations,
        age65_tertiles=age65_tertiles,
        global_context=global_context,
    )
    return AnalysisBundle(
        country_map=country_map,
        country_analysis=country_analysis,
        country_analysis_complete=country_analysis_complete,
        country_correlations=country_correlations,
        age65_tertiles=age65_tertiles,
        top_asmr=top_asmr,
        global_context=global_context,
        summary=summary,
    )


def summarize_results(
    *,
    country_map: pd.DataFrame,
    country_analysis_complete: pd.DataFrame,
    country_correlations: pd.DataFrame,
    age65_tertiles: pd.DataFrame,
    global_context: pd.DataFrame,
) -> dict:
    unmatched = country_map[country_map["wb_iso3"].isna()]["gbd_name"].tolist()
    global_1990 = global_context[global_context["year_id"] == 1990]
    global_2023 = global_context[global_context["year_id"] == 2023]

    def fetch_value(frame: pd.DataFrame, measure: str, metric: str, field: str = "mean") -> float:
        value = frame[(frame["measure"] == measure) & (frame["metric"] == metric)][field]
        if value.empty:
            raise KeyError(f"Missing {measure=} {metric=} {field=}")
        return float(value.iloc[0])

    correlations = {
        row["indicator"]: {
            "rho": float(row["spearman_rho"]),
            "p_value": float(row["p_value"]),
        }
        for _, row in country_correlations.iterrows()
    }

    tertiles = {}
    for _, row in age65_tertiles.iterrows():
        tertiles[str(row["age65_tertile"])] = {
            "count": int(row["count"]),
            "median": float(row["median"]),
            "mean": float(row["mean"]),
            "min": float(row["min"]),
            "max": float(row["max"]),
        }

    return {
        "country_map_matched": int(country_map["wb_iso3"].notna().sum()),
        "country_map_total": int(len(country_map)),
        "country_map_unmatched": unmatched,
        "analysis_complete_n": int(len(country_analysis_complete)),
        "correlations": correlations,
        "age65_tertiles": tertiles,
        "global_context": {
            "age65_pct_1990": fetch_value(global_1990, "DALY", "count", "age65_pct"),
            "age65_pct_2023": fetch_value(global_2023, "DALY", "count", "age65_pct"),
            "life_expectancy_1990": fetch_value(global_1990, "DALY", "count", "life_expectancy"),
            "life_expectancy_2023": fetch_value(global_2023, "DALY", "count", "life_expectancy"),
            "old_age_dependency_1990": fetch_value(global_1990, "DALY", "count", "old_age_dependency"),
            "old_age_dependency_2023": fetch_value(global_2023, "DALY", "count", "old_age_dependency"),
            "daly_count_1990": fetch_value(global_1990, "DALY", "count"),
            "daly_count_2023": fetch_value(global_2023, "DALY", "count"),
            "daly_asr_1990": fetch_value(global_1990, "DALY", "age_standardized_rate"),
            "daly_asr_2023": fetch_value(global_2023, "DALY", "age_standardized_rate"),
            "incidence_asr_1990": fetch_value(global_1990, "incidence", "age_standardized_rate"),
            "incidence_asr_2023": fetch_value(global_2023, "incidence", "age_standardized_rate"),
            "prevalence_asr_1990": fetch_value(global_1990, "prevalence", "age_standardized_rate"),
            "prevalence_asr_2023": fetch_value(global_2023, "prevalence", "age_standardized_rate"),
            "death_count_1990": fetch_value(global_1990, "Deaths", "count"),
            "death_count_2023": fetch_value(global_2023, "Deaths", "count"),
            "death_asr_1990": fetch_value(global_1990, "Deaths", "age_standardized_rate"),
            "death_asr_2023": fetch_value(global_2023, "Deaths", "age_standardized_rate"),
        },
    }


def format_p_value(p_value: float) -> str:
    return "p<0.001" if p_value < 0.001 else f"p={p_value:.3f}"


def build_manuscript_text(summary: dict) -> dict[str, str]:
    global_ctx = summary["global_context"]
    corr = summary["correlations"]
    tertiles = summary["age65_tertiles"]

    methods_insert_heading = "Global aging ecological analysis"
    methods_insert_body = (
        "To align the epidemiological findings with the demographic transition described in the original study protocol, "
        "we additionally linked country-level skin and subcutaneous disease mortality with external aging indicators from "
        "the World Bank Open Data API (https://api.worldbank.org). Three 2023 indicators were retained: population ages "
        "65 years and older as a percentage of the total population (SP.POP.65UP.TO.ZS), life expectancy at birth "
        "(SP.DYN.LE00.IN), and the old-age dependency ratio (SP.POP.DPND.OL). Because country-level incidence, prevalence, "
        "and DALY extracts for adults aged 45 years and older were not available in the local GBD archive, the ecological "
        "aging module was anchored on the 2023 age-standardized mortality rate (ASMR) for skin and subcutaneous diseases, "
        "which was available for 204 country and territory locations in the local GBD 2023 mortality extract. GBD country "
        "names were harmonized to World Bank naming conventions through direct name matching and a predefined manual mapping. "
        "Taiwan, Cook Islands, Niue, and Tokelau could not be linked to a World Bank country series and were excluded from "
        "the ecological component. Spearman correlation coefficients were calculated between each aging indicator and SSD "
        "ASMR, and countries were further grouped into tertiles of the 65+ population share to compare mortality gradients."
    )

    results_insert_heading = "Global aging context and country-level ecological association"
    results_insert_body = (
        f"From 1990 to 2023, the global demographic profile shifted substantially toward older populations. The proportion "
        f"of people aged 65 years and older increased from {global_ctx['age65_pct_1990']:.2f}% in 1990 to "
        f"{global_ctx['age65_pct_2023']:.2f}% in 2023, while global life expectancy rose from "
        f"{global_ctx['life_expectancy_1990']:.2f} to {global_ctx['life_expectancy_2023']:.2f} years and the old-age "
        f"dependency ratio increased from {global_ctx['old_age_dependency_1990']:.2f} to "
        f"{global_ctx['old_age_dependency_2023']:.2f}. Over the same interval, the global SSD burden also intensified: "
        f"the age-standardized incidence rate increased from {global_ctx['incidence_asr_1990']:.1f} to "
        f"{global_ctx['incidence_asr_2023']:.1f} per 100,000, the age-standardized DALY rate rose from "
        f"{global_ctx['daly_asr_1990']:.1f} to {global_ctx['daly_asr_2023']:.1f} per 100,000, total DALYs increased from "
        f"{global_ctx['daly_count_1990']/1_000_000:.1f} million to {global_ctx['daly_count_2023']/1_000_000:.1f} million, "
        f"and all-age deaths increased from {global_ctx['death_count_1990']:.0f} to {global_ctx['death_count_2023']:.0f}.\n"
        f"In the 2023 country-level ecological analysis, {summary['country_map_matched']} of "
        f"{summary['country_map_total']} GBD countries or territories were successfully linked to World Bank aging indicators, "
        f"and {summary['analysis_complete_n']} countries had complete data for correlation analyses. Contrary to the crude "
        f"expectation that older populations would necessarily exhibit higher skin-related mortality, higher population aging "
        f"was associated with lower SSD ASMR after age standardization. The 65+ population share showed a moderate inverse "
        f"correlation with SSD ASMR (rho={corr['age65_pct']['rho']:.3f}, {format_p_value(corr['age65_pct']['p_value'])}), "
        f"as did life expectancy (rho={corr['life_expectancy']['rho']:.3f}, "
        f"{format_p_value(corr['life_expectancy']['p_value'])}) and the old-age dependency ratio "
        f"(rho={corr['old_age_dependency']['rho']:.3f}, {format_p_value(corr['old_age_dependency']['p_value'])}). "
        f"Countries in the highest tertile of population aging had a markedly lower mean SSD ASMR than those in the lowest "
        f"tertile ({tertiles['T3']['mean']:.2f} vs {tertiles['T1']['mean']:.2f} per 100,000; median "
        f"{tertiles['T3']['median']:.2f} vs {tertiles['T1']['median']:.2f})."
    )

    discussion_insert = (
        f"The aging-ecology module adds an important nuance to the interpretation of our results. At the global level, the "
        f"absolute burden of SSDs increased alongside population aging, with the worldwide share of people aged 65 years "
        f"and older rising from {global_ctx['age65_pct_1990']:.2f}% to {global_ctx['age65_pct_2023']:.2f} and total SSD "
        f"DALYs increasing from {global_ctx['daly_count_1990']/1_000_000:.1f} million to "
        f"{global_ctx['daly_count_2023']/1_000_000:.1f} million. However, after age standardization at the country level, "
        f"older demographic structure was consistently associated with lower SSD mortality. This pattern suggests that "
        f"population aging alone does not drive fatal outcomes; rather, older and longer-living societies may offset part "
        f"of the mortality risk through stronger primary care, wound care systems, infection control, chronic disease "
        f"management, and better access to dermatologic services. In contrast, younger but resource-constrained settings may "
        f"still experience disproportionately high skin-related mortality from preventable infectious and ulcerative conditions."
    )

    limitations_append = (
        " In addition, the aging component relied on country-level World Bank indicators and the locally available GBD "
        "mortality extract. Therefore, we could not directly evaluate country-level associations of aging indicators with "
        "incidence, prevalence, or DALYs, nor could we harmonize individual-level skin disease phenotypes across the local "
        "global aging cohort files with sufficient coverage for a unified multi-cohort analysis."
    )

    abstract_methods_append = (
        " To contextualize demographic transition, we further linked 2023 country-level skin mortality with World Bank "
        "aging indicators, including population aged 65 years and older, life expectancy, and the old-age dependency ratio."
    )
    abstract_results_append = (
        f" In country-level ecological analyses, higher population aging was associated with lower age-standardized skin "
        f"mortality (65+ share: rho={corr['age65_pct']['rho']:.2f}; life expectancy: rho={corr['life_expectancy']['rho']:.2f}; "
        f"old-age dependency ratio: rho={corr['old_age_dependency']['rho']:.2f}; all p<0.001)."
    )
    abstract_conclusion_append = (
        " Although demographic aging was accompanied by higher absolute global burden, older national population structures "
        "were not associated with higher age-standardized skin mortality, suggesting an important modifying role of health "
        "system capacity and long-term care."
    )
    conclusion_append = (
        " At the same time, the inverse ecological association between national aging indicators and age-standardized skin "
        "mortality implies that health-system resilience, rather than demographic aging alone, may determine whether growing "
        "elderly populations translate into worse fatal skin disease outcomes."
    )

    return {
        "methods_insert_heading": methods_insert_heading,
        "methods_insert_body": methods_insert_body,
        "results_insert_heading": results_insert_heading,
        "results_insert_body": results_insert_body,
        "discussion_insert": discussion_insert,
        "limitations_append": limitations_append,
        "abstract_methods_append": abstract_methods_append,
        "abstract_results_append": abstract_results_append,
        "abstract_conclusion_append": abstract_conclusion_append,
        "conclusion_append": conclusion_append,
    }


def insert_paragraph_after(paragraph: Paragraph, text: str, style: str | None = None) -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._element.addnext(new_p)
    new_para = Paragraph(new_p, paragraph._parent)
    new_para.text = text
    if style:
        try:
            new_para.style = style
        except KeyError:
            pass
    return new_para


def insert_paragraph_before(paragraph: Paragraph, text: str, style: str | None = None) -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._element.addprevious(new_p)
    new_para = Paragraph(new_p, paragraph._parent)
    new_para.text = text
    if style:
        try:
            new_para.style = style
        except KeyError:
            pass
    return new_para


def find_paragraph(doc: Document, startswith: str) -> Paragraph:
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if text.startswith(startswith) or startswith in text:
            return paragraph
    raise ValueError(f"Could not find paragraph starting with: {startswith}")


def update_manuscript(input_path: Path, output_path: Path, summary: dict) -> None:
    text_blocks = build_manuscript_text(summary)
    doc = Document(str(input_path))

    methods_para = find_paragraph(
        doc,
        "Subgroup Analysis by Disease Type",
    )
    insert_paragraph_before(methods_para, text_blocks["methods_insert_heading"], style="Heading 2")
    insert_paragraph_before(methods_para, text_blocks["methods_insert_body"])

    results_para = find_paragraph(
        doc,
        "Age and Sex Disparities in the Burden of Skin and Subcutaneous Diseases",
    )
    insert_paragraph_before(results_para, text_blocks["results_insert_heading"], style="Heading 2")
    insert_paragraph_before(results_para, text_blocks["results_insert_body"])

    discussion_anchor = find_paragraph(
        doc,
        "The differentiation by age subgroup and sex yields nuanced insights.",
    )
    insert_paragraph_before(discussion_anchor, text_blocks["discussion_insert"])

    limitations_para = find_paragraph(
        doc,
        "Nonetheless, our study has limitations.",
    )
    limitations_para.text = limitations_para.text.strip() + text_blocks["limitations_append"]

    abstract_methods_para = find_paragraph(
        doc,
        "We performed a cross-sectional and longitudinal analysis using data from the Global Burden of Disease",
    )
    abstract_methods_para.text = abstract_methods_para.text.strip() + text_blocks["abstract_methods_append"]

    abstract_results_para = find_paragraph(
        doc,
        "Globally, the age-standardized incidence rate of SSDs increased slightly",
    )
    abstract_results_para.text = abstract_results_para.text.strip() + text_blocks["abstract_results_append"]

    abstract_conclusion_para = find_paragraph(
        doc,
        "From 1990 to 2023, the global burden of SSDs in adults aged 45 years and older increased modestly",
    )
    abstract_conclusion_para.text = abstract_conclusion_para.text.strip() + text_blocks["abstract_conclusion_append"]

    conclusion_para = find_paragraph(
        doc,
        "As populations continue to age globally, the dermatologic health needs of older adults warrant growing attention and resources.",
    )
    conclusion_para.text = conclusion_para.text.strip() + text_blocks["conclusion_append"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


def write_outputs(bundle: AnalysisBundle, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle.country_map.to_csv(output_dir / "skin_aging_country_name_map.csv", index=False)
    bundle.country_analysis.to_csv(output_dir / "skin_aging_2023_country_merged.csv", index=False)
    bundle.country_analysis_complete.to_csv(output_dir / "skin_aging_2023_country_complete.csv", index=False)
    bundle.country_correlations.to_csv(output_dir / "skin_aging_2023_correlations.csv", index=False)
    bundle.age65_tertiles.to_csv(output_dir / "skin_aging_2023_age65_tertiles.csv", index=False)
    bundle.top_asmr.to_csv(output_dir / "skin_aging_2023_top_asmr.csv", index=False)
    bundle.global_context.to_csv(output_dir / "skin_aging_global_context_1990_2023.csv", index=False)
    with (output_dir / "skin_aging_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(bundle.summary, handle, ensure_ascii=False, indent=2)

    summary_md = [
        "# Skin Aging Ecology Summary",
        "",
        f"- Matched GBD countries to World Bank indicators: {bundle.summary['country_map_matched']}/{bundle.summary['country_map_total']}",
        f"- Unmatched GBD countries: {', '.join(bundle.summary['country_map_unmatched'])}",
        f"- Countries with complete 2023 analysis data: {bundle.summary['analysis_complete_n']}",
        "",
        "## Correlations",
    ]
    for _, row in bundle.country_correlations.iterrows():
        summary_md.append(
            f"- {row['indicator']}: rho={row['spearman_rho']:.3f}, p={row['p_value']:.3e}"
        )
    summary_md.extend(
        [
            "",
            "## Global context",
            (
                f"- Population aged 65+ rose from {bundle.summary['global_context']['age65_pct_1990']:.2f}% "
                f"to {bundle.summary['global_context']['age65_pct_2023']:.2f}%."
            ),
            (
                f"- SSD DALY counts rose from {bundle.summary['global_context']['daly_count_1990']/1_000_000:.1f} million "
                f"to {bundle.summary['global_context']['daly_count_2023']/1_000_000:.1f} million."
            ),
        ]
    )
    (output_dir / "skin_aging_summary.md").write_text("\n".join(summary_md), encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser()
    manuscript_path = Path(args.manuscript).expanduser()
    output_docx = Path(args.output_docx).expanduser()

    bundle = build_analysis_bundle()
    write_outputs(bundle, output_dir)

    if not args.skip_docx:
        update_manuscript(manuscript_path, output_docx, bundle.summary)

    print(f"Analysis outputs written to: {output_dir}")
    if not args.skip_docx:
        print(f"Updated manuscript written to: {output_docx}")


if __name__ == "__main__":
    main()
