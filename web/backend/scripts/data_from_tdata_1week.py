from concurrent.futures import ThreadPoolExecutor, as_completed
import pickle
from pathlib import Path

import pandas as pd

from CLPainter.web.backend.app._config.settings import settings


MAX_WORKERS = 10
SOURCE_FREQUENCY = "freq=1day"
TARGET_FREQUENCY = "freq=1week"
MARKET_DIR = "market=cn"
FIELDS = ["open", "close", "low", "high", "volume"]
ASSET_CLASS_DIRS = {
    "stock": "asset_class=stock",
    "index": "asset_class=index",
    "etf": "asset_class=fund",
}


def load_daily_list(source_path: Path) -> list:
    if not source_path.is_file():
        raise FileNotFoundError(f"日K数据不存在: {source_path}")

    with source_path.open("rb") as file:
        daily_list = pickle.load(file)
    if not isinstance(daily_list, list):
        raise ValueError(f"日K数据格式错误，应为 list: {source_path}")
    if any(len(row) != len(FIELDS) + 1 for row in daily_list):
        raise ValueError(f"日K数据字段数量错误: {source_path}")
    return daily_list


def aggregate_daily_to_weekly(daily_list: list) -> list:
    if not daily_list:
        return []

    daily = pd.DataFrame(daily_list, columns=["trade_date", *FIELDS])
    daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="raise")
    daily = daily.sort_values("trade_date")
    if daily["trade_date"].duplicated().any():
        raise ValueError("日K数据存在重复日期")

    daily["week_start"] = daily["trade_date"] - pd.to_timedelta(daily["trade_date"].dt.weekday, unit="D")
    weekly = daily.groupby("week_start", sort=True).agg({
        "trade_date": "last",
        "open": "first",
        "close": "last",
        "low": "min",
        "high": "max",
        "volume": "sum",
    })
    return [
        [trade_date.strftime("%Y-%m-%d"), *map(float, row)]
        for trade_date, row in zip(weekly["trade_date"], weekly[FIELDS].to_numpy())
    ]


def save_weekly_list(output_path: Path, weekly_list: list) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as file:
        pickle.dump(weekly_list, file, protocol=pickle.HIGHEST_PROTOCOL)


def transform_and_save_symbol(source_path: Path, output_path: Path) -> bool:
    weekly_list = aggregate_daily_to_weekly(load_daily_list(source_path))
    save_weekly_list(output_path, weekly_list)
    return True


def clean_stale_files(output_dir: Path, generated_files: set) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("*.pkl"):
        if path.is_file() and path.name not in generated_files:
            path.unlink()


def convert_asset_class(asset_class: str, source_root: Path, output_root: Path) -> set:
    source_dir = source_root / SOURCE_FREQUENCY / MARKET_DIR / ASSET_CLASS_DIRS[asset_class]
    output_dir = output_root / TARGET_FREQUENCY / MARKET_DIR / ASSET_CLASS_DIRS[asset_class]
    generated_files = set()
    futures = {}
    source_files = list(source_dir.glob("*.pkl"))

    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(source_files)))) as executor:
        for source_path in source_files:
            future = executor.submit(transform_and_save_symbol, source_path, output_dir / source_path.name)
            futures[future] = source_path.name

    output_dir.mkdir(parents=True, exist_ok=True)
    for future in as_completed(futures):
        future.result()
        generated_files.add(futures[future])

    clean_stale_files(output_dir, generated_files)
    return generated_files


if __name__ == "__main__":
    data_root = Path(settings.DATA_DIR)
    for asset_class in ASSET_CLASS_DIRS:
        files = convert_asset_class(asset_class, data_root, data_root)
        print(f"{asset_class}: 已生成周线 {len(files)} 个标的")
