from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Union
from enum import Enum
from collections import deque
import numpy as np
import pandas as pd

from .bi import BiBase


class TeZhengXuLieType(int, Enum):
    """笔的类型"""
    DING = 1  # 顶分型特征序列
    DI = 2  # 底分型特征序列


class TeZhengXuLieCategory(int, Enum):
    """笔的类型"""
    First = 1  # 第一种特征序列
    Second = 2  # 第二种特征序列


@dataclass
class TeZhengXuLie:
    """笔的特征序列"""
    type: TeZhengXuLieType = field(default=TeZhengXuLieType.DING)
    category: TeZhengXuLieCategory = field(default=TeZhengXuLieCategory.First)  # 默认第一类
    bi_list: List[BiBase] = field(default_factory=list,repr=False)  # 内部三笔列表
    bi_idx_list: List[int] = field(default_factory=list)  # 特征序列组件三笔在原始笔列表中的索引

    # tzxl索引(generate_te_zheng_xu_lie 事后填充)
    idx: Optional[int] = None

    @property
    def left_bi(self) -> BiBase:
        return self.bi_list[0]

    @property
    def mid_bi(self) -> BiBase:
        return self.bi_list[1]

    @property
    def right_bi(self) -> BiBase:
        return self.bi_list[2]

    @property
    def mid_idx(self) -> int:
        return self.mid_bi.start_idx

    def is_first_category(self) -> bool:
        return self.category == TeZhengXuLieCategory.First

    def is_second_category(self) -> bool:
        return self.category == TeZhengXuLieCategory.Second

    @property
    def left_bi_idx(self) -> int:
        return self.bi_idx_list[0]

    @property
    def mid_bi_idx(self) -> int:
        return self.bi_idx_list[1]

    @property
    def right_bi_idx(self) -> int:
        return self.bi_idx_list[2]

    def is_top(self) -> bool:
        return self.type == TeZhengXuLieType.DING

    def is_bottom(self) -> bool:
        return self.type == TeZhengXuLieType.DI

    @property
    def start_idx(self) -> int:
        return self.mid_bi.start_idx

    @property
    def start_time(self) -> pd.Timestamp:
        return self.mid_bi.start_time

    @property
    def start_price(self) -> float:
        return self.mid_bi.start_price

    @property
    def high_price(self) -> float:
        return max(self.mid_bi.start_price, self.mid_bi.end_price)

    @property
    def low_price(self) -> float:
        return min(self.mid_bi.start_price, self.mid_bi.end_price)


def _find_confirmation(bi_list: List[BiBase], idx: int, is_bottom: bool) -> Optional[int]:
    """从 idx 开始向后寻找特征序列的确认笔。"""
    mid_bi = bi_list[idx]
    right_idx = idx + 2
    if is_bottom:
        merged_low = mid_bi.start_price
        merged_high = mid_bi.end_price
        while right_idx < len(bi_list):
            right_bi = bi_list[right_idx]
            if right_bi.start_price < merged_low:
                return None
            if right_bi.start_price > merged_low and right_bi.end_price > merged_high:
                return right_idx
            if (right_bi.start_price >= merged_low and right_bi.end_price <= merged_high) or (
                right_bi.start_price <= merged_low and right_bi.end_price >= merged_high
            ):
                merged_high = min(merged_high, right_bi.end_price)
                merged_low = min(merged_low, right_bi.start_price)
            else:
                raise ValueError("意外的笔")
            right_idx += 2
        return None

    merged_high = mid_bi.start_price
    merged_low = mid_bi.end_price
    while right_idx < len(bi_list):
        right_bi = bi_list[right_idx]
        if right_bi.start_price > merged_high:
            return None
        if right_bi.start_price < merged_high and right_bi.end_price < merged_low:
            return right_idx
        if (right_bi.start_price >= merged_low and right_bi.end_price <= merged_high) or (
            right_bi.start_price <= merged_low and right_bi.end_price >= merged_high
        ):
            merged_high = max(merged_high, right_bi.start_price)
            merged_low = max(merged_low, right_bi.end_price)
        else:
            raise ValueError("意外的笔")
        right_idx += 2
    return None


def _filter_extreme_sequences(sequences: List[TeZhengXuLie]) -> List[TeZhengXuLie]:
    """连续同向特征序列只保留更极值的一个。"""
    filtered: List[TeZhengXuLie] = []
    is_top = True
    temp: List[TeZhengXuLie] = []
    for tzxl in sequences:
        if tzxl.is_top() == is_top:
            temp.append(tzxl)
            continue
        if temp:
            filtered.append(
                max(temp, key=lambda item: item.high_price)
                if is_top
                else min(temp, key=lambda item: item.low_price)
            )
        is_top = not is_top
        temp = [tzxl]
    if temp:
        filtered.append(
            max(temp, key=lambda item: item.high_price)
            if is_top
            else min(temp, key=lambda item: item.low_price)
        )
    return filtered


def generate_te_zheng_xu_lie(bi_list: List[BiBase]) -> List[TeZhengXuLie]:
    """生成笔特征序列。"""
    sequences: List[TeZhengXuLie] = []
    for idx in range(2, len(bi_list) - 2):
        left_bi = bi_list[idx - 2]
        mid_bi = bi_list[idx]
        if mid_bi.is_up():
            if mid_bi.start_price >= left_bi.start_price:
                continue
            right_idx = _find_confirmation(bi_list, idx, True)
            if right_idx is None:
                continue
            category = (
                TeZhengXuLieCategory.Second
                if mid_bi.end_price < left_bi.start_price
                else TeZhengXuLieCategory.First
            )
            sequences.append(
                TeZhengXuLie(
                    type=TeZhengXuLieType.DI,
                    category=category,
                    bi_list=[left_bi, mid_bi, bi_list[right_idx]],
                    bi_idx_list=[idx - 2, idx, right_idx],
                )
            )
        else:
            if mid_bi.start_price <= left_bi.start_price:
                continue
            right_idx = _find_confirmation(bi_list, idx, False)
            if right_idx is None:
                continue
            category = (
                TeZhengXuLieCategory.Second
                if mid_bi.end_price > left_bi.start_price
                else TeZhengXuLieCategory.First
            )
            sequences.append(
                TeZhengXuLie(
                    type=TeZhengXuLieType.DING,
                    category=category,
                    bi_list=[left_bi, mid_bi, bi_list[right_idx]],
                    bi_idx_list=[idx - 2, idx, right_idx],
                )
            )

    filtered = _filter_extreme_sequences(sequences)
    assert np.all(np.diff([tzxl.is_top() for tzxl in filtered]) != 0), "不满足特征序列顶底交替的要求"
    for i, tzxl in enumerate(filtered):
        tzxl.idx = i
    return filtered
