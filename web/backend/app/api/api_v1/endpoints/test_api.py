import gzip
import hashlib
import json
import logging
import pickle
import re
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..endpoints import SUPPORTED_CHART_FREQUENCIES, get_chart_payload_versions, load_chart_payload
from ....classification_view import instrument_classification_payload
from ....db.base import engine
from ....db.models import ClStateSnapshot, Instrument, StockScreenerPreset, StockScreenerRun, WatchlistBoard, WatchlistItem
from ...._config.logging_config import setup_logger
from ...._config.settings import settings
from ....screener.history import FREQUENCIES, chart_url, list_runs, run_detail
from ....screener.freshness import screener_data_version, screener_read_snapshot

setup_logger()
logger = logging.getLogger(__name__)

router = APIRouter()

_SIMPLE_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_SIMPLE_FREQUENCIES = frozenset(key.removeprefix("freq=") for key in SUPPORTED_CHART_FREQUENCIES)
_SEARCH_LIMIT = 20
_TEMPLATE_PATH = Path(settings.APP_DIR) / "templates" / "lightweight_charts_demo.html"
_LAZY_MODULES = {
    "ma": "ma_data",
    "gaps": "gaps_data",
    "boll": "boll_data",
    "rsi": "rsi_data",
    "macd": "macd_data",
}
_WATCHLIST_NAME_PATTERN = re.compile(r"^\S.{0,62}\S$|^\S$")
_SCREENER_MARKET_LABELS = {"cn": "中国"}
_SCREENER_ASSET_CLASS_LABELS = {"stock": "股票", "fund": "基金", "index": "指数"}
_SCREENER_SCOPE_LABELS = {"bi": "笔", "xianduan": "线段"}
_SCREENER_STATE_FIELDS = (
    ("relative_pivot_position", "相对当前中枢位置", ((0, "无中枢"), (1, "中枢内"), (2, "中枢下"), (3, "中枢上"))),
    (
        "relative_previous_pivot_position",
        "相对扩展中枢位置",
        ((0, "无中枢"), (1, "中枢内"), (2, "中枢下"), (3, "中枢上")),
    ),
    ("last_structure_right_type", "右侧类型", ((0, "无分型"), (1, "底分型"), (2, "顶分型"))),
    ("second_point_type", "二买/二卖", ((0, "都不是"), (1, "二买"), (2, "二卖"))),
    ("third_point_type", "三买/三卖", ((0, "都不是"), (1, "三买"), (2, "三卖"))),
    ("quasi_third_point_type", "类三买/类三卖", ((0, "都不是"), (1, "类三买"), (2, "类三卖"))),
    (
        "second_third_combined_type",
        "二三合买/二三合卖",
        ((0, "都不是"), (1, "二三合买"), (2, "二三合卖")),
    ),
)
_SCREENER_STATE_LIMITS = {
    "relative_pivot_position": (0, 1, 2, 3),
    "relative_previous_pivot_position": (0, 1, 2, 3),
    "last_structure_right_type": (0, 1, 2),
    "second_point_type": (0, 1, 2),
    "third_point_type": (0, 1, 2),
    "quasi_third_point_type": (0, 1, 2),
    "second_third_combined_type": (0, 1, 2),
}


def _normalize_frequency(value: str) -> str:
    """将1day等简化周期参数转换为freq=1day格式。"""
    if value not in _SIMPLE_FREQUENCIES:
        supported = ", ".join(sorted(_SIMPLE_FREQUENCIES))
        raise ValueError(f"不支持的K线周期: {value}，支持: {supported}")
    return f"freq={value}"


def _normalize_directory_value(value: str, prefix: str, field_name: str) -> str:
    """将cn等简化目录参数转换为market=cn格式。"""
    if not _SIMPLE_VALUE_PATTERN.fullmatch(value):
        raise ValueError(f"非法的{field_name}: {value}")
    return f"{prefix}{value}"


class WatchlistBoardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class WatchlistBoardRename(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class WatchlistItemCreate(BaseModel):
    instrument_id: int = Field(gt=0)


class WatchlistItemOrder(BaseModel):
    instrument_ids: list[int] = Field(min_length=1)


class StockScreenerQuery(BaseModel):
    market: str | None = None
    asset_class: str | None = None
    frequency: str | None = None
    scope: str | None = None
    relative_pivot_position: int | None = None
    relative_previous_pivot_position: int | None = None
    last_structure_right_type: int | None = None
    second_point_type: int | None = None
    third_point_type: int | None = None
    quasi_third_point_type: int | None = None
    second_third_combined_type: int | None = None


class StockScreenerPresetFilters(StockScreenerQuery):
    model_config = ConfigDict(extra="forbid", strict=True)

    market: str | None = Field(default=None, max_length=16)
    asset_class: str | None = Field(default=None, max_length=32)
    frequency: str | None = Field(default=None, max_length=16)
    scope: str | None = Field(default=None, max_length=16)

    @model_validator(mode="after")
    def validate_supported_values(self) -> "StockScreenerPresetFilters":
        allowed_fields = {
            "market": _SCREENER_MARKET_LABELS,
            "asset_class": _SCREENER_ASSET_CLASS_LABELS,
            "frequency": _SIMPLE_FREQUENCIES,
            "scope": _SCREENER_SCOPE_LABELS,
            **_SCREENER_STATE_LIMITS,
        }
        for field, allowed in allowed_fields.items():
            value = getattr(self, field)
            if value is not None and value not in allowed:
                raise ValueError(f"{field} 的取值无效")
        return self


class StockScreenerPresetWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=64)
    filters: StockScreenerPresetFilters

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        if isinstance(value, str):
            if any(ord(character) < 32 for character in value):
                raise ValueError("方案名称不能包含控制字符")
            return value.strip()
        return value


template_dir = f"{settings.APP_DIR}/templates"
templates = Jinja2Templates(directory=template_dir)
templates.env.cache = None


@router.get("/instrument/search")
async def search_instruments(
    q: str = Query(min_length=1, max_length=64),
    frequency: str = "1day",
):
    """按代码或简称搜索当前有效标的，并返回图表地址。"""
    keyword = q.strip()
    if not keyword:
        return {"results": []}
    try:
        frequency_key = _normalize_frequency(frequency)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    code_keyword = keyword.replace(".", "").upper()
    name_keyword = f"%{keyword}%"
    with Session(engine) as session:
        instruments = session.scalars(
            select(Instrument)
            .where(
                Instrument.code.like(f"%{code_keyword}%")
                | Instrument.name.like(name_keyword)
                | Instrument.display_name.like(name_keyword)
            )
            .order_by(Instrument.code, Instrument.asset_class)
            .limit(_SEARCH_LIMIT * 2)
        ).all()

    exact_keyword = code_keyword
    instruments = sorted(
        instruments,
        key=lambda item: (
            item.code != exact_keyword,
            not item.code.startswith(exact_keyword),
            not item.name.startswith(keyword),
            not item.display_name.startswith(keyword),
            item.code,
        ),
    )[:_SEARCH_LIMIT]

    def build_result(instrument: Instrument) -> dict:
        query = urlencode(
            {
                "symbol": instrument.code,
                "frequency": frequency_key.removeprefix("freq="),
                "market": instrument.market,
                "asset_class": instrument.asset_class,
            }
        )
        return {
            "code": instrument.code,
            "name": instrument.name,
            "display_name": instrument.display_name,
            "market": instrument.market,
            "asset_class": instrument.asset_class,
            "url": f"/api/v1/test_api/lightweight_charts_demo?{query}",
        }

    return {"results": [build_result(instrument) for instrument in instruments]}


def _validate_watchlist_name(name: str) -> str:
    normalized_name = name.strip()
    if not _WATCHLIST_NAME_PATTERN.fullmatch(normalized_name):
        raise HTTPException(status_code=400, detail="板块名称不能为空，且长度不能超过64个字符")
    return normalized_name


def _get_watchlist_board(session: Session, board_id: int) -> WatchlistBoard:
    board = session.get(WatchlistBoard, board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="自选板块不存在")
    return board


@lru_cache(maxsize=512)
def _read_daily_quote(path_str: str, mtime_ns: int) -> tuple[float | None, float | None]:
    """读取日线最后一根相对前收的涨跌和涨跌幅。"""
    with open(path_str, "rb") as file:
        rows = pickle.load(file)
    if not rows or len(rows[-1]) < 3:
        return None, None
    close = float(rows[-1][2])
    if len(rows) < 2 or len(rows[-2]) < 3:
        return 0.0, 0.0
    previous_close = float(rows[-2][2])
    if previous_close == 0:
        return 0.0, 0.0
    change = close - previous_close
    return change, change / previous_close * 100


def _latest_daily_quote(instrument: Instrument) -> dict:
    """返回标的日线最后一根的涨跌；没有数据时字段为空。"""
    path = (
        Path(settings.DATA_DIR)
        / "freq=1day"
        / f"market={instrument.market}"
        / f"asset_class={instrument.asset_class}"
        / f"{instrument.code}.pkl"
    )
    empty = {"change": None, "change_pct": None, "price_precision": instrument.price_precision}
    if not path.is_file():
        return empty
    try:
        change, change_pct = _read_daily_quote(str(path), path.stat().st_mtime_ns)
    except (OSError, pickle.PickleError, EOFError, ValueError, IndexError, TypeError):
        return empty
    if change is None or change_pct is None:
        return empty
    return {
        "change": round(change, instrument.price_precision),
        "change_pct": round(change_pct, 2),
        "price_precision": instrument.price_precision,
    }


def _serialize_watchlist_board(session: Session, board: WatchlistBoard) -> dict:
    items = session.execute(
        select(WatchlistItem, Instrument)
        .join(Instrument, WatchlistItem.instrument_id == Instrument.id)
        .where(WatchlistItem.board_id == board.id)
        .order_by(WatchlistItem.sort_order, WatchlistItem.id)
    ).all()
    return {
        "id": board.id,
        "name": board.name,
        "sort_order": board.sort_order,
        "items": [
            {
                "instrument_id": item.instrument_id,
                "code": instrument.code,
                "name": instrument.name,
                "display_name": instrument.display_name,
                "market": instrument.market,
                "asset_class": instrument.asset_class,
                **_latest_daily_quote(instrument),
                "url": (
                    "/api/v1/test_api/lightweight_charts_demo?"
                    + urlencode(
                        {
                            "symbol": instrument.code,
                            "market": instrument.market,
                            "asset_class": instrument.asset_class,
                        }
                    )
                ),
            }
            for item, instrument in items
        ],
    }


@router.get("/watchlists")
async def list_watchlists():
    """获取全部自选板块及其标的。"""
    with Session(engine) as session:
        boards = session.scalars(select(WatchlistBoard).order_by(WatchlistBoard.sort_order, WatchlistBoard.id)).all()
        return {"boards": [_serialize_watchlist_board(session, board) for board in boards]}


@router.post("/watchlists", status_code=201)
async def create_watchlist(payload: WatchlistBoardCreate):
    """创建自选板块。"""
    name = _validate_watchlist_name(payload.name)
    with Session(engine) as session:
        if session.scalar(select(func.count()).select_from(WatchlistBoard).where(WatchlistBoard.name == name)):
            raise HTTPException(status_code=400, detail="板块名称已存在")
        sort_order = session.scalar(select(func.coalesce(func.max(WatchlistBoard.sort_order), -1))) + 1
        board = WatchlistBoard(name=name, sort_order=sort_order)
        session.add(board)
        session.commit()
        session.refresh(board)
        return _serialize_watchlist_board(session, board)


@router.patch("/watchlists/{board_id}")
async def rename_watchlist(board_id: int, payload: WatchlistBoardRename):
    """修改自选板块名称。"""
    name = _validate_watchlist_name(payload.name)
    with Session(engine) as session:
        board = _get_watchlist_board(session, board_id)
        duplicated_board = session.scalar(select(WatchlistBoard).where(WatchlistBoard.name == name, WatchlistBoard.id != board_id))
        if duplicated_board is not None:
            raise HTTPException(status_code=400, detail="板块名称已存在")
        board.name = name
        session.commit()
        session.refresh(board)
        return _serialize_watchlist_board(session, board)


@router.delete("/watchlists/{board_id}", status_code=204)
async def delete_watchlist(board_id: int):
    """删除自选板块。"""
    with Session(engine) as session:
        board = _get_watchlist_board(session, board_id)
        session.delete(board)
        session.commit()


@router.post("/watchlists/{board_id}/items", status_code=201)
async def add_watchlist_item(board_id: int, payload: WatchlistItemCreate):
    """添加标的到自选板块。"""
    with Session(engine) as session:
        board = _get_watchlist_board(session, board_id)
        instrument = session.get(Instrument, payload.instrument_id)
        if instrument is None:
            raise HTTPException(status_code=404, detail="标的不存在")
        exists = session.scalar(
            select(func.count())
            .select_from(WatchlistItem)
            .where(WatchlistItem.board_id == board.id, WatchlistItem.instrument_id == instrument.id)
        )
        if exists:
            raise HTTPException(status_code=400, detail="该标的已在板块中")
        sort_order = (
            session.scalar(
                select(func.coalesce(func.max(WatchlistItem.sort_order), -1)).where(WatchlistItem.board_id == board.id)
            )
            + 1
        )
        session.add(
            WatchlistItem(board_id=board.id, instrument_id=instrument.id, sort_order=sort_order)
        )
        session.commit()
        return _serialize_watchlist_board(session, board)


@router.put("/watchlists/{board_id}/items/order")
async def reorder_watchlist_items(board_id: int, payload: WatchlistItemOrder):
    """按给定顺序重排自选板块内的标的。"""
    with Session(engine) as session:
        board = _get_watchlist_board(session, board_id)
        items = session.scalars(select(WatchlistItem).where(WatchlistItem.board_id == board.id)).all()
        current_ids = {item.instrument_id for item in items}
        requested_ids = payload.instrument_ids
        if len(requested_ids) != len(set(requested_ids)) or set(requested_ids) != current_ids:
            raise HTTPException(status_code=400, detail="标的顺序与板块内容不一致")
        order = {instrument_id: index for index, instrument_id in enumerate(requested_ids)}
        for item in items:
            item.sort_order = order[item.instrument_id]
        session.commit()
        return _serialize_watchlist_board(session, board)


@router.delete("/watchlists/{board_id}/items/{instrument_id}", status_code=204)
async def remove_watchlist_item(board_id: int, instrument_id: int):
    """从自选板块移除标的。"""
    with Session(engine) as session:
        board = _get_watchlist_board(session, board_id)
        deleted_count = session.execute(
            delete(WatchlistItem).where(
                WatchlistItem.board_id == board.id,
                WatchlistItem.instrument_id == instrument_id,
            )
        ).rowcount
        if not deleted_count:
            raise HTTPException(status_code=404, detail="标的不在板块中")
        session.commit()


def _serialize_screener_preset(preset: StockScreenerPreset) -> dict:
    return {
        "id": preset.id,
        "name": preset.name,
        "filters": preset.filters,
        "created_at": preset.created_at,
        "updated_at": preset.updated_at,
    }


def _get_screener_preset(session: Session, preset_id: int) -> StockScreenerPreset:
    preset = session.get(StockScreenerPreset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="选股方案不存在，请刷新方案列表")
    return preset


def _commit_screener_preset(session: Session, preset: StockScreenerPreset) -> dict:
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="方案名称已存在，请换一个名称") from error
    session.refresh(preset)
    return _serialize_screener_preset(preset)


@router.get("/stock_screener/presets")
def list_stock_screener_presets() -> dict:
    """列出本服务实例共享的选股方案。"""
    with Session(engine) as session:
        presets = session.scalars(select(StockScreenerPreset).order_by(StockScreenerPreset.id)).all()
        return {"presets": [_serialize_screener_preset(preset) for preset in presets]}


@router.post("/stock_screener/presets", status_code=201)
def create_stock_screener_preset(payload: StockScreenerPresetWrite) -> dict:
    """只保存条件；缺省值规范化为 null，明确表示不限。"""
    with Session(engine) as session:
        preset = StockScreenerPreset(name=payload.name, filters=payload.filters.model_dump())
        session.add(preset)
        return _commit_screener_preset(session, preset)


@router.put("/stock_screener/presets/{preset_id}")
def update_stock_screener_preset(preset_id: int, payload: StockScreenerPresetWrite) -> dict:
    with Session(engine) as session:
        preset = _get_screener_preset(session, preset_id)
        preset.name = payload.name
        preset.filters = payload.filters.model_dump()
        return _commit_screener_preset(session, preset)


@router.delete("/stock_screener/presets/{preset_id}", status_code=204)
def delete_stock_screener_preset(preset_id: int) -> Response:
    with Session(engine) as session:
        if session.scalar(select(StockScreenerRun.id).where(StockScreenerRun.preset_id == preset_id).limit(1)) is not None:
            raise HTTPException(status_code=409, detail="方案已有历史结果，不能直接删除；可继续修改方案条件")
        session.delete(_get_screener_preset(session, preset_id))
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise HTTPException(status_code=409, detail="方案已生成历史结果，不能直接删除") from error
    return Response(status_code=204)


@router.get("/stock_screener/runs")
def stock_screener_runs(
    preset_id: int = Query(0, ge=0),
    frequency: str = "",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    with Session(engine) as session:
        try:
            return list_runs(session, preset_id=preset_id, frequency=frequency, limit=limit, offset=offset)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/stock_screener/runs/{run_id}")
def stock_screener_run_detail(run_id: int) -> dict:
    with Session(engine) as session:
        detail = run_detail(session, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="历史版本不存在")
        return detail


@router.get("/stock_screener/history", response_class=HTMLResponse)
def stock_screener_history(
    request: Request,
    preset_id: int = Query(0, ge=0),
    frequency: str = "",
    run_id: int = Query(0, ge=0),
    view: str = "results",
    offset: int = Query(0, ge=0),
    standalone: int = Query(0, ge=0, le=1),
):
    if view not in {"results", "added", "removed", "retained"}:
        raise HTTPException(status_code=400, detail="不支持的结果视图")
    with Session(engine) as session:
        try:
            listing = list_runs(session, preset_id=preset_id, frequency=frequency, limit=50, offset=offset)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        selected_id = run_id or (listing["runs"][0]["id"] if listing["runs"] else 0)
        detail = run_detail(session, selected_id) if selected_id else None
        if run_id and (
            detail is None
            or (preset_id and detail["preset_id"] != preset_id)
            or (frequency and detail["frequency"] != frequency)
        ):
            raise HTTPException(status_code=404, detail="历史版本不存在或不符合当前筛选")
        presets = [
            {"id": item.id, "name": item.name}
            for item in session.scalars(select(StockScreenerPreset).order_by(StockScreenerPreset.id))
        ]

    if not standalone:
        candidates = (detail[view] or detail["results"]) if detail else []
        item = candidates[0] if candidates else {"code": "000001SH", "market": "cn", "asset_class": "index"}
        chart_frequency = detail["frequency"] if detail else (frequency or "1day")
        context = {
            "screener_mode": "history",
            "history_preset": preset_id,
            "history_frequency": frequency,
            "history_run_id": selected_id,
            "history_view": view,
            "history_offset": offset,
            "history_scroll": 0,
        }
        return RedirectResponse(chart_url(item, chart_frequency) + "&" + urlencode(context), status_code=303)

    def history_link(**updates):
        values = {
            "preset_id": preset_id,
            "frequency": frequency,
            "run_id": selected_id,
            "view": view,
            "offset": offset,
            "standalone": 1,
        }
        values.update(updates)
        return "/api/v1/test_api/stock_screener/history?" + urlencode(values)

    rows = [{**item, "chart_url": chart_url(item, detail["frequency"])} for item in detail[view]] if detail else []
    template = templates.env.get_template("screener_history.html")
    return HTMLResponse(
        template.render(
            presets=presets,
            preset_id=preset_id,
            frequency=frequency,
            frequencies=FREQUENCIES,
            listing=listing,
            detail=detail,
            rows=rows,
            view=view,
            offset=offset,
            history_link=history_link,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/stock_screener/options")
async def stock_screener_options():
    """返回选股面板可用的市场、资产类别、周期、构件和状态选项。"""
    with Session(engine) as session:
        markets = session.scalars(
            select(Instrument.market).join(
                ClStateSnapshot, Instrument.id == ClStateSnapshot.instrument_id
            ).distinct().order_by(Instrument.market)
        ).all()
        asset_classes = session.scalars(
            select(Instrument.asset_class).join(
                ClStateSnapshot, Instrument.id == ClStateSnapshot.instrument_id
            ).distinct().order_by(Instrument.asset_class)
        ).all()
        frequencies = session.scalars(
            select(ClStateSnapshot.frequency).distinct().order_by(ClStateSnapshot.frequency)
        ).all()
        scopes = session.scalars(
            select(ClStateSnapshot.scope).distinct().order_by(ClStateSnapshot.scope)
        ).all()

    dimensions = [
        {
            "field": "market",
            "label": "市场",
            "options": [
                {"value": value, "label": _SCREENER_MARKET_LABELS.get(value, value)}
                for value in markets
            ],
        },
        {
            "field": "asset_class",
            "label": "种类",
            "options": [
                {"value": value, "label": _SCREENER_ASSET_CLASS_LABELS.get(value, value)}
                for value in asset_classes
            ],
        },
        {
            "field": "frequency",
            "label": "周期",
            "options": [
                {
                    "value": value,
                    "label": SUPPORTED_CHART_FREQUENCIES.get(f"freq={value}", value),
                }
                for value in frequencies
            ],
        },
        {
            "field": "scope",
            "label": "构件",
            "options": [
                {"value": value, "label": _SCREENER_SCOPE_LABELS.get(value, value)}
                for value in scopes
            ],
        },
    ]
    states = [
        {
            "field": field,
            "label": label,
            "options": [{"value": value, "label": option_label} for value, option_label in options],
        }
        for field, label, options in _SCREENER_STATE_FIELDS
    ]
    return {"dimensions": dimensions, "states": states}


@router.get("/stock_screener/version")
def stock_screener_version():
    """Return a read-only version of the realtime screener dataset."""
    with screener_read_snapshot(engine) as session:
        version = screener_data_version(session)
    return JSONResponse({"data_version": version}, headers={"Cache-Control": "no-store"})


@router.post("/stock_screener/query")
def stock_screener_query(payload: StockScreenerQuery):
    """按状态组合查询标的。"""
    conditions = []
    if payload.market:
        conditions.append(Instrument.market == payload.market)
    if payload.asset_class:
        conditions.append(Instrument.asset_class == payload.asset_class)
    if payload.frequency:
        conditions.append(ClStateSnapshot.frequency == payload.frequency)
    if payload.scope:
        conditions.append(ClStateSnapshot.scope == payload.scope)

    for field, allowed_values in _SCREENER_STATE_LIMITS.items():
        value = getattr(payload, field)
        if value is None:
            continue
        if value not in allowed_values:
            raise HTTPException(status_code=400, detail=f"{field} 的取值无效: {value}")
        conditions.append(getattr(ClStateSnapshot, field) == value)

    statement = (
        select(Instrument, ClStateSnapshot.frequency)
        .join(ClStateSnapshot, Instrument.id == ClStateSnapshot.instrument_id)
        .where(*conditions)
        .order_by(Instrument.code, ClStateSnapshot.frequency)
    )
    with screener_read_snapshot(engine) as session:
        rows = session.execute(statement).all()
        data_version = screener_data_version(session)

    grouped = {}
    for instrument, frequency in rows:
        item = grouped.setdefault(
            instrument.id,
            {
                "instrument_id": instrument.id,
                "code": instrument.code,
                "name": instrument.name,
                "display_name": instrument.display_name or instrument.name,
                "market": instrument.market,
                "asset_class": instrument.asset_class,
                "frequencies": set(),
            },
        )
        item["frequencies"].add(frequency)

    results = []
    for item in grouped.values():
        frequencies = sorted(item["frequencies"])
        selected_frequency = payload.frequency or frequencies[0]
        query = urlencode(
            {
                "symbol": item["code"],
                "frequency": selected_frequency,
                "market": item["market"],
                "asset_class": item["asset_class"],
            }
        )
        results.append({
            **item,
            "frequencies": frequencies,
            "frequency": selected_frequency,
            "url": f"/api/v1/test_api/lightweight_charts_demo?{query}",
        })
    results.sort(key=lambda item: (item["code"], item["asset_class"]))
    return JSONResponse(
        {
            "count": len(results), "results": results, "data_version": data_version,
            "queried_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/lightweight_charts_demo", response_class=HTMLResponse)
async def lightweight_charts_demo(
    request: Request,
    symbol: str = "000001SH",
    frequency: str = "1day",
    market: str = "cn",
    asset_class: str = "stock",
    market_dir: str | None = None,
    asset_class_dir: str | None = None,
):
    """读取图表payload，渲染页面并处理ETag与gzip响应。"""
    try:
        if market_dir is not None:
            raise ValueError("参数market_dir已改名为market")
        if asset_class_dir is not None:
            raise ValueError("参数asset_class_dir已改名为asset_class")
        frequency_key = _normalize_frequency(frequency)
        market_key = _normalize_directory_value(market, "market=", "市场")
        asset_class_key = _normalize_directory_value(asset_class, "asset_class=", "资产类别")
        frequency_versions = get_chart_payload_versions(symbol, market_key, asset_class_key)
    except ValueError as error:
        return HTMLResponse(
            content=f"<h1>错误</h1><p>{escape(str(error))}</p>",
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )
    except Exception:
        logger.error("读取Lightweight Charts缓存版本失败", exc_info=True)
        return HTMLResponse(
            content="<h1>错误</h1><p>图表暂时不可用，请稍后重试。</p>",
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    # 内部 ValueError 不能作为参数错误回显；保留诊断到服务端日志。
    try:
        with Session(engine) as session:
            instrument = session.scalar(
                select(Instrument).where(
                    Instrument.market == market_key.removeprefix("market="),
                    Instrument.asset_class == asset_class_key.removeprefix("asset_class="),
                    Instrument.code == symbol,
                )
            )
            instrument_display_name = instrument.display_name if instrument is not None else symbol
            instrument_id = instrument.id if instrument is not None else None
            classification = instrument_classification_payload(session, instrument)
        instrument_name_version = hashlib.sha256(instrument_display_name.encode("utf-8")).hexdigest()[:16]
        instrument_updated_at = (
            instrument.updated_at.isoformat() if instrument is not None and instrument.updated_at is not None else ""
        )
        classification_json = json.dumps(classification, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        classification_version = hashlib.sha256(classification_json.encode("utf-8")).hexdigest()[:16]
        cache_version = "-".join(map(str, frequency_versions))

        template_version = "-".join(
            str(path.stat().st_mtime_ns)
            for path in (
                _TEMPLATE_PATH,
                _TEMPLATE_PATH.with_name("_instrument_classification.html"),
                _TEMPLATE_PATH.with_name("_chart_workspace.js"),
                _TEMPLATE_PATH.with_name("_frontend_requests.js"),
                _TEMPLATE_PATH.with_name("_screener_workspace.js"),
                _TEMPLATE_PATH.with_name("_chart_indicators.js"),
                _TEMPLATE_PATH.parent.parent / "static/css/instrument-classification.css",
                _TEMPLATE_PATH.parent.parent / "static/js/screener-history.js",
            )
        )
        html_content = await run_in_threadpool(
            _build_lightweight_charts_page,
            symbol,
            frequency_key,
            cache_version,
            frequency_versions,
            market_key,
            asset_class_key,
            instrument_display_name,
            instrument_id,
            classification_json,
            template_version,
        )
    except Exception as error:
        if (
            request.query_params.get("screener_mode") == "history"
            and isinstance(error, (FileNotFoundError, ValueError))
            and "template_version" in locals()
        ):
            logger.warning("历史工作台图表暂不可用: symbol=%s frequency=%s error=%s", symbol, frequency, type(error).__name__)
            empty = {
                name: "[]"
                for name in (
                    "candle_data",
                    "change_data",
                    "bi_data",
                    "xd_data",
                    "zhongshu_data",
                    "zhongshu_in_xianduan_data",
                    "xianduan_zhongshu_data",
                    "xianduan_zhongshu_another_data",
                    "volume_data",
                )
            }
            empty.update(precision=2, chart_error="该标的暂无可用图表数据，请在历史名单中选择其他标的")
            return HTMLResponse(
                _render_lightweight_charts_page(
                    empty,
                    symbol,
                    frequency_key,
                    frequency_versions,
                    market_key,
                    asset_class_key,
                    instrument_display_name,
                    instrument_id,
                    classification_json,
                    template_version,
                ),
                headers={"Cache-Control": "no-store"},
            )
        logger.error(f"读取Lightweight Charts数据失败: {error}", exc_info=True)
        return HTMLResponse(
            content="<h1>错误</h1><p>图表暂时不可用，请稍后重试。</p>",
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    etag = (
        f'W/"{symbol}-{frequency_key}-{market_key}-{asset_class_key}-'
        f'{instrument_name_version}-{instrument_updated_at}-{classification_version}-{template_version}-{cache_version}"'
    )
    common_headers = {"ETag": etag, "Cache-Control": "private, no-cache", "Vary": "Accept-Encoding"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=common_headers)

    if "gzip" in request.headers.get("accept-encoding", "").lower():
        compressed_content = await run_in_threadpool(
            _compress_lightweight_charts_page, symbol, frequency_key, cache_version, html_content
        )
        return Response(
            content=compressed_content,
            media_type="text/html; charset=utf-8",
            headers={**common_headers, "Content-Encoding": "gzip"},
        )

    return HTMLResponse(content=html_content, headers=common_headers)


@router.get("/lightweight_charts_module")
async def lightweight_charts_module(
    symbol: str,
    frequency: str,
    market: str,
    asset_class: str,
    module: str,
):
    """按需返回指标模块，减少首屏HTML体积。"""
    try:
        frequency_key = _normalize_frequency(frequency)
        market_key = _normalize_directory_value(market, "market=", "市场")
        asset_class_key = _normalize_directory_value(asset_class, "asset_class=", "资产类别")
        field = _LAZY_MODULES.get(module)
        if field is None:
            raise ValueError(f"不支持的图表模块: {module}")
        payload = await run_in_threadpool(
            load_chart_payload, symbol, frequency_key, market_key, asset_class_key
        )
        if field not in payload:
            raise ValueError(f"图表缓存缺少模块字段: {field}")
        return Response(
            content=json.dumps({"module": module, "data": payload[field]}),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@lru_cache(maxsize=16)
def _build_lightweight_charts_page(
    symbol: str,
    frequency: str,
    cache_version: str,
    frequency_versions: tuple[int, ...],
    market: str,
    asset_class: str,
    display_name: str,
    instrument_id: int | None,
    classification_json: str,
    template_version: str,
) -> str:
    """按缓存版本读取图表payload并渲染完整HTML。"""
    payload = load_chart_payload(symbol, frequency, market, asset_class)
    return _render_lightweight_charts_page(
        payload,
        symbol,
        frequency,
        frequency_versions,
        market,
        asset_class,
        display_name,
        instrument_id,
        classification_json,
        template_version,
    )


def _render_lightweight_charts_page(
    payload: dict,
    symbol: str,
    frequency: str,
    frequency_versions: tuple[int, ...],
    market: str,
    asset_class: str,
    display_name: str,
    instrument_id: int | None,
    classification_json: str,
    template_version: str,
) -> str:
    payload = {key: value for key, value in payload.items() if key not in _LAZY_MODULES.values()}
    payload.setdefault("ma_data", "[]")
    payload.setdefault("gaps_data", "[]")
    payload.setdefault("boll_data", "[]")
    payload.setdefault("rsi_data", "[]")
    payload.setdefault("macd_data", '{"lines":[],"stats":[],"markers":[]}')
    payload.setdefault("change_data", "[]")
    payload["frequency"] = frequency
    payload["symbol"] = symbol
    payload["market"] = market
    payload["asset_class"] = asset_class
    payload["frequency_options"] = [
        {
            "value": value,
            "label": label,
            "available": bool(frequency_versions[index]),
        }
        for index, (value, label) in enumerate(SUPPORTED_CHART_FREQUENCIES.items())
    ]
    payload["instrument_display_name"] = display_name
    payload["instrument_id"] = instrument_id
    payload["classification"] = json.loads(classification_json)
    payload["classification_assets_version"] = template_version
    template = templates.env.get_template("lightweight_charts_demo.html")
    return template.render(**payload)


@lru_cache(maxsize=16)
def _compress_lightweight_charts_page(
    symbol: str, frequency: str, cache_version: str, html_content: str
) -> bytes:
    """按缓存版本生成可复用的gzip页面内容。"""
    return gzip.compress(html_content.encode("utf-8"), compresslevel=6, mtime=0)
