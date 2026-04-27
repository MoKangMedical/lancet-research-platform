#!/usr/bin/env python3
"""Advanced PubMed pipeline:
1) Fetch real references with PMID/DOI
2) Group references by topic
3) Flag high-impact journals + recent-5y set
4) Generate intro-ready narrative draft
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from Bio import Entrez
from habanero import Crossref

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
CURRENT_YEAR = datetime.now().year

# Pragmatic proxy list for "high-impact" journals in clinical/epi medicine.
HIGH_IMPACT_JOURNALS = {
    "N Engl J Med",
    "Lancet",
    "JAMA",
    "BMJ",
    "Ann Intern Med",
    "JAMA Intern Med",
    "JAMA Netw Open",
    "Nat Med",
    "Nat Commun",
    "PLOS Med",
    "Circulation",
    "Eur Heart J",
}

TOPIC_RULES: dict[str, list[str]] = {
    "exposure_risk": [
        "risk", "association", "exposure", "predict", "biomarker", "index", "obesity", "bmi",
    ],
    "outcomes_mortality": [
        "mortality", "death", "survival", "cardiovascular", "all-cause", "event",
    ],
    "methods_causal": [
        "propensity", "causal", "target trial", "inverse probability", "mediation", "instrumental",
    ],
    "population_aging": [
        "aging", "older", "elderly", "geriatric", "frailty",
    ],
    "dataset_or_validation": [
        "nhanes", "mimic", "gbd", "validation", "external", "cohort", "machine learning",
    ],
}


@dataclass
class RefRow:
    pmid: str
    doi: str
    year: int | None
    title: str
    journal: str
    authors: str
    abstract: str

    @property
    def pubmed_url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"

    @property
    def doi_url(self) -> str:
        return f"https://doi.org/{self.doi}" if self.doi else ""

    @property
    def is_recent5y(self) -> bool:
        return bool(self.year and self.year >= CURRENT_YEAR - 4)

    @property
    def is_high_impact(self) -> bool:
        return self.journal in HIGH_IMPACT_JOURNALS


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--query", required=True)
    p.add_argument("--retmax", type=int, default=80)
    p.add_argument("--email", default="research-bot@example.com")
    p.add_argument("--outdir", default="/Users/apple/Documents/lancet-research-platform/outputs/references")
    p.add_argument("--project_name", default="Unnamed Study")
    return p.parse_args()


def _safe_get_year(pub_date: dict[str, Any]) -> int | None:
    if "Year" in pub_date:
        try:
            return int(str(pub_date["Year"]))
        except Exception:
            return None
    if "MedlineDate" in pub_date:
        m = re.search(r"(19|20)\d{2}", str(pub_date["MedlineDate"]))
        if m:
            return int(m.group(0))
    return None


def extract_year(article: dict[str, Any]) -> int | None:
    try:
        d = article["MedlineCitation"]["Article"]["Journal"]["JournalIssue"]["PubDate"]
        return _safe_get_year(d)
    except Exception:
        return None


def extract_title(article: dict[str, Any]) -> str:
    try:
        return str(article["MedlineCitation"]["Article"].get("ArticleTitle", "")).replace("\n", " ").strip()
    except Exception:
        return ""


def extract_journal(article: dict[str, Any]) -> str:
    try:
        return str(article["MedlineCitation"]["Article"]["Journal"].get("ISOAbbreviation", ""))
    except Exception:
        return ""


def extract_authors(article: dict[str, Any]) -> str:
    names = []
    try:
        for a in article["MedlineCitation"]["Article"].get("AuthorList", []):
            ln = a.get("LastName", "")
            ini = a.get("Initials", "")
            if ln:
                names.append((ln + " " + ini).strip())
    except Exception:
        pass
    return "; ".join(names[:10])


def extract_abstract(article: dict[str, Any]) -> str:
    try:
        ab = article["MedlineCitation"]["Article"].get("Abstract", {}).get("AbstractText", [])
        if isinstance(ab, list):
            return " ".join(str(x) for x in ab).replace("\n", " ").strip()
        return str(ab).replace("\n", " ").strip()
    except Exception:
        return ""


def extract_pmid(article: dict[str, Any]) -> str:
    try:
        return str(article["MedlineCitation"]["PMID"])
    except Exception:
        return ""


def extract_doi(article: dict[str, Any]) -> str:
    try:
        ids = article["MedlineCitation"]["Article"].get("ELocationID", [])
        if not isinstance(ids, list):
            ids = [ids]
        for item in ids:
            if getattr(item, "attributes", {}).get("EIdType") == "doi":
                return str(item)
    except Exception:
        pass
    try:
        for item in article.get("PubmedData", {}).get("ArticleIdList", []):
            if getattr(item, "attributes", {}).get("IdType") == "doi":
                return str(item)
    except Exception:
        pass
    return ""


def backfill_doi(cr: Crossref, title: str) -> str:
    if not title:
        return ""
    try:
        items = cr.works(query_title=title, limit=1).get("message", {}).get("items", [])
        if items:
            doi = items[0].get("DOI", "")
            if doi and DOI_RE.search(doi):
                return doi
    except Exception:
        pass
    return ""


def classify_topic(title: str, abstract: str) -> str:
    text = (title + " " + abstract).lower()
    score: dict[str, int] = {k: 0 for k in TOPIC_RULES}
    for topic, kws in TOPIC_RULES.items():
        score[topic] = sum(1 for kw in kws if kw in text)
    best = max(score, key=score.get)
    return best if score[best] > 0 else "other"


def cite_token(r: RefRow) -> str:
    y = str(r.year) if r.year else "n.d."
    first = r.authors.split(";")[0] if r.authors else "Unknown"
    return f"{first} ({y}) [PMID:{r.pmid}]"


def build_intro_draft(project_name: str, refs: list[RefRow], grouped: dict[str, list[RefRow]]) -> str:
    n_total = len(refs)
    n_recent = sum(r.is_recent5y for r in refs)
    n_hi = sum(r.is_high_impact for r in refs)

    def top_tokens(topic: str, k: int = 3) -> str:
        rows = sorted(grouped.get(topic, []), key=lambda x: (x.year or 0), reverse=True)[:k]
        return "; ".join(cite_token(r) for r in rows) if rows else "No key citations yet"

    return (
        f"# Intro Draft: {project_name}\n\n"
        f"This evidence snapshot includes {n_total} PubMed-indexed studies, with {n_recent} published in the recent 5-year window "
        f"({CURRENT_YEAR-4}-{CURRENT_YEAR}) and {n_hi} appearing in high-impact general or specialty journals.\n\n"
        "## Paragraph 1: Burden and relevance\n"
        "The clinical and public-health burden remains substantial, with recent epidemiologic analyses consistently linking risk-factor patterns to major outcomes. "
        f"Representative studies include {top_tokens('outcomes_mortality')}.\n\n"
        "## Paragraph 2: Exposure-outcome evidence\n"
        "Current evidence suggests robust exposure-outcome associations, though effect sizes vary by population structure, confounding control, and endpoint definitions. "
        f"Key references: {top_tokens('exposure_risk')}.\n\n"
        "## Paragraph 3: Methods and credibility\n"
        "Methodological rigor has improved with wider use of causal-inference and advanced survival approaches, but residual confounding and transportability remain major concerns. "
        f"Method-oriented references: {top_tokens('methods_causal')}.\n\n"
        "## Paragraph 4: Gap and study rationale\n"
        "Existing studies still show heterogeneity in phenotype definition, covariate harmonization, and external validity across datasets. "
        "A unified, reproducible framework combining consistent cohort definitions, sensitivity analyses, and transparent reporting is therefore needed.\n"
    )


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    Entrez.email = args.email
    cr = Crossref()

    h = Entrez.esearch(db="pubmed", term=args.query, retmax=args.retmax, sort="relevance")
    sr = Entrez.read(h)
    ids = sr.get("IdList", [])
    if not ids:
        print("No results found.")
        return

    f = Entrez.efetch(db="pubmed", id=",".join(ids), rettype="medline", retmode="xml")
    data = Entrez.read(f)

    refs: list[RefRow] = []
    seen: set[str] = set()

    for a in data.get("PubmedArticle", []):
        pmid = extract_pmid(a)
        if not pmid or pmid in seen:
            continue
        seen.add(pmid)

        title = extract_title(a)
        doi = extract_doi(a) or backfill_doi(cr, title)

        refs.append(
            RefRow(
                pmid=pmid,
                doi=doi,
                year=extract_year(a),
                title=title,
                journal=extract_journal(a),
                authors=extract_authors(a),
                abstract=extract_abstract(a),
            )
        )

    grouped: dict[str, list[RefRow]] = defaultdict(list)
    for r in refs:
        grouped[classify_topic(r.title, r.abstract)].append(r)

    # master table
    csv_path = outdir / "pubmed_references_advanced.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fcsv:
        w = csv.DictWriter(
            fcsv,
            fieldnames=[
                "pmid", "doi", "year", "journal", "title", "authors", "topic",
                "is_recent5y", "is_high_impact", "pubmed_url", "doi_url",
            ],
        )
        w.writeheader()
        for r in refs:
            topic = classify_topic(r.title, r.abstract)
            w.writerow(
                {
                    "pmid": r.pmid,
                    "doi": r.doi,
                    "year": r.year or "",
                    "journal": r.journal,
                    "title": r.title,
                    "authors": r.authors,
                    "topic": topic,
                    "is_recent5y": int(r.is_recent5y),
                    "is_high_impact": int(r.is_high_impact),
                    "pubmed_url": r.pubmed_url,
                    "doi_url": r.doi_url,
                }
            )

    # filtered tables
    recent = [r for r in refs if r.is_recent5y]
    high_impact = [r for r in refs if r.is_high_impact]

    def dump_simple(path: Path, rows: list[RefRow]) -> None:
        with path.open("w", newline="", encoding="utf-8") as fcsv:
            w = csv.writer(fcsv)
            w.writerow(["pmid", "doi", "year", "journal", "title", "authors", "pubmed_url", "doi_url"])
            for r in rows:
                w.writerow([r.pmid, r.doi, r.year or "", r.journal, r.title, r.authors, r.pubmed_url, r.doi_url])

    dump_simple(outdir / "pubmed_recent5y.csv", recent)
    dump_simple(outdir / "pubmed_high_impact.csv", high_impact)

    # grouped json
    grouped_json = {
        topic: [
            {
                "pmid": r.pmid,
                "doi": r.doi,
                "year": r.year,
                "journal": r.journal,
                "title": r.title,
                "authors": r.authors,
                "pubmed_url": r.pubmed_url,
                "doi_url": r.doi_url,
            }
            for r in sorted(rows, key=lambda x: (x.year or 0), reverse=True)
        ]
        for topic, rows in grouped.items()
    }
    (outdir / "pubmed_grouped.json").write_text(json.dumps(grouped_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # intro draft
    intro = build_intro_draft(args.project_name, refs, grouped)
    intro_path = outdir / "intro_lit_review_draft.md"
    intro_path.write_text(intro, encoding="utf-8")

    print(f"Saved {len(refs)} references")
    print(f"Master: {csv_path}")
    print(f"Recent5y: {outdir / 'pubmed_recent5y.csv'}")
    print(f"HighImpact: {outdir / 'pubmed_high_impact.csv'}")
    print(f"Grouped: {outdir / 'pubmed_grouped.json'}")
    print(f"IntroDraft: {intro_path}")


if __name__ == "__main__":
    main()
