"""Only complete, post-close batches may create immutable successful results."""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..db.models import Instrument, StockScreenerPreset, StockScreenerRun

logger = logging.getLogger(__name__)
FREQUENCIES = {"1day": "日", "1week": "周", "1month": "月", "1quarter": "季", "1year": "年"}
STATE_FIELDS = {
    "relative_pivot_position",
    "relative_previous_pivot_position",
    "last_structure_right_type",
    "second_point_type",
    "third_point_type",
    "quasi_third_point_type",
    "second_third_combined_type",
}


def as_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    return date.fromisoformat(text[:10])


def batch_trade_date(records: list[dict]) -> date:
    days = [
        as_date(item["data_trade_date"]) for item in records if item["market"] == "cn" and item["frequency"] == "1day"
    ]
    if not days:
        raise ValueError("批次没有日线数据日期")
    return max(days)


def require_pipeline_ready(records: list[dict], started_at: str | None) -> None:
    if not started_at:
        raise ValueError("缺少完整流水线的开始时间，不能确认本批采集在盘后开始")
    start = datetime.fromisoformat(started_at)
    if start.tzinfo is None:
        raise ValueError("流水线开始时间必须包含时区")
    day = batch_trade_date(records)
    threshold = datetime.combine(day, datetime.min.time().replace(hour=16), tzinfo=ZoneInfo("Asia/Shanghai"))
    if start < threshold:
        raise ValueError("本批流水线在数据交易日 16:00 前开始，不归档盘中采集结果")


def next_trade_day(day: date, calendar_loader: Callable | None = None) -> date:
    if calendar_loader is None:
        from ddp.util import get_trade_calendar

        calendar_loader = get_trade_calendar
    days = [as_date(value) for value in calendar_loader(start=day.isoformat(), length=2, out="list", secumarket="CN")]
    if len(days) < 2 or days[0] != day or days[1] <= day:
        raise ValueError("DDP 日历未确认数据交易日及下一交易日，不能推测周期结束")
    return days[1]


def is_period_end(day: date, following: date, frequency: str) -> bool:
    def key(value: date) -> object:
        if frequency == "1day":
            return value
        if frequency == "1week":
            return value - timedelta(days=value.weekday())
        if frequency == "1month":
            return value.year, value.month
        if frequency == "1quarter":
            return value.year, (value.month - 1) // 3
        if frequency == "1year":
            return value.year
        raise ValueError("Unsupported archive frequency")

    return key(day) != key(following)


def instrument_key(item: dict) -> tuple[str, str, str]:
    return item["market"], item["asset_class"], item["code"]


def chart_url(item: dict, frequency: str) -> str:
    return "/api/v1/test_api/lightweight_charts_demo?" + urlencode(
        {
            "symbol": item["code"],
            "frequency": frequency,
            "market": item["market"],
            "asset_class": item["asset_class"],
        }
    )


def _batch_results(preset: StockScreenerPreset, instruments: list[Instrument], lookup: dict, day: date) -> list[dict]:
    filters = preset.filters
    if set(filters) - (STATE_FIELDS | {"market", "asset_class", "frequency", "scope"}):
        raise ValueError("方案包含未知筛选字段")
    if filters.get("market") not in (None, "cn"):
        raise ValueError("当前自动归档只支持 CN 交易日历")
    universe = [
        item
        for item in instruments
        if item.market == "cn"
        and (filters.get("asset_class") is None or item.asset_class == filters["asset_class"])
        and (item.list_date is None or item.list_date <= day)
        and (item.delist_date is None or item.delist_date > day)
    ]
    if not universe:
        raise ValueError("没有可确认的有效标的范围")
    scopes = (
        {filters["scope"]}
        if filters.get("scope")
        else {
            key[-1]
            for key in lookup
            if key[0] == "cn"
            and key[3] == filters["frequency"]
            and (filters.get("asset_class") is None or key[1] == filters["asset_class"])
        }
    )
    if not scopes:
        raise ValueError("对应周期没有可用构件状态")
    results = []
    for item in sorted(universe, key=lambda value: (value.code, value.asset_class)):
        matches = False
        for scope in scopes:
            key = (item.market, item.asset_class, item.code, filters["frequency"], scope)
            record = lookup.get(key)
            if record is None or as_date(record.get("data_trade_date")) != day:
                raise ValueError("标的 " + item.code + " 状态缺失或数据日期不一致，拒绝归档")
            if all(
                value is None or record.get(field) == value for field, value in filters.items() if field in STATE_FIELDS
            ):
                matches = True
        if matches:
            results.append(
                {
                    "code": item.code,
                    "display_name": item.display_name or item.name,
                    "market": item.market,
                    "asset_class": item.asset_class,
                }
            )
    return results


def archive_due_presets(
    engine: Engine, records: list[dict], *, now: datetime | None = None, calendar_loader: Callable | None = None
) -> dict:
    report = {"saved": 0, "existing": 0, "not_due": 0, "failed": 0, "disabled": 0}
    with Session(engine) as session:
        presets = session.scalars(select(StockScreenerPreset).order_by(StockScreenerPreset.id)).all()
        enabled = [preset for preset in presets if preset.filters.get("frequency") in FREQUENCIES]
        report["disabled"] = len(presets) - len(enabled)
        if not enabled:
            return report
        try:
            day = batch_trade_date(records)
            clock = now or datetime.now(ZoneInfo("Asia/Shanghai"))
            if clock.tzinfo is None:
                raise ValueError("归档时间必须包含时区")
            clock = clock.astimezone(ZoneInfo("Asia/Shanghai"))
            if day > clock.date():
                raise ValueError("批次数据日期晚于当前日期")
            if day == clock.date() and clock.hour < 16:
                report["not_due"] = len(enabled)
                logger.info("尚未到盘后归档门槛，本批不留档")
                return report
            following = next_trade_day(day, calendar_loader)
            lookup = {
                (item["market"], item["asset_class"], item["code"], item["frequency"], item["scope"]): item
                for item in records
            }
            if len(lookup) != len(records):
                raise ValueError("批次存在重复状态身份")
        except (ValueError, TypeError, KeyError, OSError) as error:
            logger.error("选股归档批次不可用: %s", error)
            report["failed"] = len(enabled)
            return report
        instruments = session.scalars(select(Instrument)).all()
        for preset in enabled:
            frequency = preset.filters["frequency"]
            if not is_period_end(day, following, frequency):
                report["not_due"] += 1
                continue
            existing = session.scalar(
                select(StockScreenerRun.id).where(
                    StockScreenerRun.preset_id == preset.id,
                    StockScreenerRun.frequency == frequency,
                    StockScreenerRun.version_date == day,
                )
            )
            if existing is not None:
                report["existing"] += 1
                continue
            try:
                results = _batch_results(preset, instruments, lookup, day)
            except (ValueError, TypeError, KeyError) as error:
                logger.error("方案 %s / %s 未归档: %s", preset.id, day, error)
                report["failed"] += 1
                continue
            statement = insert(StockScreenerRun).values(
                preset_id=preset.id, frequency=frequency, version_date=day, results=results
            )
            changed = session.execute(
                statement.on_conflict_do_nothing(index_elements=["preset_id", "frequency", "version_date"])
            )
            report["saved" if changed.rowcount else "existing"] += 1
        session.commit()
    logger.info("选股归档完成: %s", report)
    return report


def run_summary(run: StockScreenerRun, name: str) -> dict:
    return {
        "id": run.id,
        "preset_id": run.preset_id,
        "preset_name": name,
        "frequency": run.frequency,
        "version_date": run.version_date.isoformat(),
        "count": len(run.results),
    }


def run_detail(session: Session, run_id: int) -> dict | None:
    run = session.get(StockScreenerRun, run_id)
    if run is None:
        return None
    preset = session.get(StockScreenerPreset, run.preset_id)
    result = run_summary(run, preset.name if preset else "方案不存在")
    previous = session.scalar(
        select(StockScreenerRun)
        .where(
            StockScreenerRun.preset_id == run.preset_id,
            StockScreenerRun.frequency == run.frequency,
            StockScreenerRun.version_date < run.version_date,
        )
        .order_by(StockScreenerRun.version_date.desc())
        .limit(1)
    )
    current = {instrument_key(item): item for item in run.results}
    before = {instrument_key(item): item for item in previous.results} if previous else {}
    result.update(
        results=run.results,
        previous_version=previous.version_date.isoformat() if previous else None,
        comparison_available=previous is not None,
        added=[current[key] for key in sorted(current.keys() - before.keys())] if previous else [],
        removed=[before[key] for key in sorted(before.keys() - current.keys())] if previous else [],
        retained=[current[key] for key in sorted(current.keys() & before.keys())] if previous else [],
    )
    return result


def list_runs(session: Session, *, preset_id: int = 0, frequency: str = "", limit: int = 50, offset: int = 0) -> dict:
    if frequency and frequency not in FREQUENCIES:
        raise ValueError("不支持的历史周期")
    conditions = []
    if preset_id:
        conditions.append(StockScreenerRun.preset_id == preset_id)
    if frequency:
        conditions.append(StockScreenerRun.frequency == frequency)
    total = session.scalar(select(func.count()).select_from(StockScreenerRun).where(*conditions))
    rows = (
        session.execute(
            select(
                StockScreenerRun.id,
                StockScreenerRun.preset_id,
                StockScreenerRun.frequency,
                StockScreenerRun.version_date,
                StockScreenerPreset.name.label("preset_name"),
                func.json_array_length(StockScreenerRun.results).label("count"),
            )
            .join(StockScreenerPreset, StockScreenerPreset.id == StockScreenerRun.preset_id)
            .where(*conditions)
            .order_by(StockScreenerRun.version_date.desc(), StockScreenerRun.id.desc())
            .offset(offset)
            .limit(limit)
        )
        .mappings()
        .all()
    )
    return {"total": total, "runs": [{**row, "version_date": row["version_date"].isoformat()} for row in rows]}
