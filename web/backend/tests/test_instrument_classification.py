"""Latest classifications: instrument-scoped, current-only, atomic and timestamp-free."""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session

from CLPainter.web.backend.app.classification import (
    build_records,
    refresh_classifications,
)
from CLPainter.web.backend.app.db import base, models

NOW = datetime(2026, 11, 20, 18, tzinfo=ZoneInfo("Asia/Hong_Kong"))
DAY = "2026-11-20"
CODE = "300750.SZ"


def instrument(code="300750SZ", **kwargs):
    return models.Instrument(
        code=code,
        name=code,
        market=kwargs.pop("market", "cn"),
        asset_class=kwargs.pop("asset_class", "stock"),
        list_date=kwargs.pop("list_date", date(2018, 6, 11)),
        **kwargs,
    )


def sources():
    def frame(value):
        return pd.DataFrame({CODE: [value], "600519.SH": [value]}, index=pd.to_datetime([DAY]))

    data = {"sector": frame(801730), "industry": frame(801737), "subindustry": frame(857371)}
    data["concept_l3"] = frame([11080003, 11080003, 13011424, 18011235, 11010003, 11081407, 11100022, 11100023])
    data["industry_info"] = pd.DataFrame(
        [
            {"code": 801730, "level": 1, "name": "SW equipment", "start_date": "2014-01-01", "end_date": "2200-01-01"},
            {"code": 801737, "level": 2, "name": "SW batteries", "start_date": "2021-12-13", "end_date": "2200-01-01"},
            {"code": 857371, "level": 3, "name": "SW lithium", "start_date": "2021-12-13", "end_date": "2200-01-01"},
        ]
    ).set_index("code")
    definitions = []
    for code, name, parent in [
        (11080003, "Lithium", 11),
        (13011424, "Storage", 13),
        (18011235, "Fujian", 18),
        (11010003, "Ended", 11),
        (11081407, "Future", 11),
        (11100022, "Unpublished", 11),
        (11100023, "Exited", 11),
    ]:
        definitions.append(
            {
                "concept_code": code,
                "concept_name": name,
                "class_code": parent,
                "class_name": str(parent),
                "sub_class_code": code // 10000,
                "sub_class_name": "Group",
                "startDate": "2016-01-01",
                "endDate": "2200-01-01",
                "concept_state": 1,
                "pubDate": "2016-01-01 08:00:00",
            }
        )
    definitions[3].update(endDate="2026-11-19", concept_state=0)
    definitions[4]["startDate"] = "2026-11-21"
    definitions[5]["pubDate"] = "2026-11-21 08:00:00"
    definitions.append({**definitions[0], "sub_class_code": 1304, "sub_class_name": "Another group"})
    catalog = pd.DataFrame(definitions)
    membership = pd.DataFrame(
        [
            {
                "stock_code": stock,
                "concept_code": item["concept_code"],
                "startDate": "2018-01-01",
                "endDate": "2026-11-19" if item["concept_code"] == 11100023 else "2200-01-01",
            }
            for stock in [CODE, "600519.SH"]
            for item in definitions
        ]
    )
    return data, catalog, membership


def targets():
    row = instrument()
    row.id = 7
    return [row]


def test_builds_one_record_with_all_active_concepts_and_region_subset():
    rows = build_records(targets(), *sources(), now=NOW)
    assert len(rows) == 1
    row = rows[0]
    assert row["instrument_id"] == 7
    assert row["sw_l1_code"] == "801730" and row["sw_l3_name"] == "SW lithium"
    assert [item["code"] for item in row["concepts"]] == ["11080003", "13011424", "18011235"]
    assert len(row["concepts"][0]["paths"]) == 2
    assert [item["code"] for item in row["regions"]] == ["18011235"]
    forbidden = ("date", "time", "_at", "valid_", "pubDate")

    def check_keys(value):
        if isinstance(value, dict):
            assert not any(any(word in key for word in forbidden) for key in value)
            for child in value.values():
                check_keys(child)
        elif isinstance(value, list):
            for child in value:
                check_keys(child)

    check_keys(row)


def test_validity_is_checked_at_query_time_not_the_source_trade_date():
    data, catalog, membership = sources()
    for name in ("sector", "industry", "subindustry", "concept_l3"):
        data[name].index = pd.to_datetime(["2026-11-19"])
    catalog.loc[catalog.concept_code == 13011424, "endDate"] = "2026-11-19"
    assert "13011424" not in {
        c["code"] for c in build_records(targets(), data, catalog, membership, now=NOW)[0]["concepts"]
    }


def test_only_latest_row_is_used_and_unknown_is_not_empty():
    data, catalog, membership = sources()
    for name in ("sector", "industry", "subindustry", "concept_l3"):
        old = data[name].copy()
        old.index = pd.to_datetime(["2026-11-19"])
        data[name] = pd.concat([old, data[name]])
    data["concept_l3"].at[pd.Timestamp(DAY), CODE] = np.nan
    result = build_records(targets(), data, catalog, membership, now=NOW)[0]
    assert result["concepts"] is None and result["regions"] is None
    data["concept_l3"].at[pd.Timestamp(DAY), CODE] = []
    result = build_records(targets(), data, catalog, membership, now=NOW)[0]
    assert result["concepts"] == [] and result["regions"] == []


def test_source_dates_must_agree_instead_of_silently_using_old_values():
    data, catalog, membership = sources()
    data["concept_l3"].index = pd.to_datetime(["2026-11-19"])
    with pytest.raises(ValueError, match="date"):
        build_records(targets(), data, catalog, membership, now=NOW)


def test_missing_source_column_fails_instead_of_claiming_no_concepts():
    data, catalog, membership = sources()
    data["concept_l3"] = data["concept_l3"].drop(columns=[CODE])
    with pytest.raises(ValueError, match="300750"):
        build_records(targets(), data, catalog, membership, now=NOW)


def test_missing_metadata_fails_before_publication():
    data, catalog, membership = sources()
    catalog = catalog.loc[catalog.concept_code != 11080003]
    with pytest.raises(ValueError, match="11080003"):
        build_records(targets(), data, catalog, membership, now=NOW)


def test_expired_industry_is_not_returned_and_active_conflicts_are_rejected():
    data, catalog, membership = sources()
    data["industry_info"].loc[801730, "end_date"] = "2026-11-19"
    row = build_records(targets(), data, catalog, membership, now=NOW)[0]
    assert row["sw_l1_code"] is None and row["sw_l1_name"] is None
    data["industry_info"].loc[801730, "end_date"] = "2200-01-01"
    duplicate = data["industry_info"].loc[[801730]].copy()
    duplicate["name"] = "Conflicting name"
    data["industry_info"] = pd.concat([data["industry_info"], duplicate])
    with pytest.raises(ValueError, match="801730"):
        build_records(targets(), data, catalog, membership, now=NOW)


def test_inclusive_concept_interval_boundaries_are_kept():
    data, catalog, membership = sources()
    catalog.loc[catalog.concept_code == 13011424, ["startDate", "endDate"]] = DAY
    membership.loc[membership.concept_code == 13011424, ["startDate", "endDate"]] = DAY
    assert "13011424" in {
        c["code"] for c in build_records(targets(), data, catalog, membership, now=NOW)[0]["concepts"]
    }


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'classification.db'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    base.Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                instrument(),
                instrument("600519SH"),
                instrument("000300SH", asset_class="index"),
                instrument("510300SH", asset_class="fund"),
                instrument("AAPL", market="us"),
                instrument("000002SZ", delist_date=date(2026, 11, 19)),
                instrument("000003SZ", list_date=date(2026, 11, 21)),
            ]
        )
        session.commit()
    yield engine
    engine.dispose()


def refresh(engine, data=None, catalog=None, membership=None, **kwargs):
    defaults = sources()
    data = defaults[0] if data is None else data
    catalog = defaults[1] if catalog is None else catalog
    membership = defaults[2] if membership is None else membership
    return refresh_classifications(
        engine,
        fetcher=lambda *a, **kw: data,
        catalog_loader=lambda **kw: catalog,
        membership_loader=lambda **kw: membership,
        now=NOW,
        **kwargs,
    )


def test_only_instrument_stocks_are_persisted_and_reruns_replace_lists(database):
    result = refresh(database)
    assert result["saved"] == 2
    with Session(database) as session:
        rows = session.scalars(select(models.InstrumentClassification)).all()
        assert len(rows) == 2
        ids = {row.instrument_id for row in rows}
        assert ids == {1, 2}
    data, catalog, membership = sources()
    catalog.loc[catalog.concept_code == 11080003, "endDate"] = "2026-11-19"
    refresh(database, data, catalog, membership)
    with Session(database) as session:
        rows = session.scalars(select(models.InstrumentClassification)).all()
        assert len(rows) == 2
        assert all("11080003" not in {c["code"] for c in row.concepts} for row in rows)


def test_source_exception_does_not_destroy_previous_result(database):
    refresh(database)

    def fail(**kwargs):
        raise RuntimeError("source unavailable")

    with pytest.raises(RuntimeError, match="source unavailable"):
        refresh_classifications(
            database,
            fetcher=lambda *a, **kw: sources()[0],
            catalog_loader=fail,
            membership_loader=lambda **kw: sources()[2],
            now=NOW,
        )
    with Session(database) as session:
        assert len(session.scalars(select(models.InstrumentClassification)).all()) == 2


def test_unknown_instrument_never_gets_inserted_from_source(database):
    data, catalog, membership = sources()
    for name in ("sector", "industry", "subindustry", "concept_l3"):
        data[name]["000001.SZ"] = data[name][CODE]
    membership = pd.concat([membership, membership.assign(stock_code="000001.SZ")])
    refresh(database, data, catalog, membership)
    with Session(database) as session:
        assert {row.instrument_id for row in session.scalars(select(models.InstrumentClassification))} == {1, 2}


def test_dry_run_has_no_database_writes(database):
    assert refresh(database, dry_run=True)["saved"] == 0
    with Session(database) as session:
        assert session.scalars(select(models.InstrumentClassification)).all() == []


def test_universe_changes_during_collection_abort_publication(database):
    data, catalog, membership = sources()

    def changing_fetcher(*args, **kwargs):
        with Session(database) as session:
            session.add(instrument("000004SZ"))
            session.commit()
        return data

    with pytest.raises(ValueError, match="instrument"):
        refresh_classifications(
            database,
            fetcher=changing_fetcher,
            catalog_loader=lambda **kw: catalog,
            membership_loader=lambda **kw: membership,
            now=NOW,
        )
    with Session(database) as session:
        assert session.scalars(select(models.InstrumentClassification)).all() == []


def test_foreign_key_cascade_and_no_timestamp_columns(database):
    refresh(database)
    with Session(database) as session:
        session.delete(session.get(models.Instrument, 1))
        session.commit()
        assert session.get(models.InstrumentClassification, 1) is None
    columns = {c["name"] for c in inspect(database).get_columns("instrument_classification")}
    assert columns == {
        "instrument_id",
        "sw_l1_code",
        "sw_l1_name",
        "sw_l2_code",
        "sw_l2_name",
        "sw_l3_code",
        "sw_l3_name",
        "concepts",
        "regions",
    }


def test_migration_is_reversible_without_changing_existing_tables(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    monkeypatch.setattr(base, "engine", engine)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "f7d3b0a5c9e2")
    command.upgrade(config, "head")
    assert "instrument_classification" in inspect(engine).get_table_names()
    assert len(inspect(engine).get_columns("instrument_classification")) == 9
    command.downgrade(config, "f7d3b0a5c9e2")
    assert "instrument_classification" not in inspect(engine).get_table_names()
    assert "stock_screener_run" in inspect(engine).get_table_names()
    engine.dispose()


def test_state_zero_is_excluded_even_if_end_date_is_open():
    data, catalog, membership = sources()
    catalog.loc[catalog.concept_code == 13011424, "concept_state"] = 0
    assert "13011424" not in {
        c["code"] for c in build_records(targets(), data, catalog, membership, now=NOW)[0]["concepts"]
    }


def test_empty_catalog_or_malformed_dates_are_not_treated_as_no_concepts():
    data, catalog, membership = sources()
    with pytest.raises(ValueError, match="Empty"):
        build_records(targets(), data, catalog.iloc[:0], membership, now=NOW)
    catalog.loc[catalog.concept_code == 13011424, "endDate"] = "not-a-date"
    with pytest.raises(ValueError):
        build_records(targets(), data, catalog, membership, now=NOW)


def test_non_stock_and_retired_instrument_results_are_removed(database):
    refresh(database)
    with Session(database) as session:
        session.get(models.Instrument, 1).delist_date = date(2026, 11, 20)
        session.commit()
    refresh(database)
    with Session(database) as session:
        assert {row.instrument_id for row in session.scalars(select(models.InstrumentClassification))} == {2}


def test_empty_instrument_universe_does_not_query_any_source(database):
    with Session(database) as session:
        for row in session.scalars(select(models.Instrument)):
            row.asset_class = "index"
        session.commit()

    def forbidden(*args, **kwargs):
        pytest.fail("No sources should be queried for an empty stock universe")

    report = refresh_classifications(
        database,
        fetcher=forbidden,
        catalog_loader=forbidden,
        membership_loader=forbidden,
        now=NOW,
    )
    assert report["instruments"] == report["saved"] == 0


def test_same_concept_code_keeps_path_names_and_uses_latest_published_display_name():
    data, catalog, membership = sources()
    index = catalog.index[-1]
    catalog.loc[index, "concept_name"] = "Lithium concept"
    catalog.loc[index, "pubDate"] = "2021-10-22 20:21:04"
    row = build_records(targets(), data, catalog, membership, now=NOW)[0]
    concept = next(item for item in row["concepts"] if item["code"] == "11080003")
    assert concept["name"] == "Lithium concept"
    assert {path["concept_name"] for path in concept["paths"]} == {"Lithium", "Lithium concept"}


def test_missing_industry_name_does_not_become_the_literal_none():
    data, catalog, membership = sources()
    data["industry_info"].loc[801730, "name"] = None
    with pytest.raises(ValueError, match="801730"):
        build_records(targets(), data, catalog, membership, now=NOW)


def test_cli_lock_serializes_collection_and_does_not_store_time(tmp_path):
    import runpy

    script = Path(__file__).resolve().parents[1] / "scripts/data_ingestion/update_instrument_classification.py"
    entry = runpy.run_path(str(script))
    with (
        entry["collection_lock"](tmp_path / "instrument.db"),
        pytest.raises(BlockingIOError),
        entry["collection_lock"](tmp_path / "instrument.db"),
    ):
        pytest.fail("Concurrent collection must not start")
    with entry["collection_lock"](tmp_path / "instrument.db"):
        pass
    assert (tmp_path / "instrument.db.classification.lock").read_bytes() == b""


def test_cli_sanitizes_arbitrary_external_failures(tmp_path, monkeypatch, capsys):
    import runpy

    from CLPainter.web.backend.app import classification

    script = Path(__file__).resolve().parents[1] / "scripts/data_ingestion/update_instrument_classification.py"
    entry = runpy.run_path(str(script))

    class UnexpectedServiceError(Exception):
        pass

    def fail(*args, **kwargs):
        raise UnexpectedServiceError("password=should-never-be-printed")

    monkeypatch.setattr(classification, "refresh_classifications", fail)
    monkeypatch.setattr("sys.argv", [str(script), "--dry-run"])
    assert entry["main"]() == 1
    stderr = capsys.readouterr().err
    assert "UnexpectedServiceError" in stderr and "should-never-be-printed" not in stderr


def test_missing_migration_fails_before_any_source_queries(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'not-migrated.db'}")

    def forbidden(*args, **kwargs):
        pytest.fail("Migrate before querying sources")

    with pytest.raises(ValueError, match="alembic"):
        refresh_classifications(
            engine, fetcher=forbidden, catalog_loader=forbidden, membership_loader=forbidden, now=NOW
        )
    engine.dispose()


def test_missing_publication_time_does_not_overflow_timezone_bounds():
    data, catalog, membership = sources()
    catalog.loc[catalog.concept_code == 11080003, "pubDate"] = None
    row = build_records(targets(), data, catalog, membership, now=NOW)[0]
    assert next(c for c in row["concepts"] if c["code"] == "11080003")["name"] == "Lithium"
