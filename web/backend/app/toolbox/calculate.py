from typing import Dict, Union
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
