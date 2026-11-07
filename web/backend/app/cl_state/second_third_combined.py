from typing import Any, Optional

from .second_point import second_point_type


def second_third_combined_type(cache: Any) -> Optional[int]:
    """返回最后一笔的二三合买/二三合卖类型：NULL=无法判断，0=都不是，1=二三合买，2=二三合卖。"""
    bi_list = cache.bi_list
    xian_duan_list = cache.xian_duan_list
    if not bi_list or not xian_duan_list:
        return None

    second_type = second_point_type(cache)
    if second_type is None:
        return None

    last_bi = bi_list[-1]
    segment = xian_duan_list[-1]
    segment_pivots = [
        pivot
        for pivot in (cache.bi_zhongshu_in_xianduan_list or [])
        if pivot.start_time >= segment.start_time and pivot.end_time <= segment.end_time
    ]
    if not segment_pivots:
        return 0

    last_segment_pivot = max(segment_pivots, key=lambda pivot: (pivot.start_time, pivot.end_time))
    if (
        second_type == 1
        and segment.is_down()
        and last_bi.is_down()
        and last_bi.low_price > last_segment_pivot.high_price
    ):
        return 1
    if (
        second_type == 2
        and segment.is_up()
        and last_bi.is_up()
        and last_bi.high_price < last_segment_pivot.low_price
    ):
        return 2
    return 0
