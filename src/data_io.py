from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


DATA_ROOT = Path(".")


def load_tbill_curve(
    path: str | Path = DATA_ROOT / "3-month-tbill-yield-curve.csv",
) -> pd.DataFrame:
    """
    Load the 3-month T-bill yield curve and return a daily risk-free rate series.

    The CSV is expected to match the provided file with columns
    ``observation_date`` and ``DTB3`` (percent).
    """
    df = pd.read_csv(path)
    if "observation_date" not in df.columns or "DTB3" not in df.columns:
        raise ValueError("3-month T-bill file must have 'observation_date' and 'DTB3'.")

    df = df.rename(
        columns={
            "observation_date": "date",
            "DTB3": "rf_rate_pct",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    df["rf_rate"] = df["rf_rate_pct"] / 100.0
    rf_daily = (
        df.set_index("date")[["rf_rate"]]
        .sort_index()
        .resample("D")
        .ffill()
    )
    return rf_daily


def load_btc_holdings(
    path: str | Path = DATA_ROOT / "mstr-btc-holdings-over-time.csv",
) -> pd.DataFrame:
    """
    Load the BTC holdings over time and resample to a daily series.

    Returns
    -------
    pd.DataFrame
        Daily DataFrame with a DatetimeIndex and a single column ``btc_holdings``.
    """
    df = pd.read_csv(path)
    # Some CSVs may contain a BOM on the first column name.
    first_col = df.columns[0]
    if first_col != "DateTime":
        df = df.rename(columns={first_col: "DateTime"})

    df["DateTime"] = pd.to_datetime(df["DateTime"])
    if "BTC holdings" not in df.columns:
        raise ValueError("Expected 'BTC holdings' column in holdings CSV.")

    holdings_daily = (
        df.rename(columns={"BTC holdings": "btc_holdings"})
        .set_index("DateTime")[["btc_holdings"]]
        .sort_index()
        .resample("D")
        .ffill()
    )
    return holdings_daily


def load_btc_purchase_history(
    path: str | Path = DATA_ROOT / "mstr-btc-purchase-history.csv",
) -> pd.DataFrame:
    """
    Load the BTC purchase history table.

    The source file is tab-delimited with human-formatted dollar fields.
    This loader parses the date and numeric BTC amounts and leaves
    dollar-valued columns as raw strings for now.
    """
    df = pd.read_csv(path, delimiter="\t")
    if "Date" not in df.columns:
        raise ValueError("Expected 'Date' column in BTC purchase history CSV.")

    # The Date column contains a mix of simple dates and ranges, e.g.
    # "04/01/2024 - 05/01/2024". For our purposes we take the first
    # date token as the event date.
    def _parse_date(s: Optional[str]) -> Optional[pd.Timestamp]:
        if pd.isna(s):
            return None
        parts = str(s).split("-")[0].strip()
        try:
            return pd.to_datetime(parts, format="%m/%d/%Y")
        except Exception:
            try:
                return pd.to_datetime(parts)
            except Exception:
                return None

    df["Date"] = df["Date"].map(_parse_date)
    df = df.dropna(subset=["Date"])

    # Basic numeric cleaning for BTC Purchased and Total Bitcoin.
    def _clean_number(x: Optional[str]) -> Optional[float]:
        if pd.isna(x):
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace(",", "").replace("+", "").strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    if "BTC Purchased" in df.columns:
        df["btc_purchased_num"] = df["BTC Purchased"].map(_clean_number)
    if "Total Bitcoin" in df.columns:
        df["total_btc_num"] = df["Total Bitcoin"].map(_clean_number)

    df = df.sort_values("Date").set_index("Date")
    return df


def load_mstr_daily_price_shares(
    path: str | Path = DATA_ROOT / "mstr-daily-price&shares.csv",
) -> pd.DataFrame:
    """
    Load daily MSTR close price and shares outstanding from Compustat.

    The CSV is expected to have columns:
    - tic, datadate, ajexdi, cshoc, prccd, ...

    We construct:
    - mstr_prc_adj: use closing price ``prccd`` (market cap is prccd * cshoc).
    - shares: use ``cshoc`` as reported.
    """
    df = pd.read_csv(path)
    if "datadate" not in df.columns or "prccd" not in df.columns or "cshoc" not in df.columns:
        raise ValueError("Expected 'datadate', 'prccd', and 'cshoc' in MSTR daily file.")

    df["datadate"] = pd.to_datetime(df["datadate"])
    df = df.sort_values("datadate")

    df["prccd"] = df["prccd"].astype(float)
    df["cshoc"] = df["cshoc"].astype(float)

    df["mstr_prc_adj"] = df["prccd"]
    df["shares"] = df["cshoc"]

    return df.set_index("datadate")[["mstr_prc_adj", "shares"]]


def load_mstr_balance_sheet_basic(
    path: str | Path = DATA_ROOT / "mstr-balance-sheet-basic.csv",
) -> pd.DataFrame:
    """
    Load basic quarterly balance-sheet information for MSTR from Compustat.

    We focus on:
    - dlcq: current (short-term) debt, in millions.
    - dlttq: long-term debt, in millions.

    and construct:
    - debt_total_usd = (dlcq + dlttq) * 1_000_000.
    """
    df = pd.read_csv(path)
    required = {"datadate", "dlcq", "dlttq"}
    if not required.issubset(df.columns):
        raise ValueError("Balance sheet file must contain 'datadate', 'dlcq', and 'dlttq'.")

    df["datadate"] = pd.to_datetime(df["datadate"])
    df = df.sort_values("datadate")

    df["dlcq"] = df["dlcq"].fillna(0.0).astype(float)
    df["dlttq"] = df["dlttq"].fillna(0.0).astype(float)
    df["debt_total_usd"] = (df["dlcq"] + df["dlttq"]) * 1_000_000.0

    return df.set_index("datadate")[["debt_total_usd"]]


def load_preferred_stock(
    path: str | Path = DATA_ROOT / "data" / "preferred_stock.csv",
) -> pd.DataFrame:
    """
    Load preferred stock data (STRK, STRF, STRC, STRD, STRE).

    Returns DataFrame with columns: ticker, name, liquidation_pref_per_share,
    dividend_rate_pct, annual_dividend_per_share, shares_outstanding,
    is_convertible, conversion_ratio_to_mstr, seniority_rank,
    total_liquidation_value, total_annual_dividend.
    """
    df = pd.read_csv(path)
    df["is_convertible"] = df["is_convertible"].astype(bool)
    df["shares_outstanding"] = df["shares_outstanding"].astype(float)
    df["liquidation_pref_per_share"] = df["liquidation_pref_per_share"].astype(float)
    df["annual_dividend_per_share"] = df["annual_dividend_per_share"].astype(float)
    df["conversion_ratio_to_mstr"] = df["conversion_ratio_to_mstr"].astype(float)

    df["total_liquidation_value"] = df["liquidation_pref_per_share"] * df["shares_outstanding"]
    df["total_annual_dividend"] = df["annual_dividend_per_share"] * df["shares_outstanding"]
    return df


def load_btc_daily() -> pd.DataFrame:
    """
    Load daily BTC-USD prices from CryptoDataDownload (Binance BTCUSDT daily).

    Returns
    -------
    pd.DataFrame
        DataFrame indexed by Date with a single column ``btc_price``.
    """
    url = "https://www.cryptodatadownload.com/cdd/Binance_BTCUSDT_d.csv"
    btc = pd.read_csv(url, skiprows=1)
    if "Date" not in btc.columns or "Close" not in btc.columns:
        raise ValueError("Unexpected BTC CSV format from CryptoDataDownload.")

    btc["Date"] = pd.to_datetime(btc["Date"])
    btc_daily = (
        btc.set_index("Date")[["Close"]]
        .rename(columns={"Close": "btc_price"})
        .sort_index()
    )
    return btc_daily
