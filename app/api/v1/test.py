import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/test", tags=["Test router"])

@router.get("")
async def test():
    return JSONResponse(content={
        "message": "This is test endpoint."
    })