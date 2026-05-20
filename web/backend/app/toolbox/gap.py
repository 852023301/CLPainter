import dataclasses
from dataclasses import dataclass, field, asdict, fields
from typing import List

@dataclass
class Gap:
    """原始的K线数据类"""

    trade_date: str
    open: float
    close: float
    low: float
    high: float
    volume: float  # 交易量单位为股