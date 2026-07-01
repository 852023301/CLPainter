from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Union
from enum import Enum
from collections import deque
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


def generate_te_zheng_xu_lie(bi_list: List[Union[Bi, FakeBi]]) -> List[TeZhengXuLie]:
    """生成特征序列"""
    te_zheng_xu_lie_list: List[TeZhengXuLie] = []

    for idx in range(2, len(bi_list) - 2):
        # 相邻bi是相反方向，
        left_bi = bi_list[idx - 2]
        mid_bi = bi_list[idx]
        right_bi = bi_list[idx + 2]

        # 底部特征序列
        if left_bi.is_up:
            if mid_bi.start_price < left_bi.start_price and mid_bi.start_price < right_bi.start_price:
                category = TeZhengXuLieCategory.Second if mid_bi.end_price < left_bi.start_price else TeZhengXuLieCategory.First
                te_zheng_xu_lie_list.append(
                    TeZhengXuLie(type=TeZhengXuLieType.DI, category=category, bi_list=[left_bi, mid_bi, right_bi]))
        # 顶部特征序列
        else:
            if mid_bi.start_price > left_bi.start_price and mid_bi.start_price > right_bi.start_price:
                category = TeZhengXuLieCategory.Second if mid_bi.end_price > left_bi.start_price else TeZhengXuLieCategory.First
                te_zheng_xu_lie_list.append(
                    TeZhengXuLie(type=TeZhengXuLieType.DING, category=category, bi_list=[left_bi, mid_bi, right_bi]))

    return te_zheng_xu_lie_list
