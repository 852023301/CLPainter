from dataclasses import dataclass, field
from typing import List
from enum import Enum
import numpy as np

from .merged_kline import MergedKLine


class FenXingType(int, Enum):
    """分型类型"""
    TOP = 1  # 顶分型
    BOTTOM = -1  # 底分型


@dataclass
class FenXing:
    """分型数据结构"""
    # 分型标记：1=顶分型，-1=底分型
    fenxing_type: FenXingType
    # 分型结束位置索引
    start_idx: int = field(init=False)
    # 分型结束位置索引
    end_idx: int = field(init=False)
    # 分型长度
    length: int = field(init=False)
    # 三根合并后K线各自的长度
    length_list: List[int] = field(init=False)
    # 三根合并后K线各自的开始索引
    start_idx_list: List[int] = field(init=False)
    # 三根合并后K线各自的结束索引
    end_idx_list: List[int] = field(init=False)
    # 分型最高价
    high_price: float = field(init=False)
    # 分型最低价
    low_price: float = field(init=False)
    # 分型最高价索引
    high_idx: int = field(init=False)
    # 分型最低价索引
    low_idx: int = field(init=False)
    # 极值的交易日
    trade_date: str = field(init=False)

    @property
    def left_idx(self) -> int:
        """获取分型左边K线的索引"""
        return self.start_idx_list[0]

    @property
    def mid_idx(self) -> int:
        """获取分型中间K线的索引"""
        return self.start_idx_list[1]

    @property
    def right_idx(self) -> int:
        """获取分型中间K线的索引"""
        return self.start_idx_list[2]

    def print_klines_info(self, all_klines):
        for i in range(self.start_idx, self.end_idx + 1):
            print(all_klines[i])

    def is_top(self):
        return self.fenxing_type == FenXingType.TOP


def generate_fenxing(all_klines: List[MergedKLine]) -> List[FenXing]:
    """
    从合并后的K线列表中提取分型集合

    Args:
        all_klines: 合并后的K线列表

    Returns:
        分型对象列表
    """
    fenxing_list: List[FenXing] = []

    if len(all_klines) < 3:
        return fenxing_list

    for idx in range(len(all_klines)):
        kline = all_klines[idx]

        # 只处理有分型标记的K线
        if kline.is_normal():
            continue

        # 创建分型对象
        fenxing = FenXing(fenxing_type=FenXingType.TOP if kline.is_top() else FenXingType.BOTTOM)

        #  寻找分型右侧最边缘的k线
        jdx = idx + 1
        while jdx < (len(all_klines) - 1):
            if all_klines[jdx].merged_length == 1:
                break
            jdx += 1

        # 设置分型结束索引
        fenxing.end_idx = jdx - 1

        # 计算分型长度：包含左、中、右三根K线的总长度
        # 左K线
        prev_offset = kline.merged_length
        mid_idx = idx - prev_offset

        if mid_idx < 0:
            continue

        mid_kline = all_klines[mid_idx]
        left_idx = mid_idx - mid_kline.merged_length

        if left_idx < 0:
            continue

        left_kline = all_klines[left_idx]

        # 分型长度为三根K线各自的 merged_length 之和
        fenxing.length = left_kline.merged_length + mid_kline.merged_length + kline.merged_length

        # 记录三根K线各自的长度
        fenxing.length_list = [
            left_kline.merged_length,
            mid_kline.merged_length,
            kline.merged_length
        ]

        # 记录三根K线各自的开始索引
        fenxing.start_idx_list = [
            left_idx - left_kline.merged_length + 1,
            left_idx + 1,
            mid_idx + 1
        ]

        # 记录三根K线各自的结束索引
        fenxing.end_idx_list = [
            fenxing.left_idx + fenxing.length_list[0] - 1,
            fenxing.mid_idx + fenxing.length_list[1] - 1,
            fenxing.right_idx + fenxing.length_list[2] - 1,
        ]

        # 设置分型开始索引
        fenxing.start_idx = fenxing.left_idx

        # def get_high_price_idx(mid_klines):
        #     HHV = -1
        #     loc = None
        #     for idx, kline in enumerate(mid_klines):
        #         if kline.merged_high > HHV:
        #             HHV = kline.merged_high
        #             loc = idx
        #     return loc
        #
        # def get_low_price_idx(mid_klines):
        #     LLV = np.inf
        #     loc = None
        #     for idx, kline in enumerate(mid_klines):
        #         if kline.merged_low < LLV:
        #             LLV = kline.merged_low
        #             loc = idx
        #     return loc

        # 确定分型的最高价和最低价及其索引
        # 顶分型：取中间K线的最高价
        # 底分型：取中间K线的最低价
        if kline.is_top():  # 顶分型
            fenxing.high_price = mid_kline.merged_high
            fenxing.high_idx = mid_kline.high_idx
            # 底价为三根K线中的最低价
            fenxing.low_price = mid_kline.merged_low
            fenxing.low_idx = mid_kline.low_idx

            fenxing.trade_date = all_klines[fenxing.high_idx].trade_date
        else:  # 底分型
            fenxing.low_price = mid_kline.merged_low
            fenxing.low_idx = mid_kline.low_idx
            # 高价为三根K线中的最高价
            fenxing.high_price = mid_kline.merged_high
            fenxing.high_idx = mid_kline.high_idx

            fenxing.trade_date = all_klines[fenxing.low_idx].trade_date

        fenxing_list.append(fenxing)
    assert np.all(np.diff([fx.is_top() for fx in fenxing_list]) != 0), "不满足分型交替的要求"
    # print(fenxing_list)

    return fenxing_list
