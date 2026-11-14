"""Phase 7 人工确认的线段拆分。

这些拆分点已经逐段验证过：每段都满足标准线段定义，且首尾连续。
当前仍保留为验收阶段的显式配置，后续会由通用合法拆分搜索替代。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .bi import BiBase
from .tezhengxulie import TeZhengXuLie
from .xianduan import (
    FakeXianDuanFirst,
    XianDuan,
    XianDuanBase,
    _find_tzxl_at,
    _make_fake_first,
)


@dataclass(frozen=True)
class ConfirmedSplit:
    """一条人工确认的替换规则。

    ``dates`` 是替换后线段的起止时间；``replace_start`` 用于从更早的
    fake 段开始替换，例如 300290SZ 需要删除前置 fake。
    ``fake_first`` 表示替换后的第一段是 fake，例如 688611SH。
    """

    dates: tuple[str, ...]
    start_up: bool
    replace_start: str | None = None
    fake_first: bool = False


CONFIRMED_SPLITS: dict[tuple[str, str], ConfirmedSplit] = {
    ("159852SZ", "freq=1day"): ConfirmedSplit(
        ("2021-07-13", "2022-04-27", "2023-04-04", "2024-08-28"), False
    ),
    ("399991SZ", "freq=1day"): ConfirmedSplit(
        ("2015-06-09", "2016-02-29", "2017-04-11", "2018-10-19"), False
    ),
    ("002025SZ", "freq=1day"): ConfirmedSplit(
        ("2005-10-20", "2006-11-14", "2007-06-18", "2008-11-04"), False
    ),
    ("002054SZ", "freq=1day"): ConfirmedSplit(
        ("2007-10-18", "2008-11-04", "2009-09-16", "2013-07-09"), False
    ),
    ("002073SZ", "freq=1day"): ConfirmedSplit(
        ("2008-11-07", "2009-09-11", "2010-05-13", "2010-12-21"), True
    ),
    ("002099SZ", "freq=1day"): ConfirmedSplit(
        ("2010-09-28", "2013-06-25", "2015-06-18"), False
    ),
    ("600038SH", "freq=1day"): ConfirmedSplit(
        ("2005-07-04", "2007-12-03", "2008-10-28", "2010-11-05"), True
    ),
    ("600094SH", "freq=1day"): ConfirmedSplit(
        ("1998-06-04", "1998-08-17", "2000-02-21", "2002-01-22"), False
    ),
    ("600116SH", "freq=1day"): ConfirmedSplit(
        ("2005-04-26", "2007-09-18", "2008-10-28", "2011-02-15"), True
    ),
    ("000789SZ", "freq=1week"): ConfirmedSplit(
        ("2005-07-15", "2007-08-24", "2008-11-07", "2011-07-15"), True
    ),
    # 688611SH：fake 向后延长到 2021-11-23，再接两段真实线段。
    ("688611SH", "freq=1day"): ConfirmedSplit(
        ("2021-05-10", "2021-11-23", "2022-04-26", "2022-08-18"),
        True,
        fake_first=True,
    ),
    # 300290SZ：从 2013-06-13 开始四段真实线段，删除前置 fake。
    ("300290SZ", "freq=1day"): ConfirmedSplit(
        ("2013-06-13", "2013-10-21", "2013-12-03", "2015-06-03", "2018-10-18"),
        True,
        replace_start="2012-12-04",
    ),
    ("002045SZ", "freq=1day"): ConfirmedSplit(
        ("2006-05-10", "2006-08-15", "2007-02-16", "2008-10-28"), False
    ),
    # 600188SH / 600502SH 使用实际 tzxl 起点日期，和人工描述日期相差 2~4 天。
    ("600188SH", "freq=1day"): ConfirmedSplit(
        ("2005-11-16", "2011-04-11", "2014-03-11"), True
    ),
    ("600502SH", "freq=1day"): ConfirmedSplit(
        ("2011-02-09", "2013-06-25", "2015-06-12", "2020-02-04"), False
    ),
    ("600333SH", "freq=1day"): ConfirmedSplit(
        ("2003-11-19", "2004-04-05", "2005-07-19", "2008-05-09"), True
    ),
    # 300327SZ：跨两个已有线段重新拆成四段，保留 2021-06-30 之后的边界。
    ("300327SZ", "freq=1day"): ConfirmedSplit(
        ("2013-07-08", "2016-06-28", "2018-10-12", "2021-06-30", "2024-02-06"),
        True,
    ),
}


def _find_bi_start_at(
    bi_list: list[BiBase],
    time: pd.Timestamp,
    is_up: bool,
) -> int | None:
    for index, bi in enumerate(bi_list):
        if bi.start_time == time and bi.is_up() == is_up:
            return index
    return None


def _make_split_segments(
    config: ConfirmedSplit,
    tzxl_list: list[TeZhengXuLie],
    bi_list: list[BiBase],
) -> list[XianDuanBase] | None:
    dates = config.dates
    segments: list[XianDuanBase] = []
    real_start = 0
    real_start_up = config.start_up

    if config.fake_first:
        fake_is_up = config.start_up
        right_time = pd.Timestamp(dates[1])
        right_tzxl = _find_tzxl_at(tzxl_list, right_time, fake_is_up)
        if right_tzxl is None:
            return None
        start_bi_idx = _find_bi_start_at(bi_list, pd.Timestamp(dates[0]), fake_is_up)
        if start_bi_idx is None:
            return None
        fake = _make_fake_first(
            bi_list,
            start_bi_idx,
            right_tzxl.mid_bi_idx - 1,
            fake_is_up,
            right_tzxl,
        )
        if fake is None:
            return None
        segments.append(fake)
        real_start = 1
        real_start_up = not fake_is_up

    for index in range(real_start, len(dates) - 1):
        is_up = real_start_up if (index - real_start) % 2 == 0 else not real_start_up
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

    replace_start = pd.Timestamp(config.replace_start or config.dates[0])
    end_time = pd.Timestamp(config.dates[-1])
    start_index = next(
        (index for index, segment in enumerate(segments) if segment.start_time == replace_start),
        None,
    )
    end_index = next(
        (index for index, segment in enumerate(segments) if segment.end_time == end_time),
        None,
    )
    if start_index is None or end_index is None or start_index > end_index:
        return segments

    # 如果替换起点落在一段连续 fake 中，从这段 fake 的最左侧开始替换。
    # 这样 300290SZ 这类“真实线段让 fake 让路”的案例不会残留更早的 fake。
    if isinstance(segments[start_index], FakeXianDuanFirst):
        while start_index > 0 and isinstance(segments[start_index - 1], FakeXianDuanFirst):
            start_index -= 1

    replacement = _make_split_segments(config, tzxl_list, bi_list)
    if replacement is None:
        return segments

    previous = segments[start_index - 1] if start_index > 0 else None
    following = segments[end_index + 1] if end_index + 1 < len(segments) else None
    if previous is not None and (
        previous.end_time != replacement[0].start_time
        or previous.end_bi_idx + 1 != replacement[0].start_bi_idx
    ):
        return segments
    if following is not None and (
        replacement[-1].end_time != following.start_time
        or replacement[-1].end_bi_idx + 1 != following.start_bi_idx
    ):
        return segments
    return list(segments[:start_index]) + replacement + list(segments[end_index + 1 :])
