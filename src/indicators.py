from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm

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


# ---------------------------------------------------------------------------
# New theory indicators: fair premium, mispricing, reflexivity, tipping point,
# weighted average cost of BTC acquisition (WACBA).
# ---------------------------------------------------------------------------


def compute_fair_premium(
    params: ModelParams,
    panel: pd.DataFrame,
    r: float | None = None,
) -> pd.Series:
    r"""Compute the fair (steady-state) premium time series.

    .. math::
        \pi^*_t = \log\!\bigl(1 + V_{\mathrm{acc},t} / \mathrm{NAV}_t\bigr)

    Using the steady-state approximation from the endogenous-premium theory:

    .. math::
        \frac{V_{\mathrm{acc}}}{\mathrm{NAV}}
        \;\approx\;
        \frac{\mathrm{IBGR}}{r + \kappa}
        \,\Bigl(1 + \frac{\sigma_S^2}{2\kappa}\Bigr)

    where IBGR is the implied BTC growth rate and *r* is the risk-free rate.
    """
    if r is None:
        if "rf_rate" in panel.columns:
            r_series = panel["rf_rate"].astype(float).fillna(0.04)
        else:
            r_series = pd.Series(0.04, index=panel.index)
    else:
        r_series = pd.Series(float(r), index=panel.index)

    kappa = params.ou_premium.kappa
    sigma_s = params.sigma_s

    h = panel["btc_holdings"].astype(float)
    pi = panel["premium"].astype(float)

    # Per-period IBGR (annualized growth rate of holdings)
    alpha = params.holdings.alpha
    lambda_m = params.holdings.lambda_m
    mean_jump = params.holdings.mean_jump_size
    pi_pos = np.maximum(pi, 0.0)
    ibgr = (alpha * pi_pos + lambda_m * mean_jump) / h

    # Steady-state accumulation value ratio
    vol_adj = 1.0 + sigma_s ** 2 / (2.0 * kappa)
    v_acc_over_nav = ibgr / (r_series + kappa) * vol_adj

    pi_star = np.log(1.0 + np.maximum(v_acc_over_nav, 0.0))
    return pd.Series(pi_star, index=panel.index, name="pi_star")


def compute_mispricing(
    pi_series: pd.Series,
    pi_star_series: pd.Series,
    window: int = 63,
) -> pd.DataFrame:
    r"""Compute mispricing and rolling z-score.

    .. math::
        \Delta_t = \pi_t - \pi^*_t, \qquad
        z_t = \frac{\Delta_t - \bar\Delta}{\hat\sigma_\Delta}

    Parameters
    ----------
    window : int
        Rolling window (trading days) for mean and std used in the z-score.
        Default 63 (~one quarter).
    """
    delta = pi_series - pi_star_series
    roll_mean = delta.rolling(window, min_periods=10).mean()
    roll_std = delta.rolling(window, min_periods=10).std()
    z_score = (delta - roll_mean) / roll_std.replace(0.0, np.nan)

    return pd.DataFrame(
        {"delta": delta, "z_score": z_score},
        index=pi_series.index,
    )


def compute_reflexivity_gain(
    params: ModelParams,
    panel: pd.DataFrame,
    eta: float = 0.02,
) -> pd.DataFrame:
    r"""Compute the feedback gain *G* and effective mean-reversion speed.

    From the market-impact theory:

    .. math::
        G_t = \eta \,\frac{|\beta_{\mathrm{TOT}}|\, E_t}{V_t\, S_t}

    where :math:`\beta_{\mathrm{TOT}}` is TEE, :math:`E_t` is equity value,
    :math:`V_t` is daily BTC volume (approximated from price * holdings as a
    scale proxy), and :math:`S_t` is BTC price.

    Effective mean-reversion:

    .. math::
        \kappa_{\mathrm{eff}} = \kappa\,(1 - G)
    """
    kappa = params.ou_premium.kappa
    gamma_pi_s = params.gamma_pi_s

    ile = compute_ile_from_panel(panel)
    tee = gamma_pi_s + ile  # β_TOT

    s = panel["btc_price"].astype(float)
    h = panel["btc_holdings"].astype(float)
    equity = panel["equity_value"].astype(float)

    # Use asset value (H*S) as a scale proxy for BTC market volume
    # (the exact volume cancels in comparative statics; this keeps the
    # gain dimensionless and in the right order of magnitude).
    v_proxy = h * s

    gain = eta * np.abs(tee) * equity / (v_proxy * s)
    gain = gain.clip(upper=2.0)  # cap for numerical sanity

    kappa_eff = kappa * (1.0 - gain)

    return pd.DataFrame(
        {"G": gain, "kappa_eff": kappa_eff},
        index=panel.index,
    )


def compute_tipping_point(
    params: ModelParams,
    panel: pd.DataFrame,
) -> pd.Series:
    r"""Compute the critical premium for the death-spiral tipping point.

    The accumulation flywheel stalls when :math:`\pi < 0`. In our model the
    critical premium below which NAV erosion exceeds new accumulation is:

    .. math::
        \pi_{\mathrm{crit},t}
        = -\frac{D_t + P_{\mathrm{liq}}}{A_t}

    This is the premium at which equity value equals zero
    (:math:`E = 0 \Leftrightarrow \pi = \log(1) = 0` under no-leverage,
    but with debt the break-even shifts negative).  A more useful metric is
    the *distance to tipping*: :math:`\pi_t - \pi_{\mathrm{crit},t}`.
    """
    h = panel["btc_holdings"].astype(float)
    s = panel["btc_price"].astype(float)
    d = panel["debt_total_usd"].astype(float)
    p = panel["preferred_liq"].astype(float) if "preferred_liq" in panel.columns else 0.0
    a = h * s

    # Critical premium: equity value = 0 ⟹ e^π NAV = 0 ⟹ A e^π - D - P = 0
    # ⟹ π_crit = log((D+P)/A).  For A > D+P this is negative (safe).
    ratio = (d + p) / a.replace(0.0, np.nan)
    pi_crit = np.log(ratio)

    return pd.Series(pi_crit, index=panel.index, name="pi_crit")


def compute_wacba(
    panel: pd.DataFrame,
    params: ModelParams,
) -> pd.Series:
    r"""Weighted Average Cost of BTC Acquisition (WACBA).

    Approximation using the two dominant channels observable from calibrated
    parameters:

    1. **ATM equity** (cost :math:`k_{\mathrm{ATM}} = 1 - e^{-\pi}`
       when :math:`\pi > 0`, i.e. *negative* cost = accretive).
    2. **Preferred stock** (cost :math:`k_{\mathrm{pref}} = d_{\mathrm{pref}} / A`
       where :math:`d_{\mathrm{pref}}` is the annual preferred dividend).

    Channel weights are inferred from the holdings dynamics calibration:
    continuous drift → ATM channel, jump component → preferred / convertible.

    .. math::
        \mathrm{WACBA}_t = w_{\mathrm{ATM}}\, k_{\mathrm{ATM},t}
                          + w_{\mathrm{pref}}\, k_{\mathrm{pref},t}
    """
    pi = panel["premium"].astype(float)
    h = panel["btc_holdings"].astype(float)
    s = panel["btc_price"].astype(float)
    a = h * s

    alpha = params.holdings.alpha
    lambda_m = params.holdings.lambda_m
    mean_jump = params.holdings.mean_jump_size

    pi_pos = np.maximum(pi, 0.0)
    cont_flow = alpha * pi_pos
    jump_flow = lambda_m * mean_jump
    total_flow = cont_flow + jump_flow
    total_flow = total_flow.replace(0.0, np.nan)

    w_atm = cont_flow / total_flow
    w_pref = jump_flow / total_flow

    # ATM cost: negative when accretive (premium > 0)
    k_atm = 1.0 - np.exp(-pi)

    # Preferred cost: annual dividend burden as fraction of assets
    pref_div = params.preferred_annual_div_0
    k_pref = pref_div / a.replace(0.0, np.nan)

    wacba = w_atm * k_atm + w_pref * k_pref
    return pd.Series(wacba, index=panel.index, name="WACBA")
