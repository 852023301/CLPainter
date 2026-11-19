"""Synthetic producer tests for historical Tushare data; no real requests or data writes."""

from datetime import date
from pathlib import Path
import pickle
import sys
from unittest.mock import Mock

import pandas as pd
import pytest

from CLPainter.web.backend.scripts.data_ingestion import data_from_tushare_old as history


@pytest.fixture(autouse=True)
def forbid_real_requests(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("Historical quality tests must not send real network requests")

    monkeypatch.setattr(history.requests.sessions.Session, "request", unexpected_request)


def frame(**values) -> pd.DataFrame:
    row = dict(ts_code="000001.SZ", trade_date="20081230", open=1.1, close=1.2, low=1.0, high=1.3, volume=10.0)
    row.update(values)
    return pd.DataFrame([row])


def no_prices() -> pd.DataFrame:
    return frame(open=float("nan"), close=float("nan"), low=float("nan"), high=float("nan"))


def unsafe_history() -> pd.DataFrame:
    return pd.concat([
        frame(trade_date="20081229", open=1.9, close=2.0, low=1.8, high=2.1),
        frame(close=float("nan"), low=1.0, high=1.5),
    ], ignore_index=True)


def existing_file(directory: Path, code: str = "000001.SZ") -> tuple[Path, bytes]:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (code.replace(".", "") + ".pkl")
    contents = pickle.dumps([["2008-12-29", 1.0, 1.1, 0.9, 1.2, 8.0]])
    path.write_bytes(contents)
    return path, contents


@pytest.mark.parametrize("missing", [0, "0", None, float("nan"), float("inf"), -float("inf")])
def test_missing_open_high_low_use_current_close(missing):
    data = frame(open=missing, low=missing, high=missing)
    before = data.copy(deep=True)
    assert history._convert_history_to_pv_list(data) == [["2008-12-30", 1.2, 1.2, 1.2, 1.2, 10.0]]
    pd.testing.assert_frame_equal(data, before)


def test_zero_bounds_do_not_reject_a_safe_previous_close_fill():
    data = pd.concat([
        frame(trade_date="20081229"),
        frame(close=float("nan"), open=0, high=0, low=0),
    ], ignore_index=True)
    result = history._convert_history_to_pv_list(data)
    assert result is not None
    assert result[1] == ["2008-12-30", 1.2, 1.2, 1.2, 1.2, 10.0]


def test_real_bounds_still_reject_an_unsafe_previous_close_fill():
    assert history._convert_history_to_pv_list(unsafe_history()) is None


def test_zero_close_and_volume_keep_the_existing_policy():
    assert history._convert_history_to_pv_list(frame(close=0, volume=0)) == [
        ["2008-12-30", 1.1, 0.0, 1.0, 1.3, 0.0],
    ]


@pytest.mark.parametrize("empty_kind", ["empty_response", "no_valid_prices"])
@pytest.mark.parametrize("has_previous", [False, True])
def test_empty_conversion_does_not_create_or_replace_a_file(tmp_path, empty_kind, has_previous):
    directory = tmp_path / "history"
    path = directory / "000001SZ.pkl"
    if has_previous:
        path, before = existing_file(directory)
    data = frame().iloc[:0] if empty_kind == "empty_response" else no_prices()
    assert history._save_history(directory, "000001.SZ", data) is None
    if has_previous:
        assert path.read_bytes() == before
    else:
        assert not path.exists()
    assert not path.with_suffix(".pkl.tmp").exists()


@pytest.mark.parametrize("has_previous", [False, True])
def test_unsafe_conversion_preserves_previous_file(tmp_path, has_previous):
    directory = tmp_path / "history"
    path = directory / "000001SZ.pkl"
    if has_previous:
        path, before = existing_file(directory)
    with pytest.raises(ValueError, match="000001.SZ"):
        history._save_history(directory, "000001.SZ", unsafe_history())
    if has_previous:
        assert path.read_bytes() == before
    else:
        assert not path.exists()
    assert not path.with_suffix(".pkl.tmp").exists()


@pytest.mark.parametrize("has_previous", [False, True])
def test_valid_history_is_written_and_can_replace_an_old_file(tmp_path, has_previous):
    if has_previous:
        existing_file(tmp_path)
    path = history._save_history(tmp_path, "000001.SZ", frame(open=0, low=0, high=0))
    assert path == tmp_path / "000001SZ.pkl"
    with path.open("rb") as file:
        assert pickle.load(file) == [["2008-12-30", 1.2, 1.2, 1.2, 1.2, 10.0]]
    assert not path.with_suffix(".pkl.tmp").exists()


def test_write_failure_does_not_replace_the_old_file(tmp_path, monkeypatch):
    path, before = existing_file(tmp_path)
    monkeypatch.setattr(history.pickle, "dump", Mock(side_effect=OSError("synthetic write failure")))
    with pytest.raises(OSError, match="synthetic write failure"):
        history._save_history(tmp_path, "000001.SZ", frame())
    assert path.read_bytes() == before


def histories(tmp_path, monkeypatch, *, overwrite=False, list_date="20000101"):
    data = frame()
    fetch = Mock(return_value=data)
    monkeypatch.setattr(history, "fetch_history_for_security", fetch)
    securities = pd.DataFrame([{"ts_code": "000001.SZ", "list_date": list_date}])
    result = list(history._iter_history_for_list(
        object(), securities, "stock", None, date(2008, 12, 31), 0,
        history_dir=tmp_path, overwrite=overwrite,
    ))
    return result, fetch, data


@pytest.mark.parametrize("contents", [b"", pickle.dumps([]), pickle.dumps({}), b"not-a-pickle"])
def test_empty_or_corrupt_pickle_is_not_considered_completed(tmp_path, monkeypatch, contents):
    path = tmp_path / "000001SZ.pkl"
    path.write_bytes(contents)
    result, fetch, data = histories(tmp_path, monkeypatch)
    fetch.assert_called_once()
    assert result[0][0] == "000001.SZ" and result[0][1] is data
    assert path.read_bytes() == contents  # Classification alone must not delete or overwrite files.


def test_completed_nonempty_history_is_skipped_without_fetching(tmp_path, monkeypatch):
    path, before = existing_file(tmp_path)
    result, fetch, _ = histories(tmp_path, monkeypatch)
    assert result == [("000001.SZ", None)]
    fetch.assert_not_called()
    assert path.read_bytes() == before


def test_overwrite_explicitly_fetches_even_when_old_history_is_valid(tmp_path, monkeypatch):
    existing_file(tmp_path)
    result, fetch, data = histories(tmp_path, monkeypatch, overwrite=True)
    fetch.assert_called_once()
    assert result[0][1] is data


def test_read_permission_error_is_not_reclassified_as_empty_history(tmp_path, monkeypatch):
    path, _ = existing_file(tmp_path)
    original_open = Path.open

    def fail_for_history(self, *args, **kwargs):
        if self == path:
            raise PermissionError("synthetic permission failure")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_for_history)
    with pytest.raises(PermissionError, match="synthetic permission failure"):
        histories(tmp_path, monkeypatch)


def test_placeholder_listing_date_policy_is_unchanged(tmp_path, monkeypatch):
    _, fetch, _ = histories(tmp_path, monkeypatch, list_date="18000101")
    fetch.assert_called_once()
    assert fetch.call_args.args[3] is None


def test_listed_after_history_cutoff_still_does_not_fetch(tmp_path, monkeypatch):
    result, fetch, _ = histories(tmp_path, monkeypatch, list_date="20090101")
    fetch.assert_not_called()
    assert result[0][1].empty


def test_main_counts_converted_empty_history_as_empty_not_saved(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["historical-data"])
    monkeypatch.setattr(history, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(history.ts, "pro_api", lambda token: object())
    monkeypatch.setattr(history, "_load_cached_lists", lambda: {
        category: pd.DataFrame(columns=["ts_code"]) for category in history.CATEGORIES
    })
    samples = [
        ("000001.SZ", None),
        ("000002.SZ", unsafe_history()),
        ("000003.SZ", frame().iloc[:0]),
        ("000004.SZ", no_prices()),
        ("000005.SZ", frame()),
    ]

    def fake_histories(pro_api, securities, category, *args, **kwargs):
        return iter(samples if category == "stock" else ())

    monkeypatch.setattr(history, "_iter_history_for_list", fake_histories)
    history.main()
    output = capsys.readouterr().out
    assert "stock: 已保存 1，无数据 2，续跑跳过 1，缺失跳过 1" in output
    directory = history._get_history_dir(tmp_path, "stock")
    assert sorted(path.name for path in directory.glob("*.pkl")) == ["000005SZ.pkl"]
