from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .data_io import load_btc_purchase_history


@dataclass
class OUParams:
    kappa: float
    theta: float
    sigma: float


@dataclass
class HoldingParams:
    alpha: float
    lambda_m: float
    mean_jump_size: float


@dataclass
class ModelParams:
    """
    Bundle of calibrated parameters needed for simulation and indicators.
    """

    # BTC dynamics under P
    mu_s: float
    sigma_s: float

    # Premium OU dynamics under P
    ou_premium: OUParams
    rho: float
    gamma_pi_s: float

    # Holdings dynamics
    holdings: HoldingParams

    # Balance-sheet state used for baseline simulations
    debt_0: float
    shares_0: float

    # Preferred stock
    preferred_liq_0: float = 0.0
    preferred_annual_div_0: float = 0.0

    # NAV floor used in log computations
    nav_floor: float = 1.0

    def to_dict(self) -> Dict[str, float]:
        d: Dict[str, float] = {
            "mu_s": self.mu_s,
            "sigma_s": self.sigma_s,
            "rho": self.rho,
            "gamma_pi_s": self.gamma_pi_s,
            "debt_0": self.debt_0,
            "shares_0": self.shares_0,
            "preferred_liq_0": self.preferred_liq_0,
            "preferred_annual_div_0": self.preferred_annual_div_0,
            "nav_floor": self.nav_floor,
        }
        d.update({f"ou_{k}": v for k, v in asdict(self.ou_premium).items()})
        d.update({f"holdings_{k}": v for k, v in asdict(self.holdings).items()})
        return d


def _annualize_vol(returns: pd.Series, trading_days: int = 252) -> float:
    r = returns.dropna().astype(float)
    if r.empty:
        return float("nan")
    return float(r.std(ddof=1) * np.sqrt(trading_days))


def fit_btc_vol(
    panel: pd.DataFrame,
    price_col: str = "btc_price",
    start_date: str = "2021-01-01",
) -> float:
    """
    Estimate historical BTC volatility from log-returns.
    """
    df = panel.copy()
    df = df[df.index >= pd.to_datetime(start_date)]
    prices = df[price_col].astype(float)
    log_ret = np.log(prices).diff()
    return _annualize_vol(log_ret)


def fit_ou_premium(
    premium: pd.Series,
    dt: float = 1.0 / 252.0,
) -> OUParams:
    """
    Fit an OU process to the premium time series via AR(1) regression.
    """
    s = premium.dropna().astype(float)
    if len(s) < 10:
        raise ValueError("Premium series too short for OU calibration.")

    y = s.shift(-1).iloc[:-1]
    x = s.iloc[:-1]

    X = sm.add_constant(x.to_numpy())
    model = sm.OLS(y.to_numpy(), X, missing="drop")
    res = model.fit()
    a, b = res.params

    b = float(np.clip(b, 1e-6, 1 - 1e-6))
    kappa = -np.log(b) / dt
    theta = a / (1.0 - b)

    resid_var = float(res.mse_resid)
    denom = 1.0 - np.exp(-2.0 * kappa * dt)
    sigma = np.sqrt(resid_var * 2.0 * kappa / denom)

    return OUParams(kappa=kappa, theta=theta, sigma=sigma)


def estimate_rho_and_gamma(
    btc_log_returns: pd.Series,
    premium_changes: pd.Series,
) -> Tuple[float, float]:
    """
    Estimate correlation and regression beta between BTC returns and premium changes.
    """
    df = pd.concat(
        [btc_log_returns.rename("r_s"), premium_changes.rename("d_pi")],
        axis=1,
    ).dropna()

    if df.empty:
        raise ValueError("No overlapping data to estimate rho and gamma.")

    rho = float(df["r_s"].corr(df["d_pi"]))

    X = sm.add_constant(df["r_s"].to_numpy())
    y = df["d_pi"].to_numpy()
    model = sm.OLS(y, X)
    res = model.fit()
    gamma = float(res.params[1])

    return rho, gamma


def fit_holdings_dynamics(
    panel: pd.DataFrame,
    start_date: str = "2021-01-01",
) -> HoldingParams:
    """
    Estimate simple holdings dynamics from the panel.
    """
    df = panel.copy()
    df = df[df.index >= pd.to_datetime(start_date)]

    h = df["btc_holdings"].astype(float)
    pi = df["premium"].astype(float)

    delta_h = h.diff().fillna(0.0)
    event_mask = delta_h != 0.0

    non_event_mask = ~event_mask
    pi_pos = np.maximum(pi, 0.0)
    y_cont = delta_h[non_event_mask]
    x_cont = pi_pos[non_event_mask]

    if y_cont.abs().sum() == 0:
        alpha = 0.0
    else:
        X = sm.add_constant(x_cont.to_numpy())
        y = y_cont.to_numpy()
        model = sm.OLS(y, X)
        res = model.fit()
        alpha = float(res.params[1])
        if not np.isfinite(alpha) or abs(alpha) < 1e-8:
            alpha = 0.0

    ph = load_btc_purchase_history()
    ph = ph.loc[
        (ph.index >= df.index.min())
        & (ph.index <= df.index.max())
    ]

    jump_sizes = None
    if "btc_purchased_num" in ph.columns:
        js = ph["btc_purchased_num"].dropna()
        # Filter to positive purchases only; the flywheel model assumes ΔH ≥ 0.
        jump_sizes = js[js > 0]
        if jump_sizes.empty:
            jump_sizes = None

    if jump_sizes is None:
        jump_sizes = delta_h[event_mask]

    if jump_sizes.empty:
        lambda_m = 0.0
        mean_jump_size = 0.0
    else:
        first_date = jump_sizes.index.min()
        last_date = jump_sizes.index.max()
        years = (last_date - first_date).days / 365.25
        years = max(years, 1e-6)
        lambda_m = float(len(jump_sizes) / years)
        mean_jump_size = float(jump_sizes.mean())

    return HoldingParams(
        alpha=alpha,
        lambda_m=lambda_m,
        mean_jump_size=mean_jump_size,
    )


def build_model_params(
    panel: pd.DataFrame,
    panel_calib: pd.DataFrame,
    nav_floor: float = 1.0,
    start_date: str = "2021-01-01",
    preferred_liq_0: float = 0.0,
    preferred_annual_div_0: float = 0.0,
) -> ModelParams:
    """
    Calibrate all core parameters and bundle them for simulation.
    """
    df = panel[panel.index >= pd.to_datetime(start_date)]
    prices = df["btc_price"].astype(float)
    log_ret = np.log(prices).diff().dropna()
    if log_ret.empty:
        raise ValueError("No BTC returns available for drift/vol calibration.")
    mu_s = float(log_ret.mean() * 252.0)
    sigma_s = _annualize_vol(log_ret)

    ou = fit_ou_premium(panel_calib["premium"])

    btc_log_ret = np.log(panel_calib["btc_price"].astype(float)).diff()
    premium_changes = panel_calib["premium"].astype(float).diff()
    rho, gamma_pi_s = estimate_rho_and_gamma(btc_log_ret, premium_changes)

    holdings = fit_holdings_dynamics(panel, start_date=start_date)

    last = panel.iloc[-1]
    debt_0 = float(last["debt_total_usd"])
    shares_0 = float(last["shares"])

    return ModelParams(
        mu_s=mu_s,
        sigma_s=sigma_s,
        ou_premium=ou,
        rho=rho,
        gamma_pi_s=gamma_pi_s,
        holdings=holdings,
        debt_0=debt_0,
        shares_0=shares_0,
        preferred_liq_0=preferred_liq_0,
        preferred_annual_div_0=preferred_annual_div_0,
        nav_floor=float(nav_floor),
    )
