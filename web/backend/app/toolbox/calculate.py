from typing import Dict, List, Union, Optional
import pandas as pd


def calculate_macd(
    close: pd.Series,
    short_window: int = 10,
    long_window: int = 21,
    signal_window: int = 7
) -> Dict[str, Union[pd.Series, list]]:
    """
    计算 MACD 指标

    Args:
        close: 收盘价序列
        short_window: 短期 EMA 窗口
        long_window: 长期 EMA 窗口
        signal_window: 信号线 DEA 窗口

    Returns:
        包含 DIF, DEA 和 MACD_Hist 的字典
    """
    # 计算 EMA
    ema_short = close.ewm(span=short_window, adjust=False).mean()
    ema_long = close.ewm(span=long_window, adjust=False).mean()

    # 计算 DIF (差离值)
    dif = ema_short - ema_long

    # 计算 DEA (讯号线)
    dea = dif.ewm(span=signal_window, adjust=False).mean()

    # 计算柱状图 (MACD Histogram)
    histogram = (dif - dea) * 2

    return {
        'DIF': dif,
        'DEA': dea,
        'MACD_Hist': histogram.tolist()
    }


# MACD 4-color palette: TongDaXin uses RED/WHITE/GREEN/WHITE; pure WHITE is invisible
# on a white background, so the weakening bars use light tints instead.
_MACD_RED_STRONG = '#ef5350'      # MACD>prev and MACD>0   (rising positive)
_MACD_RED_LIGHT = '#f4a8a4'      # MACD<=prev and MACD>0  (falling positive)
_MACD_GREEN_STRONG = '#00a800'   # MACD<prev and MACD<0   (falling negative)
_MACD_GREEN_LIGHT = '#9fd6a8'    # MACD>=prev and MACD<0  (rising negative)


def calculate_macd_indicator(
    close: pd.Series,
    short: int = 10,
    long: int = 21,
    mid: int = 7,
    precision: int = 2,
) -> Dict[str, Union[List, Dict]]:
    """
    TongDaXin-style MACD (DIFF / DEA / MACD histogram) preserving every feature of the
    reference formula: 4-color histogram, red/green column area (x100) with block length
    and average area, lianzeng (consecutive same-trend bars via turning-point detection),
    and area text annotations at sign flips and at the last bar.

    Returns {"lines":[DIFF,DEA], "stats":[per-bar], "markers":[area annotations]}.
    """
    import numpy as np

    ema_short = close.ewm(span=short, adjust=False).mean()
    ema_long = close.ewm(span=long, adjust=False).mean()
    dif = ema_short - ema_long
    dea = dif.ewm(span=mid, adjust=False).mean()
    macd = (dif - dea) * 2

    macd_prev = macd.shift(1)
    pos = macd > 0
    block = (pos != pos.shift(1)).cumsum()  # id of each same-sign run

    block_sum = macd.groupby(block).cumsum()        # running sum within run
    block_len = macd.groupby(block).cumcount() + 1  # length within run

    red_area = (block_sum * 100).where(pos, 0.0)
    green_area = (block_sum * 100).where(~pos, 0.0)

    mm1 = macd.shift(1)
    mm2 = macd.shift(2)
    is_turn = (np.maximum(macd.values, mm2.values) < mm1.values) | (np.minimum(macd.values, mm2.values) > mm1.values)
    is_turn_s = pd.Series(is_turn, index=macd.index).fillna(False)
    idx = pd.Series(np.arange(len(macd)), index=macd.index)
    last_turn = idx.where(is_turn_s).ffill()
    same_len = (idx - last_turn).fillna(idx) + 1  # BARSLAST(IS_TURNING_POINT)+1
    lianzeng = same_len.where(macd > macd.shift(1), -same_len)

    times = list(close.index)
    macd_v = macd.tolist()
    prev_v = macd_prev.tolist()
    dif_v = dif.tolist()
    dea_v = dea.tolist()
    red_v = red_area.tolist()
    green_v = green_area.tolist()
    len_v = block_len.tolist()
    lian_v = lianzeng.tolist()

    stats = []
    lines_diff = []
    lines_dea = []
    for i, t in enumerate(times):
        m = macd_v[i]
        mp = prev_v[i]
        if mp != mp:  # NaN (first bar)
            color = _MACD_RED_STRONG if m > 0 else (_MACD_GREEN_STRONG if m < 0 else _MACD_GREEN_LIGHT)
        elif m > 0:
            color = _MACD_RED_STRONG if m > mp else _MACD_RED_LIGHT
        elif m < 0:
            color = _MACD_GREEN_STRONG if m < mp else _MACD_GREEN_LIGHT
        else:
            color = _MACD_GREEN_LIGHT
        area = red_v[i] if m > 0 else green_v[i]
        avg = (area / len_v[i]) if len_v[i] else 0.0
        stats.append({
            "time": str(t),
            "dif": round(float(dif_v[i]), precision),
            "dea": round(float(dea_v[i]), precision),
            "macd": round(float(m), precision),
            "color": color,
            "lianzeng": int(lian_v[i]),
            "area": round(float(area), 2),
            "avg": round(float(avg), 2),
        })
        lines_diff.append({"time": str(t), "value": round(float(dif_v[i]), precision)})
        lines_dea.append({"time": str(t), "value": round(float(dea_v[i]), precision)})

    markers = []
    prev_pos = None
    for i, t in enumerate(times):
        cur_pos = macd_v[i] > 0
        if prev_pos is True and not cur_pos:
            markers.append({"time": str(t), "position": "aboveBar", "color": _MACD_RED_STRONG,
                            "shape": "circle", "text": f"{red_v[i-1]:.1f}"})
        elif prev_pos is False and cur_pos:
            markers.append({"time": str(t), "position": "belowBar", "color": _MACD_GREEN_STRONG,
                            "shape": "circle", "text": f"{abs(green_v[i-1]):.1f}"})
        prev_pos = cur_pos
    last_t = str(times[-1])
    lm = macd_v[-1]
    if not markers or markers[-1]["time"] != last_t:
        if lm > 0:
            markers.append({"time": last_t, "position": "aboveBar", "color": _MACD_RED_STRONG,
                            "shape": "circle", "text": f"{red_v[-1]:.1f}"})
        elif lm < 0:
            markers.append({"time": last_t, "position": "belowBar", "color": _MACD_GREEN_STRONG,
                            "shape": "circle", "text": f"{abs(green_v[-1]):.1f}"})

    return {
        "lines": [
            {"key": "DIFF", "color": "#ff9800", "values": lines_diff},
            {"key": "DEA", "color": "#5b9bd5", "values": lines_dea},
        ],
        "stats": stats,
        "markers": markers,
    }

def calculate_ma(close: pd.Series, day_count: int) -> pd.Series:
    """
    计算移动平均线 (MA)

    Args:
        close: 收盘价序列
        day_count: 移动平均的天数

    Returns:
        移动平均值序列
    """
    return close.rolling(window=day_count).mean().round(2)


def calculate_ma_list(
    close: pd.Series,
    periods: List[int],
    min_periods: Optional[int] = None,
) -> List[Dict[str, Union[str, int, List[Dict[str, Union[str, float]]]]]]:
    """
    一次性计算多条简单移动平均线(MA), 返回前端可直接渲染的结构.

    Args:
        close: 收盘价序列(已按时间升序)
        periods: MA 窗口期列表, 例如 [5, 10, 20, 30]
        min_periods: 窗口内至少需要多少个非 NaN 点才输出值;
                     None 时使用 pandas 默认(等于 window, 即满窗才输出)

    Returns:
        [{"period": 5, "values": [{"time": "2024-01-07", "value": 10.32}, ...]}, ...]
        窗口未满处的 NaN 会被跳过, 不出现在 values 里.
    """
    result: List[Dict[str, Union[str, int, List[Dict[str, Union[str, float]]]]]] = []
    for period in periods:
        rolling_kwargs = {"window": period}
        if min_periods is not None:
            rolling_kwargs["min_periods"] = min_periods
        series = close.rolling(**rolling_kwargs).mean().round(2)
        values = [
            {"time": str(idx), "value": float(val)}
            for idx, val in series.items() if pd.notna(val)
        ]
        result.append({"period": period, "values": values})
    return result




def _series_to_values(series: pd.Series, precision: int = 2) -> List[Dict[str, Union[str, float]]]:
    """
    将 pandas Series 转为前端可渲染的 [{time, value}] 结构, 自动跳过 NaN.

    Args:
        series: 已按时间升序的序列
        precision: 数值保留小数位

    Returns:
        [{"time": "2024-01-07", "value": 10.32}, ...]
    """
    return [
        {"time": str(idx), "value": round(float(val), precision)}
        for idx, val in series.items() if pd.notna(val)
    ]


def calculate_boll_list(
    close: pd.Series,
    n: int = 26,
    k: int = 2,
    precision: int = 2,
) -> List[Dict[str, Union[str, List]]]:
    """
    一次性计算布林带(BOLL), 默认参数 (26, 2):
      MID  = SMA(close, n)
      UP   = MID + k * STD(close, n)   # STD 采用总体标准差(ddof=0), 与通达信一致
      DOWN = MID - k * STD(close, n)

    Returns:
        [{"key": "BOLL_UP", "values": [...]}, {"key": "BOLL_MID", ...}, {"key": "BOLL_DOWN", ...}]
    """
    mid = close.rolling(window=n).mean()
    std = close.rolling(window=n).std(ddof=0)
    up = mid + k * std
    down = mid - k * std
    return [
        {"key": "BOLL_UP", "values": _series_to_values(up, precision)},
        {"key": "BOLL_MID", "values": _series_to_values(mid, precision)},
        {"key": "BOLL_DOWN", "values": _series_to_values(down, precision)},
    ]


def calculate_rsi_list(
    close: pd.Series,
    periods: Optional[List[int]] = None,
    precision: int = 2,
) -> List[Dict[str, Union[str, List]]]:
    """
    一次性计算多周期 RSI (Wilder 平滑), 默认周期 [6, 12, 24]:
      RS  = 平均上涨幅度 / 平均下跌幅度 (ewm, alpha=1/period)
      RSI = 100 - 100 / (1 + RS)

    Returns:
        [{"key": "RSI6", "values": [...]}, {"key": "RSI12", ...}, {"key": "RSI24", ...}]
    """
    if periods is None:
        periods = [6, 12, 24]
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    result: List[Dict[str, Union[str, List]]] = []
    for period in periods:
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)
        result.append({"key": f"RSI{period}", "values": _series_to_values(rsi, precision)})
    return result


def calculate_ma_colors(periods: List[int], alpha: float = 0.9) -> List[str]:
    """
    根据 periods 列表确定性地生成 MA 配色:
      - 同一 periods 每次运行/调用都得到完全相同的颜色(seed 基于 periods 元组的哈希)
      - periods 内容/长度变化时, 整组颜色会重新生成

    Args:
        periods: MA 窗口期列表, 例如 [5, 10, 20, 30]
        alpha: 颜色透明度, 默认 0.9

    Returns:
        与 periods 等长的 rgba 颜色字符串列表, RGB 分量限定在 60-230 区间
        (避免过暗/过亮, 保证在 K 线黑白背景上都读)
    """
    import random
    rng = random.Random(tuple(periods).__hash__())
    return [
        f'rgba({rng.randint(60, 230)}, {rng.randint(60, 230)}, {rng.randint(60, 230)}, {alpha})'
        for _ in periods
    ]
