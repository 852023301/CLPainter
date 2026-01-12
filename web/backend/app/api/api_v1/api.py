from fastapi import APIRouter
from .endpoints import data_api
from .endpoints import test_api
from .endpoints import professional_demo_api
from .endpoints import professional_demo_api2




api_router = APIRouter()

api_router.include_router(data_api.router, prefix="/data_api", tags=["data_api"])
api_router.include_router(test_api.router, prefix="/test_api", tags=["test_api"])
api_router.include_router(professional_demo_api.router, prefix="/professional_demo_api", tags=["professional_demo_api"])
api_router.include_router(professional_demo_api2.router, prefix="/professional_demo_api", tags=["professional_demo_api"])