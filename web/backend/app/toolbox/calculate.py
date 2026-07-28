from typing import Dict, List, Union
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
    min_periods: int = 1,
) -> List[Dict[str, Union[str, int, List[Dict[str, Union[str, float]]]]]]:
    """
    一次性计算多条简单移动平均线(MA), 返回前端可直接渲染的结构.

    Args:
        close: 收盘价序列(已按时间升序)
        periods: MA 窗口期列表, 例如 [5, 10, 20, 30]
        min_periods: 窗口内至少需要多少个非 NaN 点才输出值, 默认 1
                     (pandas rolling 默认要求满窗才输出, 这里透传该参数)

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
