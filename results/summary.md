# Strategy (MSTR) BTC Structural Model -- Summary

**As of date:** 2026-03-17

## Capital Structure

- **BTC Holdings:** 761,068 BTC
- **BTC Price:** $73,909.36
- **BTC Asset Value:** $56.25B
- **Debt:** $8.22B
- **Preferred Liquidation Value:** $10.23B
- **Preferred Annual Dividend:** $976.6M
- **Common Shares:** 320.4M

### Preferred Stock Detail

| Ticker | Div Rate | Shares | Liq Value | Annual Div | Convertible |
|--------|----------|--------|-----------|------------|-------------|
| STRK | 8.0% | 12.8M | $1.28B | $102M | Yes |
| STRF | 10.0% | 10.5M | $1.05B | $105M | No |
| STRC | 9.6% | 50.0M | $5.00B | $479M | No |
| STRD | 10.0% | 25.0M | $2.50B | $250M | No |
| STRE | 10.0% | 5.0M | $0.40B | $40M | No |

## Calibrated Parameters

- **mu_s**: 0.11119021353118116
- **sigma_s**: 0.48649820207568567
- **rho**: -0.3680159137155432
- **gamma_pi_s**: -3.5970287536571397
- **debt_0**: 8222070000.0
- **shares_0**: 320440000.0
- **preferred_liq_0**: 10229353900.0
- **preferred_annual_div_0**: 976573822.0
- **nav_floor**: 1.0
- **ou_kappa**: 5.2136544604770165
- **ou_theta**: 1.0805109745558952
- **ou_sigma**: 3.7943578361266157
- **holdings_alpha**: 0.0
- **holdings_lambda_m**: 19.04976051091006
- **holdings_mean_jump_size**: 7043.551020408163

## Key Indicators

- **current_date**: 2026-03-17
- **S0**: 73909.36
- **H0**: 761068.0
- **D0**: 8222070000.0
- **N0**: 320440000.0
- **preferred_liq_total**: 10229353900.0
- **preferred_annual_div_total**: 976573822.0
- **pi0**: 0.24216726950671505
- **ILE_current**: 1.488150665547579
- **TEE_current**: -2.108878088109561
- **PMRI_current**: -0.7134605135110367
- **IBGR_total_current**: 0.17630219649906664
- **IBGR_per_share_3y**: 0.1761834832175858
- **IFRD_mean**: 35327916376.529175
- **IFRD_p95**: 71779486368.09663
- **survival_prob_3y_eps0**: 0.919
- **survival_prob_3y_eps10pct**: 0.8908
- **dividend_coverage_ratio_current**: 49.18008010712374
- **dividend_coverage_ratio_3y_mean**: 113.69384101704367
- **dividend_coverage_prob_undercovered_3y**: 0.01
- **pi_star_current**: 0.03376858078089663
- **mispricing_delta_current**: 0.2083986887258184
- **mispricing_z_score_current**: 0.2679567213447082
- **reflexivity_gain_current**: 4.885477689646627e-07
- **kappa_eff_current**: 5.2136519133577615
- **pi_crit_current**: -1.1146653649167593
- **distance_to_tipping**: 1.3568326344234742
- **WACBA_current**: 0.01736129733030759

## Theory Indicators

- **Fair Premium (pi*):** 0.0338
- **Mispricing (Delta):** 0.2084
- **Mispricing z-score:** 0.27
- **Reflexivity Gain (G):** 0.0000
- **Effective kappa:** 5.214
- **Tipping Point (pi_crit):** -1.1147
- **Distance to Tipping:** 1.3568
- **WACBA:** 0.0174
