#!/usr/bin/env python3
"""Build Lancet-style numbered references and intro draft.

Input:
  pubmed_references_advanced.csv (from 21_pubmed_lit_review_pipeline.py)
Output:
  lancet_intro_numbered.md
  lancet_references_numbered.md
  lancet_citations_map.csv
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Ref:
    pmid: str
    doi: str
    year: int | None
    journal: str
    title: str
    authors: str
    topic: str
    is_recent5y: bool
    is_high_impact: bool
    pubmed_url: str
    doi_url: str


def parse_bool(v: str) -> bool:
    return str(v).strip() in {"1", "true", "True", "YES", "yes"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--in_csv",
        default="/Users/apple/Documents/lancet-research-platform/outputs/references/pubmed_references_advanced.csv",
    )
    p.add_argument(
        "--outdir",
        default="/Users/apple/Documents/lancet-research-platform/outputs/references",
    )
    p.add_argument("--project_name", default="Unnamed Study")
    p.add_argument("--max_refs", type=int, default=30)
    return p.parse_args()


def load_refs(path: Path) -> list[Ref]:
    refs: list[Ref] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            year = int(r["year"]) if r.get("year") and str(r["year"]).isdigit() else None
            refs.append(
                Ref(
                    pmid=r.get("pmid", ""),
                    doi=r.get("doi", ""),
                    year=year,
                    journal=r.get("journal", ""),
                    title=r.get("title", ""),
                    authors=r.get("authors", ""),
                    topic=r.get("topic", "other"),
                    is_recent5y=parse_bool(r.get("is_recent5y", "0")),
                    is_high_impact=parse_bool(r.get("is_high_impact", "0")),
                    pubmed_url=r.get("pubmed_url", ""),
                    doi_url=r.get("doi_url", ""),
                )
            )
    return refs


def first_author(authors: str) -> str:
    if not authors:
        return "Unknown"
    return authors.split(";")[0].strip()


def priority_sort_key(r: Ref) -> tuple:
    return (
        0 if r.is_high_impact else 1,
        0 if r.is_recent5y else 1,
        -(r.year or 0),
        r.pmid,
    )


def take_topic(refs: list[Ref], topic: str, k: int) -> list[Ref]:
    pool = [r for r in refs if r.topic == topic]
    pool.sort(key=priority_sort_key)
    return pool[:k]


def format_ref_line(i: int, r: Ref) -> str:
    y = str(r.year) if r.year else "n.d."
    doi = f" doi:{r.doi}." if r.doi else ""
    return f"{i}. {r.authors}. {r.title} {r.journal}. {y}.{doi} PMID:{r.pmid}."


def build_intro(project_name: str, cite_id: dict[str, int], topic_sets: dict[str, list[Ref]], refs: list[Ref]) -> str:
    n_total = len(refs)
    n_recent = sum(1 for r in refs if r.is_recent5y)
    n_hi = sum(1 for r in refs if r.is_high_impact)

    def cite_marks(rs: list[Ref]) -> str:
        ids = [cite_id[r.pmid] for r in rs if r.pmid in cite_id]
        ids = sorted(set(ids))
        return "[" + ",".join(str(i) for i in ids) + "]" if ids else ""

    def fallback(topic: str, k: int) -> list[Ref]:
        rs = topic_sets.get(topic, [])
        if rs:
            return rs[:k]
        return refs[:k]

    p1 = fallback("outcomes_mortality", 3) + fallback("exposure_risk", 1)
    p2 = fallback("exposure_risk", 4)
    p3 = fallback("methods_causal", 4)
    p4 = fallback("dataset_or_validation", 4) + fallback("population_aging", 2)

    return (
        f"# Introduction Draft ({project_name})\n\n"
        f"A PubMed-based evidence scan identified {n_total} eligible studies, including {n_recent} published within the recent 5-year window and {n_hi} in high-impact journals. "
        f"\n\n"
        f"Prior epidemiologic evidence consistently links cardiometabolic and clinical risk profiles to all-cause and cardiovascular mortality across diverse adult populations {cite_marks(p1)}. "
        f"However, effect heterogeneity remains substantial across case definitions, baseline risk strata, and model specifications.\n\n"
        f"Recent studies have expanded exposure metrics and risk stratification approaches, yet between-study comparability remains limited by differences in covariate harmonization and endpoint definition {cite_marks(p2)}. "
        f"This heterogeneity constrains direct translation into unified prevention and risk-prediction strategies.\n\n"
        f"Methodological advances in causal inference and modern survival frameworks improve internal validity, but residual confounding, selection bias, and transportability continue to threaten causal interpretation in observational datasets {cite_marks(p3)}. "
        f"Therefore, robust sensitivity analyses and transparent diagnostics are essential.\n\n"
        f"A reproducible multi-dataset framework integrating standardized cohort construction, prespecified analyses, and harmonized reporting can address current evidence gaps and improve generalizability {cite_marks(p4)}. "
        f"The present study is designed to provide this unified analytic and reporting pipeline.\n"
    )


def main() -> None:
    args = parse_args()
    in_csv = Path(args.in_csv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    refs = load_refs(in_csv)
    refs.sort(key=priority_sort_key)

    # Build citation core set by topic quotas, then fill to max_refs.
    quotas = {
        "outcomes_mortality": 8,
        "exposure_risk": 8,
        "methods_causal": 6,
        "dataset_or_validation": 5,
        "population_aging": 3,
    }

    selected: list[Ref] = []
    seen: set[str] = set()
    for topic, q in quotas.items():
        for r in take_topic(refs, topic, q):
            if r.pmid in seen:
                continue
            selected.append(r)
            seen.add(r.pmid)

    for r in refs:
        if len(selected) >= args.max_refs:
            break
        if r.pmid in seen:
            continue
        selected.append(r)
        seen.add(r.pmid)

    selected = selected[: args.max_refs]

    # Number references.
    cite_id = {r.pmid: i + 1 for i, r in enumerate(selected)}

    # Topic subsets over selected refs for paragraph citations.
    topic_sets: dict[str, list[Ref]] = {}
    for t in quotas:
        topic_sets[t] = [r for r in selected if r.topic == t]

    intro = build_intro(args.project_name, cite_id, topic_sets, selected)

    intro_path = outdir / "lancet_intro_numbered.md"
    refs_path = outdir / "lancet_references_numbered.md"
    map_path = outdir / "lancet_citations_map.csv"

    intro_path.write_text(intro, encoding="utf-8")

    with refs_path.open("w", encoding="utf-8") as f:
        f.write("# References (Numbered)\n\n")
        for i, r in enumerate(selected, start=1):
            f.write(format_ref_line(i, r) + "\n")

    with map_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ref_no", "pmid", "doi", "year", "journal", "first_author", "title", "pubmed_url", "doi_url", "topic"])
        for i, r in enumerate(selected, start=1):
            w.writerow([i, r.pmid, r.doi, r.year or "", r.journal, first_author(r.authors), r.title, r.pubmed_url, r.doi_url, r.topic])

    print(f"Wrote intro: {intro_path}")
    print(f"Wrote refs: {refs_path}")
    print(f"Wrote map: {map_path}")
    print(f"Total numbered refs: {len(selected)}")


if __name__ == "__main__":
    main()
