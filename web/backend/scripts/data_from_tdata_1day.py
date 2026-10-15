# 只需要未复权（除权）数据
from bisect import bisect_left, bisect_right
from tdata import fetch_data
import numpy as np
import pandas as pd
import pickle
from pathlib import Path
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from CLPainter.web.backend.app._config.settings import settings
from CLPainter.web.backend.app.db.base import engine
from CLPainter.web.backend.app.db.models import Instrument

START_DATE = "2009-01-01"
END_DATE = None
MAX_WORKERS = 10
MARKET_DIR = "market=cn"
ASSET_CLASS_DIR = "asset_class=stock"
FIELDS = ["open", "close", "low", "high", "volume"]
DR_FIELDS = [f"{j}_dr" for j in FIELDS]
OLD_DATA_CUTOFF = "2008-12-31"
OLD_DATA_ROOT = Path(settings.OLD_DATA_DIR)
ASSET_CLASS_DIRS = {
    "stock": "asset_class=stock",
    "index": "asset_class=index",
    "etf": "asset_class=fund",
}
SOURCE_CODE_SUFFIXES = ("CSI", "CNI", "SH", "SZ", "BJ")


def to_source_code(chart_code):
    """将 Instrument 中的图表代码还原为数据源代码，例如 000001SZ -> 000001.SZ。"""
    for suffix in SOURCE_CODE_SUFFIXES:
        if chart_code.endswith(suffix):
            return f"{chart_code[:-len(suffix)]}.{suffix}"
    return chart_code


def load_instrument_info(asset_class):
    """从 Instrument 读取当前有效标的的上市日期与精度。"""
    today = datetime.date.today()
    with Session(engine) as session:
        instruments = session.scalars(
            select(Instrument).where(
                Instrument.market == "cn",
                Instrument.asset_class == asset_class,
                Instrument.list_date.is_not(None),
                Instrument.list_date <= today,
                or_(Instrument.delist_date.is_(None), Instrument.delist_date > today),
            )
        ).all()

    return {
        to_source_code(instrument.code): {
            "list_date": instrument.list_date.strftime("%Y-%m-%d"),
            "price_precision": instrument.price_precision,
        }
        for instrument in instruments
    }


def load_old_pv_list(code, asset_class, start_date):
    """读取旧K线；上市不晚于2008-12-31的标的必须存在旧文件。"""
    if start_date > OLD_DATA_CUTOFF:
        return []

    asset_class_dir = ASSET_CLASS_DIRS[asset_class]
    old_dir = OLD_DATA_ROOT / "freq=1day" / MARKET_DIR / asset_class_dir
    symbol = code.split(".", 1)[0]
    candidates = [
        old_dir / f"{code.replace('.', '')}.pkl",
        old_dir / f"{symbol}SH.pkl",
        old_dir / f"{symbol}SZ.pkl",
        old_dir / f"{symbol}CSI.pkl",
        old_dir / f"{symbol}CNI.pkl",
    ]
    old_path = next((path for path in candidates if path.is_file() and path.stat().st_size > 0), None)
    if old_path is None:
        raise FileNotFoundError(
            f"{code} 上市时间早于等于 {OLD_DATA_CUTOFF}，但缺少有效旧数据文件，已尝试: "
            + ", ".join(str(path) for path in candidates)
        )

    with old_path.open("rb") as file:
        old_list = pickle.load(file)
    if not isinstance(old_list, list):
        raise ValueError(f"{code} 旧数据格式错误，应为 list: {old_path}")
    return old_list


def save_pv_list(output_path, old_list, new_list, code):
    """拼接旧新数据并校验日期顺序。"""
    final_list = old_list + new_list
    dates = [row[0] for row in final_list]
    if any(date_previous >= date_current for date_previous, date_current in zip(dates, dates[1:])):
        raise ValueError(f"{code} 拼接后日期非严格递增")
    with output_path.open("wb") as file:
        pickle.dump(final_list, file, protocol=pickle.HIGHEST_PROTOCOL)


def transform_and_save_symbol(symbol_idx, symbol, dates, field_arrays,
                              data_start_date, original_start_date, output_path, precision, asset_class="stock"):
    """校验并转换单个标的K线，然后写入目标pickle文件。"""
    start_idx = bisect_left(dates, data_start_date)
    end_idx = len(dates)
    if END_DATE:
        end_idx = bisect_right(dates, END_DATE)

    date_slice = dates[start_idx:end_idx]
    values = np.stack([
        field_array[symbol_idx, start_idx:end_idx]
        for field_array in field_arrays
    ])
    validation_values = values[:-1]
    invalid_mask = np.isnan(validation_values).any(axis=0) | (validation_values == 0).any(axis=0)
    if invalid_mask.any():
        first_invalid = start_idx + int(np.flatnonzero(invalid_mask)[0])
        print(f"{symbol} {date_slice[first_invalid - start_idx]}存在空值或0，不处理")
        return False

    rounded_values = np.round(values, decimals=precision)
    final_list = [
        [date, *values_on_date]
        for date, values_on_date in zip(date_slice, rounded_values.T.tolist())
    ]
    save_pv_list(
        output_path,
        load_old_pv_list(
            symbol,
            asset_class,
            original_start_date.strftime("%Y-%m-%d") if hasattr(original_start_date, "strftime") else original_start_date,
        ),
        final_list,
        symbol,
    )
    return True


def write_index_data(index_name, code, index_data, start_date, dsc_path):
    """将指数批量数据裁剪为标准K线列表并保存。"""
    effective_start_date = max(START_DATE, start_date) if START_DATE else start_date
    columns = ["open", "close", "low", "high", "volume"]
    data = [index_data[f"{index_name}_{column}"] for column in columns]
    concat_data = pd.concat(data, axis=1)
    concat_data.columns = columns
    concat_data = concat_data[concat_data.index >= effective_start_date]
    if END_DATE:
        concat_data = concat_data[concat_data.index <= END_DATE]

    concat_data.index = pd.DatetimeIndex(concat_data.index).strftime("%Y-%m-%d")
    final_list = concat_data.reset_index().values.tolist()
    save_pv_list(
        dsc_path / f"{code.replace('.', '')}.pkl",
        load_old_pv_list(code, "index", start_date),
        final_list,
        code,
    )


def clean_stale_files(dsc_path, generated_files):
    """删除本轮没有生成的历史数据文件。"""
    for path in dsc_path.iterdir():
        if path.is_file() and path.name not in generated_files:
            path.unlink()


def change_data_type_and_save(columns, dates, field_arrays, info_dict,
                              dsc_path, precision=None, asset_class="stock"):
    """并行转换有效标的K线，返回本轮成功生成的文件名集合。"""
    file_names = set()
    dsc_path = Path(dsc_path)
    dsc_path.mkdir(parents=True, exist_ok=True)
    futures = {}

    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(columns)))) as executor:
        for idx, column_name in enumerate(columns):
            instrument = info_dict.get(column_name)
            if instrument is None:
                continue
            original_start_date = instrument["list_date"]
            symbol_precision = instrument.get("price_precision", precision)
            if symbol_precision is None:
                raise ValueError(f"{column_name} 缺少价格精度")

            data_start_date = max(START_DATE, original_start_date) if START_DATE else original_start_date
            file_name = f"{column_name.replace('.', '')}.pkl"
            future = executor.submit(
                transform_and_save_symbol,
                idx,
                column_name,
                dates,
                field_arrays,
                data_start_date,
                original_start_date,
                dsc_path / file_name,
                symbol_precision,
                asset_class,
            )
            futures[future] = file_name

        for future in as_completed(futures):
            if future.result():
                file_names.add(futures[future])

    return file_names


if __name__ == "__main__":
    #########################################
    # 个股
    generated_files = set()
    stock_info_dict = load_instrument_info("stock")


    d = fetch_data(DR_FIELDS, start_date=START_DATE, end_date=END_DATE)

    first_key = list(d.keys())[0]
    dates = pd.DatetimeIndex(d[first_key].index).strftime("%Y-%m-%d").tolist()
    columns = [column for column in d[first_key].columns.tolist() if column in stock_info_dict]
    stock_field_arrays = []
    for column in DR_FIELDS:
        stock_field_arrays.append(d.pop(column)[columns].to_numpy().T.copy())
    del d

    generated_files.update(change_data_type_and_save(columns, dates, stock_field_arrays, stock_info_dict,
                                                     dsc_path=Path(settings.DATA_DIR, "freq=1day", MARKET_DIR, ASSET_CLASS_DIR)))
    del stock_field_arrays

    #########################################
    #  指数
    index_info_dict = load_instrument_info("index")

    index_map = {

        "hs300": "000300.SH",
        "zz500": "000905.SH",
        "zz1000": "000852.SH",
        "cybz": "399006.SZ",
        "zz985": "000985.SH",
        "kc50": "000688.SH",
        "szzs": "000001.SH",
        "sz50": "000016.SH",
        "szcz": "399001.SZ",
        "gz2000": "399303.SZ",
        "zz2000": "932000.SH",
        "zzhl": "000922.SH",
        "a500": "000510.SH",
        # "bz50": "899050.BJ",
        "kczz": "000680.SH",
    }

    file_names = set()
    dsc_path = Path(settings.DATA_DIR, "freq=1day", MARKET_DIR, ASSET_CLASS_DIR)
    columns = FIELDS
    index_data_names = [f"{index_name}_{column}" for index_name in index_map for column in columns]
    index_data = fetch_data(index_data_names, start_date=START_DATE, end_date=END_DATE)
    dsc_path.mkdir(parents=True, exist_ok=True)
    index_dsc_path = Path(settings.DATA_DIR, "freq=1day", MARKET_DIR, ASSET_CLASS_DIRS["index"])
    index_dsc_path.mkdir(parents=True, exist_ok=True)

    futures = {}
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(index_map)))) as executor:
        for index_name, code in index_map.items():
            start_date = index_info_dict.get(code)
            if start_date is None:
                print(f"指数 {code} 缺少 start_date，不处理")
                continue
            start_date = start_date["list_date"]

            future = executor.submit(
                write_index_data,
                index_name,
                code,
                index_data,
                start_date,
                index_dsc_path,
            )
            futures[future] = f"{code.replace('.', '')}.pkl"

        for future in as_completed(futures):
            future.result()
            file_names.add(futures[future])

    generated_files.update(file_names)
    del index_data

    #########################################
    # etf
    etf_info_dict = load_instrument_info("fund")

    cols = [f"etf_{column}_dr" for column in FIELDS]
    d = fetch_data(cols,start_date=START_DATE,end_date=END_DATE)
    dates = pd.DatetimeIndex(d[cols[0]].index).strftime("%Y-%m-%d").tolist()
    columns = [column for column in d[cols[0]].columns.tolist() if column in etf_info_dict]
    etf_field_arrays = []
    for column in cols:
        etf_field_arrays.append(d.pop(column)[columns].to_numpy().T.copy())
    del d

    generated_files.update(change_data_type_and_save(columns, dates, etf_field_arrays, etf_info_dict,
                                                     dsc_path=Path(settings.DATA_DIR, "freq=1day", MARKET_DIR, ASSET_CLASS_DIRS["etf"]), asset_class="etf"))
    del etf_field_arrays

    clean_stale_files(Path(settings.DATA_DIR, "freq=1day", MARKET_DIR, ASSET_CLASS_DIR), generated_files)
