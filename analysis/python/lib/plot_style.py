from __future__ import annotations

import matplotlib.pyplot as plt
import seaborn as sns


def apply_pub_style() -> None:
    sns.set_theme(style='whitegrid', context='talk')
    plt.rcParams.update({
        'figure.dpi': 130,
        'savefig.dpi': 240,
        'axes.titlesize': 16,
        'axes.labelsize': 13,
        'xtick.labelsize': 11,
        'ytick.labelsize': 11,
        'legend.fontsize': 10,
        'font.family': 'DejaVu Sans',
    })
