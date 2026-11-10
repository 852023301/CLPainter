"""缠论笔端点回归。

用例清单在 ``regression_cases.py``，本文件只负责执行 bi 级案例和 pivot 级案例。
"""

from pathlib import Path

import pytest

from CLPainter.web.backend.app.toolbox.datacube import (
    CACHE_DUMP_DIR,
    load_data_cache_pickle,
)
from CLPainter.web.backend.tests.regression_cases import BI_CASES, PIVOT_CASES

CACHE_ROOT = Path(CACHE_DUMP_DIR)
pytestmark = pytest.mark.skipif(
    not CACHE_ROOT.exists(),
    reason=f"curated 缓存目录不存在: {CACHE_ROOT}",
)


def _load_cache(case):
    return load_data_cache_pickle(
        case.symbol,
        case.frequency,
        "market=cn",
        case.asset_class,
        CACHE_ROOT,
    )


def _load_bis(case) -> list[tuple]:
    cache = _load_cache(case)
    return [
        (
            bi.bi_type.value,
            str(bi.start_time.date()),
            str(bi.end_time.date()),
        )
        for bi in (cache.bi_list or [])
    ]


def _assert_match(actual: list[tuple], case) -> None:
    expected = tuple(case.expected)
    if case.match == "full":
        assert actual == list(expected), f"{case.case_id}: 笔列表不匹配"
    elif case.match == "prefix":
        assert actual[: len(expected)] == list(expected), f"{case.case_id}: 前 {len(expected)} 笔不匹配"
    elif case.match == "suffix":
        assert actual[-len(expected) :] == list(expected), f"{case.case_id}: 后 {len(expected)} 笔不匹配"
    else:
        raise AssertionError(f"{case.case_id}: 未知 match 模式 {case.match}")


@pytest.mark.parametrize("case", BI_CASES, ids=lambda case: case.case_id)
def test_bi_regression(case):
    _assert_match(_load_bis(case), case)


def test_bi_cases_have_unique_ids():
    ids = [case.case_id for case in BI_CASES]
    assert len(ids) == len(set(ids))


def test_bi_cases_cover_expected_document_ids():
    ids = {case.case_id.split("-", 1)[0] for case in BI_CASES}
    assert {
        "S2",
        "S12",
        "S14",
        "S15",
        "S16",
        "S17",
        "S18",
        "S19",
    }.issubset(ids)


@pytest.mark.parametrize("case", PIVOT_CASES, ids=lambda case: case.case_id)
def test_pivot_regression(case):
    cache = _load_cache(case)
    if case.case_id == "S14-weekly":
        assert cache.bi_zhongshu_in_xianduan_list, "300663SZ 周线缺少线段中枢"
    else:
        raise AssertionError(f"{case.case_id}: 未实现的 pivot 检查")
