from __future__ import annotations

import os
import pickle
import time
import requests
import math
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional, Tuple

import pandas as pd
import tushare as ts

from CLPainter.web.backend.app._config.settings import settings

INDEX_MARKETS: Tuple[str, ...] = ("SSE", "SZSE", "CSI", "MSCI", "CICC", "SW", "OTH", "CNI")
DEFAULT_HISTORY_END = date(2008, 12, 31)
OUTPUT_DIR = Path(settings.OLD_DATA_DIR)
FREQUENCY_DIR = "freq=1day"
MARKET_DIR = "market=cn"
CATEGORY_ASSET_CLASS_DIRS = {
    "stock": "asset_class=stock",
    "index": "asset_class=index",
    "etf": "asset_class=fund",
}
PV_FIELD_ORDER = ("open", "close", "low", "high", "volume")
DEFAULT_REQUEST_INTERVAL_SECONDS = 0.13
REQUEST_MAX_ATTEMPTS = 5
REQUEST_RETRY_WAIT_SECONDS = 5.0
LISTS_CACHE_PATH = OUTPUT_DIR / "tushare_lists.pkl"
HISTORY_COLUMNS: Tuple[str, ...] = ("ts_code", "trade_date", *PV_FIELD_ORDER)
CATEGORIES: Tuple[str, ...] = ("stock", "index", "etf")

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


def _fetch_with_retry(func: Any, request_name: str, **kwargs: Any) -> pd.DataFrame:
    for attempt in range(1, REQUEST_MAX_ATTEMPTS + 1):
        try:
            return _fetch(func, **kwargs)
        except requests.RequestException as error:
            if attempt == REQUEST_MAX_ATTEMPTS:
                raise
            wait_seconds = REQUEST_RETRY_WAIT_SECONDS * attempt
            print(f"\n{request_name} 请求失败，{wait_seconds:.0f} 秒后重试（第 {attempt}/{REQUEST_MAX_ATTEMPTS - 1} 次）: {error}")
            time.sleep(wait_seconds)
    raise RuntimeError("unreachable retry state")


def _select_columns(data: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    return data.loc[:, [column for column in columns if column in data.columns]]


def _convert_history_to_pv_list(data: pd.DataFrame) -> list:
    if data.empty:
        return []

    history = data.copy()
    history["trade_date"] = history["trade_date"].map(_normalize_date).dt.strftime("%Y-%m-%d")
    history = history.dropna(subset=list(PV_FIELD_ORDER))
    history = history.loc[
        history[list(PV_FIELD_ORDER)].map(lambda value: math.isfinite(float(value))).all(axis=1)
    ]
    history = history.sort_values("trade_date")
    return [
        [trade_date, *(float(row[field]) for field in PV_FIELD_ORDER)]
        for trade_date, row in zip(history["trade_date"], history.to_dict("records"))
    ]


def fetch_stock_list(pro_api: Any, as_of: date) -> pd.DataFrame:
    raw = _fetch_with_retry(pro_api.stock_basic, "stock_basic", exchange="", list_status="L")
    result = _filter_active(raw, as_of)
    return _select_columns(result, ("ts_code", "symbol", "name", "exchange", "industry", "list_date"))


def fetch_index_list(
        pro_api: Any,
        as_of: date,
        markets: Tuple[str, ...] = INDEX_MARKETS,
) -> pd.DataFrame:
    frames = []
    for market in markets:
        raw = _fetch_with_retry(pro_api.index_basic, f"index_basic({market})", market=market)
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
    raw = _fetch_with_retry(pro_api.fund_basic, "fund_basic", market="E", status="L")
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
        index_markets: Tuple[str, ...] = INDEX_MARKETS,
) -> Dict[str, pd.DataFrame]:
    as_of = as_of or date.today()
    pro_api = ts.pro_api(token)
    return {
        "stock": fetch_stock_list(pro_api, as_of),
        "index": fetch_index_list(pro_api, as_of, index_markets),
        "etf": fetch_etf_list(pro_api, as_of),
    }


def _load_cached_lists() -> Dict[str, pd.DataFrame]:
    if not LISTS_CACHE_PATH.is_file():
        return {}
    with LISTS_CACHE_PATH.open("rb") as file:
        cached = pickle.load(file)
    return cached if isinstance(cached, dict) else {}


def _cache_lists(lists: Dict[str, pd.DataFrame]) -> None:
    LISTS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = LISTS_CACHE_PATH.with_suffix(".pkl.tmp")
    with temporary_path.open("wb") as file:
        pickle.dump(lists, file, protocol=pickle.HIGHEST_PROTOCOL)
    temporary_path.replace(LISTS_CACHE_PATH)


def _format_tushare_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _history_api(pro_api: Any, category: str) -> Any:
    api_names = {
        "stock": "daily",
        "index": "index_daily",
        "etf": "fund_daily",
    }
    if category not in api_names:
        raise ValueError(f"不支持的历史行情类型: {category}")
    return getattr(pro_api, api_names[category])


def fetch_history_for_security(
        pro_api: Any,
        category: str,
        ts_code: str,
        start_date: Optional[date],
        end_date: date,
) -> pd.DataFrame:
    api = _history_api(pro_api, category)
    params: Dict[str, Any] = {
        "ts_code": ts_code,
        "end_date": _format_tushare_date(end_date),
    }
    if start_date is not None:
        params["start_date"] = _format_tushare_date(start_date)
    raw = _fetch_with_retry(api, ts_code, **params)
    if raw.empty:
        return _empty_dataframe(HISTORY_COLUMNS)
    raw = raw.rename(columns={"vol": "volume"})
    missing_columns = [column for column in HISTORY_COLUMNS if column not in raw.columns]
    if missing_columns:
        raise ValueError(f"{ts_code} 日线返回缺少字段: {', '.join(missing_columns)}")
    return raw.loc[:, HISTORY_COLUMNS]


def _iter_history_for_list(
        pro_api: Any,
        securities: pd.DataFrame,
        category: str,
        start_date: Optional[date],
        end_date: date,
        request_interval: float,
        history_dir: Optional[Path] = None,
) -> Iterator[Tuple[str, Optional[pd.DataFrame]]]:
    if "ts_code" not in securities.columns:
        return

    codes = securities["ts_code"].dropna().astype(str).str.strip()
    codes = list(dict.fromkeys(codes.loc[codes != ""].tolist()))
    end_timestamp = pd.Timestamp(end_date)

    for ts_code in codes:
        output_path = history_dir / f"{ts_code.replace('.', '')}.pkl" if history_dir is not None else None
        if output_path is not None and output_path.is_file() and output_path.stat().st_size > 0:
            yield ts_code, None
            continue

        if "list_date" in securities.columns:
            match = securities.loc[securities["ts_code"].astype(str) == ts_code, "list_date"]
            if not match.empty:
                listed_date = _normalize_date(match.iloc[0])
                if pd.notna(listed_date) and listed_date > end_timestamp:
                    yield ts_code, _empty_dataframe(HISTORY_COLUMNS)
                    continue

        yield ts_code, fetch_history_for_security(pro_api, category, ts_code, start_date, end_date)
        if request_interval > 0:
            time.sleep(request_interval)


def _save_history(history_dir: Path, ts_code: str, data: pd.DataFrame) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    output_path = history_dir / f"{ts_code.replace('.', '')}.pkl"
    temporary_path = output_path.with_suffix(".pkl.tmp")
    pv_list = _convert_history_to_pv_list(data)
    with temporary_path.open("wb") as file:
        pickle.dump(pv_list, file, protocol=pickle.HIGHEST_PROTOCOL)
    temporary_path.replace(output_path)
    return output_path


def _get_asset_class_dir(category: str) -> str:
    if category not in CATEGORY_ASSET_CLASS_DIRS:
        raise ValueError(f"不支持的资产类型: {category}")
    return CATEGORY_ASSET_CLASS_DIRS[category]


def _get_history_dir(output_dir: Path, category: str) -> Path:
    return output_dir / FREQUENCY_DIR / MARKET_DIR / _get_asset_class_dir(category)


def main() -> None:
    token  = "ac46d24be66cf2ed037f517378d67874e8294eaf5908f39af23d04f5"
    if not token:
        raise ValueError("请通过环境变量 TUSHARE_TOKEN 提供 Tushare token")
    lists = _load_cached_lists()
    if not lists:
        lists = fetch_current_a_share_lists(token, index_markets=INDEX_MARKETS)
        _cache_lists(lists)

    pro_api = ts.pro_api(token)
    for category in CATEGORIES:
        securities = lists[category]
        history_dir = _get_history_dir(OUTPUT_DIR, category)
        print(f"{category}: 当前上市 {len(securities)} 只，开始抓取最早可用数据至 {DEFAULT_HISTORY_END}")

        saved_count = 0
        empty_count = 0
        skipped_count = 0
        histories = _iter_history_for_list(
            pro_api,
            securities,
            category,
            None,
            DEFAULT_HISTORY_END,
            DEFAULT_REQUEST_INTERVAL_SECONDS,
            history_dir=history_dir,
        )
        for ts_code, history in histories:
            if history is None:
                skipped_count += 1
                continue

            _save_history(history_dir, ts_code, history)
            if history.empty:
                empty_count += 1
            else:
                saved_count += 1
            print(
                f"\r{category}: 已保存 {saved_count}，无数据 {empty_count}，续跑跳过 {skipped_count}",
                end="",
                flush=True,
            )
        print()

if __name__ == "__main__":
    main()
