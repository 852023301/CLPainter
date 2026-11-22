"""Read-only, content-based versions for realtime screener results."""

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..db.models import ClStateSnapshot, Instrument


@contextmanager
def screener_read_snapshot(engine: Engine) -> Iterator[Session]:
    """Keep result rows and their version in one SQLite read snapshot."""
    with engine.connect() as connection, connection.begin():
        if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")
        with Session(bind=connection) as session:
            yield session


def screener_data_version(session: Session) -> str:
    """Hash query inputs, not merely counts or second-resolution timestamps."""
    digest = hashlib.sha256(b"screener-data-v1\n")
    sources = (
        (Instrument, ("id", "market", "asset_class", "code", "name", "display_name"), ("id",)),
        (
            ClStateSnapshot,
            (
                "instrument_id",
                "frequency",
                "scope",
                "relative_pivot_position",
                "relative_previous_pivot_position",
                "last_structure_right_type",
                "second_point_type",
                "third_point_type",
                "quasi_third_point_type",
                "second_third_combined_type",
            ),
            ("instrument_id", "frequency", "scope"),
        ),
    )
    for model, fields, order in sources:
        digest.update(model.__tablename__.encode("ascii") + b"\n")
        statement = select(*(getattr(model, field) for field in fields)).order_by(
            *(getattr(model, field) for field in order)
        )
        for batch in session.execute(statement).partitions(1000):
            digest.update(
                json.dumps([tuple(row) for row in batch], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            )
            digest.update(b"\n")
    return "screener-v1:" + digest.hexdigest()
