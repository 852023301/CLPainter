"""Data cleanup never touches live paths: all fixtures are under tmp_path."""

import importlib
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from CLPainter.web.backend.app.db.base import Base
from CLPainter.web.backend.app.db.models import Instrument
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def lifecycle():
    return importlib.import_module("CLPainter.web.backend.app.data_lifecycle")


@pytest.fixture
def cleanup_env(tmp_path):
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
        for code in ["KEEP0", "KEEP1", "KEEP2", "KEEP3", "KEEP4"]:
            session.add(Instrument(code=code, name=code, display_name=code, market="cn", asset_class="stock"))
        session.add(Instrument(code="ETF0", name="ETF0", display_name="ETF0", market="cn", asset_class="fund"))
        session.commit()
    yield config, engine, root
    engine.dispose()


def metadata_report(config, engine, root, scopes=None):
    path = root / "reports/metadata.json"
    lifecycle().write_metadata_report(
        path, config, engine, date(2026, 11, 20), scopes or [("cn", "stock"), ("cn", "fund")]
    )
    return path


def populate(config, root):
    roots = {
        "source": Path(config.DATA_DIR),
        "curated": Path(config.CACHE_DUMP_DIR),
        "chart_payload": Path(config.CACHE_DUMP_DIR).parent / "chart_payload",
    }
    stale = []
    kept = []
    for label, directory in roots.items():
        for frequency in ["1day", "1week", "1month", "1quarter", "1year"]:
            folder = directory / ("freq=" + frequency) / "market=cn" / "asset_class=stock"
            folder.mkdir(parents=True)
            suffix = ".chart.pkl" if label == "chart_payload" else ".pkl"
            for code in ["KEEP0", "KEEP1", "KEEP2", "KEEP3", "KEEP4", "OLD"]:
                path = folder / (code + suffix)
                path.write_bytes((label + frequency + code).encode())
                (stale if code == "OLD" else kept).append(path)
    return stale, kept


def test_dry_run_plans_all_three_roots_without_mutating_files(cleanup_env):
    config, engine, root = cleanup_env
    stale, kept = populate(config, root)
    report = metadata_report(config, engine, root)
    plan = lifecycle().plan_cleanup(config, engine, report)
    assert len(plan["files"]) == 15
    assert {item["root"] for item in plan["files"]} == {"source", "curated", "chart_payload"}
    assert all(path.is_file() for path in stale + kept)
    assert not (root / "quarantine").exists()


def test_apply_quarantines_and_restore_is_lossless(cleanup_env):
    config, engine, root = cleanup_env
    stale, kept = populate(config, root)
    contents = {str(path): path.read_bytes() for path in stale + kept}
    report = metadata_report(config, engine, root)
    manifest = lifecycle().apply_cleanup(lifecycle().plan_cleanup(config, engine, report), config, engine)
    assert manifest.is_file() and root / "quarantine" in manifest.parents
    assert all(not path.exists() for path in stale)
    assert all(path.read_bytes() == contents[str(path)] for path in kept)
    assert lifecycle().restore_cleanup(manifest, config)["restored"] == len(stale)
    assert all(path.read_bytes() == contents[str(path)] for path in stale + kept)
    assert lifecycle().restore_cleanup(manifest, config)["restored"] == 0


def test_valid_cache_is_kept_when_its_source_is_missing(cleanup_env):
    config, engine, root = cleanup_env
    path = Path(config.CACHE_DUMP_DIR) / "freq=1day/market=cn/asset_class=stock/KEEP0.pkl"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"accepted-reference")
    report = metadata_report(config, engine, root)
    assert lifecycle().plan_cleanup(config, engine, report)["files"] == []
    assert path.read_bytes() == b"accepted-reference"


def test_scope_filename_and_symlink_boundaries(cleanup_env, tmp_path):
    config, engine, root = cleanup_env
    report = metadata_report(config, engine, root, [("cn", "stock")])
    base = Path(config.DATA_DIR)
    excluded = []
    for relative in [
        "freq=1day/market=hk/asset_class=stock/OTHER.pkl",
        "freq=1day/market=cn/asset_class=fund/OTHER.pkl",
        "freq=1day/market=cn/asset_class=stock/note.txt",
        "freq=1day/market=cn/asset_class=stock/BAD.chart.pkl",
    ]:
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"keep")
        excluded.append(path)
    external = tmp_path / "outside.pkl"
    external.write_bytes(b"outside")
    symbolic = base / "freq=1day/market=cn/asset_class=stock/LINK.pkl"
    symbolic.symlink_to(external)
    old = Path(config.OLD_DATA_DIR) / "freq=1day/market=cn/asset_class=stock/OLD.pkl"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"historical")
    plan = lifecycle().plan_cleanup(config, engine, report)
    assert plan["files"] == []
    assert symbolic.is_symlink() and external.read_bytes() == b"outside"
    assert all(path.is_file() for path in excluded + [old])


@pytest.mark.parametrize("mutation", ["incomplete", "wrong_root", "wrong_date", "empty_scope", "codes_changed"])
def test_invalid_or_stale_metadata_receipts_block_cleanup(cleanup_env, mutation):
    config, engine, root = cleanup_env
    report = metadata_report(config, engine, root)
    payload = json.loads(report.read_text())
    if mutation == "incomplete":
        payload["complete"] = False
    elif mutation == "wrong_root":
        payload["data_root"] = "/somewhere/else"
    elif mutation == "wrong_date":
        payload["as_of"] = "not-a-date"
    elif mutation == "empty_scope":
        payload["scopes"] = []
    else:
        payload["scopes"][0]["codes"] = []
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        lifecycle().plan_cleanup(config, engine, report)
    assert not (root / "quarantine").exists()


def test_changed_data_after_plan_is_not_moved(cleanup_env):
    config, engine, root = cleanup_env
    stale, kept = populate(config, root)
    report = metadata_report(config, engine, root)
    plan = lifecycle().plan_cleanup(config, engine, report)
    stale[-1].write_bytes(b"new data written by another producer")
    with pytest.raises(ValueError):
        lifecycle().apply_cleanup(plan, config, engine)
    assert all(path.is_file() for path in stale + kept)


def test_large_candidate_ratio_is_refused(cleanup_env):
    config, engine, root = cleanup_env
    path = Path(config.DATA_DIR) / "freq=1day/market=cn/asset_class=stock/OLD.pkl"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old")
    report = metadata_report(config, engine, root)
    with pytest.raises(ValueError):
        lifecycle().plan_cleanup(config, engine, report)
    assert path.exists()


def test_restore_does_not_overwrite_new_source_data(cleanup_env):
    config, engine, root = cleanup_env
    stale, _kept = populate(config, root)
    report = metadata_report(config, engine, root)
    manifest = lifecycle().apply_cleanup(lifecycle().plan_cleanup(config, engine, report), config, engine)
    stale[0].write_bytes(b"new source")
    with pytest.raises(FileExistsError):
        lifecycle().restore_cleanup(manifest, config)
    assert stale[0].read_bytes() == b"new source"


def test_partial_move_failure_keeps_a_recoverable_manifest(cleanup_env, monkeypatch):
    config, engine, root = cleanup_env
    stale, kept = populate(config, root)
    report = metadata_report(config, engine, root)
    plan = lifecycle().plan_cleanup(config, engine, report)
    original = lifecycle().os.rename
    count = 0

    def rename(source, destination):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("simulated filesystem failure")
        return original(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle().os, "rename", rename)
        with pytest.raises(OSError):
            lifecycle().apply_cleanup(plan, config, engine)
    manifests = list((root / "quarantine").glob("*/manifest.json"))
    assert len(manifests) == 1
    assert lifecycle().restore_cleanup(manifests[0], config)["restored"] == 1
    assert all(path.exists() for path in stale + kept)


def test_next_morning_processing_date_uses_previous_completed_trade_day():
    calls = []

    def calendar(**kwargs):
        calls.append(kwargs)
        return ["2026-11-20"]

    result = lifecycle().resolve_processing_date(
        now=datetime(2026, 11, 21, 9, tzinfo=ZoneInfo("Asia/Shanghai")), calendar_loader=calendar
    )
    assert result == date(2026, 11, 20)
    assert calls[0]["end"] == "2026-11-20" and calls[0]["secumarket"] == "CN"


def test_metadata_changed_after_plan_prevents_moving_newly_valid_data(cleanup_env):
    config, engine, root = cleanup_env
    stale, kept = populate(config, root)
    report = metadata_report(config, engine, root)
    plan = lifecycle().plan_cleanup(config, engine, report)
    with Session(engine) as session:
        session.add(Instrument(code="OLD", name="now valid", market="cn", asset_class="stock"))
        session.commit()
    with pytest.raises(ValueError):
        lifecycle().apply_cleanup(plan, config, engine)
    assert all(path.exists() for path in stale + kept)


def test_restore_survives_deleted_temporary_metadata_receipt(cleanup_env):
    config, engine, root = cleanup_env
    stale, _ = populate(config, root)
    report = metadata_report(config, engine, root)
    manifest = lifecycle().apply_cleanup(lifecycle().plan_cleanup(config, engine, report), config, engine)
    assert (manifest.parent / "metadata.json").read_bytes() == report.read_bytes()
    report.unlink()
    assert lifecycle().restore_cleanup(manifest, config)["restored"] == len(stale)


def test_manifest_cannot_restore_outside_owned_roots(cleanup_env):
    config, engine, root = cleanup_env
    populate(config, root)
    report = metadata_report(config, engine, root)
    manifest = lifecycle().apply_cleanup(lifecycle().plan_cleanup(config, engine, report), config, engine)
    payload = json.loads(manifest.read_text())
    payload["files"][0]["relative"] = "../../instrument.db"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        lifecycle().restore_cleanup(manifest, config)
    assert Path(config.DB_PATH).is_file()


def test_cli_defaults_to_dry_run_and_supports_explicit_apply_restore(cleanup_env):
    import os
    import subprocess
    import sys

    config, engine, root = cleanup_env
    stale, kept = populate(config, root)
    report = metadata_report(config, engine, root)
    env = os.environ.copy()
    env.update({key: str(value) for key, value in vars(config).items()})
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    script = Path(__file__).resolve().parents[1] / "scripts/maintenance/cleanup_stale_data.py"

    def run(*args):
        result = subprocess.run(
            [sys.executable, str(script), *args], env=env, capture_output=True, text=True, timeout=30, check=False
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    preview = run("--metadata-report", str(report))
    assert preview["mode"] == "dry-run" and preview["count"] == 15
    assert all(path.exists() for path in stale + kept)
    applied = run("--metadata-report", str(report), "--apply")
    assert applied["mode"] == "quarantine" and all(not path.exists() for path in stale)
    restored = run("--restore", applied["manifest"])
    assert restored["restored"] == 15 and all(path.exists() for path in stale + kept)


def test_even_a_rebound_plan_cannot_move_a_currently_valid_instrument(cleanup_env):
    import hashlib

    config, engine, root = cleanup_env
    stale, kept = populate(config, root)
    report = metadata_report(config, engine, root)
    plan = lifecycle().plan_cleanup(config, engine, report)
    with Session(engine) as session:
        session.add(Instrument(code="OLD", name="now valid", market="cn", asset_class="stock"))
        session.commit()
    metadata_report(config, engine, root)
    plan["metadata_sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        lifecycle().apply_cleanup(plan, config, engine)
    assert all(path.exists() for path in stale + kept)


def test_dry_run_does_not_create_a_missing_database(cleanup_env):
    config, engine, root = cleanup_env
    report = metadata_report(config, engine, root)
    engine.dispose()
    Path(config.DB_PATH).unlink()
    with pytest.raises(ValueError):
        lifecycle().plan_cleanup(config, engine, report)
    assert not Path(config.DB_PATH).exists()


def test_production_configuration_cannot_target_the_test_root(cleanup_env):
    config, engine, root = cleanup_env
    report = metadata_report(config, engine, root)
    config.APP_ENV = "production"
    with pytest.raises(ValueError):
        lifecycle().plan_cleanup(config, engine, report)
    assert not (root / "quarantine").exists()


@pytest.mark.parametrize("values", [[], ["2026-11-19"], ["2026-11-21"]])
def test_stale_or_future_fetches_cannot_be_treated_as_the_requested_batch(values):
    with pytest.raises(ValueError):
        lifecycle().require_processing_data_date(values, date(2026, 11, 20))


def test_quarantine_cannot_overlap_the_source_scan_root(cleanup_env):
    config, _engine, root = cleanup_env
    config.DATA_DIR = str(root / "quarantine")
    with pytest.raises(ValueError):
        lifecycle().managed_roots(config)


def test_quarantine_cannot_be_the_historical_data_directory(cleanup_env):
    config, _engine, root = cleanup_env
    config.OLD_DATA_DIR = str(root / "quarantine")
    with pytest.raises(ValueError):
        lifecycle().managed_roots(config)
