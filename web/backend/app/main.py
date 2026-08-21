from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles
from .api.api_v1.api import api_router
from pathlib import Path

root_router = APIRouter()
app = FastAPI(title="DMS Backend API")


@root_router.get("/", status_code=200)
def root() -> str:
    return 'Welcome to DMS Backend API'


# app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(api_router, prefix="/api/v1")
app.include_router(root_router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

if __name__ == '__main__':
    import uvicorn

    # app.run(host='0.0.0.0', port=5000)
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="debug")
