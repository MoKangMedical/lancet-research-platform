#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import plotly.express as px
import pycountry

ROOT = Path("/Users/apple/Documents/lancet-research-platform")

# Common GBD and IHME naming variants that do not map cleanly via pycountry.
LOCATION_ALIASES = {
    "Russian Federation": "RUS",
    "Iran (Islamic Republic of)": "IRN",
    "Viet Nam": "VNM",
    "Republic of Korea": "KOR",
    "Democratic People's Republic of Korea": "PRK",
    "Bolivia (Plurinational State of)": "BOL",
    "Venezuela (Bolivarian Republic of)": "VEN",
    "Syrian Arab Republic": "SYR",
    "United Republic of Tanzania": "TZA",
    "Congo (Brazzaville)": "COG",
    "Congo (Kinshasa)": "COD",
    "Cote d'Ivoire": "CIV",
    "Côte d'Ivoire": "CIV",
    "Türkiye": "TUR",
    "Turkey": "TUR",
    "Micronesia (Federated States of)": "FSM",
    "Moldova": "MDA",
    "Republic of Moldova": "MDA",
    "Palestine": "PSE",
    "State of Palestine": "PSE",
    "Laos": "LAO",
    "Lao People's Democratic Republic": "LAO",
    "Brunei": "BRN",
    "Brunei Darussalam": "BRN",
    "Cape Verde": "CPV",
    "Cabo Verde": "CPV",
    "Swaziland": "SWZ",
    "Eswatini": "SWZ",
    "North Macedonia": "MKD",
    "Macedonia": "MKD",
    "United States": "USA",
    "United States of America": "USA",
    "United Kingdom": "GBR",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--value_col", default="val")
    p.add_argument("--location_col", default="location_name")
    p.add_argument("--iso3_col", default="")
    p.add_argument("--facet_col", default="")
    p.add_argument("--color_scale", default="YlOrRd")
    p.add_argument("--title", default="GBD Choropleth Map")
    p.add_argument(
        "--out_html",
        default=str(ROOT / "outputs/figures/gbd_choropleth_map.html"),
    )
    p.add_argument(
        "--out_png",
        default=str(ROOT / "outputs/figures/gbd_choropleth_map.png"),
    )
    p.add_argument(
        "--out_csv",
        default=str(ROOT / "outputs/tables/gbd_map_prepped.csv"),
    )
    p.add_argument("--skip_png", action="store_true")
    return p.parse_args()


def read_df(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported format: {suffix}")


def name_to_iso3(name: str) -> str | None:
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    if name in LOCATION_ALIASES:
        return LOCATION_ALIASES[name]
    try:
        return pycountry.countries.lookup(name).alpha_3
    except LookupError:
        pass
    try:
        return pycountry.countries.search_fuzzy(name)[0].alpha_3
    except LookupError:
        return None


def main() -> None:
    args = parse_args()
    df = read_df(Path(args.input)).copy()

    required = [args.value_col]
    if args.iso3_col:
        required.append(args.iso3_col)
    else:
        required.append(args.location_col)
    if args.facet_col:
        required.append(args.facet_col)

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    if args.iso3_col:
        df.loc[:, "iso3"] = df[args.iso3_col].astype(str).str.upper()
    else:
        df.loc[:, "iso3"] = df[args.location_col].map(name_to_iso3)

    plot_df = df.dropna(subset=["iso3", args.value_col]).copy()
    if plot_df.empty:
        raise ValueError("No rows left after ISO3 mapping.")

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    plot_df.to_csv(out_csv, index=False)

    hover = [c for c in [args.location_col, args.value_col, args.facet_col] if c and c in plot_df.columns]
    fig = px.choropleth(
        plot_df,
        locations="iso3",
        color=args.value_col,
        hover_name=args.location_col if args.location_col in plot_df.columns else "iso3",
        hover_data=hover,
        color_continuous_scale=args.color_scale,
        facet_col=args.facet_col if args.facet_col else None,
        projection="natural earth",
        title=args.title,
    )

    fig.update_geos(
        showcoastlines=False,
        showframe=False,
        showcountries=True,
        countrycolor="rgba(255,255,255,0.65)",
        landcolor="rgb(240,240,240)",
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=60, b=10),
        coloraxis_colorbar=dict(title=args.value_col),
        font=dict(family="DejaVu Sans", size=14),
    )

    out_html = Path(args.out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_html)

    out_png = Path(args.out_png)
    if args.skip_png:
        png_status = "skipped"
    else:
        png_status = "ok"
        try:
            fig.write_image(out_png, width=1400, height=800, scale=2)
        except Exception as exc:
            png_status = f"failed: {type(exc).__name__}"

    mapped = plot_df["iso3"].notna().sum()
    print(f"Prepared table: {out_csv}")
    print(f"Map HTML: {out_html}")
    print(f"Map PNG: {out_png} ({png_status})")
    print(f"Mapped rows: {mapped}/{len(df)}")


if __name__ == "__main__":
    main()
