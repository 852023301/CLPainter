from typing import Any, Optional


def relative_pivot_position(kline: Any, pivot: Any) -> int:
    """用一根 K 线的高低点判断相对中枢位置。"""
    if pivot is None:
        return 0
    if kline.low > pivot.high_price:
        return 3
    if kline.high < pivot.low_price:
        return 2
    return 1


def calculate_positions(cache: Any) -> tuple[Optional[int], Optional[int]]:
    """计算最后一笔终点 K 线相对当前中枢和扩展中枢的位置。

    返回 ``(relative_pivot_position, relative_previous_pivot_position)``：
    前者使用线段内笔中枢，后者使用未去重的笔中枢。
    """
    bi_list = cache.bi_list
    klines = cache.origin_kline_data
    if not klines:
        return None, None

    if not bi_list:
        return 0, 0

    last_bi = bi_list[-1]
    if last_bi.end_idx < 0 or last_bi.end_idx >= len(klines):
        return None, None

    last_kline = klines[last_bi.end_idx]
    current_pivots = cache.bi_zhongshu_in_xianduan_list or []
    previous_pivots = cache.bi_zhongshu_raw_list or []
    current_position = relative_pivot_position(
        last_kline,
        current_pivots[-1] if current_pivots else None,
    )
    previous_position = relative_pivot_position(
        last_kline,
        previous_pivots[-1] if previous_pivots else None,
    )
    return current_position, previous_position
