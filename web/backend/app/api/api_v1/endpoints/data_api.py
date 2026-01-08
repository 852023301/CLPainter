from fastapi import APIRouter
import logging
from ...._config.logging_config import setup_logger

setup_logger()
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/test1")
def test1() -> str:
    logger.info("test1_info")
    logger.debug("test1_debug")

    return "test1"
