from fastapi import APIRouter
from .endpoints import test_api

api_router = APIRouter()

api_router.include_router(test_api.router, prefix="/test_api", tags=["test_api"])
