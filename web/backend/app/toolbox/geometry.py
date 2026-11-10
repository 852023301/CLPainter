"""价格与区间极值的通用小工具。

这些函数只处理数值，不依赖笔/线段/特征序列对象，避免在多个模块里重复
实现同一套“更极值/同价”判断。
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

PRICE_EPS = 1e-8


def price_is_more_extreme(price: float, best_price: float, is_up: bool) -> bool:
    """判断 price 是否比 best_price 更极值。

    is_up=True 时越大越极值；is_up=False 时越小越极值。
    """
    if is_up:
        return price > best_price + PRICE_EPS
    return price < best_price - PRICE_EPS


def price_is_same(left: float, right: float) -> bool:
    """价格在容差内视为相同。"""
    return abs(left - right) <= PRICE_EPS


def range_extreme_indices(
    high_prices: Sequence[float],
    low_prices: Sequence[float],
    start: int,
    end: int,
) -> tuple[int, int]:
    """返回闭区间 [start, end] 内最高价和最低价的索引。"""
    if start < 0 or end < start or end >= len(high_prices) or end >= len(low_prices):
        raise ValueError(f"非法区间: start={start}, end={end}, length={len(high_prices)}")
    high_slice = high_prices[start : end + 1]
    low_slice = low_prices[start : end + 1]
    high_idx = start + int(np.argmax(high_slice))
    low_idx = start + int(np.argmin(low_slice))
    return high_idx, low_idx
