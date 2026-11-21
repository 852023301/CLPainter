"""Validated metadata receipts and reversible cleanup of current runtime files."""

import hashlib
import json
import os
import re
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db.models import Instrument

CODE = re.compile(r"[A-Za-z0-9_-]{1,16}")
NAMESPACE = re.compile(r"[A-Za-z0-9_-]+")


def managed_roots(config) -> dict[str, Path]:
    root = Path(config.DATA_DIR).parent.resolve()
    if root == Path("/"):
        raise ValueError("Refusing a filesystem-root data directory")
    environment = config.APP_ENV.strip().lower()
    if environment == "test" and root.name != "data_set_dev":
        raise ValueError("Test cleanup requires data_set_dev")
    if environment == "production" and root.name != "data_set":
        raise ValueError("Production cleanup requires data_set")
    if environment == "development" and root.name == "data_set":
        raise ValueError("Production data requires an explicit production environment")
    if environment not in {"test", "production", "development"}:
        raise ValueError("Unknown cleanup environment")
    roots = {
        "source": Path(config.DATA_DIR),
        "curated": Path(config.CACHE_DUMP_DIR),
        "chart_payload": Path(config.CACHE_DUMP_DIR).parent / "chart_payload",
    }
    old = Path(config.OLD_DATA_DIR).resolve()
    database = Path(config.DB_PATH).resolve()
    quarantine = root / "quarantine"
    if quarantine == old or quarantine in old.parents or old in quarantine.parents or quarantine in database.parents:
        raise ValueError("Quarantine overlaps historical data or the database")
    if root not in database.parents:
        raise ValueError("Database is outside the configured data root")
    for name, path in roots.items():
        if path.is_symlink():
            raise ValueError("Managed roots cannot be symlinks")
        roots[name] = path.resolve()
        if roots[name] == quarantine or roots[name] in quarantine.parents or quarantine in roots[name].parents:
            raise ValueError("Quarantine must be outside every managed scan root")
        if (
            root not in roots[name].parents
            or roots[name] == old
            or old in roots[name].parents
            or roots[name] in old.parents
        ):
            raise ValueError("Unsafe or historical cleanup root")
    values = list(roots.values())
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(values) for b in values[i + 1 :]):
        raise ValueError("Managed cleanup roots overlap")
    return roots


def resolve_processing_date(value: str | None = None, *, now: datetime | None = None, calendar_loader=None) -> date:
    clock = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    if clock.tzinfo is None:
        raise ValueError("Processing clock requires a timezone")
    clock = clock.astimezone(ZoneInfo("Asia/Shanghai"))
    latest = clock.date() if clock.hour >= 16 else clock.date() - timedelta(days=1)
    candidate = date.fromisoformat(value) if value else latest
    if candidate > latest:
        raise ValueError("The requested data day is not yet eligible for a complete batch")
    if calendar_loader is None:
        from ddp.util import get_trade_calendar

        calendar_loader = get_trade_calendar
    days = calendar_loader(end=candidate.isoformat(), length=1, out="list", secumarket="CN")
    if not days:
        raise ValueError("DDP calendar did not confirm a completed trading day")
    text = str(days[-1])
    selected = (
        datetime.strptime(text, "%Y%m%d").date() if len(text) == 8 and text.isdigit() else date.fromisoformat(text[:10])
    )
    if selected > candidate or (value and selected != candidate):
        raise ValueError("The requested processing date is not a confirmed trading day")
    return selected


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _scope_codes(database_engine, scopes: list[tuple[str, str]]) -> list[dict]:
    if not scopes or len(set(scopes)) != len(scopes):
        raise ValueError("Metadata scopes must be explicit and unique")
    result = []
    with Session(database_engine) as session:
        for market, asset in scopes:
            if not NAMESPACE.fullmatch(market) or not NAMESPACE.fullmatch(asset):
                raise ValueError("Invalid metadata namespace")
            codes = session.scalars(
                select(Instrument.code)
                .where(Instrument.market == market, Instrument.asset_class == asset)
                .order_by(Instrument.code)
            ).all()
            if not codes or len(codes) != len(set(codes)) or any(not CODE.fullmatch(code) for code in codes):
                raise ValueError("Metadata scope is empty or contains invalid identities")
            result.append({"market": market, "asset_class": asset, "codes": codes})
    return result


def write_metadata_report(path: Path, config, database_engine, as_of: date, scopes: list[tuple[str, str]]) -> None:
    roots = managed_roots(config)
    target = Path(path).absolute()
    if target.suffix != ".json" or target.is_symlink():
        raise ValueError("Metadata report must be a regular JSON path")
    resolved = target.resolve()
    protected = [*roots.values(), Path(config.OLD_DATA_DIR).resolve()]
    if resolved == Path(config.DB_PATH).resolve() or any(
        resolved == directory or directory in resolved.parents for directory in protected
    ):
        raise ValueError("Metadata report cannot overwrite runtime data")
    payload = {
        "schema_version": 1,
        "complete": True,
        "as_of": as_of.isoformat(),
        "data_root": str(Path(config.DATA_DIR).parent.resolve()),
        "database": str(Path(config.DB_PATH).resolve()),
        "scopes": _scope_codes(database_engine, scopes),
    }
    _atomic_json(target, payload)


def validate_metadata_report(path: Path, config, database_engine, *, expected_digest: str | None = None) -> dict:
    managed_roots(config)
    if not Path(config.DB_PATH).is_file():
        raise ValueError("Metadata database is missing; cleanup must not create a database")
    content = Path(path).read_bytes()
    if expected_digest is not None and hashlib.sha256(content).hexdigest() != expected_digest:
        raise ValueError("Metadata report changed after planning")
    payload = json.loads(content.decode("utf-8"))
    if payload.get("schema_version") != 1 or payload.get("complete") is not True:
        raise ValueError("Metadata report does not represent a complete sync")
    if payload.get("data_root") != str(Path(config.DATA_DIR).parent.resolve()) or payload.get("database") != str(
        Path(config.DB_PATH).resolve()
    ):
        raise ValueError("Metadata report belongs to a different data root or database")
    day = date.fromisoformat(payload["as_of"])
    if day > datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("Metadata report has a future processing date")
    scopes = [(item["market"], item["asset_class"]) for item in payload.get("scopes", [])]
    if _scope_codes(database_engine, scopes) != payload["scopes"]:
        raise ValueError("Metadata has changed or the report is incomplete; resync before cleanup")
    return payload


def batch_date_from_report(path: Path | None, config, database_engine) -> date | None:
    return date.fromisoformat(validate_metadata_report(path, config, database_engine)["as_of"]) if path else None


def require_processing_data_date(values, expected: date | None) -> None:
    """A successful fetch must actually include the requested batch date."""
    if expected is None:
        return
    days = [
        value.date()
        if isinstance(value, datetime)
        else value
        if isinstance(value, date)
        else date.fromisoformat(str(value)[:10])
        for value in values
    ]
    if not days or max(days) != expected:
        raise ValueError("上游行情没有完整到达本批处理日期，停止后续聚合和归档")


def _file_identity(relative: str, root_name: str) -> tuple[str, str, str]:
    path = PurePosixPath(relative)
    if path.is_absolute() or len(path.parts) != 4 or any(part in {".", ".."} for part in path.parts):
        raise ValueError("Noncanonical runtime file path")
    frequency, market, asset, filename = path.parts
    if (
        not frequency.startswith("freq=")
        or not NAMESPACE.fullmatch(frequency[5:])
        or not market.startswith("market=")
        or not asset.startswith("asset_class=")
    ):
        raise ValueError("Unknown runtime namespace")
    suffix = ".chart.pkl" if root_name == "chart_payload" else ".pkl"
    if not filename.endswith(suffix):
        raise ValueError("Unknown runtime filename")
    code = filename[: -len(suffix)]
    if not CODE.fullmatch(code):
        raise ValueError("Unknown instrument filename")
    return market[7:], asset[12:], code


def _no_symlinks(path: Path, anchor: Path) -> None:
    relative = path.relative_to(anchor)
    current = anchor
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlinked data paths are not managed by cleanup")


def _fingerprint(path: Path) -> dict:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("File changed during inspection")
    return {"size": after.st_size, "mtime_ns": after.st_mtime_ns, "sha256": digest.hexdigest()}


def plan_cleanup(config, database_engine, report_path: Path, *, max_orphan_ratio: float = 0.2) -> dict:
    if not 0 <= max_orphan_ratio <= 1:
        raise ValueError("Candidate ratio must be between zero and one")
    roots = managed_roots(config)
    report_digest = hashlib.sha256(Path(report_path).read_bytes()).hexdigest()
    report = validate_metadata_report(report_path, config, database_engine, expected_digest=report_digest)
    allowed = {(item["market"], item["asset_class"]): set(item["codes"]) for item in report["scopes"]}
    files = []
    skipped = []
    total = Counter()
    stale = Counter()
    for root_name, directory in roots.items():
        if not directory.exists():
            continue
        for path in sorted(directory.glob("freq=*/market=*/asset_class=*/*")):
            relative = path.relative_to(directory).as_posix()
            try:
                _no_symlinks(path, directory)
                identity = _file_identity(relative, root_name)
            except ValueError:
                skipped.append(str(path))
                continue
            if not path.is_file() or identity[:2] not in allowed:
                continue
            namespace = (root_name, *identity[:2])
            total[namespace] += 1
            if identity[2] not in allowed[identity[:2]]:
                stale[namespace] += 1
                files.append(
                    {
                        "root": root_name,
                        "relative": relative,
                        "identity": list(identity),
                        "fingerprint": _fingerprint(path),
                    }
                )
    if any(count / total[namespace] > max_orphan_ratio for namespace, count in stale.items()):
        raise ValueError("Candidate ratio exceeds the cleanup safety threshold; review metadata first")
    return {
        "schema_version": 1,
        "as_of": report["as_of"],
        "data_root": report["data_root"],
        "roots": {name: str(path) for name, path in roots.items()},
        "metadata_report": str(Path(report_path).resolve()),
        "metadata_sha256": report_digest,
        "files": files,
        "skipped": skipped,
        "max_orphan_ratio": max_orphan_ratio,
    }


@contextmanager
def _cleanup_lock(root: Path):
    import fcntl

    path = root / ".data-cleanup.lock"
    if path.is_symlink():
        raise ValueError("Unsafe cleanup lock path")
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _validate_entries(plan: dict, config) -> dict[str, Path]:
    roots = managed_roots(config)
    if (
        plan.get("schema_version") != 1
        or plan.get("data_root") != str(Path(config.DATA_DIR).parent.resolve())
        or plan.get("roots") != {key: str(value) for key, value in roots.items()}
    ):
        raise ValueError("Cleanup manifest belongs to different configured roots")
    seen = set()
    for entry in plan["files"]:
        if entry["root"] not in roots:
            raise ValueError("Unknown cleanup root")
        if list(_file_identity(entry["relative"], entry["root"])) != entry["identity"]:
            raise ValueError("Manifest identity does not match its path")
        key = (entry["root"], entry["relative"])
        if key in seen:
            raise ValueError("Duplicate manifest path")
        seen.add(key)
        _no_symlinks(roots[entry["root"]] / entry["relative"], roots[entry["root"]])
    return roots


def apply_cleanup(plan: dict, config, database_engine) -> Path | None:
    roots = _validate_entries(plan, config)
    report_path = Path(plan["metadata_report"])
    if hashlib.sha256(report_path.read_bytes()).hexdigest() != plan["metadata_sha256"]:
        raise ValueError("Metadata report changed after planning")
    validate_metadata_report(report_path, config, database_engine, expected_digest=plan["metadata_sha256"])
    if not plan["files"]:
        return None
    root = Path(plan["data_root"])
    quarantine = root / "quarantine"
    if quarantine.is_symlink():
        raise ValueError("Quarantine cannot be a symlink")
    with _cleanup_lock(root):
        metadata = validate_metadata_report(
            report_path, config, database_engine, expected_digest=plan["metadata_sha256"]
        )
        if plan["as_of"] != metadata["as_of"]:
            raise ValueError("Cleanup processing date changed after planning")
        allowed = {(item["market"], item["asset_class"]): set(item["codes"]) for item in metadata["scopes"]}
        for entry in plan["files"]:
            identity = _file_identity(entry["relative"], entry["root"])
            if identity[:2] not in allowed or identity[2] in allowed[identity[:2]]:
                raise ValueError("A cleanup candidate is valid or outside the synced metadata scope")
            source = roots[entry["root"]] / entry["relative"]
            if source.is_symlink() or _fingerprint(source) != entry["fingerprint"]:
                raise ValueError("Runtime file changed after planning")
            if source.stat().st_dev != root.stat().st_dev:
                raise ValueError("Quarantine must share the source filesystem")
        batch = quarantine / (
            "cleanup-" + datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        )
        batch.mkdir(parents=True, mode=0o700)
        _atomic_json(batch / "metadata.json", metadata)
        manifest = batch / "manifest.json"
        payload = {**plan, "state": "planned"}
        _atomic_json(manifest, payload)
        try:
            for entry in plan["files"]:
                source = roots[entry["root"]] / entry["relative"]
                _no_symlinks(source, roots[entry["root"]])
                if _fingerprint(source) != entry["fingerprint"]:
                    raise ValueError("Runtime file changed during cleanup")
                destination = batch / entry["root"] / entry["relative"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() or destination.is_symlink():
                    raise FileExistsError(destination)
                os.rename(source, destination)
                entry["moved"] = True
                _atomic_json(manifest, payload)
        except (OSError, ValueError):
            payload["state"] = "partial"
            _atomic_json(manifest, payload)
            raise
        payload["state"] = "quarantined"
        _atomic_json(manifest, payload)
        return manifest


def restore_cleanup(manifest: Path, config) -> dict:
    manifest = Path(manifest).absolute()
    quarantine = Path(config.DATA_DIR).parent.resolve() / "quarantine"
    if quarantine not in manifest.resolve().parents or manifest.is_symlink() or manifest.name != "manifest.json":
        raise ValueError("Restore requires a manifest within the configured quarantine")
    _no_symlinks(manifest, quarantine)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    roots = _validate_entries(payload, config)
    batch = manifest.parent
    pending = []
    with _cleanup_lock(Path(payload["data_root"])):
        for entry in payload["files"]:
            source = roots[entry["root"]] / entry["relative"]
            stored = batch / entry["root"] / entry["relative"]
            _no_symlinks(stored, batch)
            if stored.exists():
                if source.exists() or source.is_symlink():
                    raise FileExistsError(source)
                if _fingerprint(stored) != entry["fingerprint"]:
                    raise ValueError("Quarantined file fingerprint mismatch")
                pending.append((stored, source))
            elif not source.is_file() or _fingerprint(source) != entry["fingerprint"]:
                raise ValueError("A manifest file is missing or has changed")
        for stored, source in pending:
            source.parent.mkdir(parents=True, exist_ok=True)
            os.rename(stored, source)
        payload["state"] = "restored"
        _atomic_json(manifest, payload)
    return {"restored": len(pending)}
