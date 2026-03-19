from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from .calibration import build_model_params
from .indicators import (
    compute_dividend_coverage_from_sim,
    compute_dividend_coverage_ratio,
    compute_fair_premium,
    compute_ibgr_per_share,
    compute_ibgr_total,
    compute_ifrd,
    compute_ile_from_panel,
    compute_mispricing,
    compute_pmri,
    compute_reflexivity_gain,
    compute_survival_probability,
    compute_tee_from_panel,
    compute_tipping_point,
    compute_wacba,
)
from .plots import (
    plot_capital_structure,
    plot_core_timeseries,
    plot_fair_premium_vs_actual,
    plot_ifrd_histogram,
    plot_mispricing_timeseries,
)
from .preprocessing import build_daily_panel
from .simulation import SimulationConfig, simulate_paths


ROOT = Path(".")
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures"


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(FIGURES_DIR, exist_ok=True)

    # 1. Data preprocessing
    panel_data = build_daily_panel()
    panel = panel_data.panel
    panel_calib = panel_data.panel_calib
    pref = panel_data.preferred

    panel.to_csv(RESULTS_DIR / "panel_processed.csv")

    # 2. Calibration (with preferred stock data)
    pref_liq = pref.total_liquidation_value if pref is not None else 0.0
    pref_div = pref.total_annual_dividend if pref is not None else 0.0

    params = build_model_params(
        panel=panel,
        panel_calib=panel_calib,
        nav_floor=1.0,
        start_date="2021-01-01",
        preferred_liq_0=pref_liq,
        preferred_annual_div_0=pref_div,
    )

    with open(RESULTS_DIR / "params.json", "w", encoding="utf-8") as f:
        json.dump(params.to_dict(), f, indent=2)

    # 3. Current-state indicators from panel
    last = panel.iloc[-1]
    s0 = float(last["btc_price"])
    h0 = float(last["btc_holdings"])
    d0 = float(last["debt_total_usd"])
    n0 = float(last["shares"])
    pi0 = float(last["premium"])

    ile_series = compute_ile_from_panel(panel)
    tee_series = compute_tee_from_panel(panel, params.gamma_pi_s)
    pmri_value = compute_pmri(params.ou_premium, pi0)
    ibgr_total = compute_ibgr_total(params, h0=h0, pi0=pi0)

    # Dividend coverage ratio (current)
    dcr_current = compute_dividend_coverage_ratio(
        asset_value=h0 * s0, debt=d0, annual_preferred_dividend=pref_div
    )

    # 3b. New theory indicators
    pi_star_series = compute_fair_premium(params, panel)
    mispricing_df = compute_mispricing(panel["premium"], pi_star_series)
    reflexivity_df = compute_reflexivity_gain(params, panel)
    pi_crit_series = compute_tipping_point(params, panel)
    wacba_series = compute_wacba(panel, params)

    pi_star_current = float(pi_star_series.iloc[-1])
    delta_current = float(mispricing_df["delta"].iloc[-1])
    z_score_current = float(mispricing_df["z_score"].iloc[-1])
    gain_current = float(reflexivity_df["G"].iloc[-1])
    kappa_eff_current = float(reflexivity_df["kappa_eff"].iloc[-1])
    pi_crit_current = float(pi_crit_series.iloc[-1])
    distance_to_tipping = float(pi0 - pi_crit_current)
    wacba_current = float(wacba_series.iloc[-1])

    # 4. Monte Carlo simulation under P
    sim_cfg = SimulationConfig(n_paths=5000, years=3.0, dt=1.0 / 252.0, random_seed=42)
    sim = simulate_paths(
        params=params,
        s0=s0,
        pi0=pi0,
        h0=h0,
        d0=d0,
        n0=n0,
        config=sim_cfg,
    )

    n_steps = sim_cfg.n_steps
    horizon_idx = n_steps

    # 5. Simulation-based indicators
    ibgr_per_share = compute_ibgr_per_share(
        sim["B"], dt=sim_cfg.dt, horizon_idx=horizon_idx
    )

    G = compute_ifrd(sim["S"], sim["H"], horizon_idx=horizon_idx)
    ifrd_summary = {
        "mean": float(np.mean(G)),
        "std": float(np.std(G)),
        "p5": float(np.percentile(G, 5)),
        "p50": float(np.percentile(G, 50)),
        "p95": float(np.percentile(G, 95)),
    }

    survival_eps0 = compute_survival_probability(
        sim["S"], sim["H"], sim["D"],
        eps=0.0, horizon_idx=horizon_idx, pref_liq=pref_liq,
    )

    survival_eps10 = compute_survival_probability(
        sim["S"], sim["H"], sim["D"],
        eps=0.1, horizon_idx=horizon_idx, pref_liq=pref_liq,
    )

    # Dividend coverage from simulation
    dcr_sim = compute_dividend_coverage_from_sim(
        sim["S"], sim["H"], sim["D"],
        annual_preferred_dividend=pref_div,
        horizon_idx=horizon_idx,
    )

    # 6. Save indicator summary
    indicators = {
        "current_date": str(panel.index[-1].date()),
        "S0": s0,
        "H0": h0,
        "D0": d0,
        "N0": n0,
        "preferred_liq_total": pref_liq,
        "preferred_annual_div_total": pref_div,
        "pi0": pi0,
        "ILE_current": float(ile_series.iloc[-1]),
        "TEE_current": float(tee_series.iloc[-1]),
        "PMRI_current": pmri_value,
        "IBGR_total_current": ibgr_total,
        "IBGR_per_share_3y": ibgr_per_share,
        "IFRD_mean": ifrd_summary["mean"],
        "IFRD_p95": ifrd_summary["p95"],
        "survival_prob_3y_eps0": survival_eps0,
        "survival_prob_3y_eps10pct": survival_eps10,
        "dividend_coverage_ratio_current": dcr_current,
        "dividend_coverage_ratio_3y_mean": dcr_sim["mean"],
        "dividend_coverage_prob_undercovered_3y": dcr_sim["prob_undercovered"],
        "pi_star_current": pi_star_current,
        "mispricing_delta_current": delta_current,
        "mispricing_z_score_current": z_score_current,
        "reflexivity_gain_current": gain_current,
        "kappa_eff_current": kappa_eff_current,
        "pi_crit_current": pi_crit_current,
        "distance_to_tipping": distance_to_tipping,
        "WACBA_current": wacba_current,
    }

    with open(RESULTS_DIR / "indicators.json", "w", encoding="utf-8") as f:
        json.dump(indicators, f, indent=2)

    # 7. Plots
    plot_core_timeseries(panel, ile_series, tee_series, FIGURES_DIR)
    plot_ifrd_histogram(G, FIGURES_DIR)
    plot_fair_premium_vs_actual(panel, pi_star_series, FIGURES_DIR)
    plot_mispricing_timeseries(mispricing_df, FIGURES_DIR)

    if pref is not None:
        plot_capital_structure(
            pref.detail,
            debt_total=d0,
            asset_total=h0 * s0,
            outdir=FIGURES_DIR,
        )

    # 8. Preferred stock detail
    if pref is not None:
        pref_info = {
            "total_liquidation_value": pref.total_liquidation_value,
            "total_annual_dividend": pref.total_annual_dividend,
            "convertible_shares": pref.convertible_shares,
            "conversion_dilution_shares": pref.conversion_dilution_shares,
            "series": pref.detail[
                ["ticker", "name", "liquidation_pref_per_share",
                 "dividend_rate_pct", "shares_outstanding", "is_convertible",
                 "total_liquidation_value", "total_annual_dividend"]
            ].to_dict(orient="records"),
        }
        with open(RESULTS_DIR / "preferred_stock.json", "w", encoding="utf-8") as f:
            json.dump(pref_info, f, indent=2, default=str)

    # 9. Markdown summary report
    summary_path = RESULTS_DIR / "summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# Strategy (MSTR) BTC Structural Model -- Summary\n\n")
        f.write(f"**As of date:** {indicators['current_date']}\n\n")

        f.write("## Capital Structure\n\n")
        f.write(f"- **BTC Holdings:** {h0:,.0f} BTC\n")
        f.write(f"- **BTC Price:** ${s0:,.2f}\n")
        f.write(f"- **BTC Asset Value:** ${h0*s0/1e9:,.2f}B\n")
        f.write(f"- **Debt:** ${d0/1e9:,.2f}B\n")
        f.write(f"- **Preferred Liquidation Value:** ${pref_liq/1e9:,.2f}B\n")
        f.write(f"- **Preferred Annual Dividend:** ${pref_div/1e6:,.1f}M\n")
        f.write(f"- **Common Shares:** {n0/1e6:,.1f}M\n\n")

        if pref is not None:
            f.write("### Preferred Stock Detail\n\n")
            f.write("| Ticker | Div Rate | Shares | Liq Value | Annual Div | Convertible |\n")
            f.write("|--------|----------|--------|-----------|------------|-------------|\n")
            for _, row in pref.detail.iterrows():
                f.write(
                    f"| {row['ticker']} | {row['dividend_rate_pct']:.1f}% "
                    f"| {row['shares_outstanding']/1e6:.1f}M "
                    f"| ${row['total_liquidation_value']/1e9:.2f}B "
                    f"| ${row['total_annual_dividend']/1e6:.0f}M "
                    f"| {'Yes' if row['is_convertible'] else 'No'} |\n"
                )
            f.write("\n")

        f.write("## Calibrated Parameters\n\n")
        for k, v in params.to_dict().items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Key Indicators\n\n")
        for k, v in indicators.items():
            f.write(f"- **{k}**: {v}\n")

        f.write("\n## Theory Indicators\n\n")
        f.write(f"- **Fair Premium (pi*):** {pi_star_current:.4f}\n")
        f.write(f"- **Mispricing (Delta):** {delta_current:.4f}\n")
        f.write(f"- **Mispricing z-score:** {z_score_current:.2f}\n")
        f.write(f"- **Reflexivity Gain (G):** {gain_current:.4f}\n")
        f.write(f"- **Effective kappa:** {kappa_eff_current:.3f}\n")
        f.write(f"- **Tipping Point (pi_crit):** {pi_crit_current:.4f}\n")
        f.write(f"- **Distance to Tipping:** {distance_to_tipping:.4f}\n")
        f.write(f"- **WACBA:** {wacba_current:.4f}\n")

    # 10. Basic textual summary to stdout
    print("=== Capital Structure ===")
    print(f"BTC Holdings: {h0:,.0f}")
    print(f"BTC Price: ${s0:,.2f}")
    print(f"Assets: ${h0*s0/1e9:,.2f}B")
    print(f"Debt: ${d0/1e9:,.2f}B")
    print(f"Preferred Liq: ${pref_liq/1e9:,.2f}B")
    print(f"Preferred Annual Div: ${pref_div/1e6:,.1f}M")

    print("\n=== Calibrated parameters ===")
    for k, v in params.to_dict().items():
        print(f"{k}: {v}")

    print("\n=== Key indicators ===")
    for k, v in indicators.items():
        print(f"{k}: {v}")

    print("\n=== Theory indicators ===")
    print(f"Fair Premium (pi*): {pi_star_current:.4f}")
    print(f"Mispricing (Delta): {delta_current:.4f}")
    print(f"Mispricing z-score: {z_score_current:.2f}")
    print(f"Reflexivity Gain (G): {gain_current:.4f}")
    print(f"Effective kappa: {kappa_eff_current:.3f}")
    print(f"Tipping Point (pi_crit): {pi_crit_current:.4f}")
    print(f"Distance to Tipping: {distance_to_tipping:.4f}")
    print(f"WACBA: {wacba_current:.4f}")


if __name__ == "__main__":
    main()
