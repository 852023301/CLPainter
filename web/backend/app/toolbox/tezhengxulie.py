from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum
from .bi import Bi


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
    bi_list: List[Bi] = field(default_factory=list)


def generate_te_zheng_xu_lie(bi_list: List[Bi]) -> List[TeZhengXuLie]:
    """生成特征序列"""
    te_zheng_xu_lie_list = []
    # for i in range(len(bi_list)):
    #     if i == 0:
    #         te_zheng_xu_lie = TeZhengXuLie(type=TeZhengXuLieType.DING)
    #         te_zheng_xu_lie.bi_list.append(bi_list[i])