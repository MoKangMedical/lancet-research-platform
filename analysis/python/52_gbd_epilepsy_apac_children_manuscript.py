#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from textwrap import dedent

import pandas as pd

AGGREGATE_LABEL = "Asia-Pacific aggregate"
MEASURE_ORDER = ["Incidence", "Deaths", "DALYs"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build proposal and Lancet-style manuscript drafts for the Asia-Pacific children idiopathic epilepsy GBD 2023 study."
    )
    parser.add_argument("--study-root", required=True)
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def fmt_count(value: float) -> str:
    return f"{value:,.1f}"


def fmt_rate(value: float) -> str:
    return f"{value:,.2f}"


def fmt_pct(value: float) -> str:
    return f"{value:.2f}%"


def parse_ui_count(value: str) -> float:
    leading = re.sub(",", "", value.split(" ", 1)[0])
    return float(leading)


def load_context(study_root: Path) -> dict[str, object]:
    tables_root = study_root / "outputs" / "tables"
    manuscript_root = study_root / "outputs" / "manuscript"
    return {
        "study_config": json.loads((study_root / "study_config.json").read_text(encoding="utf-8")),
        "table1": pd.read_csv(tables_root / "epilepsy_apac_children_table_1_2023_summary.csv"),
        "table2": pd.read_csv(tables_root / "epilepsy_apac_children_table_2_trend_eapc.csv"),
        "table3": pd.read_csv(tables_root / "epilepsy_apac_children_table_3_age_sex_2023.csv"),
        "table4": pd.read_csv(tables_root / "epilepsy_apac_children_table_4_country_ranking_2023.csv"),
        "qc": json.loads((tables_root / "epilepsy_apac_children_qc.json").read_text(encoding="utf-8")),
        "key_metrics": json.loads((tables_root / "epilepsy_apac_children_key_metrics.json").read_text(encoding="utf-8")),
        "results_draft": (manuscript_root / "results_draft.md").read_text(encoding="utf-8"),
        "figure_legends": (manuscript_root / "figure_legends.md").read_text(encoding="utf-8"),
    }


def build_metrics(ctx: dict[str, object]) -> dict[str, object]:
    table1: pd.DataFrame = ctx["table1"]  # type: ignore[assignment]
    table2: pd.DataFrame = ctx["table2"]  # type: ignore[assignment]
    table3: pd.DataFrame = ctx["table3"]  # type: ignore[assignment]
    table4: pd.DataFrame = ctx["table4"]  # type: ignore[assignment]

    table1_lookup = table1.set_index("location_name").to_dict("index")
    aggregate = table1_lookup[AGGREGATE_LABEL]

    aggregate_counts = {
        "Incidence": parse_ui_count(aggregate["incidence_count_2023_ui"]),
        "Deaths": parse_ui_count(aggregate["deaths_count_2023_ui"]),
        "DALYs": parse_ui_count(aggregate["dalys_count_2023_ui"]),
    }

    subregions = table1.loc[table1["location_name"] != AGGREGATE_LABEL].copy()
    subregions = subregions.assign(
        incidence_count_num=lambda df: df["incidence_count_2023_ui"].map(parse_ui_count),
        deaths_count_num=lambda df: df["deaths_count_2023_ui"].map(parse_ui_count),
        dalys_count_num=lambda df: df["dalys_count_2023_ui"].map(parse_ui_count),
        incidence_share_pct=lambda df: df["incidence_count_2023_ui"].map(parse_ui_count) / aggregate_counts["Incidence"] * 100.0,
        deaths_share_pct=lambda df: df["deaths_count_2023_ui"].map(parse_ui_count) / aggregate_counts["Deaths"] * 100.0,
        dalys_share_pct=lambda df: df["dalys_count_2023_ui"].map(parse_ui_count) / aggregate_counts["DALYs"] * 100.0,
    )

    table2_agg = table2.loc[table2["location_name"] == AGGREGATE_LABEL].set_index("measure_short").to_dict("index")
    table2_sub = table2.loc[table2["location_name"] != AGGREGATE_LABEL].copy()

    incidence_increase = table2_sub.loc[table2_sub["measure_short"] == "Incidence"].sort_values("eapc", ascending=False)
    deaths_decline = table2_sub.loc[table2_sub["measure_short"] == "Deaths"].sort_values("eapc", ascending=True)
    dalys_decline = table2_sub.loc[table2_sub["measure_short"] == "DALYs"].sort_values("eapc", ascending=True)

    age_both = table3.loc[table3["sex_name"] == "Both"].copy()
    age_both = age_both.assign(
        aggregate_total=lambda df: df["measure_short"].map(aggregate_counts),
        share_pct=lambda df: df["count"] / df["aggregate_total"] * 100.0,
    )
    under5 = age_both.loc[age_both["age_name"] == "<5 years"].set_index("measure_short").to_dict("index")

    under5_male_deaths = table3.loc[
        (table3["measure_short"] == "Deaths") & (table3["sex_name"] == "Male") & (table3["age_name"] == "<5 years"), "rate"
    ].iloc[0]
    under5_female_deaths = table3.loc[
        (table3["measure_short"] == "Deaths") & (table3["sex_name"] == "Female") & (table3["age_name"] == "<5 years"), "rate"
    ].iloc[0]
    under5_male_dalys = table3.loc[
        (table3["measure_short"] == "DALYs") & (table3["sex_name"] == "Male") & (table3["age_name"] == "<5 years"), "rate"
    ].iloc[0]
    under5_female_dalys = table3.loc[
        (table3["measure_short"] == "DALYs") & (table3["sex_name"] == "Female") & (table3["age_name"] == "<5 years"), "rate"
    ].iloc[0]

    top_abs_dalys = table4.sort_values("dalys_count", ascending=False).iloc[0].to_dict()
    top_abs_deaths = table4.sort_values("deaths_count", ascending=False).iloc[0].to_dict()
    top_abs_incidence = table4.sort_values("incidence_count", ascending=False).iloc[0].to_dict()
    top_rate_dalys = table4.sort_values("dalys_rate", ascending=False).iloc[0].to_dict()
    top_rate_deaths = table4.sort_values("deaths_rate", ascending=False).iloc[0].to_dict()
    top_rate_incidence = table4.sort_values("incidence_rate", ascending=False).iloc[0].to_dict()

    return {
        "aggregate": aggregate,
        "aggregate_counts": aggregate_counts,
        "subregions": subregions,
        "aggregate_eapc": table2_agg,
        "incidence_increase": incidence_increase,
        "deaths_decline": deaths_decline,
        "dalys_decline": dalys_decline,
        "under5": under5,
        "under5_female_vs_male_death_ratio": under5_female_deaths / under5_male_deaths,
        "under5_female_vs_male_daly_ratio": under5_female_dalys / under5_male_dalys,
        "top_abs_dalys": top_abs_dalys,
        "top_abs_deaths": top_abs_deaths,
        "top_abs_incidence": top_abs_incidence,
        "top_rate_dalys": top_rate_dalys,
        "top_rate_deaths": top_rate_deaths,
        "top_rate_incidence": top_rate_incidence,
    }


def build_proposal_zh(ctx: dict[str, object], metrics: dict[str, object]) -> str:
    agg = metrics["aggregate"]  # type: ignore[assignment]
    under5 = metrics["under5"]  # type: ignore[assignment]
    south_asia = metrics["subregions"].loc[metrics["subregions"]["location_name"] == "South Asia"].iloc[0]  # type: ignore[index]
    top_abs_dalys = metrics["top_abs_dalys"]  # type: ignore[assignment]
    top_rate_dalys = metrics["top_rate_dalys"]  # type: ignore[assignment]

    return dedent(
        f"""
        # 研究方案

        ## 一、课题名称

        1990至2023年亚太地区儿童特发性癫痫发病、死亡和DALY负担及变化趋势：基于GBD 2023的研究

        ## 二、研究背景

        癫痫是儿童神经系统常见慢性疾病之一，既可导致长期复发性发作，也会带来认知、教育、家庭照护和社会参与方面的持续负担。与基于单中心病例资料的临床研究不同，疾病负担研究能够从区域与国家层面刻画发病、死亡和伤残调整寿命年（DALY）的长期变化趋势，为卫生政策、资源配置和儿童神经专科服务规划提供依据。

        亚太地区人口规模大、经济社会发展差异显著、卫生资源分布不均衡，儿童癫痫的识别、治疗和死亡结局可能存在明显异质性。现有研究往往集中于单一国家、单中心临床队列或全人群分析，缺乏面向亚太儿童人群、同时覆盖发病、死亡和DALY三类核心指标的统一负担评估。GBD 2023 为这一问题提供了可重复的官方估计框架。

        本项目基于官方 GBD Results 工具自定义导出，严格限定研究对象为 0-14 岁儿童，聚焦 GBD 官方病因“Idiopathic epilepsy”，并按照亚太地区六个官方子区域进行分析。初步结果显示，2023 年亚太儿童特发性癫痫估计发生 {agg['incidence_count_2023_ui']} 新发病例，死亡 {agg['deaths_count_2023_ui']} 例，造成 {agg['dalys_count_2023_ui']} DALYs；其中南亚占亚太总 DALYs 的 {fmt_pct(float(south_asia['dalys_share_pct']))}，提示区域不均衡十分突出。

        ## 三、研究目的

        1. 描述 1990-2023 年亚太地区 0-14 岁儿童特发性癫痫的发病、死亡和 DALY 负担水平。
        2. 比较 East Asia、South Asia、Southeast Asia、High-income Asia Pacific、Australasia 和 Oceania 六个子区域的疾病负担差异。
        3. 分析不同年龄组和性别的负担异质性，识别高负担年龄-性别组合。
        4. 比较各国家和地区在 2023 年的绝对负担和相对负担，识别高 DALY 率或高死亡率国家。
        5. 通过 EAPC 评估 1990-2023 年疾病负担变化趋势，为区域卫生政策提供依据。

        ## 四、研究设计

        本研究为基于二手数据的描述性疾病负担研究。数据来源于 Global Burden of Disease Study 2023（GBD 2023）官方 Results 工具的定制化导出结果。研究不涉及个体患者招募、随访或干预，不属于临床试验，也不进行个体层面的预后或危险因素推断。

        ## 五、研究对象与范围

        1. 研究地区：亚太地区，操作性定义为 East Asia、South Asia、Southeast Asia、High-income Asia Pacific、Australasia 和 Oceania 六个 GBD 官方子区域，共纳入 45 个国家和地区。
        2. 研究人群：0-14 岁儿童，包括 `<5 years`、`5-9 years` 和 `10-14 years` 三个年龄组。
        3. 性别分层：Both sexes、Male、Female。
        4. 研究病因：GBD 官方病因条目 `Idiopathic epilepsy`。
        5. 研究时间：1990-2023 年。

        ## 六、主要研究指标

        1. 发病人数与发病率（Incidence, Number/Rate）。
        2. 死亡人数与死亡率（Deaths, Number/Rate）。
        3. DALY 数与 DALY 率（DALYs, Number/Rate）。
        4. 年龄别、性别别和地区别分层结果。
        5. 1990-2023 年变化幅度与估计年均变化百分比（EAPC）。

        ## 七、统计学方法

        1. 保留 GBD 官方导出的年龄别人数和率作为主要分析终点。
        2. 对同一地区、同一年、同一性别下三个年龄组的病例数进行求和，以形成儿童总体计数指标。
        3. 不直接相加年龄别率，而是利用 `population = count / rate × 100000` 重建年龄别分母，再计算儿童总体合并粗率。
        4. 使用对数线性模型 `ln(rate) = alpha + beta × year` 估计长期趋势，并计算 `EAPC = 100 × (exp(beta) - 1)`。
        5. 对 2023 年国家层面结果进行排序，重点呈现 DALY 率和死亡率最高的国家与地区。

        ## 八、质量控制

        1. 仅使用官方 GBD Results 导出数据，不再使用任何模拟数据。
        2. 检查重复行、缺失行和不符合 `lower ≤ mean ≤ upper` 的异常行。
        3. 对年龄别数量与率进行一一匹配，重建分母后再进行儿童总体率计算。
        4. 亚太总体通过国家层面数据聚合生成，避免与官方子区域行重复计数。

        ## 九、初步结果依据

        1. 2023 年亚太地区儿童特发性癫痫发病率为 {agg['incidence_rate_2023']} /10万，死亡率为 {agg['deaths_rate_2023']} /10万，DALY 率为 {agg['dalys_rate_2023']} /10万。
        2. 南亚承担了亚太地区 {fmt_pct(float(south_asia['deaths_share_pct']))} 的死亡和 {fmt_pct(float(south_asia['dalys_share_pct']))} 的 DALY 负担，是最主要的高负担子区域。
        3. `<5 years` 儿童是核心高负担年龄层，占亚太儿童总死亡的 {fmt_pct(float(under5['Deaths']['share_pct']))}、总 DALY 的 {fmt_pct(float(under5['DALYs']['share_pct']))}。
        4. 绝对 DALY 负担最高的国家是 {top_abs_dalys['location_name']}，而 DALY 率最高的国家是 {top_rate_dalys['location_name']}。

        ## 十、创新点与研究意义

        1. 研究对象聚焦儿童人群，避免将儿童负担淹没在全人群估计中。
        2. 研究范围覆盖整个亚太六大官方子区域和 45 个国家与地区，具有较强区域比较价值。
        3. 同时呈现发病、死亡和 DALY 三类结局，有助于区分“发现更多病例”和“结局更差”这两类公共卫生现象。
        4. 采用可重复脚本完成数据导出、清洗、分析、作图和撰稿，便于后续修改范围或追加补充分析。

        ## 十一、预期结论

        预计本研究将显示：亚太儿童特发性癫痫在 1990-2023 年间呈现“发病率相对稳定或轻度上升、死亡率和 DALY 率下降”的总体格局，但南亚仍承担主要死亡和伤残负担，且低龄儿童尤其是 `<5 years` 组仍是重点防控对象。这一结果可为儿童神经专科资源配置、早诊早治、基层转诊网络建设以及抗癫痫药物可及性改善提供流行病学依据。
        """
    ).strip()


def build_summary(metrics: dict[str, object]) -> str:
    agg = metrics["aggregate"]  # type: ignore[assignment]
    subregions: pd.DataFrame = metrics["subregions"]  # type: ignore[assignment]
    aggregate_eapc = metrics["aggregate_eapc"]  # type: ignore[assignment]
    top_abs_dalys = metrics["top_abs_dalys"]  # type: ignore[assignment]
    top_rate_dalys = metrics["top_rate_dalys"]  # type: ignore[assignment]
    top_rate_deaths = metrics["top_rate_deaths"]  # type: ignore[assignment]
    south_asia = subregions.loc[subregions["location_name"] == "South Asia"].iloc[0]
    highest_inc_subregion = subregions.sort_values("incidence_rate_2023", ascending=False).iloc[0]

    return dedent(
        f"""
        # Summary

        ## Background

        Idiopathic epilepsy remains an important cause of morbidity, disability, and avoidable mortality in childhood, but Asia-Pacific burden assessments are often reported either for all ages combined or for single countries. We aimed to quantify the incidence, mortality, and DALY burden of idiopathic epilepsy among children aged 0-14 years in the Asia-Pacific region between 1990 and 2023 using GBD 2023.

        ## Methods

        We conducted a descriptive health-estimates study based on custom exports from the official GBD 2023 Results tool. The analysis covered 45 countries and territories within six prespecified GBD subregions: East Asia, South Asia, Southeast Asia, High-income Asia Pacific, Australasia, and Oceania. We retained age-specific estimates for children aged younger than 5 years, 5-9 years, and 10-14 years, and analysed both sexes combined as well as male and female strata. Outcomes were incidence, deaths, and DALYs, each extracted as numbers and rates from 1990 to 2023. Age-specific counts and rates were treated as primary endpoints. For child-wide trend summaries, we reconstructed pooled crude rates from matched age-specific counts and rates and estimated annual percentage changes (EAPCs) using log-linear regression.

        ## Findings

        In 2023, the Asia-Pacific aggregate recorded {agg['incidence_count_2023_ui']} incident cases, {agg['deaths_count_2023_ui']} deaths, and {agg['dalys_count_2023_ui']} DALYs among children aged 0-14 years. Corresponding pooled crude rates were {agg['incidence_rate_2023']} per 100,000 for incidence, {agg['deaths_rate_2023']} per 100,000 for mortality, and {agg['dalys_rate_2023']} per 100,000 for DALYs. South Asia contributed {fmt_pct(float(south_asia['deaths_share_pct']))} of the regional deaths and {fmt_pct(float(south_asia['dalys_share_pct']))} of the DALYs in 2023. The highest subregional incidence rate was in {highest_inc_subregion['location_name']} ({fmt_rate(float(highest_inc_subregion['incidence_rate_2023']))} per 100,000), whereas South Asia had the highest mortality rate ({fmt_rate(float(south_asia['deaths_rate_2023']))} per 100,000) and DALY rate ({fmt_rate(float(south_asia['dalys_rate_2023']))} per 100,000). At the aggregate level, incidence rose slightly from 1990 to 2023 (EAPC {fmt_pct(float(aggregate_eapc['Incidence']['eapc']))}), while mortality and DALY rates declined (EAPCs {fmt_pct(float(aggregate_eapc['Deaths']['eapc']))} and {fmt_pct(float(aggregate_eapc['DALYs']['eapc']))}, respectively). India carried the largest absolute DALY burden in 2023 ({fmt_count(float(top_abs_dalys['dalys_count']))}), whereas Bhutan had the highest DALY rate ({fmt_rate(float(top_rate_dalys['dalys_rate']))} per 100,000) and death rate ({fmt_rate(float(top_rate_deaths['deaths_rate']))} per 100,000).

        ## Interpretation

        Childhood idiopathic epilepsy burden in the Asia-Pacific region improved overall between 1990 and 2023, especially for mortality and DALYs, but the burden remained large and highly unequal. South Asia accounted for most fatal and disability burden, while the highest incidence rates were observed in more affluent subregions, suggesting that diagnosis intensity and outcome severity do not align uniformly. Prevention and care strategies should prioritise under-5 children, strengthen paediatric epilepsy recognition and treatment continuity, and target regions where mortality and disability remain disproportionately high.

        ## Funding

        None specific for this analysis. Funding statements should be completed by the submitting authors.
        """
    ).strip()


def build_research_in_context(metrics: dict[str, object]) -> str:
    incidence_increase: pd.DataFrame = metrics["incidence_increase"]  # type: ignore[assignment]
    deaths_decline: pd.DataFrame = metrics["deaths_decline"]  # type: ignore[assignment]
    dalys_decline: pd.DataFrame = metrics["dalys_decline"]  # type: ignore[assignment]

    return dedent(
        f"""
        # Research in Context

        ## Evidence before this study

        A formal systematic search and reference screening workflow has not yet been completed inside this local workspace, so this section should be citation-enriched before journal submission. Even so, the current epidemiological context is clear: previous GBD-derived epilepsy analyses have usually focused on all-age populations, global summaries, or individual countries, whereas paediatric studies in Asia more often rely on cohort, hospital, or registry data that are difficult to compare across settings. We therefore identified a practical gap for a child-only, multi-country Asia-Pacific burden analysis aligned to the GBD 2023 framework.

        ## Added value of this study

        This study contributes a prespecified Asia-Pacific childhood analysis built directly from official GBD 2023 Results exports rather than simulated or secondary unofficial tables. The workflow captures 45 countries and territories plus six official GBD subregions, preserves age-specific counts and rates, reconstructs pooled crude child rates instead of mislabelling them as age-standardised rates, and links raw export files to fully reproducible tables, figures, and manuscript text. The resulting pattern is policy-relevant: incidence increased most in {incidence_increase.iloc[0]['location_name']} and remained high in several affluent or middle-income settings, whereas the steepest mortality decline was observed in {deaths_decline.iloc[0]['location_name']} and the steepest DALY decline in {dalys_decline.iloc[0]['location_name']}.

        ## Implications of all the available evidence

        The available evidence suggests that childhood epilepsy control in Asia-Pacific should not be evaluated through incidence alone. Subregions with relatively high incidence rates may still have much lower mortality and disability than settings where access to diagnosis, antiseizure treatment, or specialist referral is constrained. A more useful regional strategy is therefore to combine early recognition and case ascertainment with mortality reduction, treatment continuity, developmental follow-up, and equitable paediatric neurology capacity, especially in South Asia and among children younger than 5 years.
        """
    ).strip()


def build_introduction(metrics: dict[str, object]) -> str:
    subregions: pd.DataFrame = metrics["subregions"]  # type: ignore[assignment]
    south_asia = subregions.loc[subregions["location_name"] == "South Asia"].iloc[0]
    highest_inc_subregion = subregions.sort_values("incidence_rate_2023", ascending=False).iloc[0]
    top_abs_dalys = metrics["top_abs_dalys"]  # type: ignore[assignment]

    return dedent(
        f"""
        # Introduction

        Epilepsy is one of the most common serious neurological disorders in childhood. Recurrent seizures can begin early in life and may disrupt neurodevelopment, cognition, school participation, family functioning, and long-term social integration. Fatal outcomes are less common than chronic disability, but death still occurs through direct neurological injury, status epilepticus, treatment gaps, and the broader health-system failures that shape care for children with chronic neurological disease. For these reasons, paediatric epilepsy should be understood not only as a clinical condition managed in specialist clinics, but also as a population health issue that requires regional burden surveillance.

        The Asia-Pacific region is especially relevant to this question. It combines high-income health systems with dense diagnostic networks, middle-income countries undergoing rapid epidemiological transition, and lower-resource settings where specialist paediatric neurology capacity remains limited. That diversity creates a natural setting in which incidence, mortality, and disability might not move in parallel. In the present analysis, for example, the highest 2023 subregional incidence rate was observed in {highest_inc_subregion['location_name']} ({fmt_rate(float(highest_inc_subregion['incidence_rate_2023']))} per 100,000), whereas South Asia carried the highest mortality and DALY rates as well as {fmt_pct(float(south_asia['dalys_share_pct']))} of the regional DALY burden. Such contrasts argue against interpreting childhood epilepsy through a single all-age or all-region summary statistic.

        A second challenge is methodological. Many GBD-based studies rely on all-age age-standardised rates as headline indicators, but these quantities are not always well suited to tightly age-restricted paediatric analyses. When the target population is children aged 0-14 years, age-specific rates remain the most interpretable endpoints. If a child-wide rate is required for trend analysis, it should be reconstructed transparently from age-specific counts and denominators rather than treated as a ready-made age-standardised measure. This distinction matters, because paediatric age composition can shift over time and between countries, and because the public-health meaning of under-5 epilepsy burden differs from that of the burden in early adolescence.

        Another important point is the specific cause definition. The official GBD Results tool does not expose a broad clinical field called simply “paediatric epilepsy” for this exact workflow; instead, the reproducible cause label available to this study is `Idiopathic epilepsy`. That distinction matters for interpretation. Our results should not be read as the total burden of every seizure disorder in childhood, but rather as the burden associated with the GBD idiopathic epilepsy construct. Even within that narrower frame, however, the observed burden is large enough to justify close public-health attention, and the consistency of patterns across incidence, mortality, and DALYs still provides useful regional intelligence.

        In addition, the epidemiology of epilepsy in childhood is heterogeneous across age and sex. Infants and young children are more vulnerable to perinatal insults, congenital and genetic conditions, infections, and severe developmental sequelae. Older children may have different seizure phenotypes, treatment trajectories, survival prospects, and educational consequences. Sex differences may also vary by outcome: in our 2023 Asia-Pacific aggregate, the highest incidence rate occurred in boys younger than 5 years, whereas the highest death and DALY rates occurred in girls younger than 5 years. These patterns reinforce the need to preserve age-sex detail rather than reducing the analysis to one pooled average.

        Existing epidemiological literature provides important but incomplete perspectives. Clinical cohort studies can characterise seizure types, treatment response, and developmental outcomes, yet they are seldom regionally comparable. National registry studies improve coverage but remain country-bound. Broad GBD burden papers improve comparability but frequently report all-age patterns or global totals that do not isolate paediatric populations. A child-only Asia-Pacific analysis therefore fills a practical gap between local clinical knowledge and regional policy needs.

        We aimed to quantify the incidence, mortality, and DALY burden of idiopathic epilepsy among children aged 0-14 years in the Asia-Pacific region from 1990 to 2023, to compare trends across six official GBD subregions, to examine age-sex heterogeneity in 2023, and to identify countries with the highest absolute and relative burden. By doing so, we sought to produce an analysis that is methodologically defensible, geographically broad, and directly usable for public-health planning.
        """
    ).strip()


def build_methods(ctx: dict[str, object], metrics: dict[str, object]) -> str:
    qc = ctx["qc"]  # type: ignore[assignment]
    study_config = ctx["study_config"]  # type: ignore[assignment]
    subregions = ", ".join(item["display_name"] for item in study_config["geography"]["subregions"])
    return dedent(
        f"""
        # Methods

        ## Study design

        We conducted a descriptive health-estimates study using GBD 2023. The analysis was prespecified around a single cause, a fixed geography, a restricted paediatric age range, and three burden outcomes. Because the data source comprised aggregated modelled estimates rather than individual participants, the study design should be interpreted as population-level burden analysis rather than cohort follow-up or case-control epidemiology.

        ## Setting and geographic scope

        The geographic scope was the Asia-Pacific region, operationalised in advance as six official GBD subregions: {subregions}. Within these subregions, 45 countries and territories were retained in the custom export specification. Official subregional rows were analysed directly for subregional comparisons. A separate Asia-Pacific aggregate was then reconstructed from country-level rows only, which prevented double-counting that would have occurred if country rows and subregional rows had been combined naively.

        ## Population, age groups, and sex strata

        The target population was children aged 0-14 years. In GBD Results, this scope corresponds to the age groups younger than 5 years, 5-9 years, and 10-14 years. We analysed both sexes combined and male and female strata separately. The decision to stop at 14 years was deliberate: the study was framed around childhood rather than a broader child-and-adolescent population, and the resulting estimates are therefore easier to compare with paediatric service planning.

        ## Cause definition and outcomes

        The cause definition was the official GBD 2023 Results label `Idiopathic epilepsy`. We extracted three outcomes: incidence, deaths, and DALYs. For each outcome, both numbers and rates were downloaded. Incidence was used to describe new burden entering the healthcare system, deaths were used to capture fatal burden, and DALYs were used to integrate premature mortality with non-fatal disability into a single health-loss metric.

        ## Data source and extraction workflow

        Data were obtained through custom exports from the official GBD Results interface. The study-specific extraction specification requested all combinations of the six subregions plus their constituent countries and territories, three sex strata, three paediatric age groups, three outcomes, two metrics, and years 1990-2023. The final raw export contained {qc['raw_rows']} rows with no duplicate analytic keys and no violations of the expected lower-to-mean-to-upper uncertainty ordering. Stable identifier columns were retained throughout to reduce ambiguity during downstream processing.

        ## Data processing and derived variables

        Cleaning steps included geography annotation, measure relabelling, categorical ordering of age and sex, and validation of duplicates and uncertainty intervals. The main analytic principle was to preserve age-specific GBD estimates as the primary endpoints. We therefore did not add age-specific rates directly. Instead, when a child-wide rate was required, we reconstructed age-specific denominators using the identity population equals count divided by rate multiplied by 100,000. This yielded {qc['reconstructed_rows']} matched count-rate strata with no non-positive reconstructed populations.

        Using these reconstructed denominators, we generated pooled crude rates for each country, each official subregion, and the Asia-Pacific aggregate. For official subregions and countries, the pooled crude rate combined the three paediatric age groups within each location-sex-year-measure combination. For the Asia-Pacific aggregate, we first summed country-level age-specific counts and reconstructed populations across all 45 countries and territories, and only then recalculated the pooled crude rate. This approach preserved internal consistency and prevented the aggregate from being influenced by duplicate hierarchy levels.

        ## Statistical analysis

        Three classes of analyses were prespecified. First, we described 2023 burden by geography using child-wide counts and pooled crude rates for both sexes combined. Counts were obtained by summing the three age-specific rows, while reported count uncertainty intervals were arithmetic sums of the corresponding lower and upper bounds and should therefore be interpreted descriptively rather than as covariance-aware uncertainty intervals.

        Second, we examined temporal trends from 1990 to 2023 using pooled crude rates. For each location and outcome, we compared rates in 1990 and 2023, calculated absolute and percentage rate changes, and estimated the annual percentage change using a log-linear model of the form `ln(rate) = alpha + beta × year`. EAPC was calculated as `100 × (exp(beta) - 1)` with 95% confidence intervals derived from the standard error of `beta`.

        Third, we characterised heterogeneity in 2023 across age and sex, and ranked countries according to child-wide DALY rates, with mortality rates presented alongside the same ranked locations. Absolute burden was also reviewed to identify locations where a high case volume, rather than a high rate, might be the main driver of regional impact.

        ## Quality control

        Quality control was rule-based and deterministic. We verified the expected year span from 1990 to 2023, confirmed that no duplicate key rows were present, and checked that all exported rows satisfied the expected uncertainty ordering. We also verified that no reconstructed population values or pooled crude rates were non-positive. These checks support numerical traceability and internal consistency; they do not remove the upstream assumptions that are inherent to GBD modelled estimates.

        ## Ethics and role of the funding source

        The study used aggregated, non-identifiable secondary estimates from GBD 2023 and did not involve direct contact with human participants. Formal ethics approval and consent requirements should be determined according to the institutional policy of the submitting authors, but patient consent was not applicable to the present aggregated analysis. No funder had any role in study design, analysis, interpretation, or writing for the current draft.
        """
    ).strip()


def build_results(metrics: dict[str, object]) -> str:
    agg = metrics["aggregate"]  # type: ignore[assignment]
    subregions: pd.DataFrame = metrics["subregions"]  # type: ignore[assignment]
    aggregate_eapc = metrics["aggregate_eapc"]  # type: ignore[assignment]
    top_abs_dalys = metrics["top_abs_dalys"]  # type: ignore[assignment]
    top_abs_deaths = metrics["top_abs_deaths"]  # type: ignore[assignment]
    top_abs_incidence = metrics["top_abs_incidence"]  # type: ignore[assignment]
    top_rate_dalys = metrics["top_rate_dalys"]  # type: ignore[assignment]
    top_rate_deaths = metrics["top_rate_deaths"]  # type: ignore[assignment]
    top_rate_incidence = metrics["top_rate_incidence"]  # type: ignore[assignment]
    under5 = metrics["under5"]  # type: ignore[assignment]
    incidence_increase: pd.DataFrame = metrics["incidence_increase"]  # type: ignore[assignment]
    deaths_decline: pd.DataFrame = metrics["deaths_decline"]  # type: ignore[assignment]
    dalys_decline: pd.DataFrame = metrics["dalys_decline"]  # type: ignore[assignment]

    south_asia = subregions.loc[subregions["location_name"] == "South Asia"].iloc[0]
    east_asia = subregions.loc[subregions["location_name"] == "East Asia"].iloc[0]
    highest_inc_subregion = subregions.sort_values("incidence_rate_2023", ascending=False).iloc[0]

    return dedent(
        f"""
        # Results

        ## Regional burden in 2023

        In 2023, the Asia-Pacific aggregate recorded {agg['incidence_count_2023_ui']} incident cases, {agg['deaths_count_2023_ui']} deaths, and {agg['dalys_count_2023_ui']} DALYs among children aged 0-14 years. The corresponding pooled crude rates were {agg['incidence_rate_2023']} per 100,000 for incidence, {agg['deaths_rate_2023']} per 100,000 for mortality, and {agg['dalys_rate_2023']} per 100,000 for DALYs.

        The burden was uneven across subregions. South Asia accounted for {fmt_pct(float(south_asia['incidence_share_pct']))} of regional incident cases, {fmt_pct(float(south_asia['deaths_share_pct']))} of deaths, and {fmt_pct(float(south_asia['dalys_share_pct']))} of DALYs. East Asia and Southeast Asia each contributed roughly one-fifth of incident cases, but their fatal and DALY burden was much lower than that of South Asia. The highest incidence rate in 2023 was observed in {highest_inc_subregion['location_name']} ({fmt_rate(float(highest_inc_subregion['incidence_rate_2023']))} per 100,000), whereas South Asia had the highest mortality rate ({fmt_rate(float(south_asia['deaths_rate_2023']))} per 100,000) and DALY rate ({fmt_rate(float(south_asia['dalys_rate_2023']))} per 100,000). By contrast, East Asia had a lower mortality rate ({fmt_rate(float(east_asia['deaths_rate_2023']))} per 100,000) and DALY rate ({fmt_rate(float(east_asia['dalys_rate_2023']))} per 100,000) despite still carrying large absolute case counts.

        ## Trends from 1990 to 2023

        At the Asia-Pacific aggregate level, incidence increased modestly over the study period. The pooled crude incidence rate rose from {fmt_rate(float(aggregate_eapc['Incidence']['rate_1990']))} per 100,000 in 1990 to {fmt_rate(float(aggregate_eapc['Incidence']['rate_2023']))} per 100,000 in 2023, corresponding to an EAPC of {fmt_pct(float(aggregate_eapc['Incidence']['eapc']))}. This increase was not uniform: the largest positive incidence trend among subregions was observed in {incidence_increase.iloc[0]['location_name']} (EAPC {fmt_pct(float(incidence_increase.iloc[0]['eapc']))}), whereas incidence declined in Australasia, Oceania, and High-income Asia Pacific.

        Mortality and DALY rates moved in the opposite direction. The regional pooled crude death rate fell from {fmt_rate(float(aggregate_eapc['Deaths']['rate_1990']))} per 100,000 in 1990 to {fmt_rate(float(aggregate_eapc['Deaths']['rate_2023']))} per 100,000 in 2023, with an EAPC of {fmt_pct(float(aggregate_eapc['Deaths']['eapc']))}. The steepest mortality decline among subregions was observed in {deaths_decline.iloc[0]['location_name']} (EAPC {fmt_pct(float(deaths_decline.iloc[0]['eapc']))}). Similarly, the DALY rate declined from {fmt_rate(float(aggregate_eapc['DALYs']['rate_1990']))} per 100,000 in 1990 to {fmt_rate(float(aggregate_eapc['DALYs']['rate_2023']))} per 100,000 in 2023, with an EAPC of {fmt_pct(float(aggregate_eapc['DALYs']['eapc']))}; the steepest DALY decline among subregions was observed in {dalys_decline.iloc[0]['location_name']} (EAPC {fmt_pct(float(dalys_decline.iloc[0]['eapc']))}).

        ## Age and sex patterns in 2023

        Age heterogeneity was pronounced. Children younger than 5 years accounted for {fmt_pct(float(under5['Incidence']['share_pct']))} of regional incident cases, {fmt_pct(float(under5['Deaths']['share_pct']))} of deaths, and {fmt_pct(float(under5['DALYs']['share_pct']))} of DALYs. The pooled crude incidence rate was highest in boys younger than 5 years, while girls younger than 5 years had the highest death and DALY rates. These findings indicate that the age profile of fatal and disabling burden is even more concentrated in the youngest children than the age profile of incident cases alone.

        The sex pattern depended on the outcome. Male incidence rates exceeded female rates in all three age groups, consistent with a mild male predominance in newly measured burden. By contrast, female children had slightly higher death and DALY rates in the youngest age group, while sex differences narrowed or reversed in older children. These crossovers suggest that the age-sex structure of childhood epilepsy burden cannot be summarised adequately through incidence alone.

        ## Country-level burden in 2023

        Country-level results showed a different pattern for absolute versus relative burden. India had the largest absolute burden for all three outcomes, with {fmt_count(float(top_abs_incidence['incidence_count']))} incident cases, {fmt_count(float(top_abs_deaths['deaths_count']))} deaths, and {fmt_count(float(top_abs_dalys['dalys_count']))} DALYs in 2023. Pakistan and China also contributed substantial absolute burden, especially for deaths and DALYs. These three countries were therefore central to the regional burden in terms of service demand and total health loss.

        Relative burden told a more granular story. The highest DALY rate in 2023 was observed in {top_rate_dalys['location_name']} ({fmt_rate(float(top_rate_dalys['dalys_rate']))} per 100,000), followed closely by other South Asian and small-population settings. The highest mortality rate was likewise observed in {top_rate_deaths['location_name']} ({fmt_rate(float(top_rate_deaths['deaths_rate']))} per 100,000). By contrast, the highest incidence rate was observed in {top_rate_incidence['location_name']} ({fmt_rate(float(top_rate_incidence['incidence_rate']))} per 100,000), emphasising that high detection or high measured incidence did not necessarily coincide with the highest fatal or disability burden.

        Overall, the results reveal three consistent features: first, a large residual burden despite long-term improvement in mortality and DALYs; second, a concentration of fatal and disability burden in South Asia and in children younger than 5 years; and third, a marked separation between locations with the highest incidence and locations with the highest death or DALY rates.
        """
    ).strip()


def build_discussion(metrics: dict[str, object]) -> str:
    subregions: pd.DataFrame = metrics["subregions"]  # type: ignore[assignment]
    highest_inc_subregion = subregions.sort_values("incidence_rate_2023", ascending=False).iloc[0]
    south_asia = subregions.loc[subregions["location_name"] == "South Asia"].iloc[0]
    top_abs_dalys = metrics["top_abs_dalys"]  # type: ignore[assignment]
    top_rate_dalys = metrics["top_rate_dalys"]  # type: ignore[assignment]
    top_rate_incidence = metrics["top_rate_incidence"]  # type: ignore[assignment]
    under5 = metrics["under5"]  # type: ignore[assignment]
    death_ratio = metrics["under5_female_vs_male_death_ratio"]  # type: ignore[assignment]
    daly_ratio = metrics["under5_female_vs_male_daly_ratio"]  # type: ignore[assignment]
    aggregate_eapc = metrics["aggregate_eapc"]  # type: ignore[assignment]

    return dedent(
        f"""
        # Discussion

        This study provides a regionally harmonised picture of childhood idiopathic epilepsy burden in the Asia-Pacific region from 1990 to 2023 using official GBD 2023 Results exports. Three main findings stand out. First, the regional burden remained large in 2023, with more than {fmt_count(float(metrics['aggregate_counts']['Incidence']))} incident cases and {fmt_count(float(metrics['aggregate_counts']['DALYs']))} DALYs among children aged 0-14 years. Second, mortality and DALY rates declined substantially over the study period, while incidence rose modestly rather than falling. Third, the burden was highly unequal across geography, age, and sex, with South Asia accounting for the majority of fatal and disability burden and children younger than 5 years accounting for {fmt_pct(float(under5['Deaths']['share_pct']))} of deaths and {fmt_pct(float(under5['DALYs']['share_pct']))} of DALYs.

        The divergence between incidence and more severe outcomes is important. In 2023, the highest subregional incidence rate occurred in {highest_inc_subregion['location_name']}, while South Asia had the highest mortality and DALY rates. At the country level, the highest incidence rate was observed in {top_rate_incidence['location_name']}, whereas the highest DALY rate was observed in {top_rate_dalys['location_name']}. This pattern suggests that measured incidence is shaped partly by ascertainment, access to diagnosis, service penetration, and survival, whereas death and DALY rates are more sensitive to untreated disease, delayed care, structural disadvantage, and the long tail of disability. In practical terms, a region can report relatively high incidence because it detects and records epilepsy more effectively, yet still avoid the highest mortality or disability through better continuity of care.

        The central role of South Asia deserves emphasis. In absolute terms, South Asia contributed nearly four-fifths of deaths and more than two-thirds of DALYs in the Asia-Pacific aggregate. In relative terms, its 2023 mortality and DALY rates were the highest among all six subregions. Because South Asia also contains the most populous countries in the analysis, these two dimensions reinforce one another rather than cancelling out. The result is a dual burden in which both rate-based risk and sheer population size drive regional impact. For policymakers, this means that interventions in South Asia are likely to yield the largest gains in both efficiency and equity.

        India illustrates the difference between absolute and relative burden. It had the largest absolute burden for incident cases, deaths, and DALYs, reflecting its population scale and therefore its importance for total regional disease control. Yet the highest rate-based burden was found in smaller South Asian settings such as {top_rate_dalys['location_name']}. These smaller settings might not dominate the total Asia-Pacific burden numerically, but their high rates suggest more intense risk or more fragile care systems for affected children. A complete public-health response should therefore address both population-weighted regional impact and high-rate outlier settings.

        The age pattern also has clear implications. Under-5 children represented only about one-third of incident cases but about half of deaths and two-fifths of DALYs. That imbalance is epidemiologically plausible. In the youngest age groups, epilepsy is more likely to be linked with severe underlying conditions, early developmental vulnerability, perinatal insults, infection, metabolic disorders, or delayed access to stabilising treatment. Younger children may also experience longer cumulative disability after onset, which increases DALY burden even when immediate mortality is avoided. For health systems, this finding argues for stronger integration of neonatal, infant, and early-childhood services with paediatric neurology pathways rather than treating epilepsy as a later childhood outpatient issue alone.

        The sex pattern is more nuanced than a simple male predominance. Male children had higher incidence rates across all three paediatric age groups, but girls younger than 5 years had higher death and DALY rates, with female-to-male ratios of approximately {death_ratio:.2f} for mortality and {daly_ratio:.2f} for DALYs. The reasons cannot be resolved from GBD data alone, yet the pattern is important. It implies that the sex distribution of newly identified epilepsy is not identical to the sex distribution of severe outcomes. Biological vulnerability, treatment-seeking differences, underlying cause structure, or health-system access might all contribute. Future region-specific studies should examine whether this pattern reflects true outcome inequality or differences in ascertainment and attribution within early childhood neurological care.

        The long-term trends are broadly encouraging but incomplete. The Asia-Pacific aggregate death rate fell by more than half from 1990 to 2023, and DALY rates also declined substantially. This suggests meaningful improvement in survival, treatment, or broader child health conditions. Yet incidence did not decline in parallel; instead, it rose slightly with an EAPC of {fmt_pct(float(aggregate_eapc['Incidence']['eapc']))}. A modest rise in incidence may reflect several processes: better recognition of epilepsy, increased survival of children with neurological vulnerabilities, changes in diagnostic practice, or stable upstream risk combined with improved reporting. Whatever the mechanism, the coexistence of flatter incidence and declining mortality implies that the regional challenge has shifted from fatal burden alone toward long-term management, disability reduction, and developmental support.

        The contrast between relatively high incidence and lower severe-outcome rates in high-income or better-resourced settings deserves a more explicit interpretation. Health systems with stronger paediatric referral networks, wider use of neuroimaging and electroencephalography, and more consistent long-term follow-up are likely to identify more children living with epilepsy and to keep them alive with fewer severe consequences. That pattern can produce an apparent paradox: higher measured incidence accompanied by lower mortality and lower DALY rates. Conversely, settings with weaker diagnostic coverage may record fewer incident cases while still sustaining higher death and disability rates because untreated or delayed-treated disease is more likely to lead to serious outcomes. This is one reason why incidence should never be used alone as a shorthand for the success or failure of epilepsy control.

        The policy implications follow directly from these observations. First, South Asia should be the highest priority for reducing childhood epilepsy mortality and disability at scale. This includes improving access to paediatric neurological assessment, reliable availability of essential antiseizure medicines, community and primary-care recognition of seizure emergencies, and referral pathways for refractory or complicated cases. Second, under-5 children require targeted pathways linking maternal, newborn, infection, nutrition, and developmental services with epilepsy recognition and treatment continuity. Third, countries with high measured incidence but relatively lower mortality may offer operational lessons in early detection, documentation, and longitudinal follow-up that could be adapted elsewhere.

        There is also a systems implication for data infrastructure. A region-wide paediatric epilepsy strategy will remain incomplete if surveillance systems can capture only emergency presentations or deaths. What is needed is a continuum of information that links onset, treatment initiation, medication continuity, developmental outcomes, and school participation. GBD estimates are valuable because they enable cross-country comparison, but they cannot replace local registries, clinical audits, or treatment-access monitoring. The optimal model is therefore layered rather than competitive: GBD for regional benchmarking, national surveillance for accountability, and clinical cohorts for mechanism and care-quality detail.

        This study also has several limitations. Like all GBD-based analyses, it depends on upstream modelling assumptions, input data availability, and cause attribution rules that were not re-estimated locally. The analysis was restricted to the GBD cause label `Idiopathic epilepsy`; it should not be interpreted as a full account of all epilepsy etiologies. The Asia-Pacific aggregate was reconstructed from country rows because no single official Results row exists for the exact study scope, and its uncertainty intervals for counts are arithmetic sums rather than covariance-aware estimates. Pooled crude rates were derived from means and therefore do not carry full uncertainty intervals in the present draft. In addition, rate-based rankings for small-population countries should be interpreted cautiously because modest absolute differences can produce high rates.

        These limitations do not negate the main conclusions. Rather, they define the level at which the conclusions should be applied: population-level burden planning, not individual-level causation. The present study shows that childhood idiopathic epilepsy in the Asia-Pacific region is neither uniformly improving nor uniformly distributed. Burden is declining overall, but the residual burden remains concentrated in younger children and in South Asia, while incidence remains comparatively high in several more affluent settings. That combination argues for a two-track strategy: sustain early diagnosis and longitudinal care where systems are already functioning, and intensify mortality and disability reduction where the burden remains heaviest.

        Future work should move in three directions. First, this GBD-based regional analysis should be linked to updated literature review and country-specific clinical evidence before journal submission. Second, where local datasets are available, researchers should examine the underlying drivers of the high under-5 burden, including perinatal causes, infection, structural lesions, and medication access. Third, subsequent studies could extend the current pipeline to adolescents aged 15-19 years, to broader epilepsy etiologies, or to inequality analyses stratified by sociodemographic development. For now, the current results provide a defensible regional benchmark for childhood idiopathic epilepsy burden in Asia-Pacific.
        """
    ).strip()


def build_manuscript(ctx: dict[str, object], metrics: dict[str, object]) -> str:
    title = ctx["study_config"]["study_title_en"]  # type: ignore[index]
    return "\n\n".join(
        [
            f"# {title}",
            "Author list, affiliations, contributors, funding, and reference formatting should be completed by the submitting team.",
            build_summary(metrics),
            build_research_in_context(metrics),
            build_introduction(metrics),
            build_methods(ctx, metrics),
            build_results(metrics),
            build_discussion(metrics),
            dedent(
                """
                # Conclusion

                Among children aged 0-14 years in the Asia-Pacific region, idiopathic epilepsy remained a substantial source of incident disease, mortality, and disability in 2023. The burden declined for deaths and DALYs over time but remained concentrated in South Asia and in children younger than 5 years, while incidence stayed comparatively high in several more affluent settings. These results support a regional agenda that combines early diagnosis with stronger treatment continuity, under-5 neurological protection, and focused burden reduction in high-mortality and high-DALY settings.
                """
            ).strip(),
            dedent(
                """
                # Contributors

                Contributors should be completed by the submitting authors. Suggested contribution domains: study conception, data extraction workflow, statistical analysis, figure preparation, manuscript drafting, and critical revision.

                # Declaration of Interests

                Declaration of interests should be completed by the submitting authors.

                # Data Sharing

                The present workspace stores study-specific derived files generated from official GBD Results exports. Public reuse is subject to IHME data-use conditions for GBD Results exports and to the policies of the submitting institution.

                # Acknowledgments

                Acknowledgments should be completed by the submitting authors as appropriate.
                """
            ).strip(),
            ctx["figure_legends"],  # type: ignore[index]
            dedent(
                """
                # References

                Reference enrichment and final journal-format citation styling remain to be completed before submission.
                """
            ).strip(),
        ]
    )


def main() -> None:
    args = parse_args()
    study_root = Path(args.study_root).resolve()
    manuscript_root = study_root / "outputs" / "manuscript"
    ctx = load_context(study_root)
    metrics = build_metrics(ctx)

    proposal_zh = build_proposal_zh(ctx, metrics)
    manuscript = build_manuscript(ctx, metrics)

    save_text(manuscript_root / "research_proposal_zh.md", proposal_zh)
    save_text(manuscript_root / "lancet_main_text.md", manuscript)


if __name__ == "__main__":
    main()
