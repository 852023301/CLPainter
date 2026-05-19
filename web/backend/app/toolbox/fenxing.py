from dataclasses import dataclass, field
from typing import List

import numpy as np

from .merged_kline import MergedKLine


@dataclass
class FenXing:
    """分型数据结构"""
    # 分型标记：1=顶分型，-1=底分型
    is_top_bottom: int
    # 分型结束位置索引
    start_idx: int = field(init=False)
    # 分型结束位置索引
    end_idx: int = field(init=False)
    # 分型长度
    length: int = field(init=False)
    # 三根合并后K线各自的长度
    length_list: List[int] = field(init=False)
    # 三根合并后K线各自的开始索引
    idx_list: List[int] = field(init=False)
    # 分型最高价
    high_price: float = field(init=False)
    # 分型最低价
    low_price: float = field(init=False)
    # 分型最高价索引
    high_idx: int = field(init=False)
    # 分型最低价索引
    low_idx: int = field(init=False)

    def get_left_idx(self) -> int:
        """获取分型中间K线的索引"""
        return self.idx_list[0]

    def get_mid_idx(self) -> int:
        """获取分型中间K线的索引"""
        return self.idx_list[1]


def extract_fenxing_list(all_klines: List[MergedKLine]) -> List[FenXing]:
    """
    从合并后的K线列表中提取分型集合

    Args:
        all_klines: 合并后的K线列表

    Returns:
        分型对象列表
    """
    fenxing_list = []

    if len(all_klines) < 3:
        return fenxing_list

    for idx in range(len(all_klines)):
        kline = all_klines[idx]

        # 只处理有分型标记的K线
        if kline.is_top_bottom == 0:
            continue

        # 创建分型对象
        fenxing = FenXing(is_top_bottom=kline.is_top_bottom)

        # 设置分型结束索引
        fenxing.end_idx = idx + kline.merged_length - 1

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
        fenxing.idx_list = [
            left_idx - left_kline.merged_length + 1,
            left_idx + 1,
            mid_idx + 1
        ]

        # 设置分型开始索引
        fenxing.start_idx = fenxing.get_left_idx()

        def get_high_price_idx(mid_klines):
            HHV = -1
            loc = None
            for idx, kline in enumerate(mid_klines):
                if kline.merged_high > HHV:
                    HHV = kline.merged_high
                    loc = idx
            return loc

        def get_low_price_idx(mid_klines):
            LLV = np.inf
            loc = None
            for idx, kline in enumerate(mid_klines):
                if kline.merged_low < LLV:
                    LLV = kline.merged_low
                    loc = idx
            return loc

        # 确定分型的最高价和最低价及其索引
        # 顶分型：取中间K线的最高价
        # 底分型：取中间K线的最低价
        if kline.is_top_bottom == 1:  # 顶分型
            fenxing.high_price = mid_kline.merged_high
            fenxing.high_idx = get_high_price_idx(all_klines[left_idx + 1:mid_idx + 1]) + (left_idx + 1)
            # 底价为三根K线中的最低价
            fenxing.low_price = min(left_kline.merged_low, mid_kline.merged_low, kline.merged_low)

            fenxing.low_idx = min(
                [(left_kline.merged_low, left_idx),
                 (mid_kline.merged_low, mid_idx),
                 (kline.merged_low, idx)],
                key=lambda x: x[0]
            )[1]

        else:  # 底分型
            fenxing.low_price = mid_kline.merged_low
            fenxing.low_idx = get_low_price_idx(all_klines[left_idx + 1:mid_idx + 1]) + (left_idx + 1)
            # 高价为三根K线中的最高价
            fenxing.high_price = max(left_kline.merged_high, mid_kline.merged_high, kline.merged_high)
            fenxing.high_idx = max(
                [(left_kline.merged_high, left_idx),
                 (mid_kline.merged_high, mid_idx),
                 (kline.merged_high, idx)],
                key=lambda x: x[0]
            )[1]

        fenxing_list.append(fenxing)
    # print(fenxing_list)

    return fenxing_list
