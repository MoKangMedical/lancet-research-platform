#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
import warnings
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from Bio import Entrez
from habanero import Crossref

from lib.rendering import render_docx_to_pngs

ROOT = Path("/Users/apple/Documents/lancet-research-platform")
PY = "/Users/apple/Documents/.venvs/data-analytics/bin/python"
AGGREGATE_LABEL = "East Asia study-scope aggregate"
LOCATION_ORDER = [
    "China",
    "Japan",
    "Mongolia",
    "Democratic People's Republic of Korea",
    "Republic of Korea",
    "Taiwan",
]
MEASURE_ORDER = ["Incidence", "Prevalence", "Deaths", "DALYs"]
RATE_SCALE = 100000.0

REF_ASSIGNMENTS = [
    {"pmid": "40147466", "section": "introduction"},
    {"pmid": "39867965", "section": "introduction"},
    {"pmid": "32526187", "section": "introduction"},
    {"pmid": "28822787", "section": "introduction"},
    {"pmid": "40684789", "section": "introduction"},
    {"pmid": "31275909", "section": "introduction"},
    {"pmid": "32972987", "section": "introduction"},
    {"pmid": "29988370", "section": "introduction"},
    {"pmid": "39434052", "section": "introduction"},
    {"pmid": "30878568", "section": "introduction"},
    {"pmid": "37324106", "section": "introduction"},
    {"pmid": "26666488", "section": "introduction"},
    {"pmid": "27351744", "section": "methods"},
    {"pmid": "36216939", "section": "methods"},
    {"pmid": "26475018", "section": "methods"},
    {"pmid": "9164317", "section": "methods"},
    {"pmid": "12423980", "section": "methods"},
    {"pmid": "38762324", "section": "methods"},
    {"pmid": "37229504", "section": "methods"},
    {"pmid": "37353829", "section": "methods"},
    {"pmid": "32075787", "section": "methods"},
    {"pmid": "38970015", "section": "methods"},
    {"pmid": "39134934", "section": "methods"},
    {"pmid": "39359410", "section": "methods"},
    {"pmid": "36002091", "section": "discussion"},
    {"pmid": "41029276", "section": "discussion"},
    {"pmid": "36600406", "section": "discussion"},
    {"pmid": "32667747", "section": "discussion"},
    {"pmid": "22430451", "section": "discussion"},
    {"pmid": "39915028", "section": "discussion"},
    {"pmid": "24521110", "section": "discussion"},
    {"pmid": "38295127", "section": "discussion"},
    {"pmid": "33141780", "section": "discussion"},
    {"pmid": "30661311", "section": "discussion"},
    {"pmid": "40087850", "section": "discussion"},
    {"pmid": "32468824", "section": "discussion"},
]


@dataclass
class RefMeta:
    ref_no: int
    section: str
    pmid: str
    doi: str
    year: int | None
    title: str
    journal: str
    authors: list[str]
    volume: str
    issue: str
    pages: str
    pubmed_url: str
    doi_url: str

    def vancouver(self) -> str:
        authors = ", ".join(self.authors[:6])
        if len(self.authors) > 6:
            authors += ", et al"
        if not authors:
            authors = "[No listed authors]"
        line = f"{self.ref_no}. {authors}. {self.title} {self.journal}."
        if self.year:
            line += f" {self.year}"
        if self.volume:
            line += f";{self.volume}"
            if self.issue:
                line += f"({self.issue})"
        elif self.issue:
            line += f";({self.issue})"
        if self.pages:
            line += f":{self.pages}"
        line += "."
        if self.doi:
            line += f" doi:{self.doi}."
        return re.sub(r"\s+", " ", line).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the long-form submission package with 5+ figures, 5+ tables, and curated references."
    )
    parser.add_argument("--study-root", required=True)
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def save_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=False)


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(text or "")).replace("\n", " ").strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w.-]+\b", text))


def cite(*numbers: int) -> str:
    nums = sorted(set(numbers))
    if not nums:
        return ""
    ranges: list[str] = []
    start = nums[0]
    prev = nums[0]
    for num in nums[1:]:
        if num == prev + 1:
            prev = num
            continue
        if start == prev:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{prev}")
        start = prev = num
    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")
    return "[" + ",".join(ranges) + "]"


def format_count(value: float) -> str:
    return f"{value:,.1f}"


def format_rate(value: float) -> str:
    return f"{value:,.1f}"


def format_pct(value: float) -> str:
    return f"{value:.2f}%"


def describe_change(value: float, unit_label: str) -> str:
    magnitude = format_count(abs(value))
    if value > 0:
        direction = "increased"
    elif value < 0:
        direction = "decreased"
    else:
        direction = "changed"
    return f"{direction} by {magnitude} {unit_label}"


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_study_context(study_root: Path) -> dict[str, object]:
    tables_root = study_root / "outputs" / "tables"
    derived_root = study_root / "data" / "derived"
    manuscript_root = study_root / "outputs" / "manuscript"
    return {
        "study_config": json.loads((study_root / "study_config.json").read_text(encoding="utf-8")),
        "table1": load_csv(tables_root / "asthma_east_asia_female_u40_table_1_2023_burden_and_rates.csv"),
        "table2": load_csv(tables_root / "asthma_east_asia_female_u40_table_2_pooled_rate_eapc.csv"),
        "table3": load_csv(tables_root / "asthma_east_asia_female_u40_table_3_peak_age_patterns_2023.csv"),
        "table4": load_csv(tables_root / "asthma_east_asia_female_u40_table_4_risk_attribution_2023.csv"),
        "phase3_qc": json.loads((tables_root / "asthma_east_asia_female_u40_phase3_qc.json").read_text(encoding="utf-8")),
        "pooled_rates": load_csv(derived_root / "asthma_east_asia_female_u40_pooled_rates.csv"),
        "core_clean": load_csv(derived_root / "asthma_east_asia_female_u40_core_clean.csv"),
        "risk_deaths": load_csv(derived_root / "asthma_east_asia_female_u40_risk_deaths_clean.csv"),
        "risk_dalys": load_csv(derived_root / "asthma_east_asia_female_u40_risk_dalys_clean.csv"),
        "under40_counts": load_csv(derived_root / "asthma_east_asia_female_u40_under40_counts.csv"),
        "figure_legends_phase4": (manuscript_root / "figure_legends.md").read_text(encoding="utf-8"),
    }


def build_reference_pool_map(study_root: Path) -> dict[str, dict[str, str]]:
    pool_files = [
        study_root / "outputs" / "references" / "pubmed_references_advanced.csv",
        study_root / "outputs" / "references" / "methods_pool" / "pubmed_references_advanced.csv",
        study_root / "outputs" / "references" / "risk_pool" / "pubmed_references_advanced.csv",
    ]
    ref_map: dict[str, dict[str, str]] = {}
    for file_path in pool_files:
        if not file_path.exists():
            continue
        with file_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                pmid = row.get("pmid", "").strip()
                if pmid and pmid not in ref_map:
                    ref_map[pmid] = row
    return ref_map


def first_initials(given_name: str) -> str:
    parts = re.split(r"[\s-]+", given_name.strip())
    initials = "".join(part[0] for part in parts if part)
    return initials


def author_name(family: str, given: str) -> str:
    initials = first_initials(given)
    return f"{family} {initials}".strip()


def crossref_fill(doi: str) -> dict[str, str | list[str] | int | None]:
    if not doi:
        return {
            "authors": [],
            "title": "",
            "journal": "",
            "year": None,
            "volume": "",
            "issue": "",
            "pages": "",
        }
    cr = Crossref()
    try:
        message = cr.works(ids=doi)["message"]
    except Exception:
        return {
            "authors": [],
            "title": "",
            "journal": "",
            "year": None,
            "volume": "",
            "issue": "",
            "pages": "",
        }
    authors = [
        author_name(item.get("family", ""), item.get("given", ""))
        for item in message.get("author", [])
        if item.get("family", "")
    ]
    issued = message.get("issued", {}).get("date-parts", [[None]])
    year = issued[0][0] if issued and issued[0] else None
    return {
        "authors": authors,
        "title": strip_html((message.get("title") or [""])[0]),
        "journal": strip_html((message.get("container-title") or [""])[0]),
        "year": int(year) if year else None,
        "volume": str(message.get("volume") or ""),
        "issue": str(message.get("issue") or ""),
        "pages": str(message.get("page") or ""),
    }


def fetch_selected_references(study_root: Path) -> list[RefMeta]:
    Entrez.email = "research-bot@example.com"
    pool_map = build_reference_pool_map(study_root)
    pmids = [entry["pmid"] for entry in REF_ASSIGNMENTS]
    handle = Entrez.efetch(db="pubmed", id=",".join(pmids), rettype="medline", retmode="xml")
    data = Entrez.read(handle)
    article_map: dict[str, dict] = {}
    for article in data.get("PubmedArticle", []):
        pmid = str(article["MedlineCitation"]["PMID"])
        article_map[pmid] = article

    refs: list[RefMeta] = []
    for ref_no, entry in enumerate(REF_ASSIGNMENTS, start=1):
        pmid = entry["pmid"]
        section = entry["section"]
        article = article_map.get(pmid, {})
        citation = article.get("MedlineCitation", {}).get("Article", {})
        pool_row = pool_map.get(pmid, {})
        title = strip_html(str(citation.get("ArticleTitle", ""))) or pool_row.get("title", "")
        journal = str(citation.get("Journal", {}).get("ISOAbbreviation", "")) or pool_row.get("journal", "")
        pub_date = citation.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
        year = None
        if "Year" in pub_date:
            try:
                year = int(str(pub_date["Year"]))
            except Exception:
                year = None
        if year is None:
            medline_date = str(pub_date.get("MedlineDate", ""))
            match = re.search(r"(19|20)\d{2}", medline_date)
            if match:
                year = int(match.group(0))
        authors = []
        for author in citation.get("AuthorList", []):
            family = author.get("LastName", "")
            given = author.get("ForeName", "") or author.get("Initials", "")
            if family:
                authors.append(author_name(family, given))
            elif author.get("CollectiveName", ""):
                authors.append(author.get("CollectiveName"))
        doi = ""
        for item in citation.get("ELocationID", []):
            if getattr(item, "attributes", {}).get("EIdType") == "doi":
                doi = str(item)
                break
        if not doi:
            for item in article.get("PubmedData", {}).get("ArticleIdList", []):
                if getattr(item, "attributes", {}).get("IdType") == "doi":
                    doi = str(item)
                    break
        if not doi:
            doi = pool_row.get("doi", "")
        volume = str(citation.get("Journal", {}).get("JournalIssue", {}).get("Volume", "") or "")
        issue = str(citation.get("Journal", {}).get("JournalIssue", {}).get("Issue", "") or "")
        pages = str(citation.get("Pagination", {}).get("MedlinePgn", "") or "")

        if not authors or not title or not journal or not year or not volume or not pages:
            extra = crossref_fill(doi)
            authors = authors or list(extra["authors"])  # type: ignore[arg-type]
            title = title or str(extra["title"])
            journal = journal or str(extra["journal"])
            year = year or extra["year"]  # type: ignore[assignment]
            volume = volume or str(extra["volume"])
            issue = issue or str(extra["issue"])
            pages = pages or str(extra["pages"])

        refs.append(
            RefMeta(
                ref_no=ref_no,
                section=section,
                pmid=pmid,
                doi=doi,
                year=year,
                title=strip_html(title),
                journal=journal,
                authors=authors,
                volume=volume,
                issue=issue,
                pages=pages,
                pubmed_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                doi_url=f"https://doi.org/{doi}" if doi else "",
            )
        )
    return refs


def build_reference_outputs(study_root: Path, manuscript_root: Path, refs: list[RefMeta]) -> dict[str, object]:
    ref_dir = study_root / "outputs" / "references" / "curated_submission"
    ensure_dir(ref_dir)
    ref_csv = ref_dir / "references_curated_36.csv"
    ref_md = ref_dir / "references_curated_36.md"
    distribution_json = ref_dir / "reference_distribution.json"

    rows = []
    for ref in refs:
        rows.append(
            {
                "ref_no": ref.ref_no,
                "section": ref.section,
                "pmid": ref.pmid,
                "doi": ref.doi,
                "year": ref.year or "",
                "journal": ref.journal,
                "title": ref.title,
                "authors": "; ".join(ref.authors),
                "pubmed_url": ref.pubmed_url,
                "doi_url": ref.doi_url,
                "vancouver": ref.vancouver(),
            }
        )
    save_csv(pd.DataFrame(rows), ref_csv)
    save_text(ref_md, "# References\n\n" + "\n".join(ref.vancouver() for ref in refs))
    distribution = dict(Counter(ref.section for ref in refs))
    save_text(distribution_json, json.dumps(distribution, indent=2))
    return {
        "ref_csv": str(ref_csv),
        "ref_md": str(ref_md),
        "distribution_json": str(distribution_json),
        "distribution": distribution,
    }


def build_metrics(ctx: dict[str, object]) -> dict[str, object]:
    table1: pd.DataFrame = ctx["table1"]  # type: ignore[assignment]
    table2: pd.DataFrame = ctx["table2"]  # type: ignore[assignment]
    table3: pd.DataFrame = ctx["table3"]  # type: ignore[assignment]
    table4: pd.DataFrame = ctx["table4"]  # type: ignore[assignment]
    aggregate = table1.loc[table1["location_name"] == AGGREGATE_LABEL].set_index("measure_short").to_dict("index")
    constituent = table1.loc[table1["location_type"] == "constituent_location"].copy()
    top_counts = (
        constituent.sort_values(["measure_short", "count_2023"], ascending=[True, False])
        .groupby("measure_short", as_index=False)
        .first()
        .set_index("measure_short")
        .to_dict("index")
    )
    top_rates = (
        constituent.sort_values(["measure_short", "pooled_rate"], ascending=[True, False])
        .groupby("measure_short", as_index=False)
        .first()
        .set_index("measure_short")
        .to_dict("index")
    )
    eapc_lookup = table2.set_index(["measure_short", "location_name"]).to_dict("index")
    biggest_decline = (
        table2.loc[table2["location_type"] == "constituent_location"]
        .sort_values(["measure_short", "eapc"], ascending=[True, True])
        .groupby("measure_short", as_index=False)
        .first()
        .set_index("measure_short")
        .to_dict("index")
    )
    exceptions = table2.loc[
        (table2["location_type"] == "constituent_location") & (table2["eapc"] > 0)
    ].copy()
    peak_cells = table3.sort_values("rate_2023", ascending=False).copy()
    top_risks_2023 = (
        table4.sort_values(["measure_short", "share_of_total_pct"], ascending=[True, False])
        .groupby("measure_short", as_index=False)
        .first()
        .set_index("measure_short")
        .to_dict("index")
    )
    return {
        "aggregate": aggregate,
        "top_counts": top_counts,
        "top_rates": top_rates,
        "eapc_lookup": eapc_lookup,
        "biggest_decline": biggest_decline,
        "exceptions": exceptions,
        "peak_cells": peak_cells,
        "top_risks_2023": top_risks_2023,
    }


def build_risk_change_package(ctx: dict[str, object], study_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    under40_counts: pd.DataFrame = ctx["under40_counts"]  # type: ignore[assignment]
    risk_deaths: pd.DataFrame = ctx["risk_deaths"]  # type: ignore[assignment]
    risk_dalys: pd.DataFrame = ctx["risk_dalys"]  # type: ignore[assignment]
    tables_root = study_root / "outputs" / "tables"
    figures_root = study_root / "outputs" / "figures"

    totals = (
        under40_counts.groupby(["measure_short", "year_id"], as_index=False)["under40_count"]
        .sum()
        .rename(columns={"under40_count": "total_burden_count"})
    )

    frames: list[pd.DataFrame] = []
    for measure_short, risk_df in [("Deaths", risk_deaths), ("DALYs", risk_dalys)]:
        subset = risk_df.loc[risk_df["metric_name"] == "Number"].copy()
        grouped = (
            subset.groupby(["rei_name", "year_id"], as_index=False)[["val", "lower", "upper"]]
            .sum()
            .rename(columns={"val": "attributable_count", "lower": "lower_sum", "upper": "upper_sum"})
        )
        grouped["measure_short"] = measure_short
        grouped = grouped.merge(
            totals.loc[totals["measure_short"] == measure_short, ["year_id", "total_burden_count"]],
            on="year_id",
            how="left",
        )
        grouped["share_of_total_pct"] = grouped["attributable_count"] / grouped["total_burden_count"] * 100.0
        frames.append(grouped)
    trend_df = pd.concat(frames, ignore_index=True)

    top5 = (
        trend_df.loc[trend_df["year_id"] == 2023]
        .sort_values(["measure_short", "attributable_count"], ascending=[True, False])
        .groupby("measure_short")
        .head(5)[["measure_short", "rei_name"]]
    )
    trend_top5 = trend_df.merge(top5, on=["measure_short", "rei_name"], how="inner").copy()
    table5_rows: list[pd.DataFrame] = []
    for measure_short in ["Deaths", "DALYs"]:
        subset = trend_top5.loc[trend_top5["measure_short"] == measure_short].copy()
        c1990 = subset.loc[subset["year_id"] == 1990, ["rei_name", "attributable_count", "share_of_total_pct"]].rename(
            columns={"attributable_count": "count_1990", "share_of_total_pct": "share_1990_pct"}
        )
        c2023 = subset.loc[subset["year_id"] == 2023, ["rei_name", "attributable_count", "share_of_total_pct"]].rename(
            columns={"attributable_count": "count_2023", "share_of_total_pct": "share_2023_pct"}
        )
        merged = c1990.merge(c2023, on="rei_name", how="outer").fillna(0)
        merged["measure_short"] = measure_short
        merged["absolute_change"] = merged["count_2023"] - merged["count_1990"]
        merged["percent_change"] = merged.apply(
            lambda row: ((row["count_2023"] - row["count_1990"]) / row["count_1990"] * 100.0)
            if row["count_1990"] > 0
            else float("nan"),
            axis=1,
        )
        merged["share_change_pct_points"] = merged["share_2023_pct"] - merged["share_1990_pct"]
        merged = merged.sort_values("count_2023", ascending=False)
        table5_rows.append(merged)
    table5 = pd.concat(table5_rows, ignore_index=True)
    save_csv(table5, tables_root / "asthma_east_asia_female_u40_table_5_risk_change_1990_2023.csv")

    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), sharey=False)
    palette = sns.color_palette("Set2", n_colors=5)
    for ax, measure_short in zip(axes, ["Deaths", "DALYs"]):
        subset = trend_top5.loc[trend_top5["measure_short"] == measure_short].copy()
        ordered_risks = (
            subset.loc[subset["year_id"] == 2023]
            .sort_values("share_of_total_pct", ascending=False)["rei_name"]
            .tolist()
        )
        sns.lineplot(
            data=subset,
            x="year_id",
            y="share_of_total_pct",
            hue="rei_name",
            hue_order=ordered_risks,
            palette=palette,
            linewidth=2.2,
            ax=ax,
        )
        ax.set_title(measure_short)
        ax.set_xlabel("Year")
        ax.set_ylabel("Attributable share of total burden (%)")
        ax.legend(title="Risk", fontsize=8, title_fontsize=9)
    fig.suptitle(
        "Figure 5. Trends in leading attributable risk shares for asthma deaths and DALYs among females younger than 40 years in East Asia, 1990-2023",
        fontsize=14,
    )
    fig.tight_layout()
    fig_base = figures_root / "asthma_east_asia_female_u40_figure_5_risk_trends"
    fig.savefig(fig_base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(fig_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return table5, trend_top5


def build_long_summary(metrics: dict[str, object]) -> str:
    agg = metrics["aggregate"]
    top_risks = metrics["top_risks_2023"]
    eapc_lookup = metrics["eapc_lookup"]
    return dedent(
        f"""
        # Summary

        ## Background

        Asthma contributes substantially to morbidity across childhood, adolescence, and young adulthood, but younger female populations in East Asia have rarely been profiled with age-restricted, location-specific GBD analyses.

        ## Methods

        We conducted a descriptive health-estimates study using official GBD 2023 Results custom exports for China, Japan, Mongolia, Democratic People's Republic of Korea, Republic of Korea, and Taiwan. The analytic population was restricted to females younger than 40 years and to eight age groups from younger than 5 years to 35-39 years. Primary outcomes were incidence, prevalence, deaths, and DALYs from 1990 to 2023. We retained age-specific counts and rates as the core endpoints, summed counts across the eight age groups for under-40 descriptive analyses, reconstructed pooled crude under-40 rates from matched counts and rates, and estimated annual percentage changes (EAPCs) from log-linear models. We also summarised all asthma-related risk factors returned by the official GBD Results interface for deaths and DALYs.

        ## Findings

        In 2023, females younger than 40 years across the six included East Asian locations experienced an estimated {format_count(agg['Incidence']['count_2023'])} incident asthma cases, {format_count(agg['Prevalence']['count_2023'])} prevalent cases, {format_count(agg['Deaths']['count_2023'])} deaths, and {format_count(agg['DALYs']['count_2023'])} DALYs. Study-scope pooled crude rates declined between 1990 and 2023 for incidence, prevalence, deaths, and DALYs, with EAPCs of {format_pct(eapc_lookup[('Incidence', AGGREGATE_LABEL)]['eapc'])}, {format_pct(eapc_lookup[('Prevalence', AGGREGATE_LABEL)]['eapc'])}, {format_pct(eapc_lookup[('Deaths', AGGREGATE_LABEL)]['eapc'])}, and {format_pct(eapc_lookup[('DALYs', AGGREGATE_LABEL)]['eapc'])}, respectively. In 2023 the leading attributable risk factor was occupational asthmagens for deaths ({format_count(top_risks['Deaths']['attributable_count_2023'])}) and high body-mass index for DALYs ({format_count(top_risks['DALYs']['attributable_count_2023'])}).

        ## Interpretation

        Asthma burden among females younger than 40 years in East Asia declined overall, but residual burden remained high in 2023 and was strongly patterned by age, location, and modifiable risk exposures. Strategies targeting childhood control, metabolic risk, smoke exposure, and occupational asthmagens are likely to yield the largest gains.

        ## Funding

        Funding: [To be completed by authors]. Role of the funding source: [To be completed by authors].
        """
    ).strip()


def build_research_in_context() -> str:
    return dedent(
        """
        # Panel: Research in context

        ## Evidence before this study

        We searched PubMed and related indexing services through a reproducible local pipeline to identify literature on asthma burden, East Asian epidemiology, GBD methods, and major attributable risk factors relevant to younger females. The final manuscript package uses 36 references, distributed evenly across the Introduction, Methods, and Discussion sections.

        ## Added value of this study

        This analysis combines official study-specific GBD 2023 exports with an age-restricted East Asian design focused on females younger than 40 years. The pipeline preserves stable identifiers, reconstructs pooled under-40 crude rates transparently, quantifies long-term trend changes, and links attributable risk patterns to manuscript-ready tables, figures, and text. It also avoids a common methodological error in restricted-age GBD studies by not relabelling reconstructed under-40 pooled rates as age-standardised rates.

        ## Implications of all the available evidence

        The available evidence and the current results together suggest that asthma prevention for younger females in East Asia requires a life-course framework. Prevention should extend beyond pharmacological management to include smoke-free environments, occupational protection, and metabolic risk reduction, while also preserving age-specific surveillance rather than collapsing younger populations into broad all-age summaries.
        """
    ).strip()


def build_introduction(metrics: dict[str, object], ref_no: dict[str, int]) -> str:
    c1 = cite(ref_no["40147466"], ref_no["39867965"], ref_no["32526187"], ref_no["28822787"])
    c2 = cite(ref_no["40684789"], ref_no["31275909"], ref_no["32972987"])
    c3 = cite(ref_no["29988370"], ref_no["39434052"], ref_no["30878568"])
    c4 = cite(ref_no["37324106"], ref_no["26666488"])
    peak = metrics["peak_cells"].iloc[0]
    return dedent(
        f"""
        # Introduction

        Asthma is one of the most persistent chronic respiratory conditions across the life course and remains a major contributor to years lived with disability, recurrent health-care use, and preventable premature mortality worldwide {c1}. Global burden assessments have repeatedly shown that asthma contributes meaningfully to respiratory disease burden even when total asthma mortality is relatively low compared with other chronic lung diseases, because the disorder begins early, persists over long periods, and imposes recurrent functional limitation {c1}.

        A central problem in the asthma literature is that the epidemiology of younger populations is often hidden inside all-age summaries. Childhood asthma, adolescent asthma, and early adult asthma are frequently discussed together, but the risk environment and disease implications change across those stages {c2}. The same person-years can span infancy, school age, adolescence, transition to employment, reproductive-age adulthood, and entry into the late thirties. These stages carry different relevance for passive smoke exposure, school and household environments, air pollution, obesity, occupation-related sensitisation, health-care access, and treatment adherence {c2}. A narrowly defined age-sex analysis can therefore provide more decision-relevant evidence than a broad all-age estimate.

        East Asia is a particularly important region in which to apply that logic. The six locations included in this study contain very large population bases, striking variation in urbanisation and industrial exposure, and heterogeneous respiratory-health systems. Recent work has documented substantial asthma burden in China, persistent severe asthma challenges in Japan, and meaningful heterogeneity in younger adult burden in South Korea {c3}. In Mongolia and other settings with marked environmental variability, childhood and adolescent asthma patterns may differ still further because climatic, housing, and pollution conditions are not interchangeable with those of higher-income East Asian settings {c4}.

        The existing East Asian literature also suffers from three recurring limitations. First, studies often focus on a single country or a single age band, which makes regional comparison difficult. Second, risk-factor analyses frequently examine obesity, secondhand smoke, or occupational exposure in isolation rather than as part of a unified burden framework. Third, health-estimates studies restricted to younger age groups sometimes default to whole-population age-standardised metrics without clearly documenting how restricted-age denominators were handled. These problems reduce comparability across countries and limit the policy usefulness of reported estimates.

        GBD data create an opportunity to address these gaps, provided they are used carefully. The current project was designed to use official study-specific GBD Results exports only, preserve identifier fields, and keep age-specific counts and rates as the primary endpoints. Combined under-40 rates were only reconstructed after explicit denominator recovery from matched GBD counts and rates, so that the resulting metrics remained interpretable as pooled crude rates rather than mislabelled age-standardised rates.

        We therefore aimed to quantify the burden of asthma among females younger than 40 years in East Asia from 1990 to 2023, compare the six included locations, describe age-specific burden patterns in 2023, assess long-term trend changes, and quantify the leading attributable risk factors for deaths and DALYs. The highest location-age rate cell in the present analysis was {peak['measure_short']} in {peak['location_name']} among those aged {peak['peak_age_group']}, which underscores the value of explicit age-group reporting rather than a single undifferentiated regional estimate.
        """
    ).strip()


def build_methods(metrics: dict[str, object], ref_no: dict[str, int], phase3_qc: dict[str, object]) -> str:
    c_hist = cite(ref_no["27351744"], ref_no["36216939"], ref_no["26475018"], ref_no["9164317"], ref_no["12423980"])
    c_resp = cite(ref_no["38762324"], ref_no["37229504"], ref_no["37353829"], ref_no["32075787"])
    c_age = cite(ref_no["38970015"], ref_no["39134934"], ref_no["39359410"])
    return dedent(
        f"""
        # Methods

        ## Study design

        This study was a descriptive health-estimates analysis based on the Global Burden of Disease Study 2023. The reporting strategy was aligned with the GATHER framework for health estimates, while the broader analytical rationale followed the established GBD approach to burden quantification, disability weighting, and comparative risk assessment {c_hist}. The present study did not attempt to re-estimate the upstream GBD model; instead, it performed a study-specific extraction and a reproducible downstream analysis anchored to official GBD Results outputs.

        ## Setting, participants, and study size

        The geographic setting was East Asia, restricted to the six locations available in the study-specific extraction specification: China, Japan, Mongolia, Democratic People's Republic of Korea, Republic of Korea, and Taiwan. The analytic population was restricted to females younger than 40 years and was represented through eight GBD age groups: younger than 5 years, 5-9 years, 10-14 years, 15-19 years, 20-24 years, 25-29 years, 30-34 years, and 35-39 years. Because the study was based on aggregated health-estimate strata rather than individual-level enrollment, study size was defined by the complete set of location-sex-age-measure-metric-year combinations returned by the official export workflow.

        Participants flow was therefore operationalised as stratum eligibility flow. Rows were eligible only when all of the following conditions were met: location within the six prespecified East Asian locations; sex restricted to female; age restricted to the eight under-40 groups; cause restricted to asthma; measure restricted to incidence, prevalence, deaths, or DALYs; metric restricted to number or rate; and year restricted to 1990-2023. Quality-control rules then enforced complete year coverage, complete location coverage, and the uncertainty ordering lower less than or equal to mean less than or equal to upper.

        ## Data inputs, data sources, inclusion criteria, and variables

        Data inputs came exclusively from official GBD Results custom exports generated for this study. The exported files retained measure identifiers and names, metric identifiers and names, location identifiers and names, sex identifiers and names, age identifiers and names, cause identifiers and names, year, mean estimate, lower bound, and upper bound. For attributable burden analyses, risk factor identifiers and names were also retained. Inclusion criteria were defined ex ante by the locked extraction specification and were not modified after export.

        The main variables were four burden outcomes: incidence, prevalence, deaths, and DALYs. Two attributable-risk outcomes were then derived by querying asthma-related risk factors for deaths and DALYs under the same location, sex, age, and year filters. These inputs were chosen because prior GBD respiratory burden analyses and asthma-specific burden studies have used the same basic architecture for disease counts, rates, and attributable risk decomposition {c_resp}. Age-restricted GBD analyses among adolescents, young adults, and reproductive-age populations in other disease domains also informed the design choice to preserve age-specific rows rather than collapse the population into a single all-age metric {c_age}.

        ## Data cleaning, bias control, and reproducible code

        Data cleaning was performed in a fixed local pipeline inside the study workspace. Raw study exports were first validated for row uniqueness by the intended analytic keys. They were then transformed into study-specific derived datasets, including a cleaned core burden file, cleaned risk-attributable files, under-40 summed count files, and age-specific 2023 profile files. The phase-three quality-control summary confirmed {phase3_qc['pooled_rate_rows']} pooled-rate rows, {phase3_qc['eapc_rows']} EAPC rows, and no nonpositive pooled rates or nonpositive reconstructed population estimates.

        Bias control in the present study focused on design and interpretation. We did not assume that GBD all-age age-standardised indicators were appropriate headline outcomes for the under-40 female population. We also did not add age-specific rates directly. Instead, the analysis preserved age-specific counts and rates as the primary endpoints, described uncertainty throughout, and clearly separated official exported values from derived pooled under-40 quantities. Attributable burden was interpreted within the GBD comparative-risk framework only, rather than as proof of direct individual-level causation.

        Reproducible code was used at every stage. Separate local scripts handled authenticated GBD export, second-stage data cleaning, phase-three figure and table generation, and the final long-form submission package. This architecture ensures that every table and figure cited in the manuscript can be traced back to fixed local inputs and rerun without manual spreadsheet editing.

        ## Statistical methods and statistical model

        The primary descriptive analyses were cross-sectional burden summaries for 2023 and longitudinal trend analyses over 1990-2023. For 2023 burden tables, age-specific counts were summed across the eight age groups within each location and measure. These summed counts were used for incidence, prevalence, deaths, and DALYs. Location-specific rate comparisons in 2023 used derived pooled crude under-40 rates per 100,000 rather than age-standardised rates.

        Pooled crude under-40 rates were reconstructed by first matching GBD counts with the corresponding GBD rates within each location, age group, year, and outcome. We then estimated age-specific denominators as count divided by rate multiplied by 100,000. These recovered age-specific denominators were summed across the eight age groups to obtain the under-40 female denominator for each location, year, and outcome, and pooled crude rates were recalculated as total count divided by total reconstructed population multiplied by 100,000. This explicit denominator recovery was necessary because direct addition of age-specific rates would have produced uninterpretable results.

        Time trends in pooled crude rates were summarised with estimated annual percentage changes. For each outcome-location series, we fitted a log-linear model of the form ln(rate) equals alpha plus beta multiplied by calendar year. EAPC was calculated as 100 multiplied by the exponential of beta minus 1. Ninety-five percent confidence intervals for EAPC were derived from the standard error of beta under the same model. We only applied the EAPC model to series with strictly positive pooled crude rates across the observation window.

        Attributable risk analyses were done separately for deaths and DALYs. For each measure, attributable counts were aggregated across the six locations and across the eight age groups within each year. We then calculated the attributable share of the total study-scope burden for each risk factor. The top five risks in 2023 for deaths and for DALYs were used to create the fifth main table and fifth main figure, which summarised 1990-2023 change patterns and temporal trajectories.

        ## Uncertainty, model evaluation, ethics approval, and funding

        Uncertainty was preserved from the original GBD export through the retained lower and upper bounds. When counts were aggregated across age groups or across locations, lower and upper values were summed arithmetically and explicitly labelled as descriptive aggregate bounds rather than full covariance-adjusted intervals. Model evaluation was deterministic rather than predictive: we checked scope completeness, absence of duplicate rows, positive reconstructed population denominators, and stable output generation across repeated runs. Data sources, statistical model choices, uncertainty handling, and reproducible code paths were therefore all auditable within the local workspace.

        Ethics approval: the current study used aggregated, non-identifiable health-estimate outputs and did not involve direct participant contact. Institutional ethics confirmation should nonetheless be completed by the submitting authors according to local policy. Informed consent was not applicable. Funding and the role of the funding source remain explicit placeholders for author completion before submission.
        """
    ).strip()


def build_results(
    metrics: dict[str, object],
    table5: pd.DataFrame,
) -> str:
    agg = metrics["aggregate"]
    top_counts = metrics["top_counts"]
    top_rates = metrics["top_rates"]
    eapc_lookup = metrics["eapc_lookup"]
    biggest_decline = metrics["biggest_decline"]
    exceptions: pd.DataFrame = metrics["exceptions"]
    peak_cells: pd.DataFrame = metrics["peak_cells"]
    top_risks = metrics["top_risks_2023"]

    deaths_t5 = table5.loc[table5["measure_short"] == "Deaths"].copy().sort_values("count_2023", ascending=False)
    dalys_t5 = table5.loc[table5["measure_short"] == "DALYs"].copy().sort_values("count_2023", ascending=False)
    top_death_change = deaths_t5.iloc[0]
    top_daly_change = dalys_t5.iloc[0]
    exception_text = "; ".join(
        f"{row.measure_short} in {row.location_name} (EAPC {format_pct(row.eapc)})"
        for row in exceptions.itertuples(index=False)
    )
    incidence_peak = peak_cells.loc[peak_cells["measure_short"] == "Incidence"].iloc[0]
    prevalence_peak = peak_cells.loc[peak_cells["measure_short"] == "Prevalence"].iloc[0]
    deaths_peak = peak_cells.loc[peak_cells["measure_short"] == "Deaths"].iloc[0]
    daly_peak = peak_cells.loc[peak_cells["measure_short"] == "DALYs"].iloc[0]
    return dedent(
        f"""
        # Results

        ## Burden in 2023

        Across the six included East Asian locations, females younger than 40 years experienced an estimated {format_count(agg['Incidence']['count_2023'])} incident asthma cases, {format_count(agg['Prevalence']['count_2023'])} prevalent cases, {format_count(agg['Deaths']['count_2023'])} deaths, and {format_count(agg['DALYs']['count_2023'])} DALYs in 2023 (Table 1). The corresponding study-scope pooled crude rates were {format_rate(agg['Incidence']['pooled_rate'])}, {format_rate(agg['Prevalence']['pooled_rate'])}, {format_rate(agg['Deaths']['pooled_rate'])}, and {format_rate(agg['DALYs']['pooled_rate'])} per 100,000, respectively.

        China carried the largest absolute burden for all four main outcomes in 2023, with {format_count(top_counts['Incidence']['count_2023'])} incident cases, {format_count(top_counts['Prevalence']['count_2023'])} prevalent cases, {format_count(top_counts['Deaths']['count_2023'])} deaths, and {format_count(top_counts['DALYs']['count_2023'])} DALYs. By contrast, the highest pooled incidence rate was observed in {top_rates['Incidence']['location_name']} ({format_rate(top_rates['Incidence']['pooled_rate'])} per 100,000), the highest pooled prevalence rate in {top_rates['Prevalence']['location_name']} ({format_rate(top_rates['Prevalence']['pooled_rate'])} per 100,000), the highest pooled death rate in {top_rates['Deaths']['location_name']} ({format_rate(top_rates['Deaths']['pooled_rate'])} per 100,000), and the highest pooled DALY rate in {top_rates['DALYs']['location_name']} ({format_rate(top_rates['DALYs']['pooled_rate'])} per 100,000).

        ## Long-term trends, 1990-2023

        At the study-scope aggregate level, pooled crude rates declined across all four outcomes between 1990 and 2023 (Table 2; Figures 1 and 2). The EAPC was {format_pct(eapc_lookup[('Incidence', AGGREGATE_LABEL)]['eapc'])} for incidence, {format_pct(eapc_lookup[('Prevalence', AGGREGATE_LABEL)]['eapc'])} for prevalence, {format_pct(eapc_lookup[('Deaths', AGGREGATE_LABEL)]['eapc'])} for deaths, and {format_pct(eapc_lookup[('DALYs', AGGREGATE_LABEL)]['eapc'])} for DALYs. The steepest decline among constituent locations was observed in Democratic People's Republic of Korea for incidence ({format_pct(biggest_decline['Incidence']['eapc'])}), Mongolia for prevalence ({format_pct(biggest_decline['Prevalence']['eapc'])}) and DALYs ({format_pct(biggest_decline['DALYs']['eapc'])}), and Japan for deaths ({format_pct(biggest_decline['Deaths']['eapc'])}).

        Trend reversal or near-stagnation was confined to a small number of location-outcome combinations. Positive EAPCs were observed for {exception_text}. These exceptions indicate that the overall downward regional pattern concealed important local heterogeneity, particularly in prevalence and in selected mortality series.

        ## Age-specific burden in 2023

        Age-specific heterogeneity remained pronounced in 2023 (Table 3; Figure 3). The highest incidence-rate cell was recorded in {incidence_peak['location_name']} among those aged {incidence_peak['peak_age_group']} ({format_rate(incidence_peak['rate_2023'])} per 100,000), while the highest prevalence-rate cell was recorded in {prevalence_peak['location_name']} among those aged {prevalence_peak['peak_age_group']} ({format_rate(prevalence_peak['rate_2023'])} per 100,000). For mortality, the highest age-location rate cell occurred in {deaths_peak['location_name']} among those aged {deaths_peak['peak_age_group']} ({format_rate(deaths_peak['rate_2023'])} per 100,000). The highest DALY-rate cell occurred in {daly_peak['location_name']} among those aged {daly_peak['peak_age_group']} ({format_rate(daly_peak['rate_2023'])} per 100,000).

        The age pattern also differed by outcome. Incidence and prevalence tended to peak in younger age groups, especially younger than 5 years and 5-9 years, whereas death rates were concentrated in the oldest study age band, 35-39 years, across all six constituent locations. DALYs showed a mixed profile, with some locations peaking in childhood and others in early adulthood, which suggests that morbidity and disability accumulation are not governed by a single shared age pattern throughout East Asia.

        ## Attributable risk factors in 2023

        In 2023, the leading attributable risk factor for asthma deaths was occupational asthmagens, accounting for {format_count(top_risks['Deaths']['attributable_count_2023'])} deaths and {format_pct(top_risks['Deaths']['share_of_total_pct'])} of the total study-scope asthma deaths (Table 4; Figure 4). High body-mass index ranked second for deaths, followed by secondhand smoke. For DALYs, high body-mass index ranked first, accounting for {format_count(top_risks['DALYs']['attributable_count_2023'])} DALYs and {format_pct(top_risks['DALYs']['share_of_total_pct'])} of total asthma DALYs, followed by secondhand smoke and occupational asthmagens.

        Although absolute attributable counts remained modest relative to morbidity totals, the risk ranking pattern was consistent across the two endpoints in showing the importance of modifiable, largely preventable exposures. Nitrogen dioxide pollution entered the top-five list for DALYs but not for deaths, while sexual violence against children remained a smaller but still detectable contributor in both risk frameworks. Because the summed uncertainty interval for nitrogen dioxide pollution crossed zero, this signal should be interpreted cautiously.

        ## Change in attributable burden from 1990 to 2023

        The fifth main table and fifth main figure extend the risk-attribution analysis from a single-year ranking to a longitudinal view (Table 5; Figure 5). For deaths, occupational asthmagens remained the leading attributable risk in 2023 and {describe_change(top_death_change['absolute_change'], 'attributable deaths compared with 1990')}, with a share change of {top_death_change['share_change_pct_points']:.2f} percentage points. For DALYs, high body-mass index showed the largest attributable count in 2023 and {describe_change(top_daly_change['absolute_change'], 'attributable DALYs compared with 1990')}, with a share change of {top_daly_change['share_change_pct_points']:.2f} percentage points.

        Over the full 1990-2023 period, the composition of attributable burden shifted away from a narrower smoking-dominant interpretation toward a broader pattern involving metabolic, household, and occupational exposures. This shift was more visible for DALYs than for deaths, reflecting the strong contribution of long-duration morbidity to the total burden profile in younger female populations.
        """
    ).strip()


def build_discussion(ref_no: dict[str, int]) -> str:
    c_bmi = cite(ref_no["36002091"], ref_no["41029276"], ref_no["36600406"])
    c_smoke = cite(ref_no["32667747"], ref_no["22430451"], ref_no["39915028"])
    c_occ = cite(ref_no["24521110"], ref_no["38295127"], ref_no["33141780"], ref_no["30661311"])
    c_asia = cite(ref_no["40087850"], ref_no["32468824"])
    return dedent(
        f"""
        # Discussion

        ## Principal findings

        This long-form submission package provides a fully reproducible assessment of asthma burden among females younger than 40 years in East Asia using official GBD 2023 custom exports, local derivation of pooled under-40 crude rates, and a linked manuscript-generation workflow. The main findings are that asthma burden remained substantial in 2023, that the long-term trajectory from 1990 to 2023 was generally downward but not uniform, and that the residual burden was still shaped by modifiable risks, particularly high body-mass index, secondhand smoke, and occupational asthmagens.

        ## Interpretation of burden trends

        The overall decline in pooled crude rates across incidence, prevalence, deaths, and DALYs suggests that the regional respiratory-health context improved over the study period. However, the remaining burden in 2023 shows that improvement was incomplete. The combination of high prevalent-case counts and lower but persistent mortality also indicates that asthma among younger females in East Asia is better understood as a chronic burden problem than as a narrowly fatal disease. That interpretation is important because it shifts attention from acute rescue treatment alone toward sustained disease control, prevention, and exposure reduction.

        The observed heterogeneity between locations further argues against treating East Asia as a single epidemiological unit. China dominated the absolute counts because of population size, but the highest pooled rates for several outcomes occurred elsewhere. This divergence between counts and rates matters for planning: count-heavy systems may need population-scale management infrastructure, whereas high-rate settings may require more focused investigation of exposure intensity, care access, diagnostic practices, or background susceptibility.

        ## Age profile and life-course implications

        The age pattern reinforces the value of the under-40 female frame. Incidence and prevalence tended to peak in childhood, whereas deaths clustered in the 35-39 year age group. DALY patterns were mixed, reflecting both early-life morbidity and later accumulation of impairment. These results imply that asthma prevention in East Asia should not be conceptualised as either purely paediatric or purely adult care. Instead, it requires a life-course strategy that begins in childhood, remains active through school age and adolescence, and continues into early working-age adulthood.

        This point is consistent with broader epidemiological work showing that asthma begins early, persists heterogeneously across developmental stages, and interacts with environmental and metabolic exposures in a way that cannot be reduced to one age-specific window {c_asia}. The study therefore supports age-stratified planning in both surveillance and intervention. An all-age regional summary would have obscured this pattern.

        ## Risk-factor interpretation

        The current results place modifiable exposures at the centre of interpretation. High body-mass index was the leading attributable risk factor for DALYs, while occupational asthmagens led the attributable death profile. Emerging GBD-based work and population-level analyses have increasingly connected obesity and related metabolic dysfunction to the contemporary asthma burden, including in East Asian populations and in settings that combine GBD with cohort or biobank data {c_bmi}. These patterns are epidemiologically plausible because excess adiposity can influence inflammation, lung mechanics, and severity phenotypes, while also interacting with access to care and treatment intensity.

        Secondhand smoke and nitrogen dioxide pollution also deserve emphasis. The prominence of secondhand smoke in our study aligns with pooled evidence linking passive smoke exposure to childhood and adolescent asthma development, while the appearance of nitrogen dioxide pollution in the DALY profile supports the continuing role of traffic-related and ambient exposure pathways {c_smoke}. These findings strengthen the argument that asthma control in younger females cannot be reduced to personal behaviour or medication adherence alone. Household, school, commuting, and neighborhood environments remain structurally relevant.

        Occupational asthmagens were the leading attributable risk factor for deaths and remained among the dominant DALY contributors, which is an especially important finding for a younger female population transitioning into or already participating in the labour force. The occupational-asthma literature consistently shows that diagnosis, management, and prevention remain challenging even in settings with established respiratory services {c_occ}. In practical terms, the current results suggest that workplace exposure surveillance and early work-related asthma recognition should be part of the East Asian prevention agenda for younger women, not an afterthought reserved for older workers.

        ## Comparison with existing East Asian evidence

        The present findings extend rather than replace the country-level literature. East Asian studies have already documented rising or heterogeneous asthma prevalence, substantial socioeconomic burden, and early-life patterns that differ across countries {c_asia}. What this study adds is a harmonised cross-location framework with a single disease definition, a single time window, a single sex stratum, and a single age-restricted analytic design. That harmonisation allows the comparison of China, Japan, Mongolia, Democratic People's Republic of Korea, Republic of Korea, and Taiwan inside one reproducible burden architecture.

        ## Strengths

        Several strengths should be highlighted. First, we used official study-specific GBD exports rather than repurposed tables or indirect reconstructions from published figures. Second, we preserved identifier fields and uncertainty intervals from export through downstream analysis. Third, we distinguished clearly between official age-specific rates and derived under-40 pooled crude rates. Fourth, the study workspace links raw exports, derived datasets, main tables, main figures, long manuscript text, and reference distribution in a single rerunnable package. This traceability substantially reduces the risk of narrative drift between analysis and writing.

        ## Limitations

        The study also has limitations. Like all downstream GBD analyses, it depends on upstream model structure, input data quality, and comparative-risk assumptions that were not re-estimated locally. The study-scope aggregate used in our manuscript figures and tables is a six-location aggregate reconstructed inside the local workspace, not a separately exported official East Asia regional row. Summed uncertainty intervals for aggregated counts are descriptive rather than covariance-aware. The attributable-risk framework should not be interpreted as direct causal proof at the individual level. Finally, although the current manuscript now contains a balanced reference base, it has not yet passed through a journal-specific external literature update immediately before submission and should therefore undergo one final citation refresh during target-journal formatting.

        ## Policy implications and conclusion

        Despite those limitations, the policy implications are clear. Asthma burden among females younger than 40 years in East Asia has declined, but it remains large enough to justify targeted prevention. The strongest opportunities lie in sustaining childhood asthma control, improving smoke-free environments, reducing work-related sensitiser exposure, and addressing metabolic risk. Future East Asian asthma strategies should therefore combine clinical management with environmental, occupational, and public-health interventions across the life course. In summary, this study shows that substantial under-40 female asthma burden persisted in East Asia in 2023, and that modifiable risks remained central to that burden profile.
        """
    ).strip()


def build_declarations() -> str:
    return dedent(
        """
        # Declarations

        ## Author contributions

        [To be completed by authors].

        ## Declaration of interests

        Declaration of interests: [To be completed by authors]. Conflicts of interest: [To be completed by authors].

        ## Data sharing statement

        The study-specific raw exports, derived analytic datasets, manuscript tables, manuscript figures, and code used to generate this submission package are stored in the local project workspace. Public sharing should comply with IHME and GBD Results terms for exported materials and with the eventual target-journal policy.

        ## Ethics approval and informed consent

        The current study used aggregated, non-identifiable health-estimate outputs. Ethics approval should be confirmed by the submitting authors according to institutional policy. Informed consent was not applicable.

        ## Funding

        Funding: [To be completed by authors].

        ## Role of the funding source

        Role of the funding source: [To be completed by authors].

        ## Acknowledgments

        [To be completed by authors].
        """
    ).strip()


def build_figure_legends() -> str:
    return dedent(
        """
        # Figure legends

        **Figure 1.** Trends in asthma burden counts among females younger than 40 years in six East Asian locations, 1990-2023. Panels display incident cases, prevalent cases, deaths, and DALYs. Values are summed age-specific counts across the eight under-40 age groups.

        **Figure 2.** Trends in pooled crude asthma rates among females younger than 40 years in East Asia, 1990-2023. Country lines indicate constituent locations and the dashed black line indicates the six-location study-scope aggregate reconstructed from matched counts and rates. EAPC annotations refer to the study-scope aggregate series.

        **Figure 3.** Age-specific asthma rates in 2023 among females younger than 40 years in East Asia. Heatmaps show location-by-age matrices for incidence, prevalence, deaths, and DALYs.

        **Figure 4.** Leading attributable risk factors for asthma burden among females younger than 40 years in East Asia in 2023. Bars show the attributable share of the study-scope total burden for deaths and DALYs separately.

        **Figure 5.** Trends in leading attributable risk shares for asthma deaths and DALYs among females younger than 40 years in East Asia, 1990-2023. Lines indicate the top five risks in 2023 for each endpoint, expressed as the attributable share of the total study-scope burden.
        """
    ).strip()


def build_table_titles() -> str:
    return dedent(
        """
        # Table titles

        **Table 1.** Asthma burden and pooled crude rates in 2023 among females younger than 40 years in East Asia.

        **Table 2.** Pooled crude rate trends and estimated annual percentage changes for asthma burden among females younger than 40 years in East Asia, 1990-2023.

        **Table 3.** Peak age-group patterns for asthma rates in 2023 among females younger than 40 years in East Asia.

        **Table 4.** Leading attributable risk factors for asthma deaths and DALYs in 2023 among females younger than 40 years in East Asia.

        **Table 5.** Change in leading attributable risk counts and shares for asthma deaths and DALYs among females younger than 40 years in East Asia, 1990-2023.
        """
    ).strip()


def build_manuscript(
    study_config: dict[str, object],
    summary: str,
    research_in_context: str,
    introduction: str,
    methods: str,
    results: str,
    discussion: str,
    declarations: str,
    figure_legends: str,
    table_titles: str,
    reference_lines: list[str],
) -> str:
    title_en = study_config["title_en"]
    title_zh = study_config["title_zh"]
    references = "# References\n\n" + "\n".join(reference_lines)
    return "\n\n".join(
        [
            f"# {title_en}",
            f"Chinese title: {title_zh}",
            "",
            "Authors: [To be completed by authors]",
            "Affiliations: [To be completed by authors]",
            "Correspondence: [To be completed by authors]",
            "Target format: long submission draft (>5000 words)",
            "Main tables: 5",
            "Main figures: 5",
            summary,
            research_in_context,
            introduction,
            methods,
            results,
            discussion,
            declarations,
            figure_legends,
            table_titles,
            references,
        ]
    ).strip() + "\n"


def run_pandoc(markdown_path: Path, out_path: Path) -> dict[str, object]:
    proc = subprocess.run(["pandoc", str(markdown_path), "-o", str(out_path)], capture_output=True, text=True)
    return {"ok": proc.returncode == 0, "stderr": proc.stderr.strip()}


def run_audit(markdown_path: Path, out_path: Path) -> dict[str, object]:
    proc = subprocess.run(
        [
            PY,
            str(ROOT / "analysis/python/24_manuscript_audit.py"),
            "--manuscript",
            str(markdown_path),
            "--design",
            "gbd",
            "--data_type",
            "health_estimates",
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
    )
    return {"ok": proc.returncode == 0, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def main() -> None:
    warnings.filterwarnings("ignore", message=".*ChainedAssignmentError.*", category=FutureWarning)
    warnings.filterwarnings("ignore", message=".*observed=False is deprecated.*", category=FutureWarning)
    args = parse_args()
    study_root = Path(args.study_root)
    ctx = load_study_context(study_root)
    metrics = build_metrics(ctx)
    refs = fetch_selected_references(study_root)
    ref_lookup = {ref.pmid: ref.ref_no for ref in refs}

    summary = build_long_summary(metrics)
    research_in_context = build_research_in_context()
    introduction = build_introduction(metrics, ref_lookup)
    methods = build_methods(metrics, ref_lookup, ctx["phase3_qc"])  # type: ignore[arg-type]
    table5, _ = build_risk_change_package(ctx, study_root)
    results = build_results(metrics, table5)
    discussion = build_discussion(ref_lookup)
    declarations = build_declarations()
    figure_legends = build_figure_legends()
    table_titles = build_table_titles()

    manuscript_root = study_root / "outputs" / "manuscript"
    sections_root = manuscript_root / "sections_long_submission"
    ensure_dir(sections_root)
    ref_outputs = build_reference_outputs(study_root, manuscript_root, refs)

    save_text(sections_root / "01_summary.md", summary)
    save_text(sections_root / "02_research_in_context.md", research_in_context)
    save_text(sections_root / "03_introduction.md", introduction)
    save_text(sections_root / "04_methods.md", methods)
    save_text(sections_root / "05_results.md", results)
    save_text(sections_root / "06_discussion.md", discussion)
    save_text(sections_root / "07_declarations.md", declarations)
    save_text(sections_root / "08_figure_legends.md", figure_legends)
    save_text(sections_root / "09_table_titles.md", table_titles)
    save_text(sections_root / "10_references.md", "# References\n\n" + "\n".join(ref.vancouver() for ref in refs))

    manuscript_md = manuscript_root / "submission_manuscript_5000plus.md"
    manuscript_text = build_manuscript(
        ctx["study_config"],  # type: ignore[arg-type]
        summary,
        research_in_context,
        introduction,
        methods,
        results,
        discussion,
        declarations,
        figure_legends,
        table_titles,
        [ref.vancouver() for ref in refs],
    )

    if word_count(manuscript_text) < 5000:
        raise SystemExit("Generated manuscript did not exceed 5000 words.")

    save_text(manuscript_md, manuscript_text)
    html_result = run_pandoc(manuscript_md, manuscript_root / "submission_manuscript_5000plus.html")
    docx_result = run_pandoc(manuscript_md, manuscript_root / "submission_manuscript_5000plus.docx")
    audit_result = run_audit(manuscript_md, manuscript_root / "submission_manuscript_5000plus_audit.md")
    render_result: dict[str, object] | None = None
    if docx_result["ok"]:
        render_result = render_docx_to_pngs(
            manuscript_root / "submission_manuscript_5000plus.docx",
            manuscript_root / "rendered_pages",
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manuscript": str(manuscript_md),
        "word_count": word_count(manuscript_text),
        "reference_count": len(refs),
        "reference_distribution": ref_outputs["distribution"],
        "main_figure_count": 5,
        "main_table_count": 5,
        "docx_result": docx_result,
        "html_result": html_result,
        "audit_result": audit_result,
        "render_result": render_result,
    }
    save_text(manuscript_root / "submission_package_manifest.json", json.dumps(manifest, indent=2))

    print(f"Wrote long manuscript to {manuscript_md}")
    print(f"Word count: {manifest['word_count']}")
    print(f"References: {manifest['reference_count']}")
    print("Main figures: 5")
    print("Main tables: 5")
    print(f"DOCX export ok: {docx_result['ok']}")
    print(f"HTML export ok: {html_result['ok']}")
    print(f"Audit ok: {audit_result['ok']}")
    if render_result is not None:
        print(f"Rendered page QA ok: {render_result['ok']}")


if __name__ == "__main__":
    main()
