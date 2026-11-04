from typing import Any


def build_snapshot_record(
    cache: Any,
    *,
    code: str,
    frequency: str,
    market: str,
    asset_class: str,
    scope: str = "bi",
) -> dict:
    """从已加载的缓存构造一条状态快照记录。"""
    from .fenxing import last_structure_right_type
    from .second_point import second_point_type
    from .positions import calculate_positions

    current_position, previous_position = calculate_positions(cache)
    return {
        "code": code,
        "frequency": frequency,
        "market": market,
        "asset_class": asset_class,
        "scope": scope,
        "relative_pivot_position": current_position,
        "relative_previous_pivot_position": previous_position,
        "last_structure_right_type": last_structure_right_type(cache),
        "second_point_type": second_point_type(cache),
    }


def persist_snapshots(records: list[dict]) -> int:
    """批量写入状态快照，返回找不到 instrument 的记录数。"""
    if not records:
        return 0

    from sqlalchemy import func, select
    from sqlalchemy.dialects.sqlite import insert
    from sqlalchemy.orm import Session

    from ..db.base import engine
    from ..db.models import ClStateSnapshot, Instrument

    with Session(engine) as session:
        instruments = session.scalars(select(Instrument)).all()
        instrument_ids = {
            (instrument.market, instrument.asset_class, instrument.code): instrument.id
            for instrument in instruments
        }

        values = []
        missing = 0
        for record in records:
            instrument_id = instrument_ids.get(
                (record["market"], record["asset_class"], record["code"])
            )
            if instrument_id is None:
                missing += 1
                continue
            values.append({
                "instrument_id": instrument_id,
                "frequency": record["frequency"],
                "scope": record["scope"],
                "relative_pivot_position": record["relative_pivot_position"],
                "relative_previous_pivot_position": record["relative_previous_pivot_position"],
                "last_structure_right_type": record["last_structure_right_type"],
                "second_point_type": record["second_point_type"],
            })

        for start in range(0, len(values), 500):
            statement = insert(ClStateSnapshot).values(values[start:start + 500])
            statement = statement.on_conflict_do_update(
                index_elements=["instrument_id", "frequency", "scope"],
                set_={
                    "relative_pivot_position": statement.excluded.relative_pivot_position,
                    "relative_previous_pivot_position": statement.excluded.relative_previous_pivot_position,
                    "last_structure_right_type": statement.excluded.last_structure_right_type,
                    "second_point_type": statement.excluded.second_point_type,
                    "calculated_at": func.current_timestamp(),
                },
            )
            session.execute(statement)
        session.commit()

    return missing
