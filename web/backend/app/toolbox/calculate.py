import pandas as pd


def calculate_macd(close , short_window=10, long_window=21, signal_window=7):
    # 计算EMA
    ema_short = close.ewm(span=short_window, adjust=False).mean()
    ema_long = close.ewm(span=long_window, adjust=False).mean()

    # 计算DIF
    dif = ema_short - ema_long

    # 计算DEA
    dea = dif.ewm(span=signal_window, adjust=False).mean()

    # 计算柱状图
    histogram = (dif - dea) * 2

    result = dict()
    # 合并到原数据
    result['DIF'] = dif
    result['DEA'] = dea
    result['MACD_Hist'] =   list(histogram)
    return result



def calculate_ma(close, day_count: int):
    # result: List[Union[float, str]] = []
    #
    # for i in range(len(trade_date_list)):
    #     if i < day_count:
    #         result.append("-")
    #         continue
    #     sum_total = 0.0
    #     for j in range(day_count):
    #         sum_total += float(origin_kline_data[i - j][1])
    #     result.append(abs(float("%.2f" % (sum_total / day_count))))
    #

    result = close.rolling(window=day_count).mean().round(2)

    return result