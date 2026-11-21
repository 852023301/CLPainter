"""Refresh current classifications for eligible local instrument rows only."""

import argparse
import json
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = BACKEND_DIR.parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


@contextmanager
def collection_lock(database_path: Path):
    """Serialize full collection runs, not just the final database transaction."""
    import fcntl

    database_path = database_path.resolve()
    lock_path = database_path.with_name(database_path.name + ".classification.lock")
    with lock_path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Read and validate all eligible instruments without writing SQLite"
    )
    options = parser.parse_args()

    from CLPainter.web.backend.app.classification import refresh_classifications
    from CLPainter.web.backend.app.db.base import DATABASE_PATH, engine

    try:
        with nullcontext() if options.dry_run else collection_lock(DATABASE_PATH):
            report = refresh_classifications(engine, dry_run=options.dry_run)
    except Exception as error:  # noqa: BLE001 -- sanitize arbitrary external failures at the CLI boundary
        # External exceptions can contain credentials; do not print raw connection details.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        if any(word in message.lower() for word in ("password", "passwd", "token", "://")):
            message = type(error).__name__
        print(f"Classification update failed; no results published: {message}", file=sys.stderr)
        return 1
    print(json.dumps({"dry_run": options.dry_run, **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
