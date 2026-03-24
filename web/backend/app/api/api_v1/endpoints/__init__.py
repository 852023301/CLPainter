import os
import pickle
from pathlib import Path
from typing import List
from dataclasses import dataclass
from typing import List, Optional


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

        # 定义顶分型和底分型  1为顶分型，-1为底分型
        self.is_top_bottom = 0

    @property
    def is_contained(self):
        return self._is_contained

    @is_contained.setter
    def is_contained(self, value):
        self._is_contained = value


def find_top_bottom(all_klines: List[MergedKLine]):
    """
    寻找合并后K线的顶底分型
    :param all_klines:
    :return:
    """
    if len(all_klines) < 2:
        return

    # 寻找每一根K线的前一根未包含K线的位置

    for idx, merged_kline in enumerate(all_klines):
        if idx < 2:
            continue

        mid_merged_kline = all_klines[idx - merged_kline.merged_length]
        left_merged_kline = all_klines[idx - merged_kline.merged_length - mid_merged_kline.merged_length]

        if merged_kline.merged_length != 1:
            continue

        # 顶底分型完成信号不会同时出现在一根K线上
        if (left_merged_kline.merged_low > mid_merged_kline.merged_low) and (
            mid_merged_kline.merged_low < merged_kline.merged_low):
            merged_kline.is_top_bottom = -1

        elif (left_merged_kline.merged_high < mid_merged_kline.merged_high) and (
            mid_merged_kline.merged_high > merged_kline.merged_high):
            merged_kline.is_top_bottom = 1

        else:
            merged_kline.is_top_bottom = 0


def merge_data():
    """
    K线合并
    :return:
    """
    # response = requests.get(
    #     url="https://echarts.apache.org/examples/data/asset/data/stock-DJI.json"
    # )
    origin_klines = get_data_init_set
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


@dataclass
class Bi:
    """笔数据结构"""
    start_idx: int  # 笔起始位置索引
    end_idx: int  # 笔结束位置索引
    start_date: str  # 起始日期
    end_date: str  # 结束日期
    start_price: float  # 起始价格
    end_price: float  # 结束价格
    bi_type: str  # 'up' 或 'down' - 笔的方向
    high_price: float  # 笔中的最高价
    low_price: float  # 笔中的最低价
    start_is_top: bool  # 笔起点是否为顶分型

    @property
    def is_up(self) -> bool:
        """是否为向上笔"""
        return self.bi_type == 'up'

    @property
    def is_down(self) -> bool:
        """是否为向下笔"""
        return self.bi_type == 'down'


def find_bi(old_klines: List[MergedKLine]) -> List[Bi]:
    """
    根据顶底分型划分笔（旧笔规则）
    旧笔规则：顶底必须交替，中间可以跳过不符合的分型
    """
    if len(old_klines) < 3:
        return []

    # 找出所有顶底分型
    top_bottoms = []
    for idx, kline in enumerate(old_klines):
        if kline.is_top_bottom != 0:
            top_bottoms.append({
                'idx': idx,
                'date': kline.trade_date,
                'price': kline.low if kline.is_top_bottom == -1 else kline.high,
                'is_top': kline.is_top_bottom == 1,
                'is_bottom': kline.is_top_bottom == -1,
                'high': kline.high,
                'low': kline.low
            })

    if len(top_bottoms) < 2:
        return []

    bi_list = []
    i = 0

    # 确定第一笔的起点（必须是顶或底）
    while i < len(top_bottoms):
        if top_bottoms[i]['is_top'] or top_bottoms[i]['is_bottom']:
            break
        i += 1

    if i >= len(top_bottoms) - 1:
        return []

    current_start = top_bottoms[i]

    # 遍历剩余的顶底分型
    for j in range(i + 1, len(top_bottoms)):
        current_end = top_bottoms[j]

        # 检查是否满足笔的规则
        # 旧笔规则：顶底交替，且价格满足特定条件
        if current_start['is_top'] and current_end['is_bottom']:
            # 顶到底：确认是向下笔
            # 检查价格是否有效：底分型的低点应该低于顶分型的低点
            if current_end['low'] < current_start['low']:
                # 计算笔的高低点
                # 向下笔：起点是顶（高点），终点是底（低点）
                high_price = current_start['high']
                low_price = current_end['low']

                bi = Bi(
                    start_idx=current_start['idx'],
                    end_idx=current_end['idx'],
                    start_date=current_start['date'],
                    end_date=current_end['date'],
                    start_price=current_start['price'],
                    end_price=current_end['price'],
                    bi_type='down',
                    high_price=high_price,
                    low_price=low_price,
                    start_is_top=True
                )
                bi_list.append(bi)
                current_start = current_end

        elif current_start['is_bottom'] and current_end['is_top']:
            # 底到顶：确认是向上笔
            # 检查价格是否有效：顶分型的高点应该高于底分型的高点
            if current_end['high'] > current_start['high']:
                # 计算笔的高低点
                # 向上笔：起点是底（低点），终点是顶（高点）
                high_price = current_end['high']
                low_price = current_start['low']

                bi = Bi(
                    start_idx=current_start['idx'],
                    end_idx=current_end['idx'],
                    start_date=current_start['date'],
                    end_date=current_end['date'],
                    start_price=current_start['price'],
                    end_price=current_end['price'],
                    bi_type='up',
                    high_price=high_price,
                    low_price=low_price,
                    start_is_top=False
                )
                bi_list.append(bi)
                current_start = current_end

    return bi_list


def get_data_init():
    # import requests
    # response = requests.get(
    #     url="https://echarts.apache.org/examples/data/asset/data/stock-DJI.json"
    # )
    # get_data_init_set = json_response = response.json()
    with open(Path(os.environ['appDir']) / "data_set/data_set.pkl", "rb", ) as f:
        json_response = pickle.load(f)
    # 解析数据
    return json_response


# 原始文件
get_data_init_set = get_data_init()

# 合并后的数据
merge_data_list = merge_data()
find_top_bottom(merge_data_list)

# for i in merge_data_list:
#     # print(i.trade_date,i.is_contained, i.merged_length)
#     print(i.trade_date, i.is_contained, i.merged_length, i.is_top_bottom)

merge_kline_data = [[data.merged_low if data.close > data.open else data.merged_high,
                     data.merged_high if data.close > data.open else data.merged_low,
                     data.merged_low, data.merged_high] for data in merge_data_list]
origin_kline_data = [[data.open,
                      data.close,
                      data.low, data.high] for data in merge_data_list]

# 交易日
trade_date_list = [data.trade_date for data in merge_data_list]
