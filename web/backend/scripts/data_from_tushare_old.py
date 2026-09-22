from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd
import tushare as ts

DEFAULT_INDEX_MARKETS: Tuple[str, ...] = ("SSE", "SZSE", "CSI", "CNI")


def _empty_dataframe(columns: Iterable[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _normalize_date(value: Any) -> pd.Timestamp:
    if value in (None, "", "None"):
        return pd.NaT
    return pd.to_datetime(value, errors="coerce")


def _filter_active(data: pd.DataFrame, as_of: date) -> pd.DataFrame:
    result = data.copy()
    if result.empty:
        return result

    if "list_date" in result.columns:
        list_date = result["list_date"].map(_normalize_date)
        result = result.loc[list_date.isna() | (list_date <= pd.Timestamp(as_of))]

    for date_column in ("delist_date", "exp_date"):
        if date_column in result.columns:
            inactive_date = result[date_column].map(_normalize_date)
            result = result.loc[inactive_date.isna() | (inactive_date >= pd.Timestamp(as_of))]

    if "status" in result.columns:
        result = result.loc[result["status"].astype(str).str.upper() == "L"]

    return result.reset_index(drop=True)


def _fetch(func: Any, **kwargs: Any) -> pd.DataFrame:
    result = func(**kwargs)
    return pd.DataFrame() if result is None else result


def _select_columns(data: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    return data.loc[:, [column for column in columns if column in data.columns]]


def fetch_stock_list(pro_api: Any, as_of: date) -> pd.DataFrame:
    raw = _fetch(pro_api.stock_basic, exchange="", list_status="L")
    result = _filter_active(raw, as_of)
    return _select_columns(result, ("ts_code", "symbol", "name", "exchange", "industry", "list_date"))


def fetch_index_list(
        pro_api: Any,
        as_of: date,
        markets: Tuple[str, ...] = DEFAULT_INDEX_MARKETS,
) -> pd.DataFrame:
    frames = []
    for market in markets:
        raw = _fetch(pro_api.index_basic, market=market)
        if not raw.empty:
            raw = raw.copy()
            raw["market"] = market
        frames.append(raw)

    if not frames:
        return _empty_dataframe(("ts_code", "name", "market", "publisher", "category", "list_date", "exp_date"))

    raw = pd.concat(frames, ignore_index=True)
    result = _filter_active(raw, as_of).drop_duplicates(subset=["ts_code"], keep="first")
    return _select_columns(result, ("ts_code", "name", "market", "publisher", "category", "list_date", "exp_date"))


def fetch_etf_list(pro_api: Any, as_of: date) -> pd.DataFrame:
    raw = _fetch(pro_api.fund_basic, market="E", status="L")
    result = _filter_active(raw, as_of)
    columns = ("ts_code", "name", "management", "custodian", "fund_type", "list_date", "delist_date")

    if result.empty:
        return _empty_dataframe(columns)

    if "fund_type" in result.columns:
        fund_type = result["fund_type"].fillna("").astype(str).str.upper().str.strip()
        result = result.loc[fund_type == "ETF"]

    if result.empty:
        result = raw.loc[raw["name"].fillna("").str.contains("ETF", case=False, na=False)]
        result = _filter_active(result, as_of)

    return _select_columns(result.drop_duplicates(subset=["ts_code"], keep="first"), columns)


def fetch_current_a_share_lists(
        token: str,
        as_of: Optional[date] = None,
        index_markets: Tuple[str, ...] = DEFAULT_INDEX_MARKETS,
) -> Dict[str, pd.DataFrame]:
    as_of = as_of or date.today()
    pro_api = ts.pro_api(token)
    return {
        "stock": fetch_stock_list(pro_api, as_of),
        "index": fetch_index_list(pro_api, as_of, index_markets),
        "etf": fetch_etf_list(pro_api, as_of),
    }


def main() -> None:
    TUSHARE_TOKEN = "ac46d24be66cf2ed037f517378d67874e8294eaf5908f39af23d04f5"

    lists = fetch_current_a_share_lists(
        TUSHARE_TOKEN,
        index_markets=tuple(market.upper() for market in DEFAULT_INDEX_MARKETS),
    )


if __name__ == "__main__":
    main()
