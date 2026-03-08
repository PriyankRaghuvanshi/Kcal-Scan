from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.meal_scan import MealScanInput, UserNutritionProfile
from app.models.supplement_scan import NutritionInsightsOutput, SupplementScanInput
from app.services.ai_insights import generate_nutrition_insights


router = APIRouter(prefix="/nutrition", tags=["nutrition-insights"])


class NutritionScanRequest(BaseModel):
    meal_scan: MealScanInput
    supplement_scan: Optional[SupplementScanInput] = None
    user_profile: Optional[UserNutritionProfile] = None


class NutritionScanResponse(BaseModel):
    focus: str = Field(default="fat_loss_intelligence")
    generated_at: str
    insights: NutritionInsightsOutput


@router.post(
    "/scan",
    response_model=NutritionScanResponse,
    summary="Generate merged nutrition insights from meal + supplement scans",
    description=(
        "Accepts scanned meal and optional supplement payloads, merges both signals, "
        "and returns real-time fat-loss and nutrition recommendations for frontend consumption."
    ),
)
def scan_nutrition(payload: NutritionScanRequest) -> NutritionScanResponse:
    try:
        insights = generate_nutrition_insights(
            meal_scan=payload.meal_scan,
            supplement_scan=payload.supplement_scan,
            user_profile=payload.user_profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive runtime safety
        raise HTTPException(
            status_code=500,
            detail="Failed to generate nutrition insights. Please retry.",
        ) from exc

    return NutritionScanResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        insights=insights,
    )
