"""Metadata/date/cleanup boundaries using temporary databases and fake sources."""

import importlib
import json
import runpy
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from CLPainter.web.backend.app.db.base import Base
from CLPainter.web.backend.app.db.models import Instrument
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def metadata_env(tmp_path, monkeypatch):
    root = tmp_path / "data_set_dev"
    root.mkdir()
    config = SimpleNamespace(
        APP_ENV="test",
        DATA_DIR=str(root / "pv_data"),
        OLD_DATA_DIR=str(root / "old_pv_data"),
        CACHE_DUMP_DIR=str(root / "dump/curated"),
        DB_PATH=str(root / "instrument.db"),
    )
    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for code in ["S0", "S1", "S2", "S3", "S4", "STALE"]:
            session.add(
                Instrument(
                    code=code,
                    name=code,
                    display_name=code,
                    market="cn",
                    asset_class="stock",
                    list_date=date(2020, 1, 1),
                )
            )
        session.add(
            Instrument(
                code="F0", name="F0", display_name="F0", market="cn", asset_class="fund", list_date=date(2020, 1, 1)
            )
        )
        session.add(
            Instrument(
                code="I0", name="I0", display_name="I0", market="cn", asset_class="index", list_date=date(2020, 1, 1)
            )
        )
        session.commit()
    module = importlib.import_module("CLPainter.web.backend.scripts.data_ingestion.meta_info")
    monkeypatch.setattr(module, "engine", engine)
    monkeypatch.setattr(module, "settings", config, raising=False)
    monkeypatch.setattr(module, "resolve_processing_date", lambda *args, **kwargs: date(2026, 11, 20), raising=False)
    yield module, config, engine, root
    engine.dispose()


def records(config, day=None):
    codes = {"stock": ["S0", "S1", "S2", "S3", "S4"], "fund": ["F0"], "index": ["I0"]}[config["asset_class"]]
    return [
        Instrument(
            code=code,
            name="current",
            display_name="current",
            market="cn",
            asset_class=config["asset_class"],
            price_precision=config["precision"],
            list_date=date(2020, 1, 1),
        )
        for code in codes
    ]


def test_metadata_is_validated_as_a_whole_before_sync_and_report(metadata_env, monkeypatch):
    module, _config, engine, root = metadata_env

    def query(config, as_of=None):
        assert as_of == date(2026, 11, 20)
        with Session(engine) as session:
            assert session.scalar(select(Instrument).where(Instrument.code == "STALE")) is not None
        return records(config, as_of)

    monkeypatch.setattr(module, "query_active_info", query)
    report = root / "reports/meta.json"
    assert module.main(["--as-of", "2026-11-20", "--report", str(report)]) in (None, 0)
    payload = json.loads(report.read_text())
    assert payload["complete"] and payload["as_of"] == "2026-11-20"
    with Session(engine) as session:
        assert session.scalar(select(Instrument).where(Instrument.code == "STALE")) is None
    assert {item["asset_class"] for item in payload["scopes"]} == {"stock", "fund", "index"}


@pytest.mark.parametrize("failure", ["empty_fund", "duplicate", "drop", "upstream_error"])
def test_bad_upstream_never_deletes_metadata_or_publishes_a_receipt(metadata_env, monkeypatch, failure):
    module, _config, engine, root = metadata_env

    def query(config, as_of=None):
        output = records(config, as_of)
        if failure == "empty_fund" and config["asset_class"] == "fund":
            return []
        if failure == "duplicate" and config["asset_class"] == "stock":
            return output + [output[0]]
        if failure == "drop" and config["asset_class"] == "stock":
            return output[:1]
        if failure == "upstream_error" and config["asset_class"] == "fund":
            raise ConnectionError("upstream unavailable")
        return output

    monkeypatch.setattr(module, "query_active_info", query)
    report = root / "reports/meta.json"
    with pytest.raises((ValueError, ConnectionError)):
        module.main(["--as-of", "2026-11-20", "--report", str(report)])
    with Session(engine) as session:
        assert session.scalar(select(Instrument).where(Instrument.code == "STALE")) is not None
        assert len(session.scalars(select(Instrument)).all()) == 8
    assert not report.exists()


def test_query_uses_processing_date_instead_of_machine_date(monkeypatch):
    module = importlib.import_module("CLPainter.web.backend.scripts.data_ingestion.meta_info")
    queries = []

    class Database:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def query_pandas(self, sql):
            queries.append(sql)
            return pd.DataFrame(
                [["S0.SZ", "S0", "S0", date(2020, 1, 1)]],
                columns=["source_code", "source_name", "source_display_name", "start_date"],
            )

    monkeypatch.setattr(module, "MysqlConnection", Database)
    module.query_active_info(module.ASSET_CLASS_CONFIG["stock"], date(2026, 11, 20))
    assert "start_date <= '2026-11-20'" in queries[0] and "end_date > '2026-11-20'" in queries[0]


def test_ingestion_filters_list_dates_by_processing_day(metadata_env, monkeypatch):
    _, _config, engine, _root = metadata_env
    module = runpy.run_path(str(BACKEND / "scripts/data_ingestion/data_from_tdata_1day.py"))
    namespace = module["load_instrument_info"].__globals__
    monkeypatch.setitem(namespace, "engine", engine)
    with Session(engine) as session:
        session.add(
            Instrument(code="FUTURE", name="future", market="cn", asset_class="stock", list_date=date(2026, 11, 21))
        )
        session.commit()
    output = module["load_instrument_info"]("stock", date(2026, 11, 20))
    assert "FUTURE" not in output and "S0" in output


def test_distributed_stale_cleanup_has_been_removed():
    for name in [
        "data_ingestion/data_from_tdata_1day.py",
        "aggregation/from_1day_to_1week.py",
        "aggregation/from_1day_to_1month.py",
        "aggregation/from_1day_to_1quarter.py",
        "aggregation/from_1day_to_1year.py",
    ]:
        text = (BACKEND / "scripts" / name).read_text(encoding="utf-8")
        assert "clean_stale_files(" not in text, name


def test_pipeline_receipt_date_is_used_as_the_fetch_end_date(metadata_env, monkeypatch):
    from CLPainter.web.backend.app.data_lifecycle import write_metadata_report

    _, config, engine, root = metadata_env
    report = root / "reports/meta.json"
    write_metadata_report(
        report, config, engine, date(2026, 11, 20), [("cn", "stock"), ("cn", "fund"), ("cn", "index")]
    )
    path = BACKEND / "scripts/data_ingestion/data_from_tdata_1day.py"
    module = runpy.run_path(str(path))
    namespace = module["load_instrument_info"].__globals__
    monkeypatch.setenv("CLPAINTER_METADATA_REPORT", str(report))
    monkeypatch.setitem(namespace, "settings", config)
    monkeypatch.setitem(namespace, "engine", engine)
    ends = []
    selected_dates = []

    def fetch(fields, start_date=None, end_date=None):
        ends.append(end_date)
        symbol = "F0" if fields[0].startswith("etf_") else "S0"
        return {
            field: pd.DataFrame([[1.0]], index=pd.DatetimeIndex(["2026-11-20"]), columns=[symbol]) for field in fields
        }

    def info(asset, as_of=None):
        selected_dates.append(as_of)
        code = "F0" if asset == "fund" else "S0"
        return {code: {"list_date": "2020-01-01", "price_precision": 2}}

    monkeypatch.setitem(namespace, "fetch_data", fetch)
    monkeypatch.setitem(namespace, "load_instrument_info", info)
    monkeypatch.setitem(namespace, "change_data_type_and_save", lambda *args, **kwargs: set())
    monkeypatch.setitem(
        namespace,
        "query_index_data",
        lambda *args: {"I0": pd.DataFrame([[1] * 5], index=pd.DatetimeIndex(["2026-11-20"]), columns=module["FIELDS"])},
    )
    module["main"]()
    assert ends == ["2026-11-20", "2026-11-20"]
    assert selected_dates == [date(2026, 11, 20)] * 3


def test_empty_index_conversion_preserves_last_good_source(tmp_path, monkeypatch):
    module = runpy.run_path(str(BACKEND / "scripts/data_ingestion/data_from_tdata_1day.py"))
    namespace = module["write_index_data"].__globals__
    path = tmp_path / "TESTSH.pkl"
    path.write_bytes(b"last-good-source")
    monkeypatch.setitem(namespace, "fill_missing_pv_rows", lambda *args: [])
    monkeypatch.setitem(namespace, "load_old_pv_list", lambda *args: [])
    frame = pd.DataFrame([[1, 1, 1, 1, 1]], index=pd.DatetimeIndex(["2026-11-20"]), columns=module["FIELDS"])
    with pytest.raises(ValueError):
        module["write_index_data"]("TEST.SH", frame, "2026-11-20", tmp_path)
    assert path.read_bytes() == b"last-good-source"
