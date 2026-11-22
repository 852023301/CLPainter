"""Opt-in frontend contracts; intentionally outside default test_*.py discovery.

The default suite must remain green while known defects are recorded.
Run this file explicitly to get RED assertions before the corresponding fixes.
No application import, live HTTP, DB access, browser or production writes.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import html
import json
import os
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

PROJECT = Path(os.environ.get("CLPAINTER_FRONTEND_BASELINE_ROOT", Path(__file__).resolve().parents[4]))
TEMPLATE = PROJECT / "web/backend/app/templates/lightweight_charts_demo.html"
API = PROJECT / "web/backend/app/api/api_v1/endpoints/test_api.py"
NODE = Path(__file__).with_suffix(".js")
NODE_CONTRACTS = (
    "module_retry", "gap_retry", "indicator_latest_wins", "indicator_preserves_range",
    "storage_bool_read", "storage_string_read", "storage_bool_write", "storage_string_write",
    "realtime_result_keyboard",
)
NODE_CONTROLS = ("control_volume_build", "control_shared_request", "control_available_storage")


@pytest.mark.parametrize("case", NODE_CONTRACTS + NODE_CONTROLS)
def test_original_javascript_contract(case):
    result = subprocess.run(
        ["node", str(NODE), "--template", str(TEMPLATE), "--case", case, "--check"],
        text=True, capture_output=True, check=False, timeout=10,
    )
    assert result.returncode != 2, "Harness error, not a valid reproduction:\n" + result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert len(report["results"]) == 1 and report["results"][0]["id"] == case
    assert result.returncode == 0 and report["results"][0]["status"] == "passed", result.stdout + result.stderr


class ParsedControls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.controls = {}
        self.probe_nodes = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.controls[values["id"]] = (tag, values)
        if "data-baseline-probe" in values:
            self.probe_nodes.append((tag, values))


@pytest.mark.parametrize("identifier", ("maTrigger", "layerTrigger"))
def test_menu_trigger_exposes_keyboard_focus(identifier):
    parser = ParsedControls()
    parser.feed(TEMPLATE.read_text(encoding="utf-8"))
    tag, attrs = parser.controls[identifier]
    native = tag == "button" or (tag == "a" and bool(attrs.get("href")))
    semantic = attrs.get("role") == "button" and int(attrs.get("tabindex", -1)) >= 0
    assert native or semantic, (identifier, tag, attrs)


@pytest.fixture
def error_client(tmp_path):
    """Execute the original endpoint AST with in-memory DB/render boundaries."""
    template = tmp_path / "app/templates/lightweight_charts_demo.html"
    for item in (
        template, template.with_name("_instrument_classification.html"), template.with_name("_chart_workspace.js"),
        tmp_path / "app/static/css/instrument-classification.css",
        tmp_path / "app/static/js/screener-history.js",
    ):
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text("baseline fixture", encoding="utf-8")

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def scalar(self, *_):
            return None

    class Selection:
        def where(self, *_):
            return self

    async def invoke(function, *args):
        return function(*args)

    def build(*_):
        return "<html><body>safe chart</body></html>"

    namespace = {
        "__name__": __name__, "Request": Request, "Response": Response, "HTMLResponse": HTMLResponse,
        "Path": Path, "json": json, "hashlib": hashlib, "html": html, "escape": html.escape,
        "_SIMPLE_FREQUENCIES": {"1day"}, "_SIMPLE_VALUE_PATTERN": re.compile(r"^[A-Za-z0-9_-]+$"),
        "get_chart_payload_versions": lambda *_: (1, 1, 1, 1, 1),
        "Session": lambda *_: FakeSession(), "engine": object(), "select": lambda *_: Selection(),
        "Instrument": SimpleNamespace(market=object(), asset_class=object(), code=object()),
        "instrument_classification_payload": lambda *_: {"status": "unregistered"},
        "_TEMPLATE_PATH": template, "_build_lightweight_charts_page": build,
        "run_in_threadpool": invoke, "logger": SimpleNamespace(error=lambda *a, **k: None, warning=lambda *a, **k: None),
    }
    tree = ast.parse(API.read_text(encoding="utf-8"))
    needed = {"_normalize_frequency", "_normalize_directory_value", "lightweight_charts_demo"}
    selected = []
    for original in tree.body:
        if isinstance(original, (ast.FunctionDef, ast.AsyncFunctionDef)) and original.name in needed:
            node = copy.deepcopy(original)
            node.decorator_list = []
            selected.append(node)
    assert {node.name for node in selected} == needed
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, str(API), "exec"), namespace)
    app = FastAPI()
    app.get("/chart")(namespace["lightweight_charts_demo"])
    with TestClient(app, headers={"Accept-Encoding": "identity"}) as client:
        yield client, namespace


@pytest.mark.parametrize("parameter", ("frequency", "market"))
def test_error_response_does_not_interpret_query_html(error_client, parameter):
    client, _ = error_client
    marker = '<span data-baseline-probe="inert">baseline</span>'
    response = client.get("/chart", params={parameter: marker})
    assert response.status_code == 400
    parser = ParsedControls()
    parser.feed(response.text)
    assert not parser.probe_nodes, "Query text became an HTML element: " + response.text


def test_error_response_hides_internal_diagnostics(error_client):
    client, namespace = error_client
    diagnostic = "BASELINE_PRIVATE_CACHE_DETAIL"

    def missing(*_):
        raise FileNotFoundError(diagnostic)

    namespace["_build_lightweight_charts_page"] = missing
    response = client.get("/chart")
    assert response.status_code == 500
    assert diagnostic not in response.text, "Internal exception was exposed in the response"


def test_control_valid_chart_response(error_client):
    client, _ = error_client
    response = client.get("/chart")
    assert response.status_code == 200
    assert "safe chart" in response.text
