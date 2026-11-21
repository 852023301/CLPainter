"""Read the current classification for chart presentation without re-fetching market data."""

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .db.models import Instrument, InstrumentClassification


def instrument_classification_payload(session: Session, instrument: Instrument | None) -> dict:
    """Keep missing snapshots, unknown fields and confirmed empty lists distinct."""
    identity = {"instrument_id": instrument.id if instrument is not None else None}
    if instrument is None:
        return {**identity, "status": "unregistered"}
    if instrument.market != "cn" or instrument.asset_class != "stock":
        return {**identity, "status": "unsupported"}
    try:
        row = session.get(InstrumentClassification, instrument.id)
    except OperationalError as error:
        if "no such table: instrument_classification" not in str(error.orig).lower():
            raise
        return {**identity, "status": "unavailable"}
    if row is None:
        return {**identity, "status": "missing"}
    return {
        **identity,
        "status": "ready",
        "industries": [
            {"level": level, "code": getattr(row, f"sw_l{level}_code"), "name": getattr(row, f"sw_l{level}_name")}
            for level in (1, 2, 3)
        ],
        "concepts": row.concepts,
        "regions": row.regions,
    }
