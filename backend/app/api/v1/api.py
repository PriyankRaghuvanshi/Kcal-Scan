from fastapi import APIRouter

from app.api.v1.nutrition_insights import router as nutrition_router


api_router = APIRouter()
api_router.include_router(nutrition_router)
