from dataclasses import dataclass, field
from typing import List


@dataclass
class MergedKLine:
    """合并后的K线数据类"""

    trade_date: str
    open: float
    close: float
    low: float
    high: float
    volume: float  # 交易量单位为股

    # K线合并状态
    _is_contained: int = field(default=0, repr=False)  # 是否被合并：1=合并，0=未合并
    merged_length: int = 1  # 连续合并的K线数量
    merged_trend: int = 1  # 合并趋势：1=向上，0=向下
    merged_high: float = field(init=False)  # 合并后的最高价
    merged_low: float = field(init=False)  # 合并后的最低价

    # 分型标记：1=顶分型，-1=底分型，0=无分型
    is_top_bottom: int = 0

    # 是否有缺口：True=有缺口，False=无缺口
    has_gap: bool = False

    def __post_init__(self):
        # 初始化合并后的高低点为当前K线的高低点
        self.merged_high = self.high
        self.merged_low = self.low

    @property
    def is_contained(self) -> int:
        return self._is_contained

    @is_contained.setter
    def is_contained(self, value: int):
        if value not in (0, 1):
            raise ValueError("is_contained must be 0 or 1")
        self._is_contained = value



def merge_klines(origin_klines: List[List]) -> List[MergedKLine]:
    """
    K线合并处理（缠论包含关系处理）

    Args:
        origin_klines: 原始K线数据列表，每个元素为 [date, open, close, low, high, volume]

    Returns:
        合并后的K线列表
    """
    if not origin_klines:
        return []

    all_klines: List[MergedKLine] = []

    for kl in origin_klines:
        merged_kline = MergedKLine(*kl)

        if not all_klines:
            # 第一根K线直接添加
            all_klines.append(merged_kline)
            continue

        last_kline = all_klines[-1]

        if merged_kline.low > last_kline.high or merged_kline.high < last_kline.low:
            merged_kline.has_gap = True

        # 判断趋势方向
        if last_kline.merged_high < merged_kline.high and last_kline.merged_low < merged_kline.low:
            merged_kline.merged_trend = 1  # 向上趋势
        elif last_kline.merged_high > merged_kline.high and last_kline.merged_low > merged_kline.low:
            merged_kline.merged_trend = 0  # 向下趋势
        else:
            # 存在包含关系，需要合并
            if _has_containment(last_kline, merged_kline):
                _apply_containment(last_kline, merged_kline)
                all_klines.append(merged_kline)
                continue

        all_klines.append(merged_kline)

    return all_klines


def _has_containment(k1: MergedKLine, k2: MergedKLine) -> bool:
    """判断两根K线是否存在包含关系"""
    return (
        (k1.merged_high <= k2.high and k1.merged_low >= k2.low) or
        (k1.high >= k2.high and k1.merged_low <= k2.low)
    )


def _apply_containment(last_kline: MergedKLine, current_kline: MergedKLine) -> None:
    """应用K线包含关系合并规则"""
    current_kline.is_contained = 1
    current_kline.merged_trend = last_kline.merged_trend
    current_kline.merged_length = last_kline.merged_length + 1

    # 根据趋势方向确定合并后的高低点
    if last_kline.merged_high <= current_kline.high and last_kline.merged_low >= current_kline.low:
        # 情况1：当前K线被上一根包含
        if current_kline.merged_trend == 1:  # 向上趋势取高高
            current_kline.merged_high = current_kline.high
            current_kline.merged_low = last_kline.low
        else:  # 向下趋势取低低
            current_kline.merged_high = last_kline.merged_high
            current_kline.merged_low = current_kline.low

    elif last_kline.high >= current_kline.high and last_kline.merged_low <= current_kline.low:
        # 情况2：上一根K线被当前包含
        if current_kline.merged_trend == 1:  # 向上趋势取高高
            current_kline.merged_high = last_kline.high
            current_kline.merged_low = current_kline.low
        else:  # 向下趋势取低低
            current_kline.merged_high = current_kline.high
            current_kline.merged_low = last_kline.merged_low
    else:
        raise ValueError(f"异常的包含关系: {last_kline.trade_date} -> {current_kline.trade_date}")



def find_top_bottom(all_klines: List[MergedKLine]) -> None:
    """
    寻找合并后K线的顶底分型
    """
    if len(all_klines) < 3:
        return

    for idx in range(2, len(all_klines)):
        current_kline = all_klines[idx]

        # 只处理未被合并的K线
        if current_kline.merged_length != 1:
            continue

        # 获取前两根未合并的K线
        prev_offset = current_kline.merged_length
        mid_idx = idx - prev_offset
        left_idx = mid_idx - all_klines[mid_idx].merged_length

        if left_idx < 0:
            continue

        left_kline = all_klines[left_idx]
        mid_kline = all_klines[mid_idx]

        # 判断底分型：左中右形成V型
        if left_kline.merged_low > mid_kline.merged_low < current_kline.merged_low:
            current_kline.is_top_bottom = -1
        # 判断顶分型：左中右形成倒V型
        elif left_kline.merged_high < mid_kline.merged_high > current_kline.merged_high:
            current_kline.is_top_bottom = 1
        else:
            current_kline.is_top_bottom = 0