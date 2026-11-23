"""Classification context in chart HTML: identity, missing states, escaping and cache freshness."""

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from CLPainter.web.backend.app.db import base, models

BACKEND = Path(__file__).resolve().parents[1]
URL = "/api/v1/test_api/lightweight_charts_demo"


def concept(code, name, class_code="11"):
    return {
        "code": str(code),
        "name": name,
        "paths": [
            {
                "class_code": class_code,
                "class_name": "地域" if class_code == "18" else "科技",
                "sub_class_code": "1108",
                "sub_class_name": "新能源汽车",
                "concept_name": name,
            }
        ],
    }


@pytest.fixture
def chart_page(tmp_path, monkeypatch):
    from CLPainter.web.backend.app._config import logging_config

    monkeypatch.setattr(logging_config, "setup_logger", lambda: None)
    routes = importlib.import_module("CLPainter.web.backend.app.api.api_v1.endpoints.test_api")
    engine = create_engine(f"sqlite:///{tmp_path / 'classification-ui.db'}", connect_args={"check_same_thread": False})
    base.Base.metadata.create_all(engine)
    with Session(engine) as session:
        rows = [
            models.Instrument(code="300750SZ", name="CATL", display_name="宁德时代", market="cn", asset_class="stock"),
            models.Instrument(
                code="600519SH", name="Moutai", display_name="贵州茅台", market="cn", asset_class="stock"
            ),
            models.Instrument(code="000001SZ", name="Bank", display_name="平安银行", market="cn", asset_class="stock"),
            models.Instrument(
                code="300750SZ", name="Index", display_name="同代码指数", market="cn", asset_class="index"
            ),
            models.Instrument(code="300750SZ", name="Other", display_name="其他市场", market="us", asset_class="stock"),
        ]
        session.add_all(rows)
        session.flush()
        region = concept(18011235, "福建", "18")
        session.add_all(
            [
                models.InstrumentClassification(
                    instrument_id=rows[0].id,
                    sw_l1_code="801730",
                    sw_l1_name="申万电力设备",
                    sw_l2_code="801737",
                    sw_l2_name="申万电池",
                    sw_l3_code="857371",
                    sw_l3_name="申万锂电池",
                    concepts=[concept(11080003, "锂电池概念"), concept(13011424, "储能概念"), region],
                    regions=[region],
                ),
                models.InstrumentClassification(
                    instrument_id=rows[1].id,
                    sw_l1_code="801120",
                    sw_l1_name="申万食品饮料",
                    sw_l2_code="801125",
                    sw_l2_name="申万白酒Ⅱ",
                    sw_l3_code="851251",
                    sw_l3_name="申万白酒Ⅲ",
                    concepts=[concept(14020001, "白酒概念")],
                    regions=[concept(18051252, "贵州", "18")],
                ),
            ]
        )
        session.commit()
    app_dir = tmp_path / "app"
    templates = app_dir / "templates"
    # Mirror full public resources, including independently added workspace assets.
    shutil.copytree(BACKEND / "app/templates", templates)
    shutil.copytree(BACKEND / "app/static", app_dir / "static")
    monkeypatch.setattr(routes, "engine", engine)
    monkeypatch.setattr(routes, "_TEMPLATE_PATH", templates / "lightweight_charts_demo.html")
    renderer = Jinja2Templates(directory=str(templates))
    renderer.env.cache = None
    monkeypatch.setattr(routes, "templates", renderer)
    versions = tuple([1] * len(routes.SUPPORTED_CHART_FREQUENCIES))
    monkeypatch.setattr(routes, "get_chart_payload_versions", lambda *args: versions)
    loads = []

    def load(symbol, frequency, market, asset_class):
        loads.append((symbol, frequency, market, asset_class))
        return {
            **{
                name: "[]"
                for name in [
                    "candle_data",
                    "bi_data",
                    "xd_data",
                    "zhongshu_data",
                    "zhongshu_in_xianduan_data",
                    "xianduan_zhongshu_data",
                    "xianduan_zhongshu_another_data",
                    "volume_data",
                ]
            },
            "precision": 2,
        }

    monkeypatch.setattr(routes, "load_chart_payload", load)
    routes._build_lightweight_charts_page.cache_clear()
    routes._compress_lightweight_charts_page.cache_clear()
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1/test_api")
    app.mount("/static", StaticFiles(directory=str(app_dir / "static")), name="static")
    with TestClient(app) as client:
        yield client, engine, loads, app_dir
    routes._build_lightweight_charts_page.cache_clear()
    routes._compress_lightweight_charts_page.cache_clear()
    engine.dispose()


def widget(response):
    assert response.status_code == 200, response.text
    start = response.text.find('<section id="instrumentClassification"')
    assert start >= 0, "The current instrument must have a classification information section"
    end = response.text.index("</section>", start) + len("</section>")
    return response.text[start:end]


def get(client, symbol="300750SZ", **params):
    return client.get(URL, params={"symbol": symbol, "market": "cn", "asset_class": "stock", **params})


def test_chart_displays_industries_regions_and_all_concepts(chart_page):
    client, _, _, _ = chart_page
    html = widget(get(client))
    for value in ("电力设备", "电池", "锂电池", "福建", "锂电池概念", "储能概念", "11080003", "801730"):
        assert value in html
    assert 'data-state="ready"' in html
    assert "<details" not in html and "<summary" not in html
    assert "classification-concept-heading" in html
    assert 'data-instrument-id="1"' in html
    assert "instrument-classification.css?v=" in get(client).text


def test_switching_symbols_frequencies_and_asset_types_does_not_leak_labels(chart_page):
    client, engine, _, _ = chart_page
    assert "白酒概念" in widget(get(client, "600519SH"))
    html = widget(get(client))
    assert "储能概念" in html and "白酒概念" not in html
    assert "储能概念" in widget(get(client, frequency="1week"))
    with Session(engine) as session:
        session.add(
            models.InstrumentClassification(instrument_id=4, concepts=[concept(7, "不能给指数显示的标签")], regions=[])
        )
        session.commit()
    for market, asset_class in [("cn", "index"), ("us", "stock")]:
        html = widget(get(client, market=market, asset_class=asset_class))
        assert 'data-state="unsupported"' in html
        assert "储能概念" not in html and "不能给指数显示的标签" not in html


def test_uncollected_and_unregistered_instruments_are_explicit(chart_page):
    client, _, _, _ = chart_page
    html = widget(get(client, "000001SZ"))
    assert 'data-state="missing"' in html and "尚未采集" in html
    html = widget(get(client, "999999SH"))
    assert 'data-state="unregistered"' in html and "未登记" in html


def test_unknown_concepts_are_not_presented_as_empty(chart_page):
    client, engine, _, _ = chart_page
    with Session(engine) as session:
        row = session.get(models.InstrumentClassification, 1)
        row.concepts = row.regions = None
        row.sw_l2_code = row.sw_l2_name = None
        session.commit()
    html = widget(get(client))
    assert "概念数据缺失" in html and "地域数据缺失" in html
    assert "无有效概念" not in html and "二级暂无" in html
    with Session(engine) as session:
        row = session.get(models.InstrumentClassification, 1)
        row.concepts = row.regions = []
        session.commit()
    html = widget(get(client))
    assert "无有效概念" in html and "无有效地域标签" in html
    assert "概念数据缺失" not in html


def test_all_labels_are_visible_without_any_disclosure_or_preview(chart_page):
    client, engine, _, _ = chart_page
    with Session(engine) as session:
        row = session.get(models.InstrumentClassification, 1)
        row.concepts = [concept(10000000 + i, f"概念标签{i:02}") for i in range(80)]
        session.commit()
    html = widget(get(client))
    assert html.count("data-concept-code=") == 80
    assert "概念标签79" in html
    assert "<details" not in html and "<summary" not in html
    assert "展开全部" not in html and "收起" not in html
    assert "classification-preview" not in html and "hidden=" not in html


def test_source_text_and_tooltips_are_html_escaped(chart_page):
    client, engine, _, _ = chart_page
    malicious = '<img src=x onerror="alert(1)"> & </script>'
    with Session(engine) as session:
        row = session.get(models.InstrumentClassification, 1)
        label = concept('1" onmouseover="bad', malicious)
        label["paths"][0]["sub_class_name"] = malicious
        row.sw_l1_name = malicious
        row.concepts = row.regions = [label]
        session.commit()
    html = widget(get(client))
    assert "<img src=x" not in html and "</script>" not in html
    assert "&lt;img" in html and "&amp;" in html
    assert 'onmouseover="bad' not in html


def test_classification_updates_invalidate_etag_html_and_gzip_without_chart_changes(chart_page):
    client, engine, loads, _ = chart_page
    first = get(client)
    assert first.headers.get("content-encoding") == "gzip"
    old_etag = first.headers["etag"]
    unchanged = client.get(URL, params={"symbol": "300750SZ"}, headers={"If-None-Match": old_etag})
    assert unchanged.status_code == 304
    assert len(loads) == 1
    with Session(engine) as session:
        session.get(models.InstrumentClassification, 1).concepts = [concept(8, "新采集的概念")]
        session.commit()
    updated = client.get(URL, params={"symbol": "300750SZ"}, headers={"If-None-Match": old_etag})
    assert updated.status_code == 200 and updated.headers["etag"] != old_etag
    html = widget(updated)
    assert "新采集的概念" in html and "储能概念" not in html
    assert len(loads) == 2


def test_newly_collected_classification_replaces_cached_missing_state(chart_page):
    client, engine, _, _ = chart_page
    first = get(client, "000001SZ")
    with Session(engine) as session:
        session.add(
            models.InstrumentClassification(
                instrument_id=3, sw_l1_code="801780", sw_l1_name="申万银行", concepts=[], regions=[]
            )
        )
        session.commit()
    updated = client.get(URL, params={"symbol": "000001SZ"}, headers={"If-None-Match": first.headers["etag"]})
    assert updated.status_code == 200 and "银行" in widget(updated)
    assert 'data-state="ready"' in widget(updated)


def test_missing_classification_table_does_not_break_existing_charts(chart_page):
    client, engine, _, _ = chart_page
    models.InstrumentClassification.__table__.drop(engine)
    response = get(client)
    html = widget(response)
    assert 'data-state="unavailable"' in html and "尚未初始化" in html
    models.InstrumentClassification.__table__.create(engine)
    with Session(engine) as session:
        session.add(models.InstrumentClassification(instrument_id=1, concepts=[], regions=[]))
        session.commit()
    updated = client.get(URL, params={"symbol": "300750SZ"}, headers={"If-None-Match": response.headers["etag"]})
    assert updated.status_code == 200 and 'data-state="ready"' in widget(updated)


@pytest.mark.parametrize(
    "resource", ["templates/_instrument_classification.html", "static/css/instrument-classification.css", "templates/_chart_workspace.js", "templates/_frontend_requests.js", "templates/_screener_workspace.js", "templates/_chart_indicators.js"]
)
def test_component_updates_invalidate_page_and_asset_versions(chart_page, resource):
    client, _, _, app_dir = chart_page
    first = get(client)
    path = app_dir / resource
    assert path.is_file(), "The classification component and stylesheet must be shipped together"
    contents = path.read_text(encoding="utf-8")
    marker = "<!-- classification component revision -->" if path.suffix == ".html" else "/* revision */"
    path.write_text(contents + marker, encoding="utf-8")
    stamp = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(stamp, stamp))
    updated = client.get(URL, params={"symbol": "300750SZ"}, headers={"If-None-Match": first.headers["etag"]})
    assert updated.status_code == 200 and updated.headers["etag"] != first.headers["etag"]
    if path.suffix in {".html", ".js"}:
        assert marker in updated.text


def test_classification_stylesheet_is_served_from_same_origin(chart_page):
    client, _, _, _ = chart_page
    response = client.get("/static/css/instrument-classification.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert ".instrument-classification" in response.text
    assert "flex-wrap: wrap" in response.text
    assert "position: absolute" not in response.text
    assert "max-height:" not in response.text and "overflow: auto" not in response.text


def test_gunicorn_app_namespace_reuses_the_active_instrument_models(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(BACKEND), str(BACKEND.parents[2])))
    env["LOG_FILE"] = str(tmp_path / "namespace.log")
    probe = (
        "import app.db.models as models; "
        "import app.classification_view as view; "
        "assert view.Instrument is models.Instrument; "
        "assert view.InstrumentClassification is models.InstrumentClassification"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
