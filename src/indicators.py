from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from .calibration import ModelParams, OUParams


def compute_ile_from_panel(panel: pd.DataFrame) -> pd.Series:
    """
    Implied Leverage Elasticity (ILE) from historical panel.

    Now accounts for preferred stock:
    beta_LS(t) = (H_t S_t) / (H_t S_t - D_t - P_liq) when denominator > 0.
    """
    h = panel["btc_holdings"].astype(float)
    s = panel["btc_price"].astype(float)
    d = panel["debt_total_usd"].astype(float)
    p = panel["preferred_liq"].astype(float) if "preferred_liq" in panel.columns else 0.0
    asset = h * s
    denom = asset - d - p
    ile = asset / denom
    ile[denom <= 0.0] = np.nan
    return ile


def compute_tee_from_panel(panel: pd.DataFrame, gamma_pi_s: float) -> pd.Series:
    """
    Total Equity Elasticity (TEE) using historical balance sheet and
    regression-based premium sensitivity gamma_pi_s.
    """
    ile = compute_ile_from_panel(panel)
    return gamma_pi_s + ile


def compute_pmri(ou_params: OUParams, pi0: float) -> float:
    """
    Premium Mean-Reversion Index (PMRI) for current premium pi0.
    """
    var_ss = ou_params.sigma ** 2 / (2.0 * ou_params.kappa)
    std_ss = np.sqrt(var_ss)
    return float((pi0 - ou_params.theta) / std_ss)


def compute_ibgr_total(params: ModelParams, h0: float, pi0: float) -> float:
    """
    Approximate total Implied BTC Growth Rate (IBGR) at current state.
    """
    if h0 <= 0.0:
        return float("nan")
    pi_pos = max(pi0, 0.0)
    alpha = params.holdings.alpha
    lambda_m = params.holdings.lambda_m
    mean_jump = params.holdings.mean_jump_size
    mu_H = (alpha * pi_pos + lambda_m * mean_jump) / h0
    return float(mu_H)


def compute_ibgr_per_share(
    B_paths: np.ndarray,
    dt: float,
    horizon_idx: int,
) -> float:
    """
    Estimate per-share IBGR from simulated BTC-per-share paths.
    """
    B0 = B_paths[0, :]
    B_T = B_paths[horizon_idx, :]
    T = horizon_idx * dt
    if T <= 0.0:
        return float("nan")
    growth = (B_T - B0) / (T * B0)
    return float(np.nanmean(growth))


def compute_ifrd(
    S_paths: np.ndarray,
    H_paths: np.ndarray,
    horizon_idx: int,
) -> np.ndarray:
    """
    Compute pathwise funding requirement G_T = sum S_t * (H_{t+1} - H_t).
    """
    S = S_paths[: horizon_idx, :]
    dH = H_paths[1 : horizon_idx + 1, :] - H_paths[:horizon_idx, :]
    G = (S * dH).sum(axis=0)
    return G


def compute_survival_probability(
    S_paths: np.ndarray,
    H_paths: np.ndarray,
    D_paths: np.ndarray,
    eps: float,
    horizon_idx: int,
    pref_liq: float = 0.0,
) -> float:
    """
    Estimate survival probability up to horizon T.

    Survival event: for all t <= T,
        H_t S_t > (1 + eps) * (D_t + P_liq).
    """
    S = S_paths[: horizon_idx + 1, :]
    H = H_paths[: horizon_idx + 1, :]
    D = D_paths[: horizon_idx + 1, :]
    A = H * S
    threshold = (1.0 + float(eps)) * (D + pref_liq)
    distress = A <= threshold
    distress_any = distress.any(axis=0)
    survival = (~distress_any).mean()
    return float(survival)


def compute_dividend_coverage_ratio(
    asset_value: float,
    debt: float,
    annual_preferred_dividend: float,
) -> float:
    """
    Dividend Coverage Ratio (DCR): measures how many times the company can
    cover its preferred dividend obligations from net asset value.

    DCR = (Assets - Debt) / Annual_Preferred_Dividend

    A ratio > 1 means the company can cover dividends; higher is better.
    Returns NaN if there are no preferred dividends.
    """
    if annual_preferred_dividend <= 0.0:
        return float("nan")
    net_assets = asset_value - debt
    return float(net_assets / annual_preferred_dividend)


def compute_dividend_coverage_from_sim(
    S_paths: np.ndarray,
    H_paths: np.ndarray,
    D_paths: np.ndarray,
    annual_preferred_dividend: float,
    horizon_idx: int,
) -> Dict[str, float]:
    """
    Compute dividend coverage statistics from simulation paths.

    Returns dict with mean, min (across time), and probability of coverage < 1.
    """
    if annual_preferred_dividend <= 0.0:
        return {"mean": float("nan"), "min": float("nan"), "prob_undercovered": 0.0}

    A = H_paths[: horizon_idx + 1, :] * S_paths[: horizon_idx + 1, :]
    D = D_paths[: horizon_idx + 1, :]
    net = A - D
    dcr = net / annual_preferred_dividend

    mean_dcr = float(np.mean(dcr[-1, :]))
    min_dcr_per_path = dcr.min(axis=0)
    prob_under = float((min_dcr_per_path < 1.0).mean())

    return {
        "mean": mean_dcr,
        "min_mean": float(np.mean(min_dcr_per_path)),
        "prob_undercovered": prob_under,
    }
