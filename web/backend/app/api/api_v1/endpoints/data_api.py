import logging
import os
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pyecharts import options as opts
from pyecharts.charts import Bar, Kline, Candlestick

from pyecharts import options as opts
from ...._config.logging_config import setup_logger

setup_logger()
logger = logging.getLogger(__name__)

router = APIRouter()
appDir = os.environ.get('appDir')
templates = Jinja2Templates(directory=f"{appDir}/templates")
