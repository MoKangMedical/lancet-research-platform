#!/usr/bin/env python3
"""Search PubMed and export real references (PMID/DOI).

Usage:
  source /Users/apple/Documents/.venvs/data-analytics/bin/activate
  python /Users/apple/Documents/lancet-research-platform/analysis/python/20_pubmed_real_refs.py \
    --query "(NHANES) AND (mortality)" --retmax 30 --outdir /Users/apple/Documents/lancet-research-platform/outputs/references
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from Bio import Entrez
from habanero import Crossref

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--query", required=True, help="PubMed query string")
    p.add_argument("--retmax", type=int, default=50)
    p.add_argument("--email", default="research-bot@example.com")
    p.add_argument("--outdir", default="/Users/apple/Documents/lancet-research-platform/outputs/references")
    return p.parse_args()


def extract_year(article: dict[str, Any]) -> str:
    try:
        d = article["MedlineCitation"]["Article"]["Journal"]["JournalIssue"]["PubDate"]
        if "Year" in d:
            return str(d["Year"])
        if "MedlineDate" in d:
            return str(d["MedlineDate"]).split(" ")[0]
    except Exception:
        pass
    return ""


def extract_doi(article: dict[str, Any]) -> str:
    doi = ""
    try:
        ids = article["MedlineCitation"]["Article"].get("ELocationID", [])
        if not isinstance(ids, list):
            ids = [ids]
        for item in ids:
            if getattr(item, "attributes", {}).get("EIdType") == "doi":
                doi = str(item)
                break
    except Exception:
        pass
    if doi:
        return doi

    try:
        for item in article.get("PubmedData", {}).get("ArticleIdList", []):
            if getattr(item, "attributes", {}).get("IdType") == "doi":
                return str(item)
    except Exception:
        pass
    return ""


def normalize_authors(article: dict[str, Any]) -> str:
    names = []
    try:
        al = article["MedlineCitation"]["Article"].get("AuthorList", [])
        for a in al:
            ln = a.get("LastName", "")
            ini = a.get("Initials", "")
            if ln:
                names.append((ln + " " + ini).strip())
    except Exception:
        pass
    return "; ".join(names[:10])


def get_title(article: dict[str, Any]) -> str:
    try:
        t = article["MedlineCitation"]["Article"].get("ArticleTitle", "")
        return str(t).replace("\n", " ").strip()
    except Exception:
        return ""


def get_journal(article: dict[str, Any]) -> str:
    try:
        return str(article["MedlineCitation"]["Article"]["Journal"].get("ISOAbbreviation", ""))
    except Exception:
        return ""


def fetch_crossref_doi_by_title(cr: Crossref, title: str) -> str:
    if not title:
        return ""
    try:
        rs = cr.works(query_title=title, limit=1)
        items = rs.get("message", {}).get("items", [])
        if not items:
            return ""
        candidate = items[0].get("DOI", "")
        if candidate and DOI_RE.search(candidate):
            return candidate
    except Exception:
        return ""
    return ""


def to_bibtex_key(first_author: str, year: str, pmid: str) -> str:
    a = (first_author.split(";")[0].split(" ")[0] if first_author else "ref").lower()
    y = year if year else "nd"
    return f"{a}{y}pmid{pmid}"


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    Entrez.email = args.email

    esearch = Entrez.esearch(db="pubmed", term=args.query, retmax=args.retmax, sort="relevance")
    search_data = Entrez.read(esearch)
    pmids = search_data.get("IdList", [])

    if not pmids:
        print("No PubMed results found.")
        return

    efetch = Entrez.efetch(db="pubmed", id=",".join(pmids), rettype="medline", retmode="xml")
    fetched = Entrez.read(efetch)
    articles = fetched.get("PubmedArticle", [])

    cr = Crossref()
    rows: list[dict[str, str]] = []

    for a in articles:
        pmid = ""
        try:
            pmid = str(a["MedlineCitation"]["PMID"])
        except Exception:
            continue

        title = get_title(a)
        year = extract_year(a)
        journal = get_journal(a)
        authors = normalize_authors(a)
        doi = extract_doi(a)
        if not doi:
            doi = fetch_crossref_doi_by_title(cr, title)

        rows.append(
            {
                "pmid": pmid,
                "doi": doi,
                "year": year,
                "title": title,
                "journal": journal,
                "authors": authors,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "doi_url": f"https://doi.org/{doi}" if doi else "",
            }
        )

    # de-duplicate by PMID
    seen: set[str] = set()
    uniq_rows: list[dict[str, str]] = []
    for r in rows:
        if r["pmid"] in seen:
            continue
        seen.add(r["pmid"])
        uniq_rows.append(r)

    csv_path = outdir / "pubmed_references.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["pmid", "doi", "year", "title", "journal", "authors", "pubmed_url", "doi_url"],
        )
        w.writeheader()
        w.writerows(uniq_rows)

    json_path = outdir / "pubmed_references.json"
    json_path.write_text(json.dumps(uniq_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    bib_path = outdir / "pubmed_references.bib"
    with bib_path.open("w", encoding="utf-8") as f:
        for r in uniq_rows:
            key = to_bibtex_key(r["authors"], r["year"], r["pmid"])
            f.write(f"@article{{{key},\n")
            f.write(f"  title = {{{r['title']}}},\n")
            if r["authors"]:
                f.write("  author = {" + r["authors"].replace("; ", " and ") + "},\n")
            if r["journal"]:
                f.write(f"  journal = {{{r['journal']}}},\n")
            if r["year"]:
                f.write(f"  year = {{{r['year']}}},\n")
            f.write(f"  pmid = {{{r['pmid']}}},\n")
            if r["doi"]:
                f.write(f"  doi = {{{r['doi']}}},\n")
            f.write("}\n\n")

    print(f"Saved {len(uniq_rows)} real references")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"BIB: {bib_path}")


if __name__ == "__main__":
    main()
