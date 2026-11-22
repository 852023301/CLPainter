"""Chart HTML errors: real HTTP, temporary DB, no live cache/data access."""

import importlib
import sys
from html import escape
from html.parser import HTMLParser
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from CLPainter.web.backend.app.db import base

URL = "/api/v1/test_api/lightweight_charts_demo"
PROBE = '<span data-error-probe="inert" title="a&b">marker & "double" \'single\'</span>'
DIAGNOSTIC = "PRIVATE_CHART_CACHE_DETAIL"


class ProbeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.probes = []

    def handle_starttag(self, tag, attrs):
        if "data-error-probe" in dict(attrs):
            self.probes.append(tag)


@pytest.fixture
def chart_errors(tmp_path, monkeypatch):
    from CLPainter.web.backend.app._config import logging_config

    monkeypatch.setattr(logging_config, "setup_logger", lambda: None)
    routes = importlib.import_module("CLPainter.web.backend.app.api.api_v1.endpoints.test_api")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    base.Base.metadata.create_all(engine)
    monkeypatch.setattr(routes, "engine", engine)
    app_dir = tmp_path / "app"
    template = app_dir / "templates/lightweight_charts_demo.html"
    resources = [
        template,
        template.with_name("_instrument_classification.html"),
        template.with_name("_chart_workspace.js"),
        app_dir / "static/css/instrument-classification.css",
        app_dir / "static/js/screener-history.js",
    ]
    for resource in resources:
        resource.parent.mkdir(parents=True, exist_ok=True)
        resource.write_text("security test fixture", encoding="utf-8")
    monkeypatch.setattr(routes, "_TEMPLATE_PATH", template)
    monkeypatch.setattr(routes, "get_chart_payload_versions", lambda *_: (1,) * len(routes.SUPPORTED_CHART_FREQUENCIES))
    original_build = routes._build_lightweight_charts_page
    original_compress = routes._compress_lightweight_charts_page
    original_build.cache_clear()
    original_compress.cache_clear()
    build = Mock(return_value="<main>SAFE_CHART</main>")
    fallback = Mock(return_value="<main>HISTORY_STILL_AVAILABLE</main>")
    monkeypatch.setattr(routes, "_build_lightweight_charts_page", build)
    monkeypatch.setattr(routes, "_render_lightweight_charts_page", fallback)
    errors = []

    def record_error(message, *args, **kwargs):
        exception = sys.exc_info() if kwargs.get("exc_info") is True else kwargs.get("exc_info")
        errors.append({"message": message, "exception": exception})

    monkeypatch.setattr(routes, "logger", Mock(error=Mock(side_effect=record_error), warning=Mock()))
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/test_api")
    try:
        with TestClient(app, raise_server_exceptions=False, headers={"Accept-Encoding": "identity"}) as client:
            yield client, routes, errors, build, fallback, resources
    finally:
        original_build.cache_clear()
        original_compress.cache_clear()
        engine.dispose()


def fail_with(error):
    def fail(*_args, **_kwargs):
        raise error

    return fail


def assert_private_error(response, error, records):
    assert response.status_code == 500, response.text
    assert DIAGNOSTIC not in response.text and PROBE not in response.text
    assert "图表暂时不可用" in response.text
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers.get("cache-control") == "no-store"
    assert "etag" not in response.headers
    assert any(
        item["exception"] and item["exception"][1] is error and item["exception"][2] is not None
        for item in records
    ), "The full server-side exception traceback must remain available to logging"


@pytest.mark.parametrize("parameter", ("frequency", "market", "asset_class", "symbol"))
def test_chart_input_error_is_html_escaped(chart_errors, monkeypatch, parameter):
    client, routes, records, build, _fallback, _resources = chart_errors
    if parameter == "symbol":
        # Symbol validation belongs to the payload-path boundary; never read a live cache.
        monkeypatch.setattr(routes, "get_chart_payload_versions", fail_with(ValueError("Invalid symbol: " + PROBE)))
    response = client.get(URL, params={parameter: PROBE})
    assert response.status_code == 400
    assert escape(PROBE) in response.text
    parser = ProbeParser()
    parser.feed(response.text)
    assert not parser.probes
    assert response.headers.get("cache-control") == "no-store"
    assert "etag" not in response.headers
    assert not records
    build.assert_not_called()


@pytest.mark.parametrize("parameter", ("market_dir", "asset_class_dir"))
def test_renamed_directory_parameter_remains_400(chart_errors, parameter):
    client, _routes, _records, build, _fallback, _resources = chart_errors
    response = client.get(URL, params={parameter: PROBE})
    assert response.status_code == 400 and "已改名" in response.text
    assert PROBE not in response.text
    assert response.headers.get("cache-control") == "no-store"
    build.assert_not_called()


@pytest.mark.parametrize(
    "stage",
    ("versions", "database", "database_value", "classification_value", "classification_json", "template_version", "render"),
)
def test_unexpected_chart_failure_is_private_and_logged(chart_errors, monkeypatch, stage):
    client, routes, records, build, _fallback, resources = chart_errors
    error = ValueError(DIAGNOSTIC + PROBE) if stage.endswith("value") else OSError(DIAGNOSTIC + PROBE)
    if stage == "versions":
        monkeypatch.setattr(routes, "get_chart_payload_versions", fail_with(error))
    elif stage in {"database", "database_value"}:
        monkeypatch.setattr(routes, "Session", fail_with(error))
    elif stage == "classification_value":
        monkeypatch.setattr(routes, "instrument_classification_payload", fail_with(error))
    elif stage == "classification_json":
        monkeypatch.setattr(routes, "instrument_classification_payload", lambda *_: {"unsupported": object()})
    elif stage == "template_version":
        resources[-1].unlink()
    else:
        build.side_effect = error
    response = client.get(URL)
    if stage in {"classification_json", "template_version"}:
        assert records, "Internal metadata failures must also be logged"
        error = records[-1]["exception"][1]
    assert_private_error(response, error, records)


@pytest.mark.parametrize("encoding", ("identity", "gzip"))
def test_valid_chart_still_supports_html_gzip_and_etag(chart_errors, encoding):
    client, _routes, records, _build, _fallback, _resources = chart_errors
    response = client.get(URL, headers={"Accept-Encoding": encoding})
    assert response.status_code == 200 and "SAFE_CHART" in response.text
    assert response.headers.get("cache-control") == "private, no-cache"
    assert bool(response.headers.get("content-encoding")) == (encoding == "gzip")
    unchanged = client.get(URL, headers={"If-None-Match": response.headers["etag"]})
    assert unchanged.status_code == 304 and not unchanged.content
    assert not records


@pytest.mark.parametrize("error_type", (FileNotFoundError, ValueError))
def test_history_missing_chart_still_renders_history(chart_errors, error_type):
    client, _routes, records, build, fallback, _resources = chart_errors
    build.side_effect = error_type(DIAGNOSTIC + PROBE)
    response = client.get(URL, params={"screener_mode": "history"})
    assert response.status_code == 200 and "HISTORY_STILL_AVAILABLE" in response.text
    assert DIAGNOSTIC not in response.text and PROBE not in response.text
    assert response.headers.get("cache-control") == "no-store"
    assert not records
    fallback.assert_called_once()


def test_history_does_not_mask_internal_setup_failure(chart_errors, monkeypatch):
    client, routes, records, _build, fallback, _resources = chart_errors
    error = ValueError(DIAGNOSTIC + PROBE)
    monkeypatch.setattr(routes, "Session", fail_with(error))
    response = client.get(URL, params={"screener_mode": "history"})
    assert_private_error(response, error, records)
    fallback.assert_not_called()
