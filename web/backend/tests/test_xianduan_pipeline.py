"""Postprocess orchestration and representative raw + explicit-reference rebuilds.

Order tests use synthetic stage operations. Raw tests run the real loader,
bi/segment generators and postprocessing; they never publish cache files.
"""

from copy import deepcopy
from typing import Callable
from pathlib import Path
import pickle
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from CLPainter.web.backend.app.toolbox import datacube as dc
from CLPainter.web.backend.tests.regression_cases import (
    BI_CASES, SEGMENT_CASES, BiCase, SegmentCase, matches_expected_rows,
)


@pytest.mark.parametrize("search", [False, True], ids=["search-off", "search-on"])
def test_postprocess_order_and_dataflow(monkeypatch: pytest.MonkeyPatch, search: bool) -> None:
    calls = []
    reference = [object()]
    features = [object()]
    bis = [object()]
    seed = [SimpleNamespace(idx=99, stages=())]

    def operation(name: str) -> Callable:
        def run(segments, *args, **kwargs) -> list:
            assert segments[0].stages == tuple(calls), "A stage received an outdated intermediate result"
            if name == "reconcile":
                assert args == (reference, features, bis)
            elif name == "confirmed":
                assert args == ("SYNTHETIC", "freq=1day", features, bis)
            else:
                assert args == (features, bis)
            calls.append(name)
            return [SimpleNamespace(idx=99, stages=tuple(calls))]
        return run

    for name, attribute in (
        ("reconcile", "reconcile_first_segments"),
        ("promote", "promote_secondary_fakes"),
        ("confirmed", "apply_confirmed_splits"),
        ("search", "search_legal_splits"),
    ):
        monkeypatch.setattr(dc, attribute, operation(name))
    monkeypatch.setattr(dc.settings, "ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH", search)
    result = dc.postprocess_xian_duan(seed, reference, features, bis, symbol="SYNTHETIC", frequency="freq=1day")
    expected = ["reconcile", "promote", "confirmed"] + (["search"] if search else [])
    assert calls == expected
    assert result[0].stages == tuple(expected) and result[0].idx == 0
    assert seed[0].stages == () and seed[0].idx == 99


@pytest.mark.parametrize("symbol,frequency", [(None, "freq=1day"), ("SYNTHETIC", None)])
def test_postprocess_does_not_apply_symbol_rules_without_identity(
    monkeypatch: pytest.MonkeyPatch, symbol: str | None, frequency: str | None,
) -> None:
    confirmed = Mock(side_effect=AssertionError("No identity was supplied"))
    identity = lambda segments, *args: segments
    monkeypatch.setattr(dc, "reconcile_first_segments", identity)
    monkeypatch.setattr(dc, "promote_secondary_fakes", identity)
    monkeypatch.setattr(dc, "apply_confirmed_splits", confirmed)
    monkeypatch.setattr(dc.settings, "ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH", False)
    segment = SimpleNamespace(idx=-1)
    assert dc.postprocess_xian_duan([segment], None, [], [], symbol=symbol, frequency=frequency) == [segment]
    assert segment.idx == 0
    confirmed.assert_not_called()


RAW_CASES = tuple(case for case in SEGMENT_CASES if case.case_id in {"S1", "S4", "S5", "S26", "S28"}) + tuple(
    case for case in BI_CASES if case.case_id in {"S2", "S15"}
) + (
    SegmentCase("confirmed-fake-first", "688611SH", "freq=1day", "asset_class=stock", "prefix", (
        ("2021-05-10", "2021-11-23", "FakeXianDuanFirst", True),
        ("2021-11-23", "2022-04-26", "XianDuan", False),
        ("2022-04-26", "2022-08-18", "XianDuan", True),
    )),
    SegmentCase("confirmed-prefix-replacement", "300290SZ", "freq=1day", "asset_class=stock", "prefix", (
        ("2013-06-13", "2013-10-21", "XianDuan", True),
        ("2013-10-21", "2013-12-03", "XianDuan", False),
        ("2013-12-03", "2015-06-03", "XianDuan", True),
        ("2015-06-03", "2018-10-18", "XianDuan", False),
    )),
    SegmentCase("confirmed-cross-window", "300327SZ", "freq=1day", "asset_class=stock", "contains",
                ("2013-07-08", "2016-06-28", "XianDuan", True)),
)


def bi_rows(cache: dc._DataCache) -> list[tuple]:
    return [(b.bi_type.value, str(b.start_time.date()), str(b.end_time.date()),
             float(b.start_price), float(b.end_price)) for b in cache.bi_list]


def segment_rows(cache: dc._DataCache) -> list[tuple]:
    return [(str(x.start_time.date()), str(x.end_time.date()), type(x).__name__, x.is_up(),
             float(x.start_price), float(x.end_price), x.start_bi_idx, x.end_bi_idx)
            for x in cache.xian_duan_list]


def assert_acceptance(case: BiCase | SegmentCase, cache: dc._DataCache) -> None:
    if isinstance(case, BiCase):
        actual = [row[:3] for row in bi_rows(cache)]
    else:
        actual = [row[:4] for row in segment_rows(cache)]
    if case.match == "contains":
        assert case.expected in actual, case.case_id
    elif case.match == "prefix":
        assert matches_expected_rows(actual[:len(case.expected)], case), case.case_id
    elif case.match == "suffix":
        assert matches_expected_rows(actual[-len(case.expected):], case), case.case_id
    elif case.match == "full":
        assert matches_expected_rows(actual, case), case.case_id
    else:
        raise AssertionError(f"Unsupported raw acceptance mode: {case.match}")


@pytest.mark.usefixtures("require_raw_data", "require_curated_data")
@pytest.mark.parametrize("case", RAW_CASES, ids=[case.case_id for case in RAW_CASES])
def test_raw_rebuild_uses_explicit_reference(
    case: BiCase | SegmentCase, monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = Path(case.frequency) / "market=cn" / case.asset_class / (case.symbol + ".pkl")
    source = Path(dc.settings.DATA_DIR) / relative
    reference_path = Path(dc.CACHE_DUMP_DIR) / relative
    assert source.is_file(), f"Required raw test file is missing: {source}"
    assert reference_path.is_file(), f"Required reference test file is missing: {reference_path}"
    versions = [(p.stat().st_size, p.stat().st_mtime_ns) for p in (source, reference_path)]
    expected_raw = pickle.loads(source.read_bytes())
    accepted = dc.load_data_cache_pickle(case.symbol, case.frequency, "market=cn", case.asset_class)
    assert accepted.raw_data == expected_raw, f"{case.case_id}: raw/reference acceptance fixtures differ in version"
    # The equality above is a test-fixture prerequisite, not a production-update restriction.
    # Capture expected state BEFORE any algorithm can touch the reference objects.
    expected_bis, expected_segments = bi_rows(accepted), segment_rows(accepted)
    reference_segments = deepcopy(accepted.xian_duan_list)
    loader = Mock(wraps=dc.load_raw_data)
    bi_generator = Mock(wraps=dc.generate_bi)
    segment_generator = Mock(wraps=dc.generate_xian_duan)
    postprocessor = Mock(wraps=dc.postprocess_xian_duan)
    monkeypatch.setattr(dc, "load_raw_data", loader)
    monkeypatch.setattr(dc, "generate_bi", bi_generator)
    monkeypatch.setattr(dc, "generate_xian_duan", segment_generator)
    monkeypatch.setattr(dc, "postprocess_xian_duan", postprocessor)
    monkeypatch.setattr(dc, "load_data_cache_pickle", Mock(side_effect=AssertionError("Do not read the result cache")))
    monkeypatch.setattr(dc.settings, "ENABLE_XIANDUAN_REPAIR_LOOP", False)
    monkeypatch.setattr(dc.settings, "ENABLE_XIANDUAN_LOCAL_RESEGMENT", False)
    monkeypatch.setattr(dc.settings, "ENABLE_XIANDUAN_LEGAL_SPLIT_SEARCH", True)
    fresh = dc._DataCache(source, reference_xian_duan_list=reference_segments)
    assert fresh._raw_data is None
    fresh.ensure_loaded()
    loader.assert_called_once_with(source)
    assert bi_generator.call_count == segment_generator.call_count == postprocessor.call_count == 1
    assert fresh is not accepted and fresh.raw_data == expected_raw
    assert fresh.reference_xian_duan_list is reference_segments
    assert bi_rows(fresh) == expected_bis
    assert segment_rows(fresh) == expected_segments
    assert_acceptance(case, fresh)
    assert [(p.stat().st_size, p.stat().st_mtime_ns) for p in (source, reference_path)] == versions
