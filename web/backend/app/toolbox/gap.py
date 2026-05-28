import dataclasses
from dataclasses import dataclass, field, asdict, fields
from typing import List
from enum import Enum


class GapDirectionType(str, Enum):
    """笔的类型"""
    UP = 'up'  # 上升缺口
    DOWN = 'down'  # 下降缺口


@dataclass
class Gap:
    """原始的K线数据类"""

    trade_date: str
    type: GapDirectionType
    position: str  # 'belowBar' 或者  'aboveBar'
    color: str
    shape: str  # 'arrowUp' 或者 'arrowDown'
    text: str

    def to_kwargs(self):
        return dataclasses.asdict(self)
