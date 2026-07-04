from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Union
from enum import Enum
from collections import deque
import numpy as np

from .bi import Bi, FakeBi


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
    category: TeZhengXuLieCategory = field(default_factory=TeZhengXuLieCategory.First)
    bi_list: List[Union[Bi, FakeBi]] = field(default_factory=list)
    bi_idx_list: List[int] = field(default_factory=list)  # 特征序列组件三笔在原始笔列表中的索引

    @property
    def left_bi(self) -> Union[Bi, FakeBi]:
        return self.bi_list[0]

    @property
    def mid_bi(self) -> Union[Bi, FakeBi]:
        return self.bi_list[1]

    @property
    def right_bi(self) -> Union[Bi, FakeBi]:
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
    def start_time(self) -> str:
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


def generate_te_zheng_xu_lie(bi_list: List[Union[Bi, FakeBi]]) -> List[TeZhengXuLie]:
    """生成特征序列"""
    te_zheng_xu_lie_list: List[TeZhengXuLie] = []
    bi_idx_length = len(bi_list)
    _end_idx  = bi_idx_length - 2
    for idx in range(2, _end_idx):
        # 相邻bi是相反方向，
        left_bi = bi_list[idx - 2]
        mid_bi = bi_list[idx]


        # 底部特征序列
        if mid_bi.is_up():
            if mid_bi.start_price < left_bi.start_price:
                find = False
                right_idx = idx + 2
                merged_low = mid_bi.start_price
                merged_high = mid_bi.end_price
                while right_idx < bi_idx_length:
                    right_bi = bi_list[right_idx]
                    # 向下合并
                    if (right_bi.start_price>=merged_low and right_bi.end_price <= merged_high) or (right_bi.start_price<=merged_low and right_bi.end_price >= merged_high):
                        merged_high = min(merged_high, right_bi.end_price)
                        merged_low = min(merged_low, right_bi.start_price)
                    else:
                        if right_bi.start_price > merged_low and right_bi.end_price > merged_high:
                            find = True
                            break
                        elif right_bi.start_price < merged_low and right_bi.end_price < merged_high:
                            break
                        else:
                            raise ValueError(f"意外的笔{right_bi=}")
                    right_idx += 2

                if find:
                    bi_idx_list = [idx - 2, idx, right_idx]

                    category = TeZhengXuLieCategory.Second if mid_bi.end_price < left_bi.start_price else TeZhengXuLieCategory.First
                    te_zheng_xu_lie_list.append(
                        TeZhengXuLie(type=TeZhengXuLieType.DI, category=category, bi_list=[left_bi, mid_bi, bi_list[right_idx]],
                                     bi_idx_list=bi_idx_list))
        # 顶部特征序列
        else:
            if mid_bi.start_price > left_bi.start_price:
                find = False
                right_idx = idx + 2
                merged_low = mid_bi.start_price
                merged_high = mid_bi.end_price
                while right_idx < bi_idx_length:
                    right_bi = bi_list[right_idx]
                    # 向上合并
                    if (right_bi.start_price>=merged_low and right_bi.end_price <= merged_high) or (right_bi.start_price<=merged_low and right_bi.end_price >= merged_high):
                        merged_high = max(merged_high, right_bi.end_price)
                        merged_low = max(merged_low, right_bi.start_price)
                    else:
                        if right_bi.start_price < merged_high and right_bi.end_price < merged_low:
                            find = True
                            break
                        elif right_bi.start_price > merged_high and right_bi.end_price > merged_low:
                            break
                        else:
                            raise ValueError(f"意外的笔{right_bi=}")
                    right_idx += 2


                if find:
                    bi_idx_list = [idx - 2, idx, right_idx]
                    category = TeZhengXuLieCategory.Second if mid_bi.end_price > left_bi.start_price else TeZhengXuLieCategory.First
                    te_zheng_xu_lie_list.append(
                        TeZhengXuLie(type=TeZhengXuLieType.DING, category=category, bi_list=[left_bi, mid_bi, bi_list[right_idx]],
                                     bi_idx_list=bi_idx_list))

    for i in te_zheng_xu_lie_list:
        print(i.mid_bi.left_fx.trade_date ,i.is_top())
    # assert np.all(np.diff([tzxl.is_top() for tzxl in te_zheng_xu_lie_list]) != 0), "不满足特征序列交替的要求"
    return te_zheng_xu_lie_list
