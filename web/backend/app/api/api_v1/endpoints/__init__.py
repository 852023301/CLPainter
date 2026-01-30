import requests
import pickle
from pathlib import Path
import os


def merge_data():
    # response = requests.get(
    #     url="https://echarts.apache.org/examples/data/asset/data/stock-DJI.json"
    # )
    origin_klines  = get_data_init_set

    class MergedKLine:
        def __init__(self, trade_date, open_, close, low, high, volume):
            self.trade_date = trade_date
            self.open = open_
            self.close = close
            self.low = low
            self.high = high
            self.volume = volume  # 交易量单位为股

            # 根据上一根k线的状态决定下一根k线的参数
            self._is_contained = 0  # 是否合并,is_contained=1是合并,is_contained=0是未合并，用于显示颜色
            self.merged_length = 1  # 连续合并的K线长度
            self.merged_trend = 1  # 合并结果,trend=1是向上,trend=0是向下，用于显示颜色
            self.merged_high = high  # 合并后的最高价
            self.merged_low = low  # 合并后的最低价

        @property
        def is_contained(self):
            return self._is_contained

        @is_contained.setter
        def is_contained(self, value):
            self._is_contained = value

    all_klines = []

    for idx, kl in enumerate(origin_klines):
        merged_kline = MergedKLine(*kl)

        if len(all_klines) == 0:
            # 第一根k线不处理
            all_klines.append(merged_kline)
            continue

        # 根据上一根k线的状态决定下一根k线的参数
        last_merged_kline = all_klines[-1]
        if last_merged_kline.merged_high < merged_kline.high and last_merged_kline.merged_low < merged_kline.low:
            merged_kline.merged_trend = 1
        elif last_merged_kline.merged_high > merged_kline.high and last_merged_kline.merged_low > merged_kline.low:
            merged_kline.merged_trend = 0
        else:

            # 判断合并
            if (last_merged_kline.merged_high <= merged_kline.high
                and last_merged_kline.merged_low >= merged_kline.low) or (
                last_merged_kline.high >= merged_kline.high and last_merged_kline.merged_low <= merged_kline.low
            ):
                merged_kline.is_contained = 1
                merged_kline.merged_trend = last_merged_kline.merged_trend
                merged_kline.merged_length = last_merged_kline.merged_length + 1

                if (
                    last_merged_kline.merged_high <= merged_kline.high and
                    last_merged_kline.merged_low >= merged_kline.low):
                    merged_kline.merged_high = merged_kline.high if merged_kline.merged_trend == 1 \
                        else last_merged_kline.merged_high
                    merged_kline.merged_low = last_merged_kline.low if merged_kline.merged_trend == 1 \
                        else merged_kline.merged_low

                elif (
                    last_merged_kline.high >= merged_kline.high and
                    last_merged_kline.merged_low <= merged_kline.low):
                    merged_kline.merged_high = last_merged_kline.high if merged_kline.merged_trend == 1 \
                        else merged_kline.high
                    merged_kline.merged_low = merged_kline.low if merged_kline.merged_trend == 1 \
                        else last_merged_kline.merged_low
                else:
                    raise Exception("异常包含关系")

        all_klines.append(merged_kline)
    return all_klines




def get_data_init():
    # response = requests.get(
    #     url="https://echarts.apache.org/examples/data/asset/data/stock-DJI.json"
    # )
    # json_response = response.json()
    with open(Path(os.environ['appDir']) / "data_set/data_set.pkl", "rb", ) as f:
        json_response = pickle.load(f)
    # 解析数据
    return json_response

# 原始文件
get_data_init_set = get_data_init()

# 合并后的数据
merge_data_list = merge_data()
merge_kline_data = [[data.merged_low if data.close > data.open else data.merged_high,
                     data.merged_high if data.close > data.open else data.merged_low,
                     data.merged_low, data.merged_high] for data in merge_data_list]
origin_kline_data = [[data.open,
                      data.close,
                      data.low, data.high] for data in merge_data_list]

#交易日
trade_date_list = [data.trade_date for data in merge_data_list]