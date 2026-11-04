from typing import Any, Optional


def second_point_type(cache: Any) -> Optional[int]:
    """返回最后一笔的二买/二卖类型：NULL=无法判断，0=都不是，1=二买，2=二卖。"""
    bi_list = cache.bi_list
    xian_duan_list = cache.xian_duan_list
    if not bi_list or not xian_duan_list:
        return None

    last_bi = bi_list[-1]
    segment = xian_duan_list[-1]
    start_idx = segment.start_bi_idx
    end_idx = segment.end_bi_idx
    if start_idx < 0 or end_idx >= len(bi_list) or start_idx > end_idx:
        return None

    segment_bi_list = bi_list[start_idx:end_idx + 1]
    if segment.is_down():
        if not last_bi.is_down():
            return 0
        candidates = [bi for bi in segment_bi_list if bi.is_down()]
        if not candidates:
            return 0
        lowest_bi = min(candidates, key=lambda bi: (bi.low_price, -bi.idx))
        if last_bi.idx != lowest_bi.idx + 2:
            return 0
        return 1 if last_bi.low_price >= lowest_bi.low_price else 0

    if segment.is_up():
        if not last_bi.is_up():
            return 0
        candidates = [bi for bi in segment_bi_list if bi.is_up()]
        if not candidates:
            return 0
        highest_bi = max(candidates, key=lambda bi: (bi.high_price, bi.idx))
        if last_bi.idx != highest_bi.idx + 2:
            return 0
        return 2 if last_bi.high_price <= highest_bi.high_price else 0

    return 0
