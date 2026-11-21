"""No real data access: verify the successful full-batch archive boundary."""

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/state/update_cl_state.py"


@pytest.mark.parametrize(
    "case,expected,archived",
    [
        ("success", 0, True),
        ("orphan_cache", 0, True),
        ("worker_failure", 1, False),
        ("skipped", 1, False),
        ("missing", 1, False),
        ("archive_failure", 1, True),
        ("intraday_source", 1, False),
        ("missing_context", 1, False),
    ],
)
def test_archive_only_after_complete_successful_state_update(tmp_path, monkeypatch, case, expected, archived):
    module = runpy.run_path(str(SCRIPT))
    namespace = module["main"].__globals__
    monkeypatch.setenv("CLPAINTER_PIPELINE_STARTED_AT", "2026-11-20T10:00:00+00:00")
    if case == "intraday_source":
        monkeypatch.setenv("CLPAINTER_PIPELINE_STARTED_AT", "2026-11-20T06:00:00+00:00")
    if case == "missing_context":
        monkeypatch.delenv("CLPAINTER_PIPELINE_STARTED_AT", raising=False)
    options = SimpleNamespace(
        dump_dir=tmp_path, frequency=None, market=None, asset_class=None, symbol=None, archive_screener=True
    )
    monkeypatch.setitem(namespace, "parse_args", lambda: options)
    paths = [tmp_path / "freq=1day/market=cn/asset_class=stock/AAA.pkl"]
    if case == "orphan_cache":
        paths.append(tmp_path / "freq=1day/market=cn/asset_class=stock/OLD.pkl")
    monkeypatch.setitem(namespace, "collect_cache_files", lambda root: paths)
    monkeypatch.setitem(namespace, "load_instrument_identities", lambda: {("cn", "stock", "AAA")})
    record = {"code": "AAA", "market": "cn", "frequency": "1day", "data_trade_date": "2026-11-20"}

    class Future:
        def result(self):
            if case == "worker_failure":
                raise ValueError("synthetic failure")
            return None if case == "skipped" else record

    class Pool:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def submit(self, *args):
            return Future()

    monkeypatch.setitem(namespace, "ProcessPoolExecutor", Pool)
    monkeypatch.setitem(namespace, "as_completed", lambda futures: list(futures))
    monkeypatch.setitem(namespace, "persist_snapshots", lambda records: 1 if case == "missing" else 0)
    calls = []

    def archive(engine, records):
        calls.append(records)
        return {"failed": 1 if case == "archive_failure" else 0, "saved": 0}

    monkeypatch.setitem(namespace, "archive_due_presets", archive)
    assert module["main"]() == expected
    assert bool(calls) is archived
    if calls:
        assert calls == [[record]]


def test_partial_updates_cannot_request_automatic_archiving(monkeypatch):
    module = runpy.run_path(str(SCRIPT))
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--archive-screener", "--frequency", "freq=1day"])
    with pytest.raises(SystemExit) as error:
        module["parse_args"]()
    assert error.value.code == 2


def test_worker_adds_real_source_date_without_changing_the_calculation(tmp_path, monkeypatch):
    module = runpy.run_path(str(SCRIPT))
    namespace = module["state_worker"].__globals__
    cache = SimpleNamespace(_bi_zhongshu_raw_list=[], _raw_data=[["2026-11-20", 1, 1, 1, 1, 1]])
    monkeypatch.setitem(namespace, "load_data_cache_pickle", lambda *args: cache)
    monkeypatch.setitem(namespace, "build_snapshot_record", lambda *args, **kwargs: {"code": "AAA"})
    result = module["state_worker"](tmp_path / "freq=1day/market=cn/asset_class=stock/AAA.pkl", tmp_path)
    assert result == {"code": "AAA", "data_trade_date": "2026-11-20"}


def test_orphan_filter_uses_complete_identity_and_never_deletes_files(tmp_path, caplog):
    module = runpy.run_path(str(SCRIPT))
    names = [
        "freq=1day/market=cn/asset_class=stock/AAA.pkl",
        "freq=1week/market=us/asset_class=stock/AAA.pkl",
        "freq=1month/market=cn/asset_class=fund/BBB.pkl",
        "freq=1day/market=cn/asset_class=fund/AAA.pkl",
        "freq=1year/market=cn/asset_class=stock/OLD.pkl",
    ]
    paths = [tmp_path / name for name in names]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"These files must not be loaded or deleted")
    versions = [(path.stat().st_size, path.stat().st_mtime_ns) for path in paths]
    identities = {("cn", "stock", "AAA"), ("us", "stock", "AAA"), ("cn", "fund", "BBB")}
    selected = module["filter_registered_caches"](paths, identities)
    assert selected == paths[:3]
    assert all(path.exists() for path in paths)
    assert versions == [(path.stat().st_size, path.stat().st_mtime_ns) for path in paths]
    assert "未登记" in caplog.text and "OLD.pkl" in caplog.text


def test_instrument_identity_lookup_is_read_only_and_does_not_create_databases(tmp_path, monkeypatch):
    import sqlite3

    module = runpy.run_path(str(SCRIPT))
    namespace = module["load_instrument_identities"].__globals__
    database = tmp_path / "metadata.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE instrument (market TEXT, asset_class TEXT, code TEXT)")
        connection.executemany(
            "INSERT INTO instrument VALUES (?, ?, ?)", [("cn", "stock", "AAA"), ("cn", "fund", "AAA")]
        )
    before = database.read_bytes()
    monkeypatch.setattr(namespace["settings"], "DB_PATH", str(database))
    assert module["load_instrument_identities"]() == {("cn", "stock", "AAA"), ("cn", "fund", "AAA")}
    assert database.read_bytes() == before
    missing = tmp_path / "not-created.db"
    monkeypatch.setattr(namespace["settings"], "DB_PATH", str(missing))
    with pytest.raises(sqlite3.OperationalError):
        module["load_instrument_identities"]()
    assert not missing.exists()
