from typing import Any, Optional


def quasi_third_point_type(cache: Any) -> Optional[int]:
    """返回最后一笔的类三买/类三卖类型：NULL=无法判断，0=都不是，1=类三买，2=类三卖。"""
    bi_list = cache.bi_list
    if len(bi_list) < 4:
        return None

    last_bi = bi_list[-1]
    reference_bi = bi_list[-3]
    previous_reference_bi = bi_list[-4]
    if last_bi.idx - previous_reference_bi.idx != 3:
        return None

    if last_bi.is_down() and reference_bi.is_down() and previous_reference_bi.is_up():
        if reference_bi.low_price >= previous_reference_bi.low_price and last_bi.low_price > reference_bi.high_price:
            return 1
        return 0
    if last_bi.is_up() and reference_bi.is_up() and previous_reference_bi.is_down():
        if reference_bi.high_price <= previous_reference_bi.high_price and last_bi.high_price < reference_bi.low_price:
            return 2
        return 0
    return 0
