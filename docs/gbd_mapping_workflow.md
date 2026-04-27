# GBD Mapping Workflow

## Supported Input Structure

Minimum columns:

- `location_name` or `iso3`
- `val`

Optional columns:

- `year`
- `sex`
- `measure_name`
- `metric_name`
- `age_name`
- `cause_name`

Typical GBD export works directly if it contains `location_name` and `val`.

## Command

```bash
source /Users/apple/Documents/.venvs/data-analytics/bin/activate
cd /Users/apple/Documents/lancet-research-platform

make gbd-map \
  INPUT=/absolute/path/gbd.csv \
  VALUE=val \
  LOCATION=location_name \
  FACET=year \
  TITLE='GBD Global Map'
```

## Outputs

- `outputs/tables/gbd_map_prepped.csv`
- `outputs/figures/gbd_choropleth_map.html`
- `outputs/figures/gbd_choropleth_map.png`

## Notes

- If your file already has ISO3 country codes, pass `ISO3=iso3`.
- `FACET=year` or `FACET=sex` will create multi-panel maps.
- The script is country-level. Subnational GBD maps need a different geometry workflow.
- `HTML` export is the stable default.
- `PNG` export is best-effort and may fail on some local Plotly/Kaleido combinations; the command will still complete and keep the `HTML` map.
