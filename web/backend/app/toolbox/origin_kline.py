import dataclasses
from dataclasses import dataclass, field, asdict, fields
from typing import List

@dataclass
class OriginKLine:
    """原始的K线数据类"""

    trade_date: str
    open: float
    close: float
    low: float
    high: float
    volume: float  # 交易量单位为股

    # 是否有缺口：True=有缺口，False=无缺口
    has_gap: bool = False

    def to_kwargs(self):
        return dataclasses.asdict(self)

    def __iter__(self):
        return (getattr(self, f.name) for f in fields(self))


def generate_origin_klines(raw_klines: List[List]) -> List[OriginKLine]:
    """
        原始K线处理（

        Args:
            raw_klines: 原始K线数据列表类，每个元素为 [date, open, close, low, high, volume]

        Returns:
            处理后的K线列表
        """


    origin_klines = [OriginKLine(*kl) for kl in raw_klines]
    gaps = []

    for idx, kl in enumerate(origin_klines):
        if idx < 1:
            continue
        last_origin_kline = origin_klines[idx-1]
        if kl.low > last_origin_kline.high:
            kl.has_gap = True

        if kl.high < last_origin_kline.low:
            kl.has_gap = True


    return origin_klines