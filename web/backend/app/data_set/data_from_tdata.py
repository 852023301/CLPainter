from tdata import fetch_data
import numpy as np
import pandas as pd
import pickle
from pathlib import Path
import datetime
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from ddp import MysqlConnection
from CLPainter.web.backend.app._config.settings import settings

START_DATE = "2009-01-01"
END_DATE = None
MAX_WORKERS = 10


def transform_and_save_symbol(columns, dates, N_D, symbol_idx, start_date,
                              dsc_path, precision):
    date_array = np.asarray(dates)
    start_idx = int(np.searchsorted(date_array, start_date, side="left"))
    end_idx = len(date_array)
    if END_DATE:
        end_idx = int(np.searchsorted(date_array, END_DATE, side="right"))

    values = N_D[:, start_idx:end_idx, symbol_idx]
    validation_values = values[:-1]
    if np.isnan(validation_values).any() or (validation_values == 0).any():
        invalid_mask = np.isnan(validation_values).any(axis=0) | (validation_values == 0).any(axis=0)
        first_invalid = start_idx + int(np.flatnonzero(invalid_mask)[0])
        print(f"{columns[symbol_idx]} {date_array[first_invalid]}存在空值或0，不处理")
        return False

    rounded_values = np.round(values, decimals=precision)
    final_list = [
        [date, *values_on_date]
        for date, values_on_date in zip(date_array[start_idx:end_idx], rounded_values.T.tolist())
    ]
    file_name = f"{columns[symbol_idx].replace('.', '')}.pkl"
    with open(dsc_path / file_name, "wb") as file:
        pickle.dump(final_list, file)
    return True


def write_index_data(index_name, code, index_data, start_date, dsc_path):
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
    file_name = f"{code.replace('.', '')}.pkl"
    with open(dsc_path / file_name, "wb") as file:
        pickle.dump(final_list, file)


def clean_stale_files(dsc_path, generated_files):
    for path in dsc_path.iterdir():
        if path.is_file() and path.name not in generated_files:
            path.unlink()


def change_data_type_and_save(columns, dates, N_D, info_dict,
                              dsc_path,
                              precision=2):
    file_names = {}
    dsc_path = Path(dsc_path)
    futures = {}

    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(columns)))) as executor:
        for idx, column_name in enumerate(columns):
            start_date = info_dict.get(column_name)
            if start_date is None:
                continue

            effective_start_date = max(START_DATE, start_date) if START_DATE else start_date
            future = executor.submit(
                transform_and_save_symbol,
                columns,
                dates,
                N_D,
                idx,
                effective_start_date,
                dsc_path,
                precision,
            )
            futures[future] = f"{column_name.replace('.', '')}.pkl"

        for future in as_completed(futures):
            if future.result():
                file_names[futures[future]] = 1

    clean_stale_files(dsc_path, file_names)


if __name__ == "__main__":
    #########################################
    # 个股
    with MysqlConnection() as sql:
        stock_info = sql.query_pandas(
            f"select stock_code,start_date from stock_info where start_date> '{datetime.datetime.now().date()}' and  end_date > '{datetime.datetime.now().date()}' ")

    stock_info_dict = dict(
        zip(stock_info['stock_code'], pd.DatetimeIndex(stock_info['start_date']).strftime("%Y-%m-%d")))

    d = fetch_data(["open", "close", "low", "high", "volume"], start_date=START_DATE, end_date=END_DATE)
    dates = pd.DatetimeIndex(d['open'].index).strftime("%Y-%m-%d").tolist()
    columns = d['open'].columns.tolist()
    stock_N_D = np.stack([d[column].values for column in ["open", "close", "low", "high", "volume"]])

    change_data_type_and_save(columns, dates, stock_N_D, stock_info_dict,
                              dsc_path=Path(settings.DATA_DIR, "all_stocks"))

    #########################################
    #  指数
    with MysqlConnection() as sql:
        index_info = sql.query_pandas(
            f"select index_code,start_date from index_info where end_date > '{datetime.datetime.now().date()}' ")
    index_info_dict = dict(
        zip(index_info['index_code'], pd.DatetimeIndex(index_info['start_date']).strftime("%Y-%m-%d")))

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

    file_names = {}
    dsc_path = Path(settings.DATA_DIR, "all_index")
    columns = ["open", "close", "low", "high", "volume"]
    index_data_names = [f"{index_name}_{column}" for index_name in index_map for column in columns]
    index_data = fetch_data(index_data_names, start_date=START_DATE, end_date=END_DATE)

    futures = {}
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(index_map)))) as executor:
        for index_name, code in index_map.items():
            start_date = index_info_dict.get(code)
            if start_date is None:
                print(f"指数 {code} 缺少 start_date，不处理")
                continue

            future = executor.submit(
                write_index_data,
                index_name,
                code,
                index_data,
                start_date,
                dsc_path,
            )
            futures[future] = f"{code.replace('.', '')}.pkl"

        for future in as_completed(futures):
            file_names[futures[future]] = 1
            future.result()

    clean_stale_files(dsc_path, file_names)

    #########################################
    # etf
    with MysqlConnection() as sql:
        etf_info = sql.query_pandas(
            f"select stock_code,start_date from etf_info where end_date > '{datetime.datetime.now().date()}' ")

    etf_info_dict = dict(zip(etf_info['stock_code'], pd.DatetimeIndex(etf_info['start_date']).strftime("%Y-%m-%d")))

    cols = [f"etf_{i}" for i in ["open", "close", "low", "high", "volume"]]
    d = fetch_data(cols,start_date=START_DATE,end_date=END_DATE)
    dates = pd.DatetimeIndex(d[cols[0]].index).strftime("%Y-%m-%d").tolist()
    columns = d[cols[0]].columns.tolist()
    etf_N_D = np.stack([d[column].values for column in cols])

    change_data_type_and_save(columns, dates, etf_N_D, etf_info_dict,
                              dsc_path=Path(settings.DATA_DIR, "all_etf"), precision=3)
