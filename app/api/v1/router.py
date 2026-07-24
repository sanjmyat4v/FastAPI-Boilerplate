from fastapi import APIRouter
from app.api.v1 import test, auth

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(test.router)
api_v1_router.include_router(auth.router)