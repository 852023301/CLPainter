"""Minimal runtime-file cleanup, exercised only under temporary directories."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data_set_dev"
    config = SimpleNamespace(
        DATA_DIR=str(root / "pv_data"),
        CACHE_DUMP_DIR=str(root / "dump/curated"),
        OLD_DATA_DIR=str(root / "old_pv_data"),
    )
    identities = {("cn", "stock", "KEEP"), ("cn", "fund", "FUND"), ("cn", "index", "INDEX")}
    kept = []
    stale = []
    for name, directory in [
        ("source", Path(config.DATA_DIR)),
        ("curated", Path(config.CACHE_DUMP_DIR)),
        ("chart_payload", Path(config.CACHE_DUMP_DIR).parent / "chart_payload"),
    ]:
        for frequency in ["1day", "1week", "1month", "1quarter", "1year"]:
            for market, asset_class, valid_code in sorted(identities):
                folder = directory / ("freq=" + frequency) / ("market=" + market) / ("asset_class=" + asset_class)
                folder.mkdir(parents=True)
                suffix = ".chart.pkl" if name == "chart_payload" else ".pkl"
                for code, group in [(valid_code, kept), ("OLD", stale)]:
                    path = folder / (code + suffix)
                    path.write_bytes((name + frequency + asset_class + code).encode())
                    group.append(path)
    module = importlib.import_module("CLPainter.web.backend.scripts.maintenance.cleanup_stale_data")
    return module, config, identities, root, kept, stale


def test_preview_is_read_only_and_checks_all_three_directories(data):
    module, config, identities, root, kept, stale = data
    before = set(root.rglob("*"))
    result = module.cleanup_files(config, identities)
    assert result["mode"] == "dry-run" and result["count"] == 45
    assert set(result["files"]) == {str(path) for path in stale}
    assert all(path.exists() for path in kept + stale)
    assert set(root.rglob("*")) == before


def test_apply_deletes_only_orphans_without_creating_backups_or_logs(data):
    module, config, identities, root, kept, stale = data
    before = set(root.rglob("*"))
    content = {path: path.read_bytes() for path in kept}
    result = module.cleanup_files(config, identities, apply=True)
    assert result["mode"] == "delete" and result["count"] == 45
    assert set(result["files"]) == {str(path) for path in stale}
    assert all(not path.exists() for path in stale)
    assert all(path.read_bytes() == content[path] for path in kept)
    assert set(root.rglob("*")) == before - set(stale)
    assert module.cleanup_files(config, identities, apply=True)["count"] == 0


def test_valid_cache_is_kept_without_a_source_and_other_scopes_are_untouched(data, tmp_path):
    module, config, identities, _root, kept, _stale = data
    for path in kept:
        if Path(config.DATA_DIR) in path.parents:
            path.unlink()
    foreign = Path(config.DATA_DIR) / "freq=1day/market=hk/asset_class=stock/OTHER.pkl"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"foreign")
    historical = Path(config.OLD_DATA_DIR) / "history.pkl"
    historical.parent.mkdir(parents=True)
    historical.write_bytes(b"keep history")
    outside = tmp_path / "outside.pkl"
    outside.write_bytes(b"outside")
    linked = Path(config.DATA_DIR) / "freq=1day/market=cn/asset_class=stock/LINK.pkl"
    linked.symlink_to(outside)
    unknown = linked.with_name("unknown.name.pkl")
    unknown.write_bytes(b"unknown")
    external = tmp_path / "external/market=cn/asset_class=fund/ORPHAN.pkl"
    external.parent.mkdir(parents=True)
    external.write_bytes(b"external")
    (Path(config.DATA_DIR) / "freq=linked").symlink_to(tmp_path / "external", target_is_directory=True)
    module.cleanup_files(config, identities, apply=True)
    assert foreign.read_bytes() == b"foreign" and historical.read_bytes() == b"keep history"
    assert linked.is_symlink() and outside.read_bytes() == b"outside"
    assert unknown.read_bytes() == b"unknown" and external.read_bytes() == b"external"
    assert all(path.exists() for path in kept if Path(config.DATA_DIR) not in path.parents)


def test_identity_includes_market_and_asset_class(data):
    module, config, identities, _root, _kept, stale = data
    identities.add(("cn", "fund", "OLD"))
    identities.add(("hk", "stock", "OLD"))
    result = module.cleanup_files(config, identities)
    assert result["count"] == 30
    assert set(result["files"]) == {str(path) for path in stale if path.parent.name != "asset_class=fund"}


@pytest.mark.parametrize("present_scopes", [set(), {("cn", "stock")}, {("cn", "stock"), ("cn", "index")}])
def test_empty_or_incomplete_metadata_refuses_cleanup(data, present_scopes):
    module, config, identities, root, kept, stale = data
    before = set(root.rglob("*"))
    incomplete = {identity for identity in identities if identity[:2] in present_scopes}
    with pytest.raises(ValueError):
        module.cleanup_files(config, incomplete, apply=True)
    assert all(path.exists() for path in kept + stale)
    assert set(root.rglob("*")) == before


@pytest.mark.parametrize("invalid_path", ["outside", "source_overlap", "history_overlap", "symlink"])
def test_managed_paths_must_stay_inside_the_data_root_without_overlap(data, tmp_path, invalid_path):
    module, config, identities, root, kept, stale = data
    if invalid_path == "outside":
        config.CACHE_DUMP_DIR = str(tmp_path / "outside/curated")
    elif invalid_path == "source_overlap":
        config.CACHE_DUMP_DIR = config.DATA_DIR
    elif invalid_path == "history_overlap":
        config.OLD_DATA_DIR = config.DATA_DIR
    else:
        alias = root / "linked-curated"
        alias.symlink_to(config.CACHE_DUMP_DIR, target_is_directory=True)
        config.CACHE_DUMP_DIR = str(alias)
    before = set(root.rglob("*"))
    with pytest.raises(ValueError):
        module.cleanup_files(config, identities, apply=True)
    assert all(path.exists() for path in kept + stale)
    assert set(root.rglob("*")) == before


@pytest.mark.parametrize("apply", [False, True])
def test_cli_reads_instrument_without_a_metadata_report(data, monkeypatch, capsys, apply):
    from CLPainter.web.backend.app.db.models import Instrument
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    module, config, identities, root, kept, stale = data
    engine = create_engine(f"sqlite:///{root / 'instrument.db'}")
    try:
        Instrument.__table__.create(engine)
        with Session(engine) as session:
            session.add_all(
                Instrument(market=market, asset_class=asset_class, code=code, name=code)
                for market, asset_class, code in identities
            )
            session.commit()
        monkeypatch.setattr(importlib.import_module("CLPainter.web.backend.app._config.settings"), "settings", config)
        monkeypatch.setattr(importlib.import_module("CLPainter.web.backend.app.db.base"), "engine", engine)
        assert module.main(["--apply"] if apply else []) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["mode"] == ("delete" if apply else "dry-run") and result["count"] == 45
        assert all(path.exists() for path in kept)
        assert all(path.exists() != apply for path in stale)
        with Session(engine) as session:
            assert set(session.execute(select(Instrument.market, Instrument.asset_class, Instrument.code))) == identities
    finally:
        engine.dispose()


def test_delete_stops_at_first_error_and_keeps_remaining_files(data, monkeypatch):
    module, config, identities, root, kept, _stale = data
    before = set(root.rglob("*"))
    unlink = Path.unlink
    attempted = []

    def fail_second_delete(path):
        attempted.append(path)
        if len(attempted) == 2:
            raise PermissionError("simulated delete failure")
        return unlink(path)

    monkeypatch.setattr(Path, "unlink", fail_second_delete)
    with pytest.raises(PermissionError, match="simulated delete failure"):
        module.cleanup_files(config, identities, apply=True)
    assert len(attempted) == 2
    assert not attempted[0].exists() and attempted[1].exists()
    assert all(path.exists() for path in kept)
    assert set(root.rglob("*")) == before - {attempted[0]}
