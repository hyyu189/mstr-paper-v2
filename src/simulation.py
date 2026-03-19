from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np

from .calibration import ModelParams


@dataclass
class SimulationConfig:
    """
    Configuration for Monte Carlo simulations under the historical measure.
    """

    n_paths: int = 5000
    years: float = 3.0
    dt: float = 1.0 / 252.0
    random_seed: int = 42

    @property
    def n_steps(self) -> int:
        return int(self.years / self.dt)


def simulate_paths(
    params: ModelParams,
    s0: float,
    pi0: float,
    h0: float,
    d0: float,
    n0: float,
    config: SimulationConfig | None = None,
) -> Dict[str, np.ndarray]:
    """
    Simulate joint paths of (S_t, pi_t, H_t, N_t, D_t, E_t, B_t, NAV_t).

    NAV includes preferred stock: NAV = H*S - D - P_liq.
    Debt, share count, and preferred liquidation value are held constant.
    """
    if config is None:
        config = SimulationConfig()

    n_steps = config.n_steps
    n_paths = config.n_paths
    dt = config.dt

    mu_s = params.mu_s
    sigma_s = params.sigma_s
    ou = params.ou_premium
    rho = params.rho
    holdings = params.holdings
    pref_liq = params.preferred_liq_0

    rng = np.random.default_rng(config.random_seed)

    # Correlated normals for BTC and premium shocks.
    corr_matrix = np.array([[1.0, rho], [rho, 1.0]])
    L = np.linalg.cholesky(corr_matrix)

    # Allocate arrays: time dimension first, path dimension second.
    shape = (n_steps + 1, n_paths)
    S = np.zeros(shape)
    PI = np.zeros(shape)
    H = np.zeros(shape)
    D = np.zeros(shape)
    N = np.zeros(shape)
    A = np.zeros(shape)
    NAV_raw = np.zeros(shape)
    NAV = np.zeros(shape)
    NAV_clip = np.zeros(shape)
    E = np.zeros(shape)
    B = np.zeros(shape)

    # Initial state broadcast across paths.
    S[0, :] = float(s0)
    PI[0, :] = float(pi0)
    H[0, :] = float(h0)
    D[:, :] = float(d0)
    N[:, :] = float(n0)

    A[0, :] = H[0, :] * S[0, :]
    NAV_raw[0, :] = A[0, :] - D[0, :] - pref_liq
    NAV[0, :] = np.maximum(NAV_raw[0, :], 0.0)
    NAV_clip[0, :] = np.maximum(NAV_raw[0, :], params.nav_floor)
    E[0, :] = np.exp(PI[0, :]) * NAV[0, :]
    B[0, :] = H[0, :] / N[0, :]

    # Precompute OU transition constants.
    exp_neg_kdt = np.exp(-ou.kappa * dt)
    ou_mean_coef = exp_neg_kdt
    ou_const = ou.theta * (1.0 - exp_neg_kdt)
    ou_var = ou.sigma ** 2 * (1.0 - np.exp(-2.0 * ou.kappa * dt)) / (2.0 * ou.kappa)
    ou_std = np.sqrt(ou_var)

    for t in range(n_steps):
        # Correlated shocks.
        z_indep = rng.standard_normal(size=(2, n_paths))
        z_s, z_pi = L @ z_indep

        # BTC price (GBM with exact discretization).
        s_t = S[t, :]
        drift = (mu_s - 0.5 * sigma_s ** 2) * dt
        diffusion = sigma_s * np.sqrt(dt) * z_s
        S[t + 1, :] = s_t * np.exp(drift + diffusion)

        # Premium OU (exact discretization).
        pi_t = PI[t, :]
        PI[t + 1, :] = ou_const + ou_mean_coef * pi_t + ou_std * z_pi

        # Holdings: continuous plus jump component.
        h_t = H[t, :]
        pi_pos = np.maximum(pi_t, 0.0)
        h_cont = h_t + holdings.alpha * pi_pos * dt

        # Jumps: Poisson(lambda_M * dt) with constant jump size = mean_jump_size.
        if holdings.lambda_m > 0.0 and holdings.mean_jump_size != 0.0:
            n_events = rng.poisson(lam=holdings.lambda_m * dt, size=n_paths)
            h_jump = n_events * holdings.mean_jump_size
        else:
            h_jump = 0.0

        H[t + 1, :] = np.maximum(h_cont + h_jump, 0.0)

        # Balance-sheet quantities (NAV = Assets - Debt - Preferred Liquidation).
        A[t + 1, :] = H[t + 1, :] * S[t + 1, :]
        NAV_raw[t + 1, :] = A[t + 1, :] - D[t + 1, :] - pref_liq
        NAV[t + 1, :] = np.maximum(NAV_raw[t + 1, :], 0.0)
        NAV_clip[t + 1, :] = np.maximum(NAV_raw[t + 1, :], params.nav_floor)

        # Equity and BTC per share from structural relation.
        E[t + 1, :] = np.exp(PI[t + 1, :]) * NAV[t + 1, :]
        B[t + 1, :] = H[t + 1, :] / N[t + 1, :]

    return {
        "S": S,
        "PI": PI,
        "H": H,
        "D": D,
        "N": N,
        "A": A,
        "NAV_raw": NAV_raw,
        "NAV": NAV,
        "NAV_clip": NAV_clip,
        "E": E,
        "B": B,
    }
