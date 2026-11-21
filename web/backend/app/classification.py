"""Current TechFin classifications, scoped exclusively to local instruments."""

import math
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import inspect, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from CLPainter.web.backend.app.db.models import Instrument, InstrumentClassification

LOCAL_TIMEZONE = ZoneInfo("Asia/Hong_Kong")
SNAPSHOT_FIELDS = ("sector", "industry", "subindustry", "concept_l3")
OUTPUT_FIELDS = (
    "sw_l1_code",
    "sw_l1_name",
    "sw_l2_code",
    "sw_l2_name",
    "sw_l3_code",
    "sw_l3_name",
    "concepts",
    "regions",
)


def source_code(code: str) -> str:
    match = re.fullmatch(r"(\d{6})\.?((?:SH|SZ|BJ))", code.strip().upper())
    if match is None:
        raise ValueError(f"Unsupported instrument stock code: {code}")
    return f"{match[1]}.{match[2]}"


def _missing(value) -> bool:
    if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
        return False
    return value is None or bool(pd.isna(value))


def _code(value) -> str | None:
    if _missing(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        raise TypeError("Boolean classification code")
    number = float(value)
    if not math.isfinite(number) or not number.is_integer() or number <= 0:
        raise ValueError(f"Invalid classification code: {value}")
    return str(int(number))


def _timestamp(value) -> pd.Timestamp | None:
    if _missing(value) or str(value).strip() in {"", "None", "NaT", "nan", "null"}:
        return None
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        return None
    return stamp.tz_localize(LOCAL_TIMEZONE) if stamp.tzinfo is None else stamp.tz_convert(LOCAL_TIMEZONE)


def _active(row: dict, day: date, start_key="startDate", end_key="endDate") -> bool:
    start, end = _timestamp(row[start_key]), _timestamp(row[end_key])
    return (start is None or start.date() <= day) and (end is None or day <= end.date())


def _require(frame: pd.DataFrame, fields: set[str], label: str) -> None:
    if not isinstance(frame, pd.DataFrame) or not fields.issubset(frame.columns):
        raise ValueError(f"Invalid {label} columns; required: {sorted(fields)}")


def _latest_rows(data: dict, now: datetime) -> tuple[date, dict[str, pd.Series]]:
    rows, dates = {}, {}
    for field in SNAPSHOT_FIELDS:
        frame = data.get(field)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise ValueError(f"Empty source snapshot: {field}")
        stamps = [_timestamp(value) for value in frame.index]
        positions = [i for i, stamp in enumerate(stamps) if stamp is not None and stamp <= now]
        ready = [i for i in positions if frame.iloc[i].notna().any()]
        if not positions:
            raise ValueError(f"No available source date: {field}")
        index = max(ready or positions, key=lambda i: stamps[i])
        dates[field] = stamps[index].date()
        rows[field] = frame.iloc[index]
        if rows[field].index.has_duplicates:
            raise ValueError(f"Duplicate source stock columns: {field}")
    if len(set(dates.values())) != 1:
        raise ValueError(f"Latest source dates disagree: {dates}")
    return next(iter(dates.values())), rows


def _eligible(session: Session, today: date) -> list[Instrument]:
    return list(
        session.scalars(
            select(Instrument)
            .where(
                Instrument.market == "cn",
                Instrument.asset_class == "stock",
                or_(Instrument.list_date.is_(None), Instrument.list_date <= today),
                or_(Instrument.delist_date.is_(None), Instrument.delist_date > today),
            )
            .order_by(Instrument.id)
        )
    )


def build_records(
    instruments: list[Instrument],
    data: dict,
    catalog: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    now: datetime,
) -> list[dict]:
    """Build timestamp-free records; all validity checks use the same query instant."""
    now = now.replace(tzinfo=LOCAL_TIMEZONE) if now.tzinfo is None else now.astimezone(LOCAL_TIMEZONE)
    day = now.date()
    _, rows = _latest_rows(data, now)
    _require(
        catalog,
        {
            "concept_code",
            "concept_name",
            "class_code",
            "class_name",
            "sub_class_code",
            "sub_class_name",
            "startDate",
            "endDate",
            "concept_state",
            "pubDate",
        },
        "concept catalog",
    )
    _require(membership, {"stock_code", "concept_code", "startDate", "endDate"}, "concept membership")
    info = data.get("industry_info")
    _require(info, {"level", "name", "start_date", "end_date"}, "industry catalog")
    if info.empty or catalog.empty:
        raise ValueError("Empty classification metadata; refusing to replace current results")

    industries = {}
    for code, row in info.iterrows():
        industries.setdefault(_code(code), []).append(row.to_dict())
    definitions, known_codes, display_versions = {}, set(), {}
    for row in catalog.to_dict("records"):
        code = _code(row["concept_code"])
        if code is None:
            raise ValueError("Missing concept catalog code")
        known_codes.add(code)
        published = _timestamp(row["pubDate"])
        if (
            not _active(row, day)
            or (_missing(row["concept_state"]) or float(row["concept_state"]) != 1)
            or (published is not None and published > now)
        ):
            continue
        name = str(row["concept_name"]).strip() if not _missing(row["concept_name"]) else ""
        if not name:
            raise ValueError(f"Missing concept name: {code}")
        path = {key: str(row[key]).strip() for key in ("class_name", "sub_class_name")}
        path.update(class_code=_code(row["class_code"]), sub_class_code=_code(row["sub_class_code"]))
        if any(_missing(row[key]) for key in ("class_name", "sub_class_name")) or not all(path.values()):
            raise ValueError(f"Missing concept classification path: {code}")
        path["concept_name"] = name
        entry = definitions.setdefault(code, {"code": code, "name": name, "paths": []})
        version = (published is not None, published)
        if code not in display_versions or version > display_versions[code]:
            entry["name"] = name
            display_versions[code] = version
        elif version == display_versions[code] and entry["name"] != name:
            raise ValueError(f"Conflicting latest concept names: {code}")
        if path not in entry["paths"]:
            entry["paths"].append(path)
    for entry in definitions.values():
        entry["paths"].sort(key=lambda path: (path["class_code"], path["sub_class_code"], path["concept_name"]))

    selected = {source_code(item.code) for item in instruments}
    active_membership = {code: set() for code in selected}
    for row in membership.to_dict("records"):
        stock = str(row["stock_code"])
        if stock in selected and _active(row, day):
            code = _code(row["concept_code"])
            if code is None:
                raise ValueError(f"Missing membership concept code: {stock}")
            active_membership[stock].add(code)

    records = []
    for instrument in instruments:
        stock = source_code(instrument.code)
        record = {"instrument_id": instrument.id}
        for level, field in enumerate(SNAPSHOT_FIELDS[:3], 1):
            if stock not in rows[field].index:
                raise ValueError(f"Missing {field} coverage for instrument {stock}")
            code = _code(rows[field][stock])
            record[f"sw_l{level}_code"] = record[f"sw_l{level}_name"] = None
            if code is None:
                continue
            if code not in industries:
                raise ValueError(f"Unknown industry code {code} for {stock}; verify the source code system")
            valid = [row for row in industries[code] if _active(row, day, "start_date", "end_date")]
            if any(_missing(row["name"]) for row in valid):
                raise ValueError(f"Missing industry name: {code}")
            values = {(str(row["name"]), _code(row["level"])) for row in valid}
            if len(values) > 1 or any(value[1] != str(level) for value in values):
                raise ValueError(f"Conflicting industry metadata: {code}")
            if values:
                name = next(iter(values))[0]
                if not name.strip() or name == "nan":
                    raise ValueError(f"Missing industry name: {code}")
                record[f"sw_l{level}_code"], record[f"sw_l{level}_name"] = code, name
        if stock not in rows["concept_l3"].index:
            raise ValueError(f"Missing concept_l3 coverage for instrument {stock}")
        raw = rows["concept_l3"][stock]
        record["concepts"] = record["regions"] = None
        if not _missing(raw):
            if not isinstance(raw, (list, tuple, np.ndarray, pd.Series)):
                raise ValueError(f"Expected concept code list for {stock}")
            codes = {_code(code) for code in raw}
            if None in codes:
                raise ValueError(f"Missing concept code inside list for {stock}")
            unknown = codes - known_codes
            if unknown:
                raise ValueError(f"Unknown concept codes for {stock}: {sorted(unknown)}")
            active = codes & definitions.keys() & active_membership[stock]
            record["concepts"] = [definitions[code] for code in sorted(active)]
            record["regions"] = [
                {**entry, "paths": [path for path in entry["paths"] if path["class_code"] == "18"]}
                for entry in record["concepts"]
                if any(path["class_code"] == "18" for path in entry["paths"])
            ]
        records.append(record)
    return records


def refresh_classifications(
    bind: Engine,
    *,
    fetcher: Callable | None = None,
    catalog_loader: Callable | None = None,
    membership_loader: Callable | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> dict:
    """Collect first, then replace the entire eligible instrument set in one transaction."""
    if not dry_run and not inspect(bind).has_table("instrument_classification"):
        raise ValueError("Missing instrument_classification table; run alembic upgrade head first")
    now = now or datetime.now(LOCAL_TIMEZONE)
    now = now.replace(tzinfo=LOCAL_TIMEZONE) if now.tzinfo is None else now.astimezone(LOCAL_TIMEZONE)
    with Session(bind) as session:
        instruments = _eligible(session, now.date())
        session.expunge_all()
    identities = {item.id: item.code for item in instruments}
    if instruments:
        if fetcher is None or catalog_loader is None or membership_loader is None:
            from tdata import fetch_data, query_concept_list, query_concept_stocks

            fetcher = fetcher or fetch_data
            catalog_loader = catalog_loader or query_concept_list
            membership_loader = membership_loader or query_concept_stocks
        day = now.date().isoformat()
        data = fetcher(
            *SNAPSHOT_FIELDS, "industry_info", start_date=(now.date() - timedelta(days=14)).isoformat(), end_date=day
        )
        catalog = catalog_loader()
        membership = membership_loader(
            start=day, end=day, stock_code=sorted({source_code(item.code) for item in instruments})
        )
        records = build_records(instruments, data, catalog, membership, now=now)
    else:
        records = []
    report = {
        "instruments": len(records),
        "saved": 0,
        "concepts": sum(len(row["concepts"] or []) for row in records),
        "regions": sum(len(row["regions"] or []) for row in records),
        "missing_concepts": sum(row["concepts"] is None for row in records),
        "missing_industries": sum(any(row[f"sw_l{level}_code"] is None for level in (1, 2, 3)) for row in records),
    }
    if dry_run:
        return report
    with Session(bind) as session:
        if bind.dialect.name == "sqlite":
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        current = {item.id: item.code for item in _eligible(session, now.date())}
        if current != identities:
            raise ValueError("instrument universe changed during collection; refusing publication")
        existing = {item.instrument_id: item for item in session.scalars(select(InstrumentClassification))}
        for record in records:
            row = existing.get(record["instrument_id"])
            if row is None:
                row = InstrumentClassification(instrument_id=record["instrument_id"])
                session.add(row)
            for key in OUTPUT_FIELDS:
                setattr(row, key, record[key])
        for key, row in existing.items():
            if key not in identities:
                session.delete(row)
        session.commit()
    report["saved"] = len(records)
    return report
