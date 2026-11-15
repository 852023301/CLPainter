"""上游数据质量回归。

S20-S23 属于数据清洗/空值处理，不属于线段算法。
这里直接使用测试环境 raw 数据和 curated 缓存做可执行断言。
"""

from pathlib import Path

import pytest

from CLPainter.web.backend.app._config.settings import settings
from CLPainter.web.backend.app.toolbox.datacube import (
    CACHE_DUMP_DIR,
    get_cache_dump_path,
    load_data_cache_pickle,
    load_raw_data,
)
from CLPainter.web.backend.tests.regression_cases import DATA_QUALITY_CASES

DATA_ROOT = Path(settings.DATA_DIR)
CACHE_ROOT = Path(CACHE_DUMP_DIR)


@pytest.fixture(scope="module", autouse=True)
def require_test_data():
    """数据质量回归必须使用真实测试数据，缺失时明确失败而不是 skip。"""
    missing = [str(path) for path in (DATA_ROOT, CACHE_ROOT) if not path.exists()]
    if missing:
        pytest.fail(f"数据质量回归缺少测试数据目录: {', '.join(missing)}")


def _source_path(case) -> Path:
    return DATA_ROOT / case.frequency / "market=cn" / case.asset_class / f"{case.symbol}.pkl"


def _cache_path(case) -> Path:
    return get_cache_dump_path(
        case.symbol,
        case.frequency,
        "market=cn",
        case.asset_class,
        CACHE_ROOT,
    )


def _cache(case):
    return load_data_cache_pickle(
        case.symbol,
        case.frequency,
        "market=cn",
        case.asset_class,
        CACHE_ROOT,
    )


def _raw_row(case, date: str):
    raw = load_raw_data(_source_path(case))
    for row in raw:
        if str(row[0])[:10] == date:
            return row
    raise AssertionError(f"{case.case_id}: raw 数据缺少 {date}")


@pytest.mark.parametrize(
    "case,date",
    (
        (DATA_QUALITY_CASES[0], "2026-03-11"),
        (DATA_QUALITY_CASES[1], "2021-09-10"),
    ),
    ids=("S20", "S21"),
)
def test_zero_ohlc_is_filled_with_close(case, date):
    row = _raw_row(case, date)
    open_price, close_price, low_price, high_price = row[1:5]
    assert open_price == close_price == low_price == high_price

    cache = _cache(case)
    kline = next(
        (
            item
            for item in cache.origin_kline_data
            if item.trade_datetime.strftime("%Y-%m-%d") == date
        ),
        None,
    )
    assert kline is not None
    assert kline.open == kline.close == kline.low == kline.high
    assert kline.has_gap is False


def test_empty_symbol_does_not_write_cache():
    case = DATA_QUALITY_CASES[2]
    assert not _source_path(case).exists()
    assert not _cache_path(case).exists()


def test_listing_placeholder_symbol_is_skipped_without_breaking_batch():
    case = DATA_QUALITY_CASES[3]
    source = _source_path(case)
    cache_path = _cache_path(case)
    assert source.exists()
    assert cache_path.exists()

    cache = _cache(case)
    assert cache.origin_kline_data
    assert all(item.trade_datetime.year > 1900 for item in cache.origin_kline_data)
