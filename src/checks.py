from __future__ import annotations

import numpy as np

from .calibration import build_model_params
from .preprocessing import build_daily_panel
from .simulation import SimulationConfig, simulate_paths


def run_smoke_checks() -> None:
    """
    Minimal end-to-end smoke checks for the pipeline.
    """
    panel_data = build_daily_panel()
    panel = panel_data.panel
    panel_calib = panel_data.panel_calib
    pref = panel_data.preferred

    assert not panel.empty, "Panel should not be empty."
    assert not panel_calib.empty, "Calibration subset should not be empty."

    nav_raw = panel["nav_raw"].to_numpy()
    nav = panel["nav"].to_numpy()
    mask_nav = ~np.isnan(nav)
    assert np.all(nav[mask_nav] >= 0.0), "NAV must be non-negative."

    premium = panel["premium"].to_numpy()
    mask_pi = ~np.isnan(premium)
    assert np.isfinite(premium[mask_pi]).all(), "Premium must be finite where defined."

    pref_liq = pref.total_liquidation_value if pref is not None else 0.0
    pref_div = pref.total_annual_dividend if pref is not None else 0.0

    params = build_model_params(
        panel, panel_calib,
        preferred_liq_0=pref_liq,
        preferred_annual_div_0=pref_div,
    )
    assert params.sigma_s > 0.0, "BTC volatility must be positive."
    assert params.ou_premium.kappa > 0.0, "OU kappa must be positive."
    assert params.ou_premium.sigma > 0.0, "OU sigma must be positive."

    last = panel.iloc[-1]
    s0 = float(last["btc_price"])
    h0 = float(last["btc_holdings"])
    d0 = float(last["debt_total_usd"])
    n0 = float(last["shares"])
    pi0 = float(last["premium"])

    cfg = SimulationConfig(n_paths=500, years=1.0, dt=1.0 / 252.0, random_seed=123)
    sim = simulate_paths(
        params=params,
        s0=s0,
        pi0=pi0,
        h0=h0,
        d0=d0,
        n0=n0,
        config=cfg,
    )

    n_steps = cfg.n_steps
    assert sim["S"].shape == (n_steps + 1, cfg.n_paths)
    assert sim["NAV"].shape == (n_steps + 1, cfg.n_paths)

    assert (sim["H"] >= 0.0).all()
    assert (sim["NAV"] >= 0.0).all()

    print("Smoke checks passed.")


if __name__ == "__main__":
    run_smoke_checks()
