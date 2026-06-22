from factory.factors.archive.FactorDataSys_BK.Script.HistoryUpdateFactorScript import start_date
from scripts.error_check.check_meta_mark import stock_info
from tdata import fetch_data
import numpy as np
import pandas as pd
import pickle
import datetime
from ddp import MysqlConnection


with MysqlConnection() as sql:
    stock_info = sql.query_pandas(f"select stock_code,start_date from stock_info where end_date > '{datetime.datetime.now().date()}' ")

stock_info_dict = dict(zip(stock_info['stock_code'], pd.DatetimeIndex(stock_info['start_date']).strftime("%Y-%m-%d")))

# 个股
d = fetch_data(["open","close","low","high","volume"])
dates =   pd.DatetimeIndex(d['open'].index ).strftime("%Y-%m-%d").tolist()
columns =   d['open'].columns.tolist()
x = np.stack([d[i].values for i in d])

for idx,i in enumerate(columns):
    file_name = columns[idx].replace(".", "")
    final_list = []
    start_date = stock_info_dict.get(columns[idx])
    if start_date is None:
        continue
    for jdx, j in enumerate(dates):
        if dates[jdx] < start_date:
            continue
        single = [dates[jdx],*[float(fl).__round__(2) for fl in x[:,jdx,idx]]]
        final_list.append(single)

    with open(f"/home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_stocks/{file_name}.pkl", "wb") as f:
        pickle.dump(final_list, f)



# docker cp /home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/all_stocks CLPainter:/root/CLPainter/web/backend/app/data_set/

#  指数

index_name = "szzs"
columns =  ["open","close","low","high","volume"]
data = fetch_data([f"{index_name}_{i}" for i in columns])
concat_data =pd.concat(data,axis=1)
concat_data.columns = columns
concat_data.index =  pd.DatetimeIndex(concat_data.index).strftime("%Y-%m-%d")
final_list = concat_data.reset_index().values.tolist()

with open(f"/home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/data_set_000002SH.pkl", "wb") as f:
    pickle.dump(final_list, f)

#  docker cp /home/wjl/TechFinWorkSpace/CLPainter/web/backend/app/data_set/data_set_000002SH.pkl CLPainter:/root/CLPainter/web/backend/app/data_set