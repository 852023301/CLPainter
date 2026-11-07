from typing import Any, Optional


def third_point_type(cache: Any) -> Optional[int]:
    """返回最后一笔的三买/三卖类型：NULL=无法判断，0=都不是，1=三买，2=三卖。"""
    bi_list = cache.bi_list
    xian_duan_list = cache.xian_duan_list
    if not bi_list or not xian_duan_list:
        return None

    segment = xian_duan_list[-1]
    segment_pivots = [
        pivot
        for pivot in (cache.bi_zhongshu_in_xianduan_list or [])
        if pivot.start_time >= segment.start_time and pivot.end_time <= segment.end_time
    ]
    if not segment_pivots:
        return 0

    last_pivot = max(segment_pivots, key=lambda pivot: (pivot.start_time, pivot.end_time))
    last_bi = bi_list[-1]
    if len(bi_list) < 2 or last_bi.idx <= last_pivot.end_bi_idx:
        return 0

    previous_bi = bi_list[-2]
    previous_still_overlaps = (
        previous_bi.high_price >= last_pivot.low_price
        and previous_bi.low_price <= last_pivot.high_price
    )
    if not previous_still_overlaps:
        return 0

    if last_bi.is_down() and previous_bi.is_up() and last_bi.low_price > last_pivot.high_price:
        return 1
    if last_bi.is_up() and previous_bi.is_down() and last_bi.high_price < last_pivot.low_price:
        return 2
    return 0
