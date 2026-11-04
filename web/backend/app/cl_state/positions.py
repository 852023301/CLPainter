from typing import Any, Optional


def relative_pivot_position(stroke: Any, pivot: Any) -> int:
    """用一笔或一段的价格区间判断相对中枢位置。"""
    if pivot is None:
        return 0
    if stroke.low_price > pivot.high_price:
        return 3
    if stroke.high_price < pivot.low_price:
        return 2
    return 1


def calculate_positions(cache: Any) -> tuple[Optional[int], Optional[int]]:
    """计算最后一笔相对当前中枢和扩展中枢的位置。

    返回 ``(relative_pivot_position, relative_previous_pivot_position)``：
    前者使用线段内笔中枢，后者使用未去重的笔中枢。
    """
    bi_list = cache.bi_list
    if not bi_list:
        return 0, 0

    last_bi = bi_list[-1]
    current_pivots = cache.bi_zhongshu_in_xianduan_list or []
    previous_pivots = cache.bi_zhongshu_raw_list or []
    current_position = relative_pivot_position(
        last_bi,
        current_pivots[-1] if current_pivots else None,
    )
    previous_position = relative_pivot_position(
        last_bi,
        previous_pivots[-1] if previous_pivots else None,
    )
    return current_position, previous_position
