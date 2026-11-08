"""缠论线段端点回归。

用例清单在 ``regression_cases.py``，本文件只负责执行 segment 级案例。
数据来源是 ``dump/curated`` 缓存，和前端实际读取的结果保持一致。
"""

from pathlib import Path

import pytest

from CLPainter.web.backend.app.toolbox.datacube import (
    CACHE_DUMP_DIR,
    load_data_cache_pickle,
)
from CLPainter.web.backend.tests.regression_cases import SEGMENT_CASES

CACHE_ROOT = Path(CACHE_DUMP_DIR)
pytestmark = pytest.mark.skipif(
    not CACHE_ROOT.exists(),
    reason=f"curated 缓存目录不存在: {CACHE_ROOT}",
)


def _load_segments(case) -> list[tuple]:
    cache = load_data_cache_pickle(
        case.symbol,
        case.frequency,
        "market=cn",
        case.asset_class,
        CACHE_ROOT,
    )
    return [
        (
            str(segment.start_time.date()),
            str(segment.end_time.date()),
            type(segment).__name__,
            segment.is_up(),
        )
        for segment in (cache.xian_duan_list or [])
    ]


def _assert_match(actual: list[tuple], case) -> None:
    expected = case.expected
    if case.match == "contains":
        assert expected in actual, f"{case.case_id}: 未找到期望线段 {expected}"
        return
    if case.match == "endpoint":
        assert any(
            start == expected or end == expected
            for start, end, _type_name, _is_up in actual
        ), f"{case.case_id}: 端点 {expected} 不在任何线段上"
        return

    expected = tuple(expected)
    if case.match == "full":
        assert actual == list(expected), f"{case.case_id}: 线段列表不匹配"
    elif case.match == "prefix":
        assert actual[: len(expected)] == list(expected), f"{case.case_id}: 前 {len(expected)} 条线段不匹配"
    elif case.match == "suffix":
        assert actual[-len(expected) :] == list(expected), f"{case.case_id}: 后 {len(expected)} 条线段不匹配"
    else:
        raise AssertionError(f"{case.case_id}: 未知 match 模式 {case.match}")


@pytest.mark.parametrize("case", SEGMENT_CASES, ids=lambda case: case.case_id)
def test_segment_regression(case):
    _assert_match(_load_segments(case), case)


def test_segment_cases_have_unique_ids():
    ids = [case.case_id for case in SEGMENT_CASES]
    assert len(ids) == len(set(ids))


def test_segment_cases_cover_expected_document_ids():
    ids = {case.case_id.split("-", 1)[0] for case in SEGMENT_CASES}
    assert {
        "S1",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8",
        "S9",
        "S10",
        "S11",
        "S13",
        "S24",
        "S25",
        "S26",
        "S27",
        "S28",
    }.issubset(ids)
