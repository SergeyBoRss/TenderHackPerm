from fastapi import APIRouter

from app.api.routers import analytics, health, imports, system


api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(health.router)
api_router.include_router(imports.router)
api_router.include_router(analytics.router)
