"""Preview or quarantine runtime files absent from current instrument metadata."""

import argparse
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR.parent.parent.parent))

SCOPES = {("cn", "stock"), ("cn", "fund"), ("cn", "index")}


def cleanup_files(config, identities: set[tuple[str, str, str]], *, apply: bool = False) -> dict:
    """Only unregistered identities are stale; a missing source is not a reason to delete a valid cache."""
    if not SCOPES <= {identity[:2] for identity in identities}:
        raise ValueError("元数据范围不完整或为空，拒绝清理")
    data_root = Path(config.DATA_DIR).parent.resolve()
    roots = {
        "source": Path(config.DATA_DIR),
        "curated": Path(config.CACHE_DUMP_DIR),
        "chart_payload": Path(config.CACHE_DUMP_DIR).parent / "chart_payload",
    }
    if data_root == Path("/") or any(path.is_symlink() for path in roots.values()):
        raise ValueError("不允许使用根目录或符号链接作为清理根")
    roots = {name: path.resolve() for name, path in roots.items()}
    if any(data_root not in path.parents for path in roots.values()):
        raise ValueError("清理目录必须位于同一数据根下")
    quarantine = data_root / "quarantine"
    protected = [*roots.values(), Path(config.OLD_DATA_DIR).resolve(), quarantine]
    if quarantine.is_symlink() or any(
        a == b or a in b.parents or b in a.parents for i, a in enumerate(protected) for b in protected[i + 1 :]
    ):
        raise ValueError("清理、历史数据和隔离目录不能重叠")
    candidates = []
    for name, directory in roots.items():
        suffix = ".chart.pkl" if name == "chart_payload" else ".pkl"
        for path in sorted(directory.glob("freq=*/market=*/asset_class=*/*")):
            relative = path.relative_to(directory)
            if path.is_symlink() or any((directory / parent).is_symlink() for parent in relative.parents):
                continue
            if not path.is_file() or not path.name.endswith(suffix):
                continue
            code = path.name[: -len(suffix)]
            if not re.fullmatch(r"[A-Za-z0-9_-]+", code):
                continue
            scope = (path.parent.parent.name.removeprefix("market="), path.parent.name.removeprefix("asset_class="))
            if scope in SCOPES and (*scope, code) not in identities:
                candidates.append((name, relative, path))
    result = {
        "mode": "quarantine" if apply else "dry-run",
        "count": len(candidates),
        "files": [str(path) for _, _, path in candidates],
    }
    if not apply or not candidates:
        return result
    batch = quarantine / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    batch.mkdir(parents=True, mode=0o700)
    log = batch / "moves.jsonl"
    try:
        with log.open("x", encoding="utf-8") as stream:
            for name, relative, source in candidates:
                destination = batch / name / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise FileExistsError(destination)
                # Write the original and destination paths before moving; partial failures remain auditable.
                stream.write(
                    json.dumps({"source": str(source), "destination": str(destination)}, ensure_ascii=False) + "\n"
                )
                stream.flush()
                source.rename(destination)
    except OSError:
        print(f"隔离中止，已移动的文件和操作日志保留在 {batch}", file=sys.stderr)
        raise
    return {**result, "log": str(log)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="按当前元数据统一预览或隔离失效的源数据与缓存")
    parser.add_argument("--apply", action="store_true", help="显式移动到隔离目录；默认只预览")
    args = parser.parse_args(argv)
    from CLPainter.web.backend.app._config.settings import settings
    from CLPainter.web.backend.app.db.base import engine
    from CLPainter.web.backend.app.db.models import Instrument
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    try:
        with Session(engine) as session:
            identities = {
                tuple(row)
                for row in session.execute(select(Instrument.market, Instrument.asset_class, Instrument.code))
            }
        print(json.dumps(cleanup_files(settings, identities, apply=args.apply), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        print(f"清理未完成: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
