"""Historical screener results: offline calendars, SQLite, and real HTTP."""

import importlib
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config
from CLPainter.web.backend.app.db import base, models
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session


@pytest.fixture
def history_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}", connect_args={"check_same_thread": False})
    base.Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            models.StockScreenerPreset(id=1, name="日线零值", filters={"frequency": "1day", "second_point_type": 0})
        )
        for code in ["AAA", "BBB", "CCC"]:
            session.add(models.Instrument(code=code, name=code, display_name=code, market="cn", asset_class="stock"))
        session.commit()
    yield engine
    engine.dispose()


def service():
    return importlib.import_module("CLPainter.web.backend.app.screener.history")


def batch(day, selected="AAA", frequency="1day"):
    records = []
    for code in ["AAA", "BBB", "CCC"]:
        for freq in {"1day", frequency}:
            records.append(
                {
                    "code": code,
                    "market": "cn",
                    "asset_class": "stock",
                    "frequency": freq,
                    "scope": "bi",
                    "second_point_type": 0 if code == selected else 1,
                    "data_trade_date": day,
                }
            )
    return records


def calendar(**kwargs):
    assert kwargs["secumarket"] == "CN" and kwargs["length"] == 2
    day = date.fromisoformat(kwargs["start"])
    next_days = {date(2026, 11, 13): date(2026, 11, 16), date(2026, 11, 20): date(2026, 11, 23)}
    return [day.isoformat(), next_days[day].isoformat()]


NOW = datetime(2026, 11, 20, 18, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.mark.parametrize(
    "frequency,expected", [("1day", True), ("1week", True), ("1month", True), ("1quarter", False), ("1year", False)]
)
def test_holiday_period_end_uses_next_trade_day(frequency, expected):
    assert service().is_period_end(date(2026, 4, 30), date(2026, 5, 6), frequency) is expected


def test_ddp_adapter_uses_the_public_calendar_api(monkeypatch):
    import ddp.util

    calls = []

    def getter(**kwargs):
        calls.append(kwargs)
        return ["2026-11-20", "2026-11-23"]

    monkeypatch.setattr(ddp.util, "get_trade_calendar", getter)
    assert service().next_trade_day(date(2026, 11, 20)) == date(2026, 11, 23)
    assert calls == [{"start": "2026-11-20", "length": 2, "out": "list", "secumarket": "CN"}]


def test_archive_success_immutable_and_differences(history_db):
    module = service()
    assert module.archive_due_presets(history_db, batch("2026-11-13"), now=NOW, calendar_loader=calendar)["saved"] == 1
    assert (
        module.archive_due_presets(history_db, batch("2026-11-20", "CCC"), now=NOW, calendar_loader=calendar)["saved"]
        == 1
    )
    repeated = module.archive_due_presets(history_db, batch("2026-11-20", "BBB"), now=NOW, calendar_loader=calendar)
    assert repeated["existing"] == 1
    with Session(history_db) as session:
        rows = session.scalars(select(models.StockScreenerRun).order_by(models.StockScreenerRun.version_date)).all()
        assert len(rows) == 2 and rows[1].version_date == date(2026, 11, 20)
        assert [item["code"] for item in rows[1].results] == ["CCC"]
        detail = module.run_detail(session, rows[1].id)
        assert detail["previous_version"] == "2026-11-13"
        assert [item["code"] for item in detail["added"]] == ["CCC"]
        assert [item["code"] for item in detail["removed"]] == ["AAA"]
        assert detail["retained"] == []
        first = module.run_detail(session, rows[0].id)
        assert first["comparison_available"] is False and first["added"] == []


def test_missing_or_stale_symbol_is_skipped(history_db):
    module = service()
    missing = [record for record in batch("2026-11-13") if record["code"] != "CCC"]
    assert module.archive_due_presets(history_db, missing, now=NOW, calendar_loader=calendar)["saved"] == 1
    stale = batch("2026-11-20")
    stale[0]["data_trade_date"] = "2026-11-06"
    assert module.archive_due_presets(history_db, stale, now=NOW, calendar_loader=calendar)["saved"] == 1
    with Session(history_db) as session:
        rows = session.scalars(select(models.StockScreenerRun).order_by(models.StockScreenerRun.version_date)).all()
        assert [row.version_date for row in rows] == [date(2026, 11, 13), date(2026, 11, 20)]
        assert [item["code"] for item in rows[0].results] == ["AAA"]
        assert rows[1].results == []


def test_empty_success_is_saved_but_intraday_and_unknown_calendars_are_not(history_db):
    module = service()
    records = batch("2026-11-20", "NO_MATCH")
    early = NOW.replace(hour=14)
    assert module.archive_due_presets(history_db, records, now=early, calendar_loader=calendar)["saved"] == 0
    assert (
        module.archive_due_presets(history_db, records, now=NOW, calendar_loader=lambda **kw: ["2026-11-20"])["failed"]
        == 1
    )
    assert module.archive_due_presets(history_db, records, now=NOW, calendar_loader=calendar)["saved"] == 1
    with Session(history_db) as session:
        assert session.scalar(select(models.StockScreenerRun)).results == []


def test_unlimited_and_minute_presets_are_not_automatically_executed(history_db):
    with Session(history_db) as session:
        session.get(models.StockScreenerPreset, 1).filters = {"frequency": None}
        session.add(models.StockScreenerPreset(name="minute", filters={"frequency": "1min"}))
        session.commit()
    report = service().archive_due_presets(
        history_db, [], now=NOW, calendar_loader=lambda **kw: pytest.fail("No calendar call expected")
    )
    assert report["saved"] == 0 and report["disabled"] == 2


def test_week_month_quarter_year_and_scope_filters(history_db):
    module = service()
    with Session(history_db) as session:
        session.get(models.StockScreenerPreset, 1).filters = {
            "frequency": "1week",
            "scope": "bi",
            "second_point_type": 0,
        }
        session.commit()
    records = batch("2026-11-20", frequency="1week")
    report = module.archive_due_presets(history_db, records, now=NOW, calendar_loader=calendar)
    assert report["saved"] == 1
    with Session(history_db) as session:
        row = session.scalar(select(models.StockScreenerRun))
        assert row.frequency == "1week" and [item["code"] for item in row.results] == ["AAA"]


def test_history_schema_is_exactly_five_columns_and_migration_is_reversible(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    monkeypatch.setattr(base, "engine", engine)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "e6c2a9f4b8d1")
    command.upgrade(config, "head")
    assert {column["name"] for column in inspect(engine).get_columns("stock_screener_run")} == {
        "id",
        "preset_id",
        "frequency",
        "version_date",
        "results",
    }
    command.downgrade(config, "e6c2a9f4b8d1")
    assert "stock_screener_run" not in inspect(engine).get_table_names()
    assert "stock_screener_preset" in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    engine.dispose()


@pytest.fixture
def history_http(history_db, monkeypatch):
    from CLPainter.web.backend.app._config import logging_config

    monkeypatch.setattr(logging_config, "setup_logger", lambda: None)
    routes = importlib.import_module("CLPainter.web.backend.app.api.api_v1.endpoints.test_api")
    monkeypatch.setattr(routes, "engine", history_db)
    monkeypatch.setattr(
        routes, "templates", Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "app/templates"))
    )
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/test_api")
    service().archive_due_presets(history_db, batch("2026-11-13"), now=NOW, calendar_loader=calendar)
    service().archive_due_presets(history_db, batch("2026-11-20", "CCC"), now=NOW, calendar_loader=calendar)
    with TestClient(app) as client:
        yield client, history_db


def test_history_http_list_detail_pagination_and_read_only(history_http):
    client, _ = history_http
    prefix = "/api/v1/test_api/stock_screener/runs"
    response = client.get(prefix, params={"limit": 1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2 and len(data["runs"]) == 1
    latest = data["runs"][0]
    assert latest["version_date"] == "2026-11-20" and "results" not in latest
    detail = client.get(prefix + "/" + str(latest["id"])).json()
    assert detail["previous_version"] == "2026-11-13"
    assert [item["code"] for item in detail["added"]] == ["CCC"]
    assert client.get(prefix, params={"offset": 1, "limit": 1}).json()["runs"][0]["version_date"] == "2026-11-13"
    assert client.get(prefix + "/99999").status_code == 404
    assert client.post(prefix, json={}).status_code == 405
    assert client.get(prefix, params={"limit": 1000}).status_code == 422
    assert client.get(prefix, params={"frequency": "unsupported"}).status_code == 400


def test_history_page_displays_frozen_results_and_escapes_names(history_http):
    client, engine = history_http
    with Session(engine) as session:
        session.get(models.StockScreenerPreset, 1).name = "<script>alert(1)</script>"
        latest = session.scalar(select(models.StockScreenerRun).order_by(models.StockScreenerRun.version_date.desc()))
        latest.results = [
            {"market": "cn", "asset_class": "stock", "code": "CCC", "display_name": "<img src=x onerror=alert(1)>"}
        ]
        identifier = latest.id
        session.commit()
    response = client.get("/api/v1/test_api/stock_screener/history", params={"run_id": identifier, "standalone": 1})
    assert response.status_code == 200, response.text
    assert "2026-11-20" in response.text and "2026-11-13" in response.text
    assert "新增" in response.text and "移出" in response.text and "本期" in response.text
    assert "&lt;script&gt;" in response.text and "&lt;img" in response.text
    assert "<script>alert(1)</script>" not in response.text and "<img src=x" not in response.text
    assert "symbol=CCC" in response.text
    removed = client.get(
        "/api/v1/test_api/stock_screener/history", params={"run_id": identifier, "view": "removed", "standalone": 1}
    )
    assert removed.status_code == 200 and "symbol=AAA" in removed.text
    assert client.get("/api/v1/test_api/stock_screener/history", params={"run_id": 99999}).status_code == 404


def test_presets_with_history_are_not_deleted(history_http):
    client, engine = history_http
    response = client.delete("/api/v1/test_api/stock_screener/presets/1")
    assert response.status_code == 409
    with Session(engine) as session:
        assert session.get(models.StockScreenerPreset, 1) is not None
        assert len(session.scalars(select(models.StockScreenerRun)).all()) == 2


def test_history_empty_page_is_readable(history_db, monkeypatch):
    from CLPainter.web.backend.app.api.api_v1.endpoints import test_api as routes

    monkeypatch.setattr(routes, "engine", history_db)
    monkeypatch.setattr(
        routes, "templates", Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "app/templates"))
    )
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/test_api")
    with TestClient(app) as client:
        response = client.get("/api/v1/test_api/stock_screener/history", params={"standalone": 1})
        assert response.status_code == 200 and "暂无归档结果" in response.text


def test_differences_use_market_asset_and_code_not_display_name(history_db):
    with Session(history_db) as session:
        session.add_all(
            [
                models.StockScreenerRun(
                    preset_id=1,
                    frequency="1day",
                    version_date=date(2026, 11, 13),
                    results=[
                        {"market": "cn", "asset_class": "stock", "code": "AAA", "display_name": "old"},
                    ],
                ),
                models.StockScreenerRun(
                    preset_id=1,
                    frequency="1day",
                    version_date=date(2026, 11, 20),
                    results=[
                        {"market": "cn", "asset_class": "stock", "code": "AAA", "display_name": "new"},
                        {"market": "cn", "asset_class": "fund", "code": "AAA", "display_name": "fund"},
                    ],
                ),
            ]
        )
        session.commit()
        latest = session.scalar(select(models.StockScreenerRun).order_by(models.StockScreenerRun.version_date.desc()))
        detail = service().run_detail(session, latest.id)
        assert len(detail["retained"]) == 1 and len(detail["added"]) == 1 and detail["removed"] == []
        assert detail["added"][0]["asset_class"] == "fund"


@pytest.mark.parametrize(
    "day,following", [(date(2026, 12, 31), date(2027, 1, 4)), (date(2027, 12, 31), date(2028, 1, 3))]
)
def test_cross_year_periods_use_their_own_calendar_bucket(day, following):
    assert service().is_period_end(day, following, "1month")
    assert service().is_period_end(day, following, "1quarter")
    assert service().is_period_end(day, following, "1year")


def test_unique_constraint_and_success_content_are_minimal(history_db):
    from sqlalchemy.exc import IntegrityError

    module = service()
    module.archive_due_presets(history_db, batch("2026-11-20"), now=NOW, calendar_loader=calendar)
    with Session(history_db) as session:
        row = session.scalar(select(models.StockScreenerRun))
        assert set(row.results[0]) == {"code", "display_name", "market", "asset_class"}
        session.add(models.StockScreenerRun(preset_id=1, frequency="1day", version_date=row.version_date, results=[]))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert len(session.scalars(select(models.StockScreenerRun)).all()) == 1


def test_missing_scope_is_skipped_and_calendar_failure_does_not_save(history_db):
    def unavailable(**kwargs):
        raise ConnectionError("calendar unavailable")

    assert (
        service().archive_due_presets(history_db, batch("2026-11-20"), now=NOW, calendar_loader=unavailable)["failed"]
        == 1
    )
    with Session(history_db) as session:
        session.get(models.StockScreenerPreset, 1).filters = {"frequency": "1day", "scope": "xianduan"}
        session.commit()
        assert session.scalars(select(models.StockScreenerRun)).all() == []
    assert service().archive_due_presets(history_db, batch("2026-11-20"), now=NOW, calendar_loader=calendar)["saved"] == 1
    with Session(history_db) as session:
        assert session.scalar(select(models.StockScreenerRun)).results == []


def test_history_page_pagination_controls(history_http):
    from datetime import timedelta

    client, engine = history_http
    with Session(engine) as session:
        session.add_all(
            models.StockScreenerRun(
                preset_id=1, frequency="1day", version_date=date(2024, 1, 3) + timedelta(weeks=i), results=[]
            )
            for i in range(49)
        )
        session.commit()
    first = client.get("/api/v1/test_api/stock_screener/history", params={"standalone": 1})
    second = client.get("/api/v1/test_api/stock_screener/history", params={"offset": 50, "standalone": 1})
    assert first.status_code == second.status_code == 200
    assert "下一页" in first.text and "上一页" in second.text


def test_legacy_history_opens_shared_latest_chart_workspace(history_http):
    from urllib.parse import parse_qs, urlparse

    client, engine = history_http
    with Session(engine) as session:
        latest = session.scalar(select(models.StockScreenerRun).order_by(models.StockScreenerRun.version_date.desc()))
        identifier = latest.id
    response = client.get(
        "/api/v1/test_api/stock_screener/history",
        params={
            "preset_id": 1,
            "frequency": "1day",
            "run_id": identifier,
            "view": "removed",
            "offset": 0,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = urlparse(response.headers["location"])
    params = parse_qs(location.query, keep_blank_values=True)
    assert location.path == "/api/v1/test_api/lightweight_charts_demo"
    assert params["symbol"] == ["AAA"] and params["frequency"] == ["1day"]
    assert params["screener_mode"] == ["history"]
    assert params["history_run_id"] == [str(identifier)]
    assert params["history_preset"] == ["1"] and params["history_view"] == ["removed"]
    assert not ({"as_of", "end_date", "version_date"} & params.keys())


def test_empty_history_still_opens_workspace(history_db, monkeypatch):
    from CLPainter.web.backend.app.api.api_v1.endpoints import test_api as routes

    monkeypatch.setattr(routes, "engine", history_db)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/test_api")
    with TestClient(app) as client:
        response = client.get("/api/v1/test_api/stock_screener/history", follow_redirects=False)
    assert response.status_code == 303
    assert "screener_mode=history" in response.headers["location"]
    assert "asset_class=index" in response.headers["location"]


def test_history_workspace_keeps_latest_bars_and_missing_chart_does_not_hide_history(history_http, monkeypatch):
    import json
    import re

    from CLPainter.web.backend.app.api.api_v1.endpoints import test_api as routes

    client, _ = history_http
    template = Path(__file__).resolve().parents[1] / "app/templates/lightweight_charts_demo.html"
    monkeypatch.setattr(routes, "_TEMPLATE_PATH", template)
    monkeypatch.setattr(
        routes, "get_chart_payload_versions", lambda *args: (1,) * len(routes.SUPPORTED_CHART_FREQUENCIES)
    )
    payload = {
        name: "[]"
        for name in [
            "change_data",
            "bi_data",
            "xd_data",
            "zhongshu_data",
            "zhongshu_in_xianduan_data",
            "xianduan_zhongshu_data",
            "xianduan_zhongshu_another_data",
            "volume_data",
        ]
    }
    payload.update(
        precision=2,
        candle_data=json.dumps(
            [
                {"time": "2026-11-13", "open": 1, "high": 2, "low": 1, "close": 2},
                {"time": "2026-11-20", "open": 2, "high": 3, "low": 2, "close": 3},
            ]
        ),
    )
    monkeypatch.setattr(routes, "load_chart_payload", lambda *args: payload)
    routes._build_lightweight_charts_page.cache_clear()
    url = "/api/v1/test_api/lightweight_charts_demo?symbol=AAA&frequency=1day&market=cn&asset_class=stock&screener_mode=history&history_run_id=1"
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert '"2026-11-20"' in response.text and '"2026-11-13"' in response.text
    assert 'id="screenerHistoryPanel"' in response.text

    def missing(*args):
        raise FileNotFoundError("missing chart")

    monkeypatch.setattr(routes, "load_chart_payload", missing)
    routes._build_lightweight_charts_page.cache_clear()
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert 'id="screenerHistoryPanel"' in response.text
    error = re.search(r"const chartError = (.*);", response.text)
    assert error and "该标的暂无可用图表数据" in json.loads(error.group(1))
    routes._build_lightweight_charts_page.cache_clear()


@pytest.mark.parametrize("module", ["ma", "boll", "rsi", "macd"])
def test_history_context_never_truncates_latest_indicator_modules(history_http, monkeypatch, module):
    import json

    from CLPainter.web.backend.app.api.api_v1.endpoints import test_api as routes

    client, _ = history_http
    values = [{"time": "2026-11-13", "value": 1}, {"time": "2026-11-20", "value": 2}]
    data = {"stats": values, "lines": []} if module == "macd" else [{"key": module, "values": values}]
    monkeypatch.setattr(routes, "load_chart_payload", lambda *args: {module + "_data": json.dumps(data)})
    response = client.get(
        "/api/v1/test_api/lightweight_charts_module",
        params={
            "symbol": "AAA",
            "frequency": "1day",
            "market": "cn",
            "asset_class": "stock",
            "module": module,
            "screener_mode": "history",
            "history_run_id": 1,
        },
    )
    assert response.status_code == 200
    stored = json.loads(response.json()["data"])
    assert "2026-11-20" in json.dumps(stored) and "2026-11-13" in json.dumps(stored)
