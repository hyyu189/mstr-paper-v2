from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data_io import (
    load_btc_daily,
    load_btc_holdings,
    load_mstr_balance_sheet_basic,
    load_mstr_daily_price_shares,
    load_preferred_stock,
    load_tbill_curve,
)


@dataclass
class PreferredStockSummary:
    """Aggregate preferred stock data for the capital structure."""

    total_liquidation_value: float
    total_annual_dividend: float
    convertible_shares: float
    conversion_dilution_shares: float
    detail: pd.DataFrame


@dataclass
class PanelData:
    """Container for the processed panel and calibration subset."""

    panel: pd.DataFrame
    panel_calib: pd.DataFrame
    preferred: PreferredStockSummary | None = None


def build_daily_panel(
    start_date: str | None = None,
    end_date: str | None = "2026-03-18",
    nav_floor: float = 1.0,
    nav_calib_threshold: float = 1e8,
) -> PanelData:
    """
    Build a cleaned daily panel from raw Compustat, holdings, BTC, and T-bill data.

    This function assembles:
    - BTC price S_t (from CryptoDataDownload).
    - BTC holdings H_t (from mstr-btc-holdings-over-time.csv).
    - MSTR price and shares (from mstr-daily-price&shares.csv).
    - Debt D_t (from mstr-balance-sheet-basic.csv, forward-filled).
    - Risk-free rate (from 3-month-tbill-yield-curve.csv, forward-filled).
    - Preferred stock liquidation value P_t (from data/preferred_stock.csv).

    NAV is computed as: NAV = Assets - Debt - Preferred_Liquidation_Value.

    Parameters
    ----------
    start_date:
        Optional ISO date string to trim the panel (e.g. ``"2021-01-01"``).
        Calibration will always start from max(start_date, 2021-01-01).
    nav_floor:
        Strictly positive floor used for ``nav_clip`` when computing logs.
    end_date:
        Optional ISO date string to cap the panel (e.g. ``"2026-03-18"``).
    nav_calib_threshold:
        NAV threshold (in USD) for including observations in the calibration
        subset.
    """
    # Load raw series.
    holdings_daily = load_btc_holdings()
    mstr_daily = load_mstr_daily_price_shares()
    bs_quarterly = load_mstr_balance_sheet_basic()
    rf_daily = load_tbill_curve()
    btc_daily = load_btc_daily()

    # Load preferred stock data.
    try:
        pref_df = load_preferred_stock()
        pref_summary = PreferredStockSummary(
            total_liquidation_value=float(pref_df["total_liquidation_value"].sum()),
            total_annual_dividend=float(pref_df["total_annual_dividend"].sum()),
            convertible_shares=float(
                pref_df.loc[pref_df["is_convertible"], "shares_outstanding"].sum()
            ),
            conversion_dilution_shares=float(
                (pref_df["shares_outstanding"] * pref_df["conversion_ratio_to_mstr"])
                .loc[pref_df["is_convertible"]]
                .sum()
            ),
            detail=pref_df,
        )
    except Exception:
        pref_summary = None

    # Determine panel date range.
    start_candidates = [
        holdings_daily.index.min().floor("D"),
        mstr_daily.index.min().floor("D"),
    ]
    start = max(start_candidates)
    if start_date is not None:
        start = max(start, pd.to_datetime(start_date))

    end_candidates = [
        btc_daily.index.max().floor("D"),
        mstr_daily.index.max().floor("D"),
        rf_daily.index.max().floor("D"),
    ]
    end = min(end_candidates)
    if end_date is not None:
        end = min(end, pd.to_datetime(end_date))

    date_index = pd.date_range(start, end, freq="D")

    # Align all series to the common daily index.
    panel = pd.DataFrame(index=date_index)

    panel = panel.join(
        btc_daily[["btc_price"]].reindex(date_index).ffill(), how="left"
    )

    panel = panel.join(
        holdings_daily[["btc_holdings"]].reindex(date_index).ffill(), how="left"
    )

    panel = panel.join(
        mstr_daily[["mstr_prc_adj", "shares"]].reindex(date_index).ffill(), how="left"
    )

    # Debt: quarterly data forward-filled and extended to end of panel.
    bs_daily = bs_quarterly.resample("D").ffill()
    bs_daily = bs_daily.reindex(date_index).ffill()
    panel = panel.join(bs_daily[["debt_total_usd"]], how="left")

    # Risk-free rate: daily from T-bill, aligned and forward-filled.
    rf_daily = rf_daily.reindex(date_index).ffill()
    panel = panel.join(rf_daily[["rf_rate"]], how="left")

    # Recompute core quantities to enforce structural consistency.
    btc_price = panel["btc_price"].astype(float)
    btc_holdings = panel["btc_holdings"].astype(float)
    debt_total = panel["debt_total_usd"].astype(float)
    shares = panel["shares"].astype(float)
    mstr_prc_adj = panel["mstr_prc_adj"].astype(float)

    asset_btc_usd = btc_price * btc_holdings

    # Preferred stock liquidation value reduces NAV available to common equity.
    pref_liq = pref_summary.total_liquidation_value if pref_summary is not None else 0.0
    nav_raw = asset_btc_usd - debt_total - pref_liq
    nav = nav_raw.clip(lower=0.0)

    # nav_clip is only used for log computations.
    nav_clip = np.maximum(nav_raw, float(nav_floor))

    equity_value = mstr_prc_adj * shares

    premium = np.log(equity_value / nav_clip)

    btc_per_share = btc_holdings / shares

    df_out = panel.copy()
    df_out["asset_btc_usd"] = asset_btc_usd
    df_out["preferred_liq"] = pref_liq
    df_out["nav_raw"] = nav_raw
    df_out["nav"] = nav
    df_out["nav_clip"] = nav_clip
    df_out["equity_value"] = equity_value
    df_out["premium"] = premium
    df_out["btc_per_share"] = btc_per_share

    df_out["is_nav_nonpositive"] = nav_raw <= 0.0
    df_out["is_nav_tiny"] = (nav_raw > 0.0) & (nav_raw < float(nav_calib_threshold))

    # Calibration subset: filter out bad NAV regimes and trim start date to 2021-01-01.
    calib = df_out.loc[df_out.index >= pd.to_datetime("2021-01-01")].copy()
    calib = calib[~calib["is_nav_nonpositive"] & ~calib["is_nav_tiny"]]

    return PanelData(panel=df_out, panel_calib=calib, preferred=pref_summary)
