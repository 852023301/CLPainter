from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Optional, Union

import numpy as np

if TYPE_CHECKING:
    from CLPainter.web.backend.app.toolbox.bi import BiBase
    from CLPainter.web.backend.app.toolbox.xianduan import XianDuanBase

ChartLike = Union[Mapping, str]


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
    macd_turned: bool = False


def macd_divergence(
    earlier: BiBase | XianDuanBase,
    later: BiBase | XianDuanBase,
    macd_data: ChartLike,
) -> MacdDivergence:
    """用当前级别副图比较前一段和后一段是否背驰。

    earlier 和 later 为两笔或两段实例，必须同方向；区间、方向和终点价格直接从实例读取。
    两个实例的 start_idx、end_idx 必须与副图对应同一份完整 K 线序列，不能传截取后的副图。

    面积优先使用副图 ``stats`` 中未舍入的 ``macd_raw``，DIF 优先使用 ``dif_raw``。
    手工传入的 stats 没有 raw 字段时，macd/dif 必须是分析用的原始数值；旧副图需重新生成以保留精度。
    上升段只累计正柱，下降段只累计负柱绝对值，
    区间是起点之后到终点，含终点。段内反向的柱子和快线不计入面积、柱高和快线极值。
    后一段创出更极端的价格，面积严格更小，两段之间至少有一根相反颜色的柱，
    且后段没有同向柱或在段内出现过收缩，才算背驰。没有同向柱时 macd_turned 仍为 False。
    转折要求后段区间内至少出现过一次同向柱收缩；反向柱增强不算收缩，末端重新增强不取消确认。
    只使用后段自身区间，不使用其终点之后的 K 线。没有同向 DIF 时极值为 None，dif_lower 为 False。
    柱高变低和快线极值变低只记在结果里，不参与判断。
    """
    upward = earlier.is_up()
    if upward != later.is_up():
        raise ValueError("比较的两笔或两段必须同方向")

    histogram, dif, _ = _load_chart(macd_data)
    earlier_strength = _stroke_strength(histogram, dif, earlier.start_idx, earlier.end_idx, upward)
    later_strength = _stroke_strength(histogram, dif, later.start_idx, later.end_idx, upward)
    macd_turned = _macd_turned(histogram, later.start_idx, later.end_idx, upward)
    more_extreme = later.end_price > earlier.end_price if upward else later.end_price < earlier.end_price
    diverged = (
        earlier_strength.area > 0.0
        and later_strength.area < earlier_strength.area
        and more_extreme
        and _separated(histogram, earlier.end_idx, later.start_idx, upward)
        and (later_strength.area == 0.0 or macd_turned)
    )
    return MacdDivergence(
        diverged,
        earlier_strength.area,
        later_strength.area,
        earlier_strength.peak,
        later_strength.peak,
        earlier_strength.peak > 0.0 and later_strength.peak < earlier_strength.peak,
        earlier_strength.dif,
        later_strength.dif,
        earlier_strength.dif is not None
        and later_strength.dif is not None
        and earlier_strength.dif > 0.0
        and later_strength.dif < earlier_strength.dif,
        macd_turned,
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
    if not isinstance(stats, list) or not stats or any(
        not isinstance(bar, Mapping) or "macd" not in bar or "time" not in bar for bar in stats
    ):
        raise ValueError("副图 stats 缺少 time 或 macd")
    macd_field = _analysis_field(stats, 'macd')
    dif_field = _analysis_field(stats, 'dif')
    histogram = _finite_column(stats, macd_field)
    dif = _finite_column(stats, dif_field) if dif_field is not None else None
    return histogram, dif, stats


def _analysis_field(stats: list, name: str) -> Optional[str]:
    for field in (f'{name}_raw', name):
        flags = [field in bar for bar in stats]
        if any(flags):
            if not all(flags):
                raise ValueError(f'副图 stats 的 {field} 不完整')
            return field
    return None


def _finite_column(stats: list, field: str) -> np.ndarray:
    try:
        values = np.asarray([bar[field] for bar in stats], dtype=float)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f'副图 {field} 必须为一维有限数值') from error
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError(f'副图 {field} 必须为一维有限数值，不允许 NaN 或 Infinity')
    return values


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
        directional_dif = np.maximum(dif_segment if upward else -dif_segment, 0.0)
        peak = float(directional_dif.max())
        dif_extreme = peak if peak > 0.0 else None
    return _StrokeStrength(float(directional.sum()), float(directional.max()), dif_extreme)


def _macd_turned(macd: np.ndarray, start_idx: int, end_idx: int, upward: bool) -> bool:
    segment = macd[start_idx + 1 : end_idx + 1]
    directional = segment if upward else -segment
    return bool(np.any((directional[:-1] > 0.0) & (directional[1:] < directional[:-1])))


def _separated(macd: np.ndarray, earlier_end_idx: int, later_start_idx: int, upward: bool) -> bool:
    if later_start_idx <= earlier_end_idx:
        return False
    gap = macd[earlier_end_idx + 1 : later_start_idx + 1]
    if upward:
        return bool(np.any(gap < 0.0))
    return bool(np.any(gap > 0.0))
