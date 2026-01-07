from fastapi import FastAPI, APIRouter

root_router = APIRouter()
app = FastAPI(title="DMS Backend API")


@root_router.get("/", status_code=200)
def root() -> str:
    return 'Welcome to DMS Backend API'


# app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(root_router)

if __name__ == '__main__':
    import uvicorn

    # app.run(host='0.0.0.0', port=5000)
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="debug")
