import gzip
import logging
from functools import lru_cache

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool

from ..endpoints import get_chart_payload_path, load_chart_payload
from ...._config.logging_config import setup_logger
from ...._config.settings import settings

setup_logger()
logger = logging.getLogger(__name__)

router = APIRouter()

template_dir = f"{settings.APP_DIR}/templates"
templates = Jinja2Templates(directory=template_dir)
templates.env.cache = None


@router.get("/lightweight_charts_demo", response_class=HTMLResponse)
async def lightweight_charts_demo(request: Request, symbol: str = "600713SH", frequency: str = "1day"):
    payload_file = get_chart_payload_path(symbol, frequency)
    try:
        cache_version = payload_file.stat().st_mtime_ns
    except FileNotFoundError:
        cache_version = 0

    try:
        html_content = await run_in_threadpool(
            _build_lightweight_charts_page, symbol, frequency, cache_version
        )
    except Exception as error:
        logger.error(f"读取Lightweight Charts数据失败: {error}", exc_info=True)
        return HTMLResponse(content=f"<h1>错误</h1><p>{str(error)}</p>", status_code=500)

    etag = f'W/"{symbol}-{frequency}-{cache_version}"'
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
def _build_lightweight_charts_page(symbol: str, frequency: str, cache_version: int) -> str:
    payload = load_chart_payload(symbol, frequency)
    template = templates.env.get_template("lightweight_charts_demo.html")
    return template.render(**payload)


@lru_cache(maxsize=16)
def _compress_lightweight_charts_page(
    symbol: str, frequency: str, cache_version: int, html_content: str
) -> bytes:
    return gzip.compress(html_content.encode("utf-8"), compresslevel=6, mtime=0)
