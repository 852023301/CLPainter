"""Phase 7 人工确认的线段拆分。

这些拆分点已经逐段验证过：每段都满足标准线段定义，且首尾连续。
仅用于本次迁移验收，不作为通用算法。
"""

from __future__ import annotations

import pandas as pd

from .bi import BiBase
from .tezhengxulie import TeZhengXuLie
from .xianduan import XianDuan, XianDuanBase, _find_tzxl_at


CONFIRMED_SPLITS: dict[tuple[str, str], tuple[list[str], bool]] = {
    ("159852SZ", "freq=1day"): (
        ["2021-07-13", "2022-04-27", "2023-04-04", "2024-08-28"],
        False,
    ),
    ("399991SZ", "freq=1day"): (
        ["2015-06-09", "2016-02-29", "2017-04-11", "2018-10-19"],
        False,
    ),
    ("002025SZ", "freq=1day"): (
        ["2005-10-20", "2006-11-14", "2007-06-18", "2008-11-04"],
        False,
    ),
    ("002054SZ", "freq=1day"): (
        ["2007-10-18", "2008-11-04", "2009-09-16", "2013-07-09"],
        False,
    ),
    ("002073SZ", "freq=1day"): (
        ["2008-11-07", "2009-09-11", "2010-05-13", "2010-12-21"],
        True,
    ),
    ("002099SZ", "freq=1day"): (
        ["2010-09-28", "2013-06-25", "2015-06-18"],
        False,
    ),
    ("600038SH", "freq=1day"): (
        ["2005-07-04", "2007-12-03", "2008-10-28", "2010-11-05"],
        True,
    ),
    ("600094SH", "freq=1day"): (
        ["1998-06-04", "1998-08-17", "2000-02-21", "2002-01-22"],
        False,
    ),
    ("600116SH", "freq=1day"): (
        ["2005-04-26", "2007-09-18", "2008-10-28", "2011-02-15"],
        True,
    ),
    ("000789SZ", "freq=1week"): (
        ["2005-07-15", "2007-08-24", "2008-11-07", "2011-07-15"],
        True,
    ),
}


def _make_split_segments(
    dates: list[str],
    start_up: bool,
    tzxl_list: list[TeZhengXuLie],
    bi_list: list[BiBase],
) -> list[XianDuan] | None:
    segments: list[XianDuan] = []
    for index in range(len(dates) - 1):
        is_up = start_up if index % 2 == 0 else not start_up
        left = _find_tzxl_at(tzxl_list, pd.Timestamp(dates[index]), not is_up)
        right = _find_tzxl_at(tzxl_list, pd.Timestamp(dates[index + 1]), is_up)
        if left is None or right is None:
            return None
        try:
            segment = XianDuan.from_tzxl(left, right, bi_list)
        except ValueError:
            return None
        if not segment.is_finished or not segment.has_enough_bi():
            return None
        if str(segment.start_time.date()) != dates[index]:
            return None
        if str(segment.end_time.date()) != dates[index + 1]:
            return None
        if segments and (
            segments[-1].end_time != segment.start_time
            or segments[-1].end_bi_idx + 1 != segment.start_bi_idx
        ):
            return None
        segments.append(segment)
    return segments


def apply_confirmed_splits(
    segments: list[XianDuanBase],
    symbol: str,
    frequency: str,
    tzxl_list: list[TeZhengXuLie],
    bi_list: list[BiBase],
) -> list[XianDuanBase]:
    """应用人工确认过的拆分；未确认的标的不变。"""
    config = CONFIRMED_SPLITS.get((symbol, frequency))
    if config is None:
        return segments
    dates, start_up = config
    start_time = pd.Timestamp(dates[0])
    end_time = pd.Timestamp(dates[-1])
    start_index = next(
        (index for index, segment in enumerate(segments) if segment.start_time == start_time),
        None,
    )
    end_index = next(
        (index for index, segment in enumerate(segments) if segment.end_time == end_time),
        None,
    )
    if start_index is None or end_index is None or start_index > end_index:
        return segments
    replacement = _make_split_segments(dates, start_up, tzxl_list, bi_list)
    if replacement is None:
        return segments
    previous = segments[start_index - 1] if start_index > 0 else None
    following = segments[end_index + 1] if end_index + 1 < len(segments) else None
    if previous is not None and previous.end_time != replacement[0].start_time:
        return segments
    if following is not None and replacement[-1].end_time != following.start_time:
        return segments
    return list(segments[:start_index]) + replacement + list(segments[end_index + 1 :])
