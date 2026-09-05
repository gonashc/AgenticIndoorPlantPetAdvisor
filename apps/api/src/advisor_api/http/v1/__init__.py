"""Version 1 application API router."""

from fastapi import APIRouter

from advisor_api.http.v1.care_plans import router as care_plans_router
from advisor_api.http.v1.recommendations import router as recommendations_router

router = APIRouter(prefix="/v1")
router.include_router(recommendations_router)
router.include_router(care_plans_router)

__all__ = ["router"]
