from fastapi import APIRouter

from app.api.routers import analytics, analytics_explain, contracts, cte, embeddings, health, imports, references, system


api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(health.router)
api_router.include_router(imports.router)
api_router.include_router(references.router)
api_router.include_router(contracts.router)
api_router.include_router(cte.router)
api_router.include_router(embeddings.router)
api_router.include_router(analytics.router)
api_router.include_router(analytics_explain.router)
