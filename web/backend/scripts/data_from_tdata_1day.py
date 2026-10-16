# 只需要未复权（除权）数据
from bisect import bisect_left, bisect_right
from tdata import fetch_data
from ddp import MysqlConnection
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
EXTENDED_FIELDS = [*FIELDS, "change_pct"]
LEGACY_EIGHT_FIELDS = [*FIELDS, "change", "change_pct"]
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
    final_list = append_change_fields(final_list)
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


def append_change_fields(pv_list):
    """按前一收盘价计算涨幅，首条无前收时填0。"""
    if not pv_list:
        return []
    if any(len(row) not in (len(FIELDS) + 1, len(EXTENDED_FIELDS) + 1, len(LEGACY_EIGHT_FIELDS) + 1) for row in pv_list):
        raise ValueError("K线字段数量错误，无法计算涨幅")

    result = []
    previous_close = None
    for row in pv_list:
        close = float(row[2])
        change_pct = (
            0.0
            if previous_close in (None, 0)
            else (close - previous_close) / previous_close * 100
        )
        result.append([row[0], *row[1:6], round(change_pct, 6)])
        previous_close = close
    return result


def query_index_data(start_date, end_date):
    """从MySQL index_data表读取全部指数OHLCV数据，并按指数代码分组。"""
    end_condition = f"AND trade_date <= '{end_date}'" if end_date else ""
    start_condition = f"AND trade_date >= '{start_date}'" if start_date else ""
    query = (
        "SELECT index_code, trade_date, open, close, low, high, volume "
        "FROM index_data "
        "WHERE 1=1 "
        f"{start_condition} "
        f"{end_condition} "
        "ORDER BY index_code, trade_date"
    )
    with MysqlConnection() as sql:
        frame = sql.query_pandas(query)

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    if frame.empty:
        raise ValueError("index_data没有可用数据")
    return {
        index_code: data_frame.set_index("trade_date")[FIELDS]
        for index_code, data_frame in frame.groupby("index_code", sort=False)
    }


def write_index_data(code, index_data, start_date, dsc_path):
    """严格校验指数OHLCV缺失值、裁剪时间范围并保存标准K线。"""
    effective_start_date = max(START_DATE, start_date) if START_DATE else start_date
    concat_data = index_data.copy()
    concat_data = concat_data[concat_data.index >= effective_start_date]
    if END_DATE:
        concat_data = concat_data[concat_data.index <= END_DATE]

    if concat_data.empty:
        raise ValueError(f"{code} 指数无有效数据，跳过")
    if not np.isfinite(concat_data.to_numpy(dtype=float)).all():
        raise ValueError(f"{code} 指数OHLCV存在空值，跳过")

    concat_data.index = pd.DatetimeIndex(concat_data.index).strftime("%Y-%m-%d")
    final_list = concat_data.reset_index().values.tolist()
    if not final_list:
        raise ValueError(f"{code} 指数清洗后无有效数据，跳过")
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

    file_names = set()
    dsc_path = Path(settings.DATA_DIR, "freq=1day", MARKET_DIR, ASSET_CLASS_DIR)
    index_data_by_code = query_index_data(START_DATE, END_DATE)
    dsc_path.mkdir(parents=True, exist_ok=True)
    index_dsc_path = Path(settings.DATA_DIR, "freq=1day", MARKET_DIR, ASSET_CLASS_DIRS["index"])
    index_dsc_path.mkdir(parents=True, exist_ok=True)

    futures = {}
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(index_data_by_code)))) as executor:
        for code in index_data_by_code:
            start_date = index_info_dict.get(code)
            if start_date is None:
                print(f"指数 {code} 缺少 start_date，不处理")
                continue
            start_date = start_date["list_date"]

            future = executor.submit(
                write_index_data,
                code,
                index_data_by_code[code],
                start_date,
                index_dsc_path,
            )
            futures[future] = f"{code.replace('.', '')}.pkl"

        skipped_count = len(index_data_by_code) - len(futures)
        for future in as_completed(futures):
            code = futures[future].removesuffix(".pkl")
            try:
                future.result()
            except (FileNotFoundError, ValueError) as error:
                print(f"指数 {code} 跳过: {error}")
                continue
            file_names.add(futures[future])
    print(f"index: 数据源 {len(index_data_by_code)}，无元数据跳过 {skipped_count}，已保存 {len(file_names)}，保存失败跳过 {len(futures) - len(file_names)}")
    clean_stale_files(index_dsc_path, file_names)

    generated_files.update(file_names)
    del index_data_by_code

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
