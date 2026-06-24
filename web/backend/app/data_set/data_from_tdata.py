from tdata import fetch_data
import numpy as np
import pandas as pd
import pickle
import datetime
from ddp import MysqlConnection


def change_data_type_and_save(columns, dates, N_D, info_dict,
                              dsc_path="/home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_stocks",
                              precision=2):
    for idx, i in enumerate(columns):
        is_write = True
        file_name = columns[idx].replace(".", "")
        final_list = []
        start_date = info_dict.get(columns[idx])
        if start_date is None:
            continue
        for jdx, j in enumerate(dates):
            if dates[jdx] < start_date:
                continue
            _single = N_D[:, jdx, idx]

            if any(np.isnan(_single[:-1])) or any(_single[:-1] == 0):
                print(f"{i} {dates[jdx]}存在空值或0，不处理")
                # print(_single)
                is_write = False
                break

            single = [dates[jdx], *[float(fl).__round__(precision) for fl in _single]]
            final_list.append(single)
        if is_write:
            with open(f"{dsc_path}/{file_name}.pkl", "wb") as f:
                pickle.dump(final_list, f)


#########################################
# 个股
with MysqlConnection() as sql:
    stock_info = sql.query_pandas(
        f"select stock_code,start_date from stock_info where end_date > '{datetime.datetime.now().date()}' ")

stock_info_dict = dict(zip(stock_info['stock_code'], pd.DatetimeIndex(stock_info['start_date']).strftime("%Y-%m-%d")))

d = fetch_data(["open", "close", "low", "high", "volume"])
dates = pd.DatetimeIndex(d['open'].index).strftime("%Y-%m-%d").tolist()
columns = d['open'].columns.tolist()
stock_N_D = np.stack([d[i].values for i in d])

change_data_type_and_save(columns, dates, stock_N_D, stock_info_dict,
                          dsc_path="/home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_stocks")
# for idx, i in enumerate(columns):
#     file_name = columns[idx].replace(".", "")
#     final_list = []
#     start_date = stock_info_dict.get(columns[idx])
#     if start_date is None:
#         continue
#     for jdx, j in enumerate(dates):
#         if dates[jdx] < start_date:
#             continue
#         _single = stock_N_D[:, jdx, idx]
#
#         if any(np.isnan(_single[:-1])) or any(_single[:-1] == 0):
#             print(f"{i} {dates[jdx]}存在空值或0，不处理")
#             print(_single)
#
#         single = [dates[jdx], *[float(fl).__round__(2) for fl in _single]]
#         final_list.append(single)
#
#     with open(f"/home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_stocks/{file_name}.pkl", "wb") as f:
#         pickle.dump(final_list, f)

# 容器内执行 rm -r  /root/CLPainter/web/backend/app/data_set/all_stocks
# 容器外执行 docker cp /home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_stocks CLPainter:/root/CLPainter/web/backend/app/data_set/


#########################################
# 旧版取指数
index_name = "szzs"
columns = ["open", "close", "low", "high", "volume"]
data = fetch_data([f"{index_name}_{i}" for i in columns])
concat_data = pd.concat(data, axis=1)
concat_data.columns = columns
concat_data.index = pd.DatetimeIndex(concat_data.index).strftime("%Y-%m-%d")
final_list = concat_data.reset_index().values.tolist()

with open(f"/home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/data_set_000001SH.pkl", "wb") as f:
    pickle.dump(final_list, f)

#  docker cp /home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/data_set_000002SH.pkl CLPainter:/root/CLPainter/web/backend/app/data_set

#########################################
#  指数
with MysqlConnection() as sql:
    index_info = sql.query_pandas(
        f"select index_code,start_date from index_info where end_date > '{datetime.datetime.now().date()}' ")
index_info_dict = dict(zip(index_info['index_code'], pd.DatetimeIndex(index_info['start_date']).strftime("%Y-%m-%d")))

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
for index_name, code in index_map.items():
    start_date = index_info_dict.get(code)
    print(start_date)
    columns = ["open", "close", "low", "high", "volume"]
    data = fetch_data([f"{index_name}_{i}" for i in columns])
    concat_data = pd.concat(data, axis=1)
    concat_data.columns = columns
    concat_data = concat_data[concat_data.index >= start_date]

    concat_data.index = pd.DatetimeIndex(concat_data.index).strftime("%Y-%m-%d")
    final_list = concat_data.reset_index().values.tolist()

    with open(f"/home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_index/{code.replace('.', '')}.pkl",
              "wb") as f:
        pickle.dump(final_list, f)

#  docker cp /home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_index CLPainter:/root/CLPainter/web/backend/app/data_set

#########################################
# etf
with MysqlConnection() as sql:
    etf_info = sql.query_pandas(
        f"select stock_code,start_date from etf_info where end_date > '{datetime.datetime.now().date()}' ")

etf_info_dict = dict(zip(etf_info['stock_code'], pd.DatetimeIndex(etf_info['start_date']).strftime("%Y-%m-%d")))

cols = [f"etf_{i}" for i in ["open", "close", "low", "high", "volume"]]
d = fetch_data(cols)
dates = pd.DatetimeIndex(d[cols[0]].index).strftime("%Y-%m-%d").tolist()
columns = d[cols[0]].columns.tolist()
etf_N_D = np.stack([d[i].values for i in d])

change_data_type_and_save(columns, dates, etf_N_D, etf_info_dict,
                          dsc_path="/home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_etf", precision=3)
# for idx, i in enumerate(columns):
#     file_name = columns[idx].replace(".", "")
#     final_list = []
#     start_date = etf_info_dict.get(columns[idx])
#     if start_date is None:
#         continue
#
#     for jdx, j in enumerate(dates):
#         if dates[jdx] < start_date:
#             continue
#         _single = etf_N_D[:, jdx, idx]
#
#         if any(np.isnan(_single[:-1])) or any(_single[:-1] == 0):
#             print(f"{i} {dates[jdx]}存在空值或0，不处理")
#             print(_single)
#
#             break
#         single = [dates[jdx], *[float(fl).__round__(3) for fl in _single]]
#
#         final_list.append(single)
#
#     with open(f"/home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_etf/{file_name}.pkl", "wb") as f:
#         pickle.dump(final_list, f)

# 容器外执行 docker cp /home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_etf CLPainter:/root/CLPainter/web/backend/app/data_set/
