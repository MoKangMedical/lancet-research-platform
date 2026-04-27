"""Top-journal epidemiology analysis template (Python).

This script provides a reproducible skeleton for:
1) Table 1 baseline summary
2) Propensity score weighting (IPTW)
3) Weighted outcome model
4) Cox time-to-event model
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from lifelines import CoxPHFitter


def make_table1(df: pd.DataFrame, by: str, cols: list[str]) -> pd.DataFrame:
    rows = []
    for c in cols:
        if pd.api.types.is_numeric_dtype(df[c]):
            g = df.groupby(by)[c]
            rows.append({"var": c, "summary": g.mean().to_dict(), "sd": g.std().to_dict()})
        else:
            ct = pd.crosstab(df[c], df[by], normalize="columns")
            rows.append({"var": c, "summary": ct.to_dict()})
    return pd.DataFrame(rows)


def iptw_weights(df: pd.DataFrame, treat: str, covars: list[str]) -> pd.Series:
    X = sm.add_constant(df[covars], has_constant="add")
    y = df[treat]
    ps_model = sm.Logit(y, X).fit(disp=False)
    ps = np.clip(ps_model.predict(X), 1e-3, 1 - 1e-3)
    w = np.where(y == 1, 1 / ps, 1 / (1 - ps))
    return pd.Series(w, index=df.index, name="iptw")


def weighted_main_model(df: pd.DataFrame, outcome: str, treat: str, covars: list[str], wcol: str):
    X = sm.add_constant(df[[treat] + covars], has_constant="add")
    y = df[outcome]
    model = sm.GLM(y, X, family=sm.families.Binomial(), freq_weights=df[wcol])
    return model.fit(cov_type="HC3")


def run_cox(df: pd.DataFrame, time_col: str, event_col: str, covars: list[str]):
    cph = CoxPHFitter()
    cph.fit(df[[time_col, event_col] + covars], duration_col=time_col, event_col=event_col)
    return cph


if __name__ == "__main__":
    print("Load your harmonized dataset and call helper functions in this template.")
