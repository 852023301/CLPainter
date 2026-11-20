"""Confirmed-split producers, not precomputed results.

Only bi/tzxl components are read from the accepted test dataset. Each tested
window is synthesized as ONE unsplit fake-last candidate. Expected dates,
directions and types are independent acceptance fixtures, not runtime-rule
output. This is a component-level transformation test, not a raw rebuild.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from CLPainter.web.backend.app.toolbox import confirmed_splits as splits
from CLPainter.web.backend.app.toolbox.bi import BiBase
from CLPainter.web.backend.app.toolbox.datacube import CACHE_DUMP_DIR, load_data_cache_pickle
from CLPainter.web.backend.app.toolbox.tezhengxulie import TeZhengXuLie
from CLPainter.web.backend.app.toolbox.xianduan import XianDuan, XianDuanBase, _make_fake_last


@dataclass(frozen=True)
class ConfirmedCase:
    symbol: str
    dates: tuple[str, ...]
    start_up: bool
    frequency: str = "freq=1day"
    asset_class: str = "asset_class=stock"
    replace_start: str | None = None
    fake_first: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return self.symbol, self.frequency

    @property
    def expected(self) -> list[tuple]:
        return [
            (start, end, "FakeXianDuanFirst" if self.fake_first and index == 0 else "XianDuan",
             self.start_up if index % 2 == 0 else not self.start_up)
            for index, (start, end) in enumerate(zip(self.dates, self.dates[1:]))
        ]


# Frozen, reviewed expectations. Do not generate these from CONFIRMED_SPLITS.
CASES = (
    ConfirmedCase("159852SZ", ("2021-07-13", "2022-04-27", "2023-04-04", "2024-08-28"), False,
                  asset_class="asset_class=fund"),
    ConfirmedCase("399991SZ", ("2015-06-09", "2016-02-29", "2017-04-11", "2018-10-19"), False,
                  asset_class="asset_class=index"),
    ConfirmedCase("002025SZ", ("2005-10-20", "2006-11-14", "2007-06-18", "2008-11-04"), False),
    ConfirmedCase("002054SZ", ("2007-10-18", "2008-11-04", "2009-09-16", "2013-07-09"), False),
    ConfirmedCase("002073SZ", ("2008-11-07", "2009-09-11", "2010-05-13", "2010-12-21"), True),
    ConfirmedCase("002099SZ", ("2010-09-28", "2013-06-25", "2015-06-18"), False),
    ConfirmedCase("600038SH", ("2005-07-04", "2007-12-03", "2008-10-28", "2010-11-05"), True),
    ConfirmedCase("600094SH", ("1998-06-04", "1998-08-17", "2000-02-21", "2002-01-22"), False),
    ConfirmedCase("600116SH", ("2005-04-26", "2007-09-18", "2008-10-28", "2011-02-15"), True),
    ConfirmedCase("000789SZ", ("2005-07-15", "2007-08-24", "2008-11-07", "2011-07-15"), True,
                  frequency="freq=1week"),
    ConfirmedCase("688611SH", ("2021-05-10", "2021-11-23", "2022-04-26", "2022-08-18"), True,
                  fake_first=True),
    ConfirmedCase("300290SZ", ("2013-06-13", "2013-10-21", "2013-12-03", "2015-06-03", "2018-10-18"), True,
                  replace_start="2012-12-04"),
    ConfirmedCase("002045SZ", ("2006-05-10", "2006-08-15", "2007-02-16", "2008-10-28"), False),
    ConfirmedCase("600188SH", ("2005-11-16", "2011-04-11", "2014-03-11"), True),
    ConfirmedCase("600502SH", ("2011-02-09", "2013-06-25", "2015-06-12", "2020-02-04"), False),
    ConfirmedCase("600333SH", ("2003-11-19", "2004-04-05", "2005-07-19", "2008-05-09"), True),
    ConfirmedCase("300327SZ", ("2013-07-08", "2016-06-28", "2018-10-12", "2021-06-30", "2024-02-06"), True),
)
CACHE_ROOT = Path(CACHE_DUMP_DIR)


def canonical(segments: list[XianDuanBase]) -> list[tuple[str, str, str, bool]]:
    return [(str(x.start_time.date()), str(x.end_time.date()), type(x).__name__, x.is_up()) for x in segments]


def input_signature(segments: list[XianDuanBase]) -> list[tuple]:
    return [(str(x.start_time), str(x.end_time), type(x).__name__, x.is_up(),
             x.start_bi_idx, x.end_bi_idx, x.start_price, x.end_price) for x in segments]


def unsplit_input(case: ConfirmedCase) -> tuple[list[XianDuanBase], list[TeZhengXuLie], list[BiBase]]:
    path = CACHE_ROOT / case.frequency / "market=cn" / case.asset_class / (case.symbol + ".pkl")
    if not path.is_file():
        pytest.fail(f"Producer regression requires accepted bi/tzxl test data: {path}")
    cache = load_data_cache_pickle(case.symbol, case.frequency, "market=cn", case.asset_class, CACHE_ROOT)
    # Do not use cache.xian_duan_list to construct the input or the expected output.
    bis = cache.bi_list
    sequences = cache.te_zheng_xu_lie_list
    start = pd.Timestamp(case.replace_start or case.dates[0])
    end = pd.Timestamp(case.dates[-1])
    first = next((i for i, bi in enumerate(bis) if bi.start_time == start), None)
    last = next((i for i, bi in enumerate(bis) if bi.end_time == end), None)
    assert first is not None and last is not None, f"{case.key}: fixture is missing a boundary bi"
    candidate = _make_fake_last(bis, first, last, case.start_up, require_enough_bi=True)
    assert candidate is not None, f"{case.key}: cannot construct the unsplit input window"
    segments = [candidate]
    assert canonical(segments) != case.expected, f"{case.key}: input already contains the answer"
    return segments, sequences, bis


def assert_produced(case: ConfirmedCase, result: list[XianDuanBase], bis: list[BiBase]) -> None:
    assert canonical(result) == case.expected, f"{case.key}: producer output does not match accepted splitting"
    for segment in result:
        assert segment.has_enough_bi()
        if isinstance(segment, XianDuan):
            assert segment.is_finished
        start = bis[segment.start_bi_idx]
        end = bis[segment.end_bi_idx]
        assert (segment.start_idx, segment.start_time, segment.start_price) == (
            start.start_idx, start.start_time, start.start_price,
        )
        assert (segment.end_idx, segment.end_time, segment.end_price) == (
            end.end_idx, end.end_time, end.end_price,
        )
    for previous, current in zip(result, result[1:]):
        assert previous.end_time == current.start_time
        assert previous.end_bi_idx + 1 == current.start_bi_idx
        assert previous.is_up() != current.is_up()


def test_all_runtime_rules_have_independent_producer_expectations() -> None:
    keys = [case.key for case in CASES]
    assert len(keys) == len(set(keys)), "Duplicate producer acceptance cases"
    assert set(keys) == set(splits.CONFIRMED_SPLITS), "A runtime rule lacks a reviewed producer fixture"


@pytest.mark.parametrize(
    "case", CASES, ids=[case.symbol + "-" + case.frequency.removeprefix("freq=") for case in CASES],
)
def test_confirmed_rule_produces_expected_segments(case: ConfirmedCase) -> None:
    segments, sequences, bis = unsplit_input(case)
    before = input_signature(segments)
    result = splits.apply_confirmed_splits(segments, case.symbol, case.frequency, sequences, bis)
    assert_produced(case, result, bis)
    assert input_signature(segments) == before, "Producer mutated the supplied input window"


@pytest.mark.parametrize(
    "case", CASES, ids=[case.symbol + "-" + case.frequency.removeprefix("freq=") for case in CASES],
)
def test_producer_assertion_rejects_a_noop(case: ConfirmedCase, monkeypatch: pytest.MonkeyPatch) -> None:
    segments, sequences, bis = unsplit_input(case)
    monkeypatch.setattr(splits, "apply_confirmed_splits", lambda items, *args, **kwargs: items)
    result = splits.apply_confirmed_splits(segments, case.symbol, case.frequency, sequences, bis)
    with pytest.raises(AssertionError, match="producer output does not match accepted splitting"):
        assert_produced(case, result, bis)
