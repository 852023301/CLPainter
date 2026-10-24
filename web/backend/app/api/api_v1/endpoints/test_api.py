import gzip
import hashlib
import json
import logging
import re
from pathlib import Path
from functools import lru_cache
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..endpoints import SUPPORTED_CHART_FREQUENCIES, get_chart_payload_versions, load_chart_payload
from ....db.base import engine
from ....db.models import Instrument, WatchlistBoard, WatchlistItem
from ...._config.logging_config import setup_logger
from ...._config.settings import settings

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
        instrument_name_version = hashlib.sha256(instrument_display_name.encode("utf-8")).hexdigest()[:16]
        instrument_updated_at = (
            instrument.updated_at.isoformat()
            if instrument is not None and instrument.updated_at is not None
            else ""
        )
    except ValueError as error:
        return HTMLResponse(content=f"<h1>错误</h1><p>{str(error)}</p>", status_code=400)

    cache_version = "-".join(map(str, frequency_versions))

    try:
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
        )
    except Exception as error:
        logger.error(f"读取Lightweight Charts数据失败: {error}", exc_info=True)
        return HTMLResponse(content=f"<h1>错误</h1><p>{str(error)}</p>", status_code=500)

    template_version = str(_TEMPLATE_PATH.stat().st_mtime_ns)
    etag = (
        f'W/"{symbol}-{frequency_key}-{market_key}-{asset_class_key}-'
        f'{instrument_name_version}-{instrument_updated_at}-{template_version}-{cache_version}"'
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
) -> str:
    """按缓存版本读取图表payload并渲染完整HTML。"""
    payload = load_chart_payload(symbol, frequency, market, asset_class)
    payload = {
        key: value
        for key, value in payload.items()
        if key not in _LAZY_MODULES.values()
    }
    payload.setdefault("ma_data", "[]")
    payload.setdefault("gaps_data", "[]")
    payload.setdefault("boll_data", "[]")
    payload.setdefault("rsi_data", "[]")
    payload.setdefault("macd_data", "{\"lines\":[],\"stats\":[],\"markers\":[]}")
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
    template = templates.env.get_template("lightweight_charts_demo.html")
    return template.render(**payload)


@lru_cache(maxsize=16)
def _compress_lightweight_charts_page(
    symbol: str, frequency: str, cache_version: str, html_content: str
) -> bytes:
    """按缓存版本生成可复用的gzip页面内容。"""
    return gzip.compress(html_content.encode("utf-8"), compresslevel=6, mtime=0)
