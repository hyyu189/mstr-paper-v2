from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


# Use a consistent seaborn theme for readability.
sns.set_theme(context="talk", style="whitegrid", font_scale=0.9)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def plot_core_timeseries(
    panel: pd.DataFrame,
    ile: Optional[pd.Series],
    tee: Optional[pd.Series],
    outdir: Path,
) -> None:
    """
    Generate core time-series plots from the historical panel.
    """
    _ensure_dir(outdir)

    # 1. Assets, debt, preferred, NAV (in billions).
    fig, ax = plt.subplots(figsize=(9, 4))
    scale = 1e9
    assets = panel["asset_btc_usd"] / scale
    debt = panel["debt_total_usd"] / scale
    nav = panel["nav"] / scale

    ax.plot(panel.index, assets, label="BTC assets $A_t$", linewidth=2.0)
    ax.plot(panel.index, debt, label="Debt $D_t$", linewidth=2.0)
    if "preferred_liq" in panel.columns:
        pref = panel["preferred_liq"] / scale
        if pref.max() > 0:
            ax.plot(panel.index, debt + pref, label="Debt + Preferred", linewidth=1.5,
                    linestyle="--", color="orange")
    ax.plot(panel.index, nav, label="NAV $(A_t-D_t-P_t)^+$", linewidth=2.0)
    ax.set_title("BTC Assets, Debt, Preferred, and NAV (USD billions)")
    ax.set_ylabel("USD billions")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(outdir / "assets_debt_nav.png", dpi=200)
    plt.close(fig)

    # 2. Premium.
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.plot(panel.index, panel["premium"], color=sns.color_palette()[3], linewidth=2.0)
    ax.axhline(0.0, color="black", linestyle="--", linewidth=1.0, alpha=0.7)
    ax.set_title(r"Premium over time: $\pi_t = \log(E_t / \mathrm{NAV}_t^{\mathrm{clip}})$")
    ax.set_ylabel("log premium")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(outdir / "premium_timeseries.png", dpi=200)
    plt.close(fig)

    # 3. BTC per share.
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.plot(panel.index, panel["btc_per_share"], color=sns.color_palette()[2], linewidth=2.0)
    ax.set_title(r"BTC per share $B_t = H_t/N_t^{\mathrm{sh}}$")
    ax.set_ylabel("BTC per share")
    ax.grid(True, alpha=0.3)

    split_date = pd.Timestamp("2024-08-08")
    if split_date in panel.index:
        ax.axvline(split_date, color="grey", linestyle="--", linewidth=1.2, alpha=0.8)
        ax.text(
            split_date,
            ax.get_ylim()[1] * 0.9,
            "10-for-1 split",
            rotation=90,
            va="top",
            ha="right",
            fontsize=8,
            color="grey",
        )

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(outdir / "btc_per_share_timeseries.png", dpi=200)
    plt.close(fig)

    # 4. ILE and TEE.
    if ile is not None and tee is not None:
        aligned = pd.concat([ile.rename("ILE"), tee.rename("TEE")], axis=1)
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(aligned.index, aligned["ILE"], label="ILE (structural leverage)", linewidth=2.0)
        ax.plot(aligned.index, aligned["TEE"], label="TEE (total equity elasticity)", linewidth=2.0)
        ax.axhline(0.0, color="black", linestyle="--", linewidth=1.0, alpha=0.7)
        ax.set_title("Leverage and Total Equity Elasticity over Time")
        ax.set_ylabel("beta to BTC")
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(outdir / "ile_tee_timeseries.png", dpi=200)
        plt.close(fig)


def plot_ifrd_histogram(
    G: np.ndarray,
    outdir: Path,
) -> None:
    """
    Plot histogram of the funding requirement distribution G_T.
    """
    _ensure_dir(outdir)

    scale = 1e9
    G_bil = G / scale

    fig, ax = plt.subplots(figsize=(9, 3.5))
    sns.histplot(G_bil, bins=40, kde=False, color=sns.color_palette()[0], ax=ax)

    mean_val = float(G_bil.mean())
    ax.axvline(mean_val, color="red", linestyle="--", linewidth=1.2, label="Mean")

    ax.set_title("Implied Funding Requirement Distribution $G_T$")
    ax.set_xlabel("Total funding $G_T$ (USD billions)")
    ax.set_ylabel("Number of paths")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(outdir / "ifrd_histogram.png", dpi=200)
    plt.close(fig)


def plot_capital_structure(
    preferred_detail: pd.DataFrame,
    debt_total: float,
    asset_total: float,
    outdir: Path,
) -> None:
    """
    Plot capital structure waterfall showing priority of claims.
    """
    _ensure_dir(outdir)

    fig, ax = plt.subplots(figsize=(9, 5))
    scale = 1e9

    # Build stacked bar
    labels = []
    sizes = []
    colors = []

    # Debt (senior)
    labels.append(f"Debt (${debt_total/scale:.1f}B)")
    sizes.append(debt_total / scale)
    colors.append(sns.color_palette()[3])

    # Preferred stock by seniority
    pref_sorted = preferred_detail.sort_values("seniority_rank")
    palette = sns.color_palette("YlOrRd", n_colors=len(pref_sorted))
    for i, (_, row) in enumerate(pref_sorted.iterrows()):
        liq = row["total_liquidation_value"]
        div = row["total_annual_dividend"]
        labels.append(f"{row['ticker']} (${liq/scale:.1f}B, {row['dividend_rate_pct']:.0f}%)")
        sizes.append(liq / scale)
        colors.append(palette[i])

    # Common equity (residual)
    total_senior = debt_total + preferred_detail["total_liquidation_value"].sum()
    equity_residual = max(asset_total - total_senior, 0) / scale
    labels.append(f"Common Equity (${equity_residual:.1f}B)")
    sizes.append(equity_residual)
    colors.append(sns.color_palette()[2])

    # Horizontal stacked bar
    left = 0
    for i, (label, size) in enumerate(zip(labels, sizes)):
        ax.barh(0, size, left=left, color=colors[i], label=label, edgecolor="white", height=0.5)
        left += size

    ax.set_yticks([])
    ax.set_xlabel("USD billions")
    ax.set_title("Strategy Capital Structure (Priority Waterfall)")
    ax.legend(loc="upper right", fontsize=8, bbox_to_anchor=(1.0, -0.1), ncol=2)
    fig.tight_layout()
    fig.savefig(outdir / "capital_structure.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
