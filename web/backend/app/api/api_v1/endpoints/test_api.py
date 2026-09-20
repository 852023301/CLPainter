import gzip
import logging
from functools import lru_cache

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool

from ..endpoints import (
    DEFAULT_ASSET_CLASS_DIR,
    DEFAULT_MARKET_DIR,
    SUPPORTED_CHART_FREQUENCIES,
    get_chart_payload_versions,
    load_chart_payload,
)
from ...._config.logging_config import setup_logger
from ...._config.settings import settings

setup_logger()
logger = logging.getLogger(__name__)

router = APIRouter()

template_dir = f"{settings.APP_DIR}/templates"
templates = Jinja2Templates(directory=template_dir)
templates.env.cache = None


@router.get("/lightweight_charts_demo", response_class=HTMLResponse)
async def lightweight_charts_demo(
    request: Request,
    symbol: str = "600713SH",
    frequency: str = "freq=1day",
    market_dir: str = DEFAULT_MARKET_DIR,
    asset_class_dir: str = DEFAULT_ASSET_CLASS_DIR,
):
    """读取图表payload，渲染页面并处理ETag与gzip响应。"""
    try:
        frequency_versions = get_chart_payload_versions(symbol, market_dir, asset_class_dir)
    except ValueError as error:
        return HTMLResponse(content=f"<h1>错误</h1><p>{str(error)}</p>", status_code=400)

    cache_version = "-".join(map(str, frequency_versions))

    try:
        html_content = await run_in_threadpool(
            _build_lightweight_charts_page,
            symbol,
            frequency,
            cache_version,
            frequency_versions,
            market_dir,
            asset_class_dir,
        )
    except Exception as error:
        logger.error(f"读取Lightweight Charts数据失败: {error}", exc_info=True)
        return HTMLResponse(content=f"<h1>错误</h1><p>{str(error)}</p>", status_code=500)

    etag = f'W/"{symbol}-{frequency}-{market_dir}-{asset_class_dir}-{cache_version}"'
    common_headers = {"ETag": etag, "Cache-Control": "private, no-cache", "Vary": "Accept-Encoding"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=common_headers)

    if "gzip" in request.headers.get("accept-encoding", "").lower():
        compressed_content = await run_in_threadpool(
            _compress_lightweight_charts_page, symbol, frequency, cache_version, html_content
        )
        return Response(
            content=compressed_content,
            media_type="text/html; charset=utf-8",
            headers={**common_headers, "Content-Encoding": "gzip"},
        )

    return HTMLResponse(content=html_content, headers=common_headers)


@lru_cache(maxsize=16)
def _build_lightweight_charts_page(
    symbol: str,
    frequency: str,
    cache_version: str,
    frequency_versions: tuple[int, ...],
    market_dir: str,
    asset_class_dir: str,
) -> str:
    """按缓存版本读取图表payload并渲染完整HTML。"""
    payload = load_chart_payload(symbol, frequency, market_dir, asset_class_dir)
    payload["frequency"] = frequency
    payload["frequency_options"] = [
        {
            "value": value,
            "label": label,
            "available": bool(frequency_versions[index]),
        }
        for index, (value, label) in enumerate(SUPPORTED_CHART_FREQUENCIES.items())
    ]
    template = templates.env.get_template("lightweight_charts_demo.html")
    return template.render(**payload)


@lru_cache(maxsize=16)
def _compress_lightweight_charts_page(
    symbol: str, frequency: str, cache_version: str, html_content: str
) -> bytes:
    """按缓存版本生成可复用的gzip页面内容。"""
    return gzip.compress(html_content.encode("utf-8"), compresslevel=6, mtime=0)
