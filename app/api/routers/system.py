from fastapi import APIRouter

from app.core.config import settings
from app.schemas.system import RootResponse


router = APIRouter(tags=["system"])


@router.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    return RootResponse(service=settings.app_name, status="running")
