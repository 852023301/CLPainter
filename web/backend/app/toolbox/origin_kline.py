import dataclasses
from dataclasses import dataclass, fields
from typing import List, Tuple
from enum import Enum
from .gap import Gap, GapDirectionType


class OriginKlineType(str, Enum):
    """笔的类型"""
    UP = 'up'  # 涨
    DOWN = 'down'  # 跌


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

    # 涨或跌
    type: OriginKlineType = OriginKlineType.UP   # close< open则为跌，其他情况视为涨

    def to_kwargs(self):
        return dataclasses.asdict(self)

    def __iter__(self):
        return (getattr(self, f.name) for f in fields(self))


def generate_origin_klines(raw_klines: List[List]) -> Tuple[List[OriginKLine], List[Gap]]:
    """
        原始K线处理（

        Args:
            raw_klines: 原始K线数据列表类，每个元素为 [date, open, close, low, high, volume]

        Returns:
            处理后的K线列表
        """

    origin_klines = [OriginKLine(*kl) for kl in raw_klines]
    gaps_list = []

    for idx, kl in enumerate(origin_klines):
        if idx < 1:
            continue

        # 涨或跌
        kl.type = OriginKlineType.UP if kl.close >= kl.open else OriginKlineType.DOWN

        last_origin_kline = origin_klines[idx - 1]
        if kl.low > last_origin_kline.high:
            kl.has_gap = True
            ratio = ((kl.low - last_origin_kline.high) / last_origin_kline.high * 100).__round__(2)
            gaps_list.append(Gap(
                trade_date=kl.trade_date,
                type=GapDirectionType.UP,
                position='belowBar',
                color='#ef5350',
                shape='arrowUp',
                text=f'+{(ratio)}%'
            ))

        if kl.high < last_origin_kline.low:
            kl.has_gap = True
            ratio = ((last_origin_kline.low - kl.high) / last_origin_kline.low * 100).__round__(2)
            gaps_list.append(Gap(
                trade_date=kl.trade_date,
                type=GapDirectionType.DOWN,
                position='aboveBar',
                color='#26a69a',
                shape='arrowDown',
                text=f'-{(ratio)}%'
            ))

    return origin_klines, gaps_list
