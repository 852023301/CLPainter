import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, APIRouter
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from CLPainter.web.backend.app._config.settings import settings
from .api.api_v1.api import api_router
from pathlib import Path

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker_target = f"{os.getenv('LHOST', '0.0.0.0')}:{os.getenv('PORT', '-')}"
    startup_info = [
        "=" * 72,
        "CLPainter Backend",
        "API: DMS Backend API",
        f"Worker: PID={os.getpid()}, Target={worker_target}",
        f"Python: {sys.version.split()[0]}",
        f"App Dir: {settings.APP_DIR}",
        f"Data Dir: {settings.DATA_DIR}",
        f"Cache Dir: {settings.CACHE_DUMP_DIR}",
        f"Started At: {datetime.now().isoformat(timespec='seconds')}",
        "=" * 72,
    ]
    logger.info("\n%s", "\n".join(startup_info))
    yield


root_router = APIRouter()
app = FastAPI(title="DMS Backend API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)


@root_router.get("/", status_code=200)
def root() -> str:
    return 'Welcome to DMS Backend API'


# app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(api_router, prefix="/api/v1")
app.include_router(root_router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(static_dir / "favicon.svg", media_type="image/svg+xml")

if __name__ == '__main__':
    import uvicorn

    # app.run(host='0.0.0.0', port=5000)
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="debug")
