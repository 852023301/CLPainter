"""Phase 7 通用合法拆分搜索测试。"""

from pathlib import Path

import pandas as pd
import pytest

from CLPainter.web.backend.app.toolbox.datacube import (
    CACHE_DUMP_DIR,
    load_data_cache_pickle,
)
from CLPainter.web.backend.app.toolbox.legal_splits import (
    _violations,
    find_legal_split,
    search_legal_splits,
)
from CLPainter.web.backend.app.toolbox.xianduan import XianDuan, _find_tzxl_at

CACHE_ROOT = Path(CACHE_DUMP_DIR)
pytestmark = pytest.mark.skipif(
    not CACHE_ROOT.exists(),
    reason=f"curated 缓存目录不存在: {CACHE_ROOT}",
)


def _load_cache(symbol: str):
    return load_data_cache_pickle(
        symbol,
        "freq=1day",
        "market=cn",
        "asset_class=stock",
        CACHE_ROOT,
    )


def _segment(cache, start: str, end: str, is_up: bool) -> XianDuan:
    left = _find_tzxl_at(
        cache.te_zheng_xu_lie_list,
        pd.Timestamp(start),
        not is_up,
    )
    right = _find_tzxl_at(
        cache.te_zheng_xu_lie_list,
        pd.Timestamp(end),
        is_up,
    )
    assert left is not None and right is not None
    return XianDuan.from_tzxl(left, right, cache.bi_list)


def _dates(segments) -> list[str]:
    return [str(segment.start_time.date()) for segment in segments] + [
        str(segments[-1].end_time.date())
    ]


@pytest.mark.parametrize(
    "symbol,start,end,is_up,expected",
    (
        (
            "002045SZ",
            "2006-05-10",
            "2008-10-28",
            False,
            ["2006-05-10", "2006-08-15", "2007-02-16", "2008-10-28"],
        ),
        (
            "600333SH",
            "2003-11-19",
            "2008-05-09",
            True,
            ["2003-11-19", "2004-04-05", "2005-07-19", "2008-05-09"],
        ),
    ),
)
def test_find_legal_split(symbol, start, end, is_up, expected):
    cache = _load_cache(symbol)
    segment = _segment(cache, start, end, is_up)
    result = find_legal_split(segment, cache.te_zheng_xu_lie_list, cache.bi_list)
    assert result is not None
    assert _dates(result) == expected


def test_search_legal_splits_reduces_violations():
    cache = _load_cache("002045SZ")
    segment = _segment(cache, "2006-05-10", "2008-10-28", False)
    before = _violations([segment], cache.te_zheng_xu_lie_list, cache.bi_list)
    result = search_legal_splits(
        [segment],
        cache.te_zheng_xu_lie_list,
        cache.bi_list,
        target_indices={0},
    )
    after = _violations(result, cache.te_zheng_xu_lie_list, cache.bi_list)
    assert len(after) < len(before)
    assert _dates(result) == [
        "2006-05-10",
        "2006-08-15",
        "2007-02-16",
        "2008-10-28",
    ]
