import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Optional, Union

import numpy as np
import pandas as pd

ChartLike = Union[Mapping, str]
Bound = Union[int, str, datetime, pd.Timestamp]
_INDEX_LIMIT = 1_000_000_000


@dataclass(frozen=True)
class MacdDivergence:
    """两段同向走势的 MACD 比较结果。"""

    diverged: bool
    earlier_area: float
    later_area: float
    earlier_peak: float
    later_peak: float
    peak_lower: bool
    earlier_dif: Optional[float]
    later_dif: Optional[float]
    dif_lower: bool


def macd_divergence(
    macd_data: ChartLike,
    earlier_start: Bound,
    earlier_end: Bound,
    later_start: Bound,
    later_end: Bound,
    upward: bool,
    earlier_end_price: float,
    later_end_price: float,
) -> MacdDivergence:
    """用当前级别副图比较前一段和后一段是否背驰。

    每段的起点和终点可以是索引，也可以是时间。日线时间用 ``2024-01-02`` 或当天零点的
    Timestamp；分钟时间用副图里的 UTC 秒，或带时分的 Timestamp。索引只在小于 10 亿时生效。

    面积使用副图 ``stats`` 里已经四舍五入的 ``macd`` 柱。上升段只累计正柱，下降段只累计负柱绝对值，
    区间是起点之后到终点，含终点。段内反向的柱子和快线不计入面积、柱高和快线极值。
    后一段创出更极端的价格，面积严格更小，并且两段之间至少有一根相反颜色的柱，才算背驰。
    柱高变低和快线极值变低只记在结果里，不参与判断。``upward`` 表示这两段的共同方向。
    """
    histogram, dif, stats = _load_chart(macd_data)
    time_index = _time_index(stats)
    earlier_start_idx = _resolve_bound(earlier_start, time_index, len(histogram))
    earlier_end_idx = _resolve_bound(earlier_end, time_index, len(histogram))
    later_start_idx = _resolve_bound(later_start, time_index, len(histogram))
    later_end_idx = _resolve_bound(later_end, time_index, len(histogram))

    earlier = _stroke_strength(histogram, dif, earlier_start_idx, earlier_end_idx, upward)
    later = _stroke_strength(histogram, dif, later_start_idx, later_end_idx, upward)
    more_extreme = later_end_price > earlier_end_price if upward else later_end_price < earlier_end_price
    diverged = (
        earlier.area > 0.0
        and later.area < earlier.area
        and more_extreme
        and _separated(histogram, earlier_end_idx, later_start_idx, upward)
    )
    return MacdDivergence(
        diverged,
        earlier.area,
        later.area,
        earlier.peak,
        later.peak,
        earlier.peak > 0.0 and later.peak < earlier.peak,
        earlier.dif,
        later.dif,
        earlier.dif is not None and later.dif is not None and earlier.dif > 0.0 and later.dif < earlier.dif,
    )


def _load_chart(macd_data: ChartLike) -> tuple:
    payload = json.loads(macd_data) if isinstance(macd_data, str) else dict(macd_data)
    if "stats" not in payload:
        nested = payload.get("macd_data")
        if isinstance(nested, str):
            nested = json.loads(nested)
        if not isinstance(nested, Mapping) or "stats" not in nested:
            raise ValueError("副图数据缺少 stats")
        payload = nested
    stats = payload["stats"]
    if not isinstance(stats, list) or any("macd" not in bar or "time" not in bar for bar in stats):
        raise ValueError("副图 stats 缺少 time 或 macd")
    dif_flags = ["dif" in bar for bar in stats]
    if any(dif_flags) and not all(dif_flags):
        raise ValueError("副图 stats 的 dif 不完整")
    dif = np.asarray([bar["dif"] for bar in stats], dtype=float) if all(dif_flags) else None
    return np.asarray([bar["macd"] for bar in stats], dtype=float), dif, stats


@dataclass(frozen=True)
class _StrokeStrength:
    area: float
    peak: float
    dif: Optional[float]


def _stroke_strength(
    macd: np.ndarray,
    dif: Optional[np.ndarray],
    start_idx: int,
    end_idx: int,
    upward: bool,
) -> _StrokeStrength:
    if start_idx < 0 or end_idx >= len(macd) or start_idx >= end_idx:
        raise ValueError(f"走势索引无效: start_idx={start_idx}, end_idx={end_idx}, macd长度={len(macd)}")
    segment = macd[start_idx + 1 : end_idx + 1]
    directional = np.maximum(segment, 0.0) if upward else np.maximum(-segment, 0.0)
    dif_extreme = None
    if dif is not None:
        dif_segment = dif[start_idx + 1 : end_idx + 1]
        dif_extreme = float(np.max(dif_segment)) if upward else float(abs(np.min(dif_segment)))
    return _StrokeStrength(float(directional.sum()), float(directional.max()), dif_extreme)


def _time_index(stats: list) -> dict:
    mapping = {}
    for index, bar in enumerate(stats):
        raw_time = bar["time"]
        mapping[raw_time] = index
        mapping[str(raw_time)] = index
    return mapping


def _resolve_bound(value: Bound, time_index: dict, size: int) -> int:
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        number = int(value)
        if number < _INDEX_LIMIT:
            if number < 0 or number >= size:
                raise ValueError(f"走势索引越界: {number}, 副图长度={size}")
            return number
        try:
            return time_index[number]
        except KeyError:
            raise ValueError(f"副图中找不到时间: {value}") from None
    key = _chart_time_key(value)
    try:
        return time_index[key]
    except KeyError:
        raise ValueError(f"副图中找不到时间: {value}") from None


def _chart_time_key(value: Bound):
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            number = int(text)
            if number >= _INDEX_LIMIT:
                return number
            raise ValueError(f"无法把字符串当时间: {value}")
        value = pd.Timestamp(text)
    if isinstance(value, datetime) and not isinstance(value, pd.Timestamp):
        value = pd.Timestamp(value)
    if not isinstance(value, pd.Timestamp):
        raise ValueError(f"无法识别的端点: {value!r}")
    if value.tzinfo is not None:
        value = value.tz_convert("UTC").tz_localize(None)
    if value == value.normalize():
        return value.strftime("%Y-%m-%d")
    return int(value.replace(tzinfo=timezone.utc).timestamp())


def _separated(macd: np.ndarray, earlier_end_idx: int, later_start_idx: int, upward: bool) -> bool:
    if later_start_idx <= earlier_end_idx:
        return False
    gap = macd[earlier_end_idx + 1 : later_start_idx + 1]
    if upward:
        return bool(np.any(gap < 0.0))
    return bool(np.any(gap > 0.0))
