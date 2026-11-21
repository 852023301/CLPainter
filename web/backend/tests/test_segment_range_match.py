"""S25 checks one downward segment covers the requested historical interval."""

from dataclasses import replace

import pytest
from CLPainter.web.backend.tests.regression_cases import SEGMENT_CASES
from CLPainter.web.backend.tests.test_regression_date_bounds import check

S25 = next(case for case in SEGMENT_CASES if case.case_id == "S25")
RANGE_CASE = replace(S25, match="contains_range", expected=("2025-09-25", "2026-10-19", False), last_end_at_least=False)


@pytest.mark.parametrize("reader", ["cache", "raw"])
@pytest.mark.parametrize(
    "rows",
    [
        [("2025-09-25", "2026-10-19", "XianDuan", False)],
        [("2025-09-25", "2026-11-20", "FakeXianDuanLast", False)],
        [("2025-08-01", "2026-11-20", "XianDuan", False)],
        [
            ("2025-09-25", "2026-10-19", "XianDuan", False),
            ("2026-10-19", "2026-10-28", "XianDuan", True),
            ("2026-10-28", "2026-11-04", "XianDuan", False),
            ("2026-11-04", "2026-11-11", "FakeXianDuanLast", True),
        ],
    ],
)
def test_segment_covering_the_whole_range_is_accepted(reader, rows):
    check(RANGE_CASE, rows, reader)


@pytest.mark.parametrize("reader", ["cache", "raw"])
@pytest.mark.parametrize(
    "rows",
    [
        [],
        [("2025-09-25", "2026-11-20", "XianDuan", True)],
        [("2025-09-26", "2026-11-20", "XianDuan", False)],
        [("2025-09-25", "2026-10-18", "FakeXianDuanLast", False)],
        [("2025-09-25", "2026-02-01", "XianDuan", False), ("2026-02-01", "2026-10-19", "XianDuan", False)],
    ],
)
def test_upward_partial_missing_or_stitched_ranges_are_rejected(reader, rows):
    with pytest.raises(AssertionError):
        check(RANGE_CASE, rows, reader)


def test_only_s25_uses_the_new_range_acceptance_rule():
    assert {case.case_id for case in SEGMENT_CASES if case.match == "contains_range"} == {"S25"}
    assert S25.expected == ("2025-09-25", "2026-10-19", False)
    assert S25.last_end_at_least is False
