"""Read-only screener dataset versions and coherent result snapshots."""

from datetime import datetime
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, update
from sqlalchemy.orm import Session

from CLPainter.web.backend.app.db import base, models

PREFIX = "/api/v1/test_api/stock_screener"


@pytest.fixture
def freshness_api(tmp_path, monkeypatch):
    from CLPainter.web.backend.app._config import logging_config

    monkeypatch.setattr(logging_config, "setup_logger", lambda: None)
    routes = importlib.import_module("CLPainter.web.backend.app.api.api_v1.endpoints.test_api")
    engine = create_engine(f"sqlite:///{tmp_path / 'freshness.db'}", connect_args={"check_same_thread": False})
    base.Base.metadata.create_all(engine)
    monkeypatch.setattr(routes, "engine", engine)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/test_api")
    with TestClient(app) as client:
        yield client, engine, routes
    engine.dispose()


def seed(engine):
    with Session(engine) as session:
        instrument = models.Instrument(code="AAA", name="Alpha", display_name="Alpha", market="cn", asset_class="stock")
        session.add(instrument)
        session.flush()
        snapshot = models.ClStateSnapshot(
            instrument_id=instrument.id,
            frequency="1day",
            scope="bi",
            second_point_type=0,
            calculated_at=datetime(2026, 11, 20, 16),
        )
        session.add(snapshot)
        session.commit()
        return instrument.id, snapshot.id


def version(client):
    response = client.get(PREFIX + "/version")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["data_version"]
    assert token.startswith("screener-v1:") and len(token) == len("screener-v1:") + 64
    return token


def test_version_is_stable_read_only_and_query_carries_metadata(freshness_api):
    client, engine, _ = freshness_api
    tables = inspect(engine).get_table_names()
    empty = version(client)
    assert version(client) == empty
    seed(engine)
    current = version(client)
    assert current != empty
    response = client.post(PREFIX + "/query", json={"scope": "bi", "frequency": "1day", "second_point_type": 0})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["data_version"] == current
    assert datetime.fromisoformat(body["queried_at"]).utcoffset() is not None
    assert body["count"] == 1 and [item["code"] for item in body["results"]] == ["AAA"]
    assert version(client) == current
    assert inspect(engine).get_table_names() == tables


@pytest.mark.parametrize(
    "field,value",
    [
        ("second_point_type", 1),
        ("relative_pivot_position", 2),
        ("relative_previous_pivot_position", 3),
        ("last_structure_right_type", 1),
        ("third_point_type", 2),
        ("quasi_third_point_type", 1),
        ("second_third_combined_type", 2),
        ("frequency", "1week"),
        ("scope", "xianduan"),
    ],
)
def test_same_timestamp_state_update_changes_version(freshness_api, field, value):
    client, engine, _ = freshness_api
    _, identifier = seed(engine)
    before = version(client)
    with engine.begin() as connection:
        connection.execute(
            update(models.ClStateSnapshot).where(models.ClStateSnapshot.id == identifier).values(**{field: value})
        )
    with Session(engine) as session:
        assert session.get(models.ClStateSnapshot, identifier).calculated_at == datetime(2026, 11, 20, 16)
    assert version(client) != before


@pytest.mark.parametrize(
    "field,value",
    [("code", "BBB"), ("name", "Renamed"), ("display_name", "New label"), ("market", "other"), ("asset_class", "fund")],
)
def test_instrument_changes_invalidate_cached_names_and_identity(freshness_api, field, value):
    client, engine, _ = freshness_api
    identifier, _ = seed(engine)
    before = version(client)
    with engine.begin() as connection:
        connection.execute(update(models.Instrument).where(models.Instrument.id == identifier).values(**{field: value}))
    assert version(client) != before


def test_nonlatest_record_changes_and_deletions_are_detected(freshness_api):
    client, engine, _ = freshness_api
    _, identifier = seed(engine)
    with Session(engine) as session:
        newer = models.Instrument(code="ZZZ", name="Last", display_name="Last", market="cn", asset_class="stock")
        session.add(newer)
        session.flush()
        session.add(
            models.ClStateSnapshot(
                instrument_id=newer.id,
                frequency="1day",
                scope="bi",
                second_point_type=0,
                calculated_at=datetime(2026, 11, 21, 16),
            )
        )
        session.commit()
    before = version(client)
    with engine.begin() as connection:
        connection.execute(
            update(models.ClStateSnapshot).where(models.ClStateSnapshot.id == identifier).values(second_point_type=1)
        )
    changed = version(client)
    assert changed != before
    with Session(engine) as session:
        session.delete(session.get(models.ClStateSnapshot, identifier))
        session.commit()
    assert version(client) != changed


def test_watchlists_and_presets_do_not_invalidate_dataset_version(freshness_api):
    client, engine, _ = freshness_api
    seed(engine)
    before = version(client)
    with Session(engine) as session:
        session.add(models.WatchlistBoard(name="Independent", sort_order=0))
        session.add(models.StockScreenerPreset(name="Independent", filters={}))
        session.commit()
    assert version(client) == before


def test_result_and_version_use_the_same_sqlite_read_snapshot(freshness_api, monkeypatch):
    client, engine, routes = freshness_api
    _, identifier = seed(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one().lower() == "wal"
    old_version = version(client)
    original = routes.screener_data_version
    changed = False

    def change_after_result_read(session):
        nonlocal changed
        if not changed:
            changed = True
            with engine.begin() as writer:
                writer.execute(
                    update(models.ClStateSnapshot)
                    .where(models.ClStateSnapshot.id == identifier)
                    .values(second_point_type=1)
                )
        return original(session)

    monkeypatch.setattr(routes, "screener_data_version", change_after_result_read)
    body = client.post(PREFIX + "/query", json={"second_point_type": 0}).json()
    assert [item["code"] for item in body["results"]] == ["AAA"]
    assert body["data_version"] == old_version, "Old rows must never be labeled with a concurrently newer version"
    assert version(client) != old_version
    assert client.post(PREFIX + "/query", json={"second_point_type": 0}).json()["results"] == []
