#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import pandas as pd

from lib.rendering import render_docx_to_pngs

ROOT = Path("/Users/apple/Documents/lancet-research-platform")
PY = "/Users/apple/Documents/.venvs/data-analytics/bin/python"
AGGREGATE_LABEL = "East Asia study-scope aggregate"
MEASURE_ORDER = ["Incidence", "Prevalence", "Deaths", "DALYs"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build phase-four manuscript sections and submission-style draft for the East Asia female under-40 asthma study."
    )
    parser.add_argument("--study-root", required=True)
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def load_context(study_root: Path) -> dict[str, object]:
    manuscript_root = study_root / "outputs" / "manuscript"
    tables_root = study_root / "outputs" / "tables"
    study_config = json.loads((study_root / "study_config.json").read_text(encoding="utf-8"))
    table1 = pd.read_csv(tables_root / "asthma_east_asia_female_u40_table_1_2023_burden_and_rates.csv")
    table2 = pd.read_csv(tables_root / "asthma_east_asia_female_u40_table_2_pooled_rate_eapc.csv")
    table3 = pd.read_csv(tables_root / "asthma_east_asia_female_u40_table_3_peak_age_patterns_2023.csv")
    table4 = pd.read_csv(tables_root / "asthma_east_asia_female_u40_table_4_risk_attribution_2023.csv")
    phase3_qc = json.loads((tables_root / "asthma_east_asia_female_u40_phase3_qc.json").read_text(encoding="utf-8"))
    results_draft = (manuscript_root / "results_draft.md").read_text(encoding="utf-8")
    figure_legends = (manuscript_root / "figure_legends.md").read_text(encoding="utf-8")
    return {
        "study_config": study_config,
        "table1": table1,
        "table2": table2,
        "table3": table3,
        "table4": table4,
        "phase3_qc": phase3_qc,
        "results_draft": results_draft,
        "figure_legends": figure_legends,
    }


def fmt_count(value: float) -> str:
    return f"{value:,.1f}"


def fmt_rate(value: float) -> str:
    return f"{value:,.1f}"


def fmt_pct(value: float) -> str:
    return f"{value:.2f}%"


def build_metrics(ctx: dict[str, object]) -> dict[str, object]:
    table1: pd.DataFrame = ctx["table1"]  # type: ignore[assignment]
    table2: pd.DataFrame = ctx["table2"]  # type: ignore[assignment]
    table3: pd.DataFrame = ctx["table3"]  # type: ignore[assignment]
    table4: pd.DataFrame = ctx["table4"]  # type: ignore[assignment]

    aggregate = table1.loc[table1["location_name"] == AGGREGATE_LABEL].copy()
    aggregate_lookup = aggregate.set_index("measure_short").to_dict("index")
    top_locations = (
        table1.loc[table1["location_type"] == "constituent_location"]
        .sort_values(["measure_short", "count_2023"], ascending=[True, False])
        .groupby("measure_short", as_index=False)
        .first()
        .set_index("measure_short")
        .to_dict("index")
    )
    eapc_lookup = table2.set_index(["measure_short", "location_name"]).to_dict("index")
    steepest_declines = (
        table2.loc[table2["location_type"] == "constituent_location"]
        .sort_values(["measure_short", "eapc"], ascending=[True, True])
        .groupby("measure_short", as_index=False)
        .first()
        .set_index("measure_short")
        .to_dict("index")
    )
    positive_exceptions = table2.loc[
        (table2["location_type"] == "constituent_location") & (table2["eapc"] > 0)
    ].copy()
    peak_cells = table3.sort_values("rate_2023", ascending=False).reset_index(drop=True)
    top_risks = (
        table4.sort_values(["measure_short", "share_of_total_pct"], ascending=[True, False])
        .groupby("measure_short", as_index=False)
        .first()
        .set_index("measure_short")
        .to_dict("index")
    )
    return {
        "aggregate": aggregate_lookup,
        "top_locations": top_locations,
        "eapc_lookup": eapc_lookup,
        "steepest_declines": steepest_declines,
        "positive_exceptions": positive_exceptions,
        "peak_cells": peak_cells,
        "top_risks": top_risks,
    }


def build_summary(metrics: dict[str, object], study_config: dict[str, object]) -> str:
    agg = metrics["aggregate"]
    top = metrics["top_locations"]
    risks = metrics["top_risks"]
    eapc = metrics["eapc_lookup"]
    return dedent(
        f"""
        # Summary

        ## Background

        Asthma remains an important chronic respiratory condition across childhood, adolescence, and young adulthood, yet disease burden assessments often prioritise all-age populations or broader adult strata. We aimed to quantify the burden of asthma among females younger than 40 years in East Asia from 1990 to 2023 and to describe the leading attributable risk factors for deaths and DALYs within this restricted population.

        ## Methods

        We conducted a descriptive health-estimates study using study-specific custom exports from the official GBD 2023 Results tool for six East Asian locations: China, Japan, Mongolia, Democratic People's Republic of Korea, Republic of Korea, and Taiwan. The analytic population was restricted to females in eight age groups from younger than 5 years to 35-39 years. Primary outcomes were incidence, prevalence, deaths, and DALYs. Age-specific counts and rates were retained as the main endpoints. For descriptive under-40 summaries, counts were summed across the eight age groups. For trend analyses, pooled crude rates were reconstructed from matched GBD counts and rates to recover age-specific denominators, after which under-40 rates and estimated annual percentage changes (EAPCs) were derived. Attributable risk analyses were done separately for deaths and DALYs with all asthma-related risks returned by the official GBD Results interface. Uncertainty intervals were retained throughout.

        ## Findings

        Across the six included East Asian locations in 2023, females younger than 40 years experienced an estimated {fmt_count(agg['Incidence']['count_2023'])} incident asthma cases, {fmt_count(agg['Prevalence']['count_2023'])} prevalent cases, {fmt_count(agg['Deaths']['count_2023'])} deaths, and {fmt_count(agg['DALYs']['count_2023'])} DALYs. China had the largest absolute burden for all four outcomes. At the study-scope aggregate level, pooled crude rates declined from 1990 to 2023 for incidence, prevalence, deaths, and DALYs, with EAPCs of {fmt_pct(eapc[('Incidence', AGGREGATE_LABEL)]['eapc'])}, {fmt_pct(eapc[('Prevalence', AGGREGATE_LABEL)]['eapc'])}, {fmt_pct(eapc[('Deaths', AGGREGATE_LABEL)]['eapc'])}, and {fmt_pct(eapc[('DALYs', AGGREGATE_LABEL)]['eapc'])}, respectively. The leading attributable risk factor in 2023 was occupational asthmagens for deaths ({fmt_count(risks['Deaths']['attributable_count_2023'])}; {fmt_pct(risks['Deaths']['share_of_total_pct'])} of total deaths) and high body-mass index for DALYs ({fmt_count(risks['DALYs']['attributable_count_2023'])}; {fmt_pct(risks['DALYs']['share_of_total_pct'])} of total DALYs).

        ## Interpretation

        Asthma burden among females younger than 40 years in East Asia declined overall between 1990 and 2023, but the residual burden remained large in 2023, especially in China. The age profile was heterogeneous, and modifiable risks including high body-mass index, secondhand smoke, and occupational asthmagens accounted for a notable share of the remaining burden. Prevention strategies for younger females in East Asia should therefore combine childhood and adolescent asthma control with household, occupational, and metabolic risk reduction.

        ## Funding

        Funding: [To be completed by authors]. Role of the funding source: [To be completed by authors].
        """
    ).strip()


def build_research_in_context(metrics: dict[str, object]) -> str:
    exceptions = metrics["positive_exceptions"]
    if len(exceptions):
        exception_text = "; ".join(
            f"{row.measure_short} in {row.location_name} (EAPC {fmt_pct(row.eapc)})"
            for row in exceptions.itertuples(index=False)
        )
    else:
        exception_text = "No positive EAPCs were identified in constituent locations."
    return dedent(
        f"""
        # Panel: Research in context

        ## Evidence before this study

        Evidence before this study: [To be completed after the formal literature search and citation screening stage]. The present workspace has not yet integrated a systematic literature review, so this subsection is intentionally preserved as a structured placeholder rather than a fabricated narrative.

        ## Added value of this study

        Added value of this study: this project used study-specific official GBD 2023 Results exports restricted to six East Asian locations, females only, and the under-40 age range. The pipeline preserved stable identifier fields, retained uncertainty intervals, and generated reproducible code outputs linking raw exports to derived tables, figures, and manuscript text. Unlike generic all-age GBD summaries, the analysis focused on age-specific burden among younger females and explicitly reconstructed pooled under-40 crude rates rather than mislabelling them as age-standardised rates. The project also identified trend exceptions that deserve targeted interpretation, including {exception_text}.

        ## Implications of all the available evidence

        Implications of all the available evidence: asthma prevention for younger females in East Asia should not be framed only as a childhood clinical problem. The current results suggest that household smoke exposure, occupational asthmagens, and metabolic risks continue to shape residual burden into adolescence and young adulthood. Once external literature is integrated, the present package should support a defensible discussion about age-tailored respiratory prevention, occupational protection, and long-horizon monitoring of young female populations in East Asia.
        """
    ).strip()


def build_introduction(metrics: dict[str, object]) -> str:
    peak = metrics["peak_cells"].iloc[0]
    return dedent(
        f"""
        # Introduction

        Asthma is a high-frequency chronic respiratory disorder that begins early in life, may persist through adolescence and young adulthood, and can still contribute to avoidable mortality and disability despite the availability of preventive and therapeutic strategies. In East Asia, the epidemiology of asthma is shaped by large population size, rapid social and environmental transitions, heterogeneous household and occupational exposures, and differences in health-system access across countries and territories. These features make the region important for burden assessment, but they also complicate interpretation when analyses are limited to all-age aggregates.

        Females younger than 40 years represent a population segment in which asthma burden has several overlapping dimensions. The study period spans infancy, school age, adolescence, reproductive-age adulthood, and the transition into the late thirties. The clinical and public-health implications of these stages differ, and the same is true for the exposure profile. Household smoke, ambient pollution, obesity-related metabolic risk, and occupational asthmagens are unlikely to matter in identical ways across the entire under-40 range. A narrowly defined age-sex analysis is therefore more informative than a broad regional summary if the goal is to support targeted prevention.

        A second methodological issue is that under-40 studies can easily drift into inappropriate reporting if all-age age-standardised indicators are used without explanation. For that reason, the present analysis prioritised age-specific counts and rates, used explicit age-group rows from the GBD Results tool, and only derived pooled crude under-40 rates when denominators could be reconstructed from matched counts and rates. This strategy was designed to preserve interpretability while still allowing trend summaries through a clearly specified statistical model.

        We therefore aimed to quantify the burden of asthma among females younger than 40 years in East Asia between 1990 and 2023, to compare burden across the six included locations, to characterise the age pattern in 2023, and to identify the leading attributable risk factors for deaths and DALYs. The highest location-age rate cell in the current study was {peak['measure_short']} in {peak['location_name']} among those aged {peak['peak_age_group']}, underscoring the need for age-specific interpretation rather than a single undifferentiated regional estimate.
        """
    ).strip()


def build_methods(metrics: dict[str, object], phase3_qc: dict[str, object], study_config: dict[str, object]) -> str:
    return dedent(
        f"""
        # Methods

        ## Study design

        This was a descriptive health-estimates study based on the Global Burden of Disease Study 2023 (GBD 2023). The design was predefined around a single disease, a fixed geography, a single sex stratum, and a prespecified age range. The primary objective was to describe burden and attributable risk patterns for asthma among females younger than 40 years in East Asia from 1990 to 2023.

        ## Setting, participants, and study size

        The setting was East Asia as operationalised in the official GBD location hierarchy. Participants were not individual persons but analytic population strata defined by location, sex, age group, year, measure, and metric. Inclusion criteria were the six East Asian locations available in the study-specific export specification: China, Japan, Mongolia, Democratic People's Republic of Korea, Republic of Korea, and Taiwan. The target population was restricted to females only and to eight age groups: younger than 5 years, 5-9 years, 10-14 years, 15-19 years, 20-24 years, 25-29 years, 30-34 years, and 35-39 years. The study size was fixed by design rather than by recruitment, producing complete strata across 34 years for each eligible location and outcome.

        Participants flow was defined as analytic stratum flow. Eligible rows were required to satisfy all scope restrictions for location, sex, age, cause, measure, metric, and year. After export, rows were retained only if they preserved the expected under-40 female scope and the uncertainty interval ordering of lower less than or equal to mean less than or equal to upper.

        ## Data inputs, data sources, and variables

        Data inputs came from custom exports generated from the official GBD Results tool. Data sources were the GBD 2023 Results interface and its returned CSV outputs, which were stored locally as study-specific raw files before downstream cleaning. Variables retained in the analysis included location identifiers and names, sex identifiers and names, age identifiers and names, cause identifiers and names, measure identifiers and names, metric identifiers and names, year, mean estimate, lower uncertainty bound, and upper uncertainty bound. For attributable burden analyses, risk factor identifiers and names were also retained.

        The main variables of interest were four outcome data domains: incidence, prevalence, deaths, and DALYs. Attributable burden was evaluated for deaths and DALYs only. Descriptive data included year coverage, age coverage, location coverage, and the presence or absence of duplicated rows after enforcing the intended analytic key. The current phase-three quality-control file confirmed {phase3_qc['pooled_rate_rows']} pooled-rate rows, {phase3_qc['eapc_rows']} EAPC rows, and no nonpositive pooled rates or nonpositive reconstructed population estimates.

        ## Data cleaning, bias control, and reproducible code

        Raw export files were cleaned into study-specific derived datasets inside the local project workspace. Data cleaning steps included column standardisation, age-order harmonisation, location-order harmonisation, row-level duplicate checking, and consistency checks for lower, mean, and upper values. Bias was addressed at the design and reporting stages rather than through sampling corrections within the current script. Specifically, we avoided headline use of all-age age-standardised rates for the under-40 female population, retained uncertainty intervals in downstream outputs, and explicitly labelled reconstructed under-40 rates as pooled crude rates. Reproducible code was implemented in the local Python pipeline, with separate scripts for export, second-stage analysis, phase-three manuscript tables and figures, and the present phase-four writing layer.

        ## Statistical methods and statistical model

        Statistical methods were prespecified in the study analysis plan. Age-specific counts and age-specific rates were treated as the primary manuscript endpoints. For under-40 descriptive counts, the eight age-specific counts were summed within each location, year, and measure. These summed counts were used for cross-sectional 2023 tables and for longitudinal count trend figures.

        When a combined under-40 rate was needed, we did not add age-specific rates directly. Instead, we reconstructed age-specific population denominators from matched GBD counts and rates using the relationship population equals count divided by rate multiplied by 100,000. The reconstructed age-specific denominators were then summed to yield the under-40 denominator for each location, year, and measure, after which pooled crude rates per 100,000 were recalculated. These pooled crude rates were used for temporal trend description and for the estimated annual percentage change analysis.

        The statistical model for estimated annual percentage change was a log-linear regression of the natural logarithm of the pooled crude rate on calendar year. For each measure and location, we fitted ln(rate) equals alpha plus beta times year. EAPC was derived as 100 multiplied by the exponential of beta minus 1, with 95% confidence intervals computed from the standard error of beta. This model was only applied to strictly positive pooled crude rate series.

        Attributable risk analyses were conducted separately for deaths and DALYs. All risk factors returned by the official GBD Results interface under the locked study filters were retained, summarised at the 2023 cross section, and ranked by attributable count and by attributable share of the study-scope total burden. Descriptive data and outcome data were visualised through four manuscript-style figures: count trends, pooled-rate trends, age-specific rate heatmaps, and attributable-risk rankings.

        ## Uncertainty, model evaluation, and limitations built into the analytic design

        Uncertainty was preserved at the export level through the lower and upper bounds returned by GBD Results. For summed under-40 counts and attributable burden tables, the lower and upper values were presented as arithmetic sums across age groups or risk rows and were explicitly labelled as such. Model evaluation in the current project consisted of deterministic quality-control checks rather than external predictive validation. These checks confirmed complete scope coverage across the six locations and 34 calendar years, absence of duplicate rows under the intended keys, successful pooled-rate reconstruction, and positive denominators for all pooled-rate cells. The manuscript-level interpretation also treated attributable burden as a GBD-defined risk attribution framework rather than as direct causal proof.

        ## Ethics approval, informed consent, funding, and role of the funding source

        Ethics approval: the analysis used publicly available aggregated health-estimate outputs from GBD 2023 and did not involve direct contact with human participants. Formal ethics approval should therefore be confirmed according to the institutional policy of the submitting authors. Informed consent was not applicable to this secondary analysis of aggregated, non-identifiable estimates.

        Funding: [To be completed by authors]. Role of the funding source: [To be completed by authors]. These items are intentionally retained as explicit submission fields because the current manuscript package is a writing and analysis scaffold rather than the final journal submission record.
        """
    ).strip()


def results_body(results_draft: str) -> str:
    text = results_draft.strip()
    if text.startswith("# Results Draft"):
        text = text[len("# Results Draft") :].lstrip()
    if "## Methods Note" in text:
        text = text.split("## Methods Note", 1)[0].rstrip()
    return "# Results\n\n" + text


def build_discussion(metrics: dict[str, object]) -> str:
    agg = metrics["aggregate"]
    top_risks = metrics["top_risks"]
    peak = metrics["peak_cells"].iloc[0]
    exceptions = metrics["positive_exceptions"]
    exception_text = "; ".join(
        f"{row.measure_short} in {row.location_name}" for row in exceptions.itertuples(index=False)
    )
    return dedent(
        f"""
        # Discussion

        ## Principal findings

        This study provides a publication-oriented burden profile for asthma among females younger than 40 years in East Asia using official GBD 2023 custom exports and a fixed reproducible pipeline. Three findings stand out. First, the absolute burden in 2023 remained substantial, with an estimated {fmt_count(agg['Incidence']['count_2023'])} incident cases, {fmt_count(agg['Prevalence']['count_2023'])} prevalent cases, {fmt_count(agg['Deaths']['count_2023'])} deaths, and {fmt_count(agg['DALYs']['count_2023'])} DALYs across the six included locations. Second, long-term trends were generally downward, but not uniformly so. Third, the residual attributable burden remained concentrated in modifiable exposures, especially occupational asthmagens, high body-mass index, and secondhand smoke.

        ## Interpretation

        The overall decline in pooled crude rates suggests meaningful progress in asthma control or in the broader determinants of severe asthma burden over the past three decades. Even so, the remaining 2023 burden indicates that gains have not eliminated clinically important morbidity or preventable deaths in younger females. China carried the largest absolute burden for all four outcomes, which is unsurprising given its population size, but the location-specific rate pattern shows that burden intensity cannot be inferred from counts alone. This distinction is one reason the current manuscript separates absolute burden from pooled crude rate trajectories.

        The age profile also matters. The highest location-age rate cell in the current analysis was {peak['measure_short']} in {peak['location_name']} among the {peak['peak_age_group']} group. That pattern reinforces the concern that younger female burden is not confined to a single developmental window. In practice, the under-40 frame spans early childhood, school age, adolescence, and adulthood with potentially different exposure structures, health-care behaviours, and diagnostic pathways. The implication is that asthma prevention in East Asia should be planned across the life course rather than concentrated exclusively in either paediatric or adult services.

        Risk attribution adds a second layer of interpretation. Occupational asthmagens accounted for the largest share of attributable asthma deaths, whereas high body-mass index accounted for the largest share of attributable DALYs. This combination is epidemiologically plausible because it points to both exposure-intensive environments and chronic risk accumulation. Secondhand smoke also ranked prominently for both deaths and DALYs, supporting the continuing importance of household and indoor exposure control for younger females. The attributable-risk profile therefore suggests that respiratory prevention in East Asia should combine smoke-free protections, occupational safeguards, and metabolic risk reduction rather than relying on pharmacological control alone.

        ## Heterogeneity and trend exceptions

        Although the overall regional trajectory was downward, the decline was not universal. Trend exceptions were observed for {exception_text}. These departures from the general direction are important because they may reflect different mixtures of diagnosis, exposure change, population structure, care access, or background surveillance practices. They also highlight why burden interpretation should remain location specific even inside a relatively compact regional frame.

        ## Strengths

        The main strengths of this study are methodological discipline and traceability. We used study-specific official GBD Results exports rather than heterogeneous secondary tables, retained stable identifier fields, preserved uncertainty intervals, and linked each statement in the draft manuscript to a directly reproducible local output. A further strength is that the analysis did not mislabel under-40 pooled rates as age-standardised rates; instead, denominators were reconstructed explicitly from matched counts and rates and the derived metrics were described as pooled crude rates throughout.

        ## Limitations

        Several limitations should be made explicit. First, this study remains dependent on the assumptions and upstream modelling architecture of GBD 2023. Second, the study-scope aggregate used in the pooled-rate tables and figures is a six-location aggregate reconstructed inside the current workspace rather than a separately exported official East Asia regional row. Third, uncertainty for aggregated counts was summarised arithmetically across component rows, which is a transparent descriptive device but not a replacement for full covariance-aware interval propagation. Fourth, the attributable burden framework should not be interpreted as direct causal proof beyond GBD definitions. Fifth, the current manuscript package has not yet been integrated with a formal literature review, so contextual comparison with previous East Asian or global asthma studies remains to be strengthened in the next stage.

        ## Implications

        The practical implication is that policy attention should remain on younger females even when asthma mortality has fallen. Prevention priorities suggested by the present results include better childhood and school-age asthma control, smoke-free household and community environments, occupational protection for young working women, and metabolic health strategies that may indirectly reduce respiratory burden. For manuscript development, the next step is to integrate formal literature review findings and decide whether an official East Asia regional aggregate export is required for the final submission package.

        ## Conclusion

        In summary, asthma burden among females younger than 40 years in East Asia declined overall from 1990 to 2023, but substantial morbidity and a non-negligible mortality burden persisted in 2023. The burden remained heterogeneous across locations and age groups, and a meaningful proportion of deaths and DALYs was attributable to modifiable risks. These findings support a life-course and exposure-aware approach to asthma prevention in younger females across East Asia.
        """
    ).strip()


def build_declarations() -> str:
    return dedent(
        """
        # Declarations

        ## Author contributions

        Author contributions: [To be completed by authors].

        ## Declaration of interests

        Declaration of interests: [To be completed by authors]. Conflicts of interest: [To be completed by authors].

        ## Data sharing statement

        Data sharing statement: study-specific raw exports, derived tables, figures, and reproducible code are stored in the local project workspace. Public sharing should follow the GBD Results and IHME terms applicable to the exported files, together with the journal policy selected for submission.

        ## Ethics approval and informed consent

        Ethics approval: [To be confirmed by authors according to institutional policy]. Informed consent: not applicable because the current study used aggregated, non-identifiable health-estimate outputs.

        ## Funding

        Funding: [To be completed by authors].

        ## Role of the funding source

        Role of the funding source: [To be completed by authors].

        ## Acknowledgments

        [To be completed by authors].
        """
    ).strip()


def build_references_placeholder() -> str:
    return dedent(
        """
        # References

        1. Institute for Health Metrics and Evaluation. Global Burden of Disease Study 2023 Results. Seattle, WA: IHME; accessed March 8, 2026.
        2. [Additional references to be inserted after the formal literature review stage].
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
    references: str,
) -> str:
    title_en = study_config["title_en"]
    title_zh = study_config["title_zh"]
    return "\n\n".join(
        [
            f"# {title_en}",
            f"Chinese title: {title_zh}",
            "",
            "Authors: [To be completed by authors]",
            "Affiliations: [To be completed by authors]",
            "Correspondence: [To be completed by authors]",
            "Word count: [Auto-fill before submission]",
            "Tables: 4 main tables",
            "Figures: 4 main figures",
            summary,
            research_in_context,
            introduction,
            methods,
            results,
            discussion,
            declarations,
            figure_legends,
            references,
        ]
    ).strip() + "\n"


def run_pandoc(markdown_path: Path, out_path: Path) -> dict[str, object]:
    cmd = ["pandoc", str(markdown_path), "-o", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "ok": proc.returncode == 0,
        "command": cmd,
        "stderr": proc.stderr.strip(),
    }


def run_audit(markdown_path: Path, out_path: Path) -> dict[str, object]:
    cmd = [
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
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "ok": proc.returncode == 0,
        "command": cmd,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def write_manifest(manifest_path: Path, payload: dict[str, object]) -> None:
    ensure_dir(manifest_path.parent)
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    study_root = Path(args.study_root)
    manuscript_root = study_root / "outputs" / "manuscript"
    sections_root = manuscript_root / "sections"
    ensure_dir(manuscript_root)
    ensure_dir(sections_root)

    ctx = load_context(study_root)
    study_config = ctx["study_config"]
    metrics = build_metrics(ctx)
    summary = build_summary(metrics, study_config)
    research_in_context = build_research_in_context(metrics)
    introduction = build_introduction(metrics)
    methods = build_methods(metrics, ctx["phase3_qc"], study_config)
    results = results_body(ctx["results_draft"])
    discussion = build_discussion(metrics)
    declarations = build_declarations()
    references = build_references_placeholder()
    figure_legends = ctx["figure_legends"]

    save_text(sections_root / "01_summary.md", summary)
    save_text(sections_root / "02_research_in_context.md", research_in_context)
    save_text(sections_root / "03_introduction.md", introduction)
    save_text(sections_root / "04_methods.md", methods)
    save_text(sections_root / "05_results.md", results)
    save_text(sections_root / "06_discussion.md", discussion)
    save_text(sections_root / "07_declarations.md", declarations)
    save_text(sections_root / "08_figure_legends.md", figure_legends)
    save_text(sections_root / "09_references.md", references)

    manuscript_md = manuscript_root / "submission_manuscript.md"
    manuscript_text = build_manuscript(
        study_config,
        summary,
        research_in_context,
        introduction,
        methods,
        results,
        discussion,
        declarations,
        figure_legends,
        references,
    )
    save_text(manuscript_md, manuscript_text)

    docx_result = run_pandoc(manuscript_md, manuscript_root / "submission_manuscript.docx")
    html_result = run_pandoc(manuscript_md, manuscript_root / "submission_manuscript.html")
    audit_result = run_audit(manuscript_md, manuscript_root / "submission_manuscript_audit.md")
    render_result: dict[str, object] | None = None
    if docx_result["ok"]:
        render_result = render_docx_to_pngs(
            manuscript_root / "submission_manuscript.docx",
            manuscript_root / "rendered_pages",
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study_root": str(study_root),
        "manuscript_markdown": str(manuscript_md),
        "docx_result": docx_result,
        "html_result": html_result,
        "audit_result": audit_result,
        "render_result": render_result,
        "sections": sorted(str(path) for path in sections_root.glob("*.md")),
    }
    write_manifest(manuscript_root / "submission_manifest.json", manifest)

    print(f"Wrote manuscript sections to {sections_root}")
    print(f"Wrote submission manuscript to {manuscript_md}")
    print(f"DOCX export ok: {docx_result['ok']}")
    print(f"HTML export ok: {html_result['ok']}")
    print(f"Audit ok: {audit_result['ok']}")
    if render_result is not None:
        print(f"Rendered page QA ok: {render_result['ok']}")


if __name__ == "__main__":
    main()
