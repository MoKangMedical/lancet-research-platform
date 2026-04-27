import importlib
import shutil

mods = [
    "pandas", "polars", "numpy", "scipy", "statsmodels", "sklearn",
    "lifelines", "matplotlib", "seaborn", "plotly", "duckdb",
    "sqlalchemy", "great_tables", "tabulate"
]

bins = ["pandoc", "soffice", "pdftoppm"]

for m in mods:
    try:
        importlib.import_module(m)
        print(f"OK: {m}")
    except Exception as e:
        print(f"MISS: {m} -> {type(e).__name__}")

for binary in bins:
    resolved = shutil.which(binary)
    if resolved:
        print(f"OK_BIN: {binary} -> {resolved}")
    else:
        print(f"MISS_BIN: {binary}")
