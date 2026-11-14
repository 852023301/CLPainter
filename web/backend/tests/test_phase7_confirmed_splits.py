"""Phase 7 人工确认拆分的回归测试。

这些用例直接读取测试环境 curated 缓存，并调用实际后处理函数，
确保人工确认的拆分不会被后续改动悄悄回退。
"""

from pathlib import Path

import pytest

from CLPainter.web.backend.app.toolbox.datacube import (
    CACHE_DUMP_DIR,
    load_data_cache_pickle,
)
from CLPainter.web.backend.app.toolbox.phase7_confirmed_splits import (
    apply_confirmed_splits,
)

CACHE_ROOT = Path(CACHE_DUMP_DIR)
pytestmark = pytest.mark.skipif(
    not CACHE_ROOT.exists(),
    reason=f"curated 缓存目录不存在: {CACHE_ROOT}",
)


CASES = (
    (
        "688611SH",
        "freq=1day",
        "asset_class=stock",
        0,
        (
            ("2021-05-10", "2021-11-23", "FakeXianDuanFirst", True),
            ("2021-11-23", "2022-04-26", "XianDuan", False),
            ("2022-04-26", "2022-08-18", "XianDuan", True),
        ),
    ),
    (
        "300290SZ",
        "freq=1day",
        "asset_class=stock",
        0,
        (
            ("2013-06-13", "2013-10-21", "XianDuan", True),
            ("2013-10-21", "2013-12-03", "XianDuan", False),
            ("2013-12-03", "2015-06-03", "XianDuan", True),
            ("2015-06-03", "2018-10-18", "XianDuan", False),
        ),
    ),
    (
        "002045SZ",
        "freq=1day",
        "asset_class=stock",
        1,
        (
            ("2006-05-10", "2006-08-15", "XianDuan", False),
            ("2006-08-15", "2007-02-16", "XianDuan", True),
            ("2007-02-16", "2008-10-28", "XianDuan", False),
        ),
    ),
    (
        "600188SH",
        "freq=1day",
        "asset_class=stock",
        7,
        (
            ("2005-11-16", "2011-04-11", "XianDuan", True),
            ("2011-04-11", "2014-03-11", "XianDuan", False),
        ),
    ),
    (
        "600502SH",
        "freq=1day",
        "asset_class=stock",
        4,
        (
            ("2011-02-09", "2013-06-25", "XianDuan", False),
            ("2013-06-25", "2015-06-12", "XianDuan", True),
            ("2015-06-12", "2020-02-04", "XianDuan", False),
        ),
    ),
    (
        "600333SH",
        "freq=1day",
        "asset_class=stock",
        2,
        (
            ("2003-11-19", "2004-04-05", "XianDuan", True),
            ("2004-04-05", "2005-07-19", "XianDuan", False),
            ("2005-07-19", "2008-05-09", "XianDuan", True),
        ),
    ),
    (
        "300327SZ",
        "freq=1day",
        "asset_class=stock",
        1,
        (
            ("2013-07-08", "2016-06-28", "XianDuan", True),
            ("2016-06-28", "2018-10-12", "XianDuan", False),
            ("2018-10-12", "2021-06-30", "XianDuan", True),
            ("2021-06-30", "2024-02-06", "XianDuan", False),
        ),
    ),
)


def _canonical(segments) -> list[tuple]:
    return [
        (
            str(segment.start_time.date()),
            str(segment.end_time.date()),
            type(segment).__name__,
            segment.is_up(),
        )
        for segment in segments
    ]


@pytest.mark.parametrize(
    "symbol,frequency,asset_class,start_index,expected",
    CASES,
    ids=[case[0] for case in CASES],
)
def test_confirmed_split_is_applied(
    symbol: str,
    frequency: str,
    asset_class: str,
    start_index: int,
    expected: tuple,
):
    cache = load_data_cache_pickle(
        symbol,
        frequency,
        "market=cn",
        asset_class,
        CACHE_ROOT,
    )
    result = apply_confirmed_splits(
        list(cache.xian_duan_list or []),
        symbol,
        frequency,
        list(cache.te_zheng_xu_lie_list or []),
        list(cache.bi_list or []),
    )
    actual = _canonical(result)
    assert actual[start_index : start_index + len(expected)] == list(expected)

    for previous, current in zip(result, result[1:]):
        assert previous.end_time == current.start_time
        assert previous.end_bi_idx + 1 == current.start_bi_idx
