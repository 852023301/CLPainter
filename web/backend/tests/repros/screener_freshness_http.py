"""Selection-state versions: real HTTP and isolated SQLite read snapshots."""
import importlib
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import Session

from CLPainter.web.backend.app.db import base, models

ROOT = "/api/v1/test_api/stock_screener"
STAMP = datetime(2026, 11, 22, 1, 0, 0)
FIELDS = (
    "relative_pivot_position", "relative_previous_pivot_position", "last_structure_right_type",
    "second_point_type", "third_point_type", "quasi_third_point_type", "second_third_combined_type",
)


@pytest.fixture
def freshness_api(tmp_path, monkeypatch):
    from CLPainter.web.backend.app._config import logging_config
    monkeypatch.setattr(logging_config, "setup_logger", lambda: None)
    routes = importlib.import_module("CLPainter.web.backend.app.api.api_v1.endpoints.test_api")
    database = tmp_path / "freshness.db"
    engine = create_engine(f"sqlite:///{database}", connect_args={"check_same_thread": False})
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.commit()
    base.Base.metadata.create_all(engine)
    with Session(engine) as session:
        for code, state in (("AAA", 0), ("BBB", 1)):
            item = models.Instrument(code=code, name=code, display_name=code, market="cn", asset_class="stock")
            session.add(item)
            session.flush()
            session.add(models.ClStateSnapshot(
                instrument_id=item.id, frequency="1day", scope="bi", calculated_at=STAMP,
                **{name: state for name in FIELDS},
            ))
        session.commit()
    monkeypatch.setattr(routes, "engine", engine)
    monkeypatch.setattr(routes, "logger", Mock())
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/test_api")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, engine, database, routes, app
    engine.dispose()


def version(client):
    response = client.get(ROOT + "/version")
    assert response.status_code == 200, response.text
    assert response.headers.get("cache-control") == "no-store"
    value = response.json()["data_version"]
    assert isinstance(value, str) and value
    return value


def query(client):
    response = client.post(ROOT + "/query", json={"frequency": "1day", "second_point_type": 0})
    assert response.status_code == 200, response.text
    return response


def test_versions_match_query_options_and_multiple_clients(freshness_api):
    client, _engine, _database, _routes, app = freshness_api
    expected = version(client)
    options = client.get(ROOT + "/options")
    result = query(client)
    assert options.json()["data_version"] == result.json()["data_version"] == expected
    assert options.headers.get("cache-control") == result.headers.get("cache-control") == "no-store"
    assert datetime.fromisoformat(result.json()["queried_at"]).tzinfo is not None
    with TestClient(app) as other:
        assert version(other) == expected
    assert [item["code"] for item in result.json()["results"]] == ["AAA"]


@pytest.mark.parametrize("field", FIELDS)
def test_each_filter_state_changes_version_without_time_or_count_change(freshness_api, field):
    client, engine, _database, _routes, _app = freshness_api
    old = version(client)
    with Session(engine) as session:
        count = session.scalar(select(func.count()).select_from(models.ClStateSnapshot))
        session.execute(update(models.ClStateSnapshot).where(models.ClStateSnapshot.instrument_id == 1).values(**{field: 2}))
        session.commit()
        assert session.scalar(select(func.count()).select_from(models.ClStateSnapshot)) == count
        assert session.scalar(select(models.ClStateSnapshot.calculated_at).limit(1)) == STAMP
    assert version(client) != old


def test_equal_counts_and_timestamps_cannot_hide_membership_swap(freshness_api):
    client, engine, _database, _routes, _app = freshness_api
    old = version(client)
    with Session(engine) as session:
        session.execute(update(models.ClStateSnapshot).where(models.ClStateSnapshot.instrument_id == 1).values(second_point_type=1))
        session.execute(update(models.ClStateSnapshot).where(models.ClStateSnapshot.instrument_id == 2).values(second_point_type=0))
        session.commit()
    assert version(client) != old
    assert [item["code"] for item in query(client).json()["results"]] == ["BBB"]


@pytest.mark.parametrize("field,value", [("code", "RENAMED"), ("display_name", "New display"), ("market", "us"), ("asset_class", "fund")])
def test_result_identity_and_display_metadata_affect_version(freshness_api, field, value):
    client, engine, _database, _routes, _app = freshness_api
    old = version(client)
    with Session(engine) as session:
        session.execute(update(models.Instrument).where(models.Instrument.id == 1).values(**{field: value}))
        session.commit()
    assert version(client) != old


def test_recalculation_timestamp_changes_version(freshness_api):
    client, engine, _database, _routes, _app = freshness_api
    old = version(client)
    with Session(engine) as session:
        session.execute(update(models.ClStateSnapshot).values(calculated_at=STAMP + timedelta(seconds=1)))
        session.commit()
    assert version(client) != old


def test_watchlist_and_preset_writes_do_not_expire_selection_results(freshness_api):
    client, engine, _database, _routes, _app = freshness_api
    old = version(client)
    with Session(engine) as session:
        session.add(models.WatchlistBoard(name="Unrelated board"))
        session.add(models.StockScreenerPreset(name="Unrelated preset", filters={}))
        session.commit()
    assert version(client) == old


def test_empty_state_has_a_valid_stable_version(freshness_api):
    client, engine, _database, _routes, _app = freshness_api
    with Session(engine) as session:
        session.query(models.ClStateSnapshot).delete()
        session.commit()
    first = version(client)
    result = query(client).json()
    assert result["count"] == 0 and result["results"] == []
    assert result["data_version"] == first == version(client)


def test_query_results_and_version_share_one_sqlite_snapshot(freshness_api):
    client, engine, database, _routes, _app = freshness_api
    old = version(client)
    written = []

    def writer(_connection, _cursor, statement, _parameters, _context, _many):
        if written or "ORDER BY instrument.code" not in statement or "json_group_array" in statement:
            return
        written.append(True)
        other = sqlite3.connect(database)
        other.execute("UPDATE cl_state_snapshot SET second_point_type=0 WHERE instrument_id=2")
        other.commit()
        other.close()

    event.listen(engine, "after_cursor_execute", writer)
    try:
        response = query(client).json()
    finally:
        event.remove(engine, "after_cursor_execute", writer)
    assert written
    assert [item["code"] for item in response["results"]] == ["AAA"]
    assert response["data_version"] == old
    assert version(client) != old


def test_options_and_version_share_one_sqlite_snapshot(freshness_api):
    client, engine, database, _routes, _app = freshness_api
    old = version(client)
    written = []

    def writer(_connection, _cursor, statement, _parameters, _context, _many):
        if written or "SELECT DISTINCT instrument.market" not in statement:
            return
        written.append(True)
        other = sqlite3.connect(database)
        other.execute("INSERT INTO instrument(code,name,display_name,market,asset_class) VALUES('US','US','US','us','stock')")
        identifier = other.execute("SELECT id FROM instrument WHERE code='US'").fetchone()[0]
        other.execute("INSERT INTO cl_state_snapshot(instrument_id,frequency,scope,second_point_type) VALUES(?, '1week', 'bi', 0)", (identifier,))
        other.commit()
        other.close()

    event.listen(engine, "after_cursor_execute", writer)
    try:
        response = client.get(ROOT + "/options")
    finally:
        event.remove(engine, "after_cursor_execute", writer)
    assert written and response.status_code == 200
    assert response.json()["data_version"] == old
    assert not any(item["value"] == "us" for item in response.json()["dimensions"][0]["options"])
    assert version(client) != old


def test_version_failure_is_private_and_uncacheable(freshness_api, monkeypatch):
    client, _engine, _database, routes, _app = freshness_api

    def broken(*_):
        raise RuntimeError("PRIVATE_FRESHNESS_DIAGNOSTIC")

    monkeypatch.setattr(routes, "selection_data_version", broken, raising=False)
    response = client.get(ROOT + "/version")
    assert response.status_code == 503
    assert "PRIVATE_FRESHNESS_DIAGNOSTIC" not in response.text
    assert response.headers.get("cache-control") == "no-store"
    assert routes.logger.error.called
