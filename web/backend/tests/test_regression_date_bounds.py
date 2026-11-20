"""Only explicitly marked final endpoints may advance beyond their baseline dates."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from CLPainter.web.backend.tests.regression_cases import BI_CASES, SEGMENT_CASES, BiCase
from CLPainter.web.backend.tests.test_bi_regressions import _assert_match as assert_bis
from CLPainter.web.backend.tests.test_xianduan_pipeline import assert_acceptance
from CLPainter.web.backend.tests.test_xianduan_regressions import _assert_match as assert_segments


CASES = tuple(case for case in BI_CASES + SEGMENT_CASES if case.case_id in {"S14-quarter", "S15", "S25", "S28"})


def rows_with_end_offset(case, days):
    rows = list(case.expected)
    index = 2 if isinstance(case, BiCase) else 1
    last = list(rows[-1])
    last[index] = (date.fromisoformat(last[index]) + timedelta(days=days)).isoformat()
    rows[-1] = tuple(last)
    return rows


def check(case, rows, reader):
    if reader == "cache":
        (assert_bis if isinstance(case, BiCase) else assert_segments)(rows, case)
        return
    if isinstance(case, BiCase):
        cache = SimpleNamespace(bi_list=[SimpleNamespace(
            bi_type=SimpleNamespace(value=direction), start_time=datetime.fromisoformat(start),
            end_time=datetime.fromisoformat(end), start_price=1, end_price=2,
        ) for direction, start, end in rows])
    else:
        cache = SimpleNamespace(xian_duan_list=[type(kind, (SimpleNamespace,), {})(
            start_time=datetime.fromisoformat(start), end_time=datetime.fromisoformat(end),
            start_price=1, end_price=2, start_bi_idx=0, end_bi_idx=1, is_up=lambda value=up: value,
        ) for start, end, kind, up in rows])
    assert_acceptance(case, cache)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
@pytest.mark.parametrize("reader", ["cache", "raw"])
@pytest.mark.parametrize("days", [0, 1, 30])
def test_final_endpoint_accepts_equal_or_later_dates(case, reader, days):
    check(case, rows_with_end_offset(case, days), reader)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
@pytest.mark.parametrize("reader", ["cache", "raw"])
def test_final_endpoint_rejects_dates_before_the_lower_bound(case, reader):
    with pytest.raises(AssertionError):
        check(case, rows_with_end_offset(case, -1), reader)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
@pytest.mark.parametrize("reader", ["cache", "raw"])
@pytest.mark.parametrize("change", ["start", "direction", "missing", "extra"])
def test_later_endpoint_does_not_relax_other_structure_checks(case, reader, change):
    rows = rows_with_end_offset(case, 1)
    last = list(rows[-1])
    if change == "start":
        last[1 if isinstance(case, BiCase) else 0] = "1900-01-01"
        rows[-1] = tuple(last)
    elif change == "direction":
        if isinstance(case, BiCase):
            last[0] = "up" if last[0] == "down" else "down"
        else:
            last[3] = not last[3]
        rows[-1] = tuple(last)
    elif change == "missing":
        rows.pop()
    else:
        rows.append(rows[-1])
    with pytest.raises(AssertionError):
        check(case, rows, reader)


@pytest.mark.parametrize("case", tuple(case for case in CASES if len(case.expected) > 1), ids=lambda case: case.case_id)
@pytest.mark.parametrize("reader", ["cache", "raw"])
def test_historical_endpoint_remains_exact(case, reader):
    rows = rows_with_end_offset(case, 1)
    index = 2 if isinstance(case, BiCase) else 1
    first = list(rows[0])
    first[index] = (date.fromisoformat(first[index]) + timedelta(days=1)).isoformat()
    rows[0] = tuple(first)
    with pytest.raises(AssertionError):
        check(case, rows, reader)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
@pytest.mark.parametrize("reader", ["cache", "raw"])
def test_unmarked_case_keeps_exact_final_date(case, reader):
    strict_case = replace(case, last_end_at_least=False)
    with pytest.raises(AssertionError):
        check(strict_case, rows_with_end_offset(case, 1), reader)


@pytest.mark.parametrize(
    "case", tuple(case for case in CASES if not isinstance(case, BiCase)), ids=lambda case: case.case_id,
)
@pytest.mark.parametrize("reader", ["cache", "raw"])
def test_later_endpoint_does_not_relax_segment_type(case, reader):
    rows = rows_with_end_offset(case, 1)
    last = list(rows[-1])
    last[2] = "XianDuan"
    rows[-1] = tuple(last)
    with pytest.raises(AssertionError):
        check(case, rows, reader)


def test_only_requested_cases_enable_the_lower_bound():
    assert {case.case_id for case in BI_CASES + SEGMENT_CASES if case.last_end_at_least} == {
        "S14-quarter", "S15", "S25", "S28",
    }
