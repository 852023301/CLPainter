"""Screener presets: real HTTP requests, isolated SQLite, reversible migration."""

import importlib
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, text

from CLPainter.web.backend.app.db import base, models


BACKEND = Path(__file__).resolve().parents[1]
PREFIX = "/api/v1/test_api/stock_screener/presets"


@pytest.fixture
def api(tmp_path, monkeypatch):
    from CLPainter.web.backend.app._config import logging_config
    monkeypatch.setattr(logging_config, "setup_logger", lambda: None)
    routes = importlib.import_module("CLPainter.web.backend.app.api.api_v1.endpoints.test_api")
    database = tmp_path / "presets.db"
    engine = create_engine(f"sqlite:///{database}", connect_args={"check_same_thread": False})
    base.Base.metadata.create_all(engine)
    monkeypatch.setattr(routes, "engine", engine)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/test_api")
    with TestClient(app) as client:
        yield client, engine, app
    engine.dispose()


def test_presets_persist_across_clients_and_preserve_unlimited_and_zero(api):
    client, engine, app = api
    assert client.get(PREFIX).json() == {"presets": []}
    response = client.post(PREFIX, json={"name": "  日线二买  ", "filters": {"second_point_type": 0}})
    assert response.status_code == 201, response.text
    preset = response.json()
    assert preset["name"] == "日线二买"
    assert preset["filters"]["second_point_type"] == 0
    assert preset["filters"]["frequency"] is None
    assert preset["filters"]["market"] is None
    assert "results" not in preset
    assert preset["created_at"] and preset["updated_at"]
    with TestClient(app) as another_browser:
        assert another_browser.get(PREFIX).json() == {"presets": [preset]}
    with engine.connect() as connection:
        stored = connection.execute(text("SELECT filters FROM stock_screener_preset")).scalar_one()
        assert json.loads(stored) == preset["filters"]


def test_update_rename_duplicate_and_delete(api):
    client, _, _ = api
    first = client.post(PREFIX, json={"name": "A", "filters": {}}).json()
    second = client.post(PREFIX, json={"name": "B", "filters": {"frequency": "1week"}}).json()
    duplicate = client.post(PREFIX, json={"name": " A ", "filters": {}})
    assert duplicate.status_code == 409
    collision = client.put(f"{PREFIX}/{first['id']}", json={"name": "B", "filters": {}})
    assert collision.status_code == 409
    assert client.get(PREFIX).json()["presets"] == [first, second]
    changed = client.put(f"{PREFIX}/{first['id']}", json={
        "name": "Updated", "filters": {"market": "cn", "frequency": "1month", "third_point_type": 1},
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["id"] == first["id"]
    assert changed.json()["filters"]["frequency"] == "1month"
    assert changed.json()["filters"]["second_point_type"] is None
    assert client.delete(f"{PREFIX}/{first['id']}").status_code == 204
    assert client.get(PREFIX).json()["presets"] == [second]
    assert client.delete(f"{PREFIX}/{first['id']}").status_code == 404
    assert client.put(f"{PREFIX}/{first['id']}", json={"name": "A", "filters": {}}).status_code == 404


@pytest.mark.parametrize("filters", [
    {"market": "unknown"}, {"asset_class": "unknown"}, {"scope": "unknown"}, {"frequency": "daily"},
    {"second_point_type": 3}, {"third_point_type": -1}, {"relative_pivot_position": 4},
    {"second_point_type": True}, {"second_point_type": "1"},
    {"results": []}, {"unknown": 1}, {"frequency": "x" * 1000},
])
def test_invalid_filters_are_not_silently_saved(api, filters):
    client, _, _ = api
    response = client.post(PREFIX, json={"name": "Bad", "filters": filters})
    assert response.status_code == 422, response.text
    assert client.get(PREFIX).json() == {"presets": []}


@pytest.mark.parametrize("name", ["", "   ", "x" * 65, "line\nbreak", 123])
def test_invalid_names_are_rejected(api, name):
    client, _, _ = api
    response = client.post(PREFIX, json={"name": name, "filters": {}})
    assert response.status_code == 422


def test_results_are_forbidden_and_unlimited_filters_can_be_saved(api):
    client, _, _ = api
    assert client.post(PREFIX, json={"name": "A", "filters": {}, "results": []}).status_code == 422
    response = client.post(PREFIX, json={"name": "All", "filters": {}})
    assert response.status_code == 201, response.text
    assert set(response.json()["filters"].values()) == {None}


def test_presets_migration_is_reversible_and_preserves_watchlists(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    monkeypatch.setattr(base, "engine", engine)
    config = Config(str(BACKEND / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_current_head() != "b4e1a7d9c3f2", "A preset migration is required"
    command.upgrade(config, "b4e1a7d9c3f2")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO watchlist_board (name, sort_order) VALUES ('keep', 0)"))
    command.upgrade(config, "head")
    assert "stock_screener_preset" in inspect(engine).get_table_names()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO stock_screener_preset (name, filters) VALUES ('sample', '{}')"))
        assert connection.execute(text("SELECT name FROM watchlist_board")).scalar_one() == "keep"
    command.downgrade(config, "b4e1a7d9c3f2")
    assert "stock_screener_preset" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT name FROM watchlist_board")).scalar_one() == "keep"
    command.upgrade(config, "head")
    assert "stock_screener_preset" in inspect(engine).get_table_names()
    engine.dispose()


def test_saved_filters_query_latest_data_without_caching_results(api):
    from sqlalchemy.orm import Session
    client, engine, _ = api
    preset = client.post(PREFIX, json={
        "name": "Live", "filters": {"scope": "bi", "frequency": "1day", "second_point_type": 0},
    }).json()
    def add_instrument(code, state):
        with Session(engine) as session:
            instrument = models.Instrument(code=code, name=code, display_name=code, market="cn", asset_class="stock")
            session.add(instrument)
            session.flush()
            session.add(models.ClStateSnapshot(
                instrument_id=instrument.id, frequency="1day", scope="bi", second_point_type=state,
            ))
            session.commit()
    add_instrument("AAA", 0)
    add_instrument("EXCLUDED", 1)
    query_url = "/api/v1/test_api/stock_screener/query"
    first = client.post(query_url, json=preset["filters"])
    assert first.status_code == 200
    assert [item["code"] for item in first.json()["results"]] == ["AAA"]
    add_instrument("BBB", 0)
    stored = client.get(PREFIX).json()["presets"][0]
    latest = client.post(query_url, json=stored["filters"])
    assert latest.status_code == 200
    assert [item["code"] for item in latest.json()["results"]] == ["AAA", "BBB"]
    assert "results" not in stored
