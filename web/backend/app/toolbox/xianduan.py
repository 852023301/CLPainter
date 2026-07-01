from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum
from tezhengxulie import TeZhengXuLie


class XianDuanDirectionType(str, Enum):
    """线段的类型"""
    UP = 'up'  # 上升段：底→顶
    DOWN = 'down'  # 下降段：顶→底


@dataclass
class XianDuan:
    """线段数据结构"""
    start_idx: int = field(init=False)  # 线段起始位置索引（特征序列所在 K 线索引）
    end_idx: int = field(init=False)  # 线段结束位置索引（特征序列所在 K 线索引）
    start_bi_idx: int = field(init=False)  # 线段起始位置的笔索引（特征序列所在 笔索引）
    end_bi_idx: int = field(init=False)  # 线段结束位置的笔索引（特征序列所在 笔索引）
    start_time: str = field(init=False)  # 起始时间
    end_time: str = field(init=False)  # 结束时间
    start_price: float = field(init=False)  # 起始价格（顶/底特征序列的极值）
    end_price: float = field(init=False)  # 结束价格（顶/底特征序列的极值）
    xianduan_type: XianDuanDirectionType = field(init=False)  # 线段的方向

    # 左右分型
    left_fx_tzxl: TeZhengXuLie
    right_fx_tzxl: TeZhengXuLie


def genetate_xian_duan(tzxl_list: List[TeZhengXuLie]) -> List[XianDuan]:
    pass
