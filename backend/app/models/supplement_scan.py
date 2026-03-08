from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SupplementScanInput(BaseModel):
    product_name: str = Field(..., min_length=2, max_length=140)
    brand: Optional[str] = None
    servings_per_day: float = Field(default=1.0, ge=0.0, le=8.0)
    calories: float = Field(default=0, ge=0, le=1200)
    protein_g: float = Field(default=0, ge=0, le=200)
    carbs_g: float = Field(default=0, ge=0, le=200)
    fat_g: float = Field(default=0, ge=0, le=120)
    sugar_g: float = Field(default=0, ge=0, le=120)
    sodium_mg: float = Field(default=0, ge=0, le=10000)
    caffeine_mg: float = Field(default=0, ge=0, le=700)
    authenticity_score: Optional[float] = Field(default=None, ge=0, le=100)
    risk_flags: List[str] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    title: str
    reason: str
    action: str
    priority: Literal["high", "medium", "low"] = "medium"


class NutritionInsightsOutput(BaseModel):
    recommendation_summary: str
    fat_loss_score: float = Field(..., ge=0, le=100)
    satiety_score: float = Field(..., ge=0, le=100)
    macro_balance_score: float = Field(..., ge=0, le=100)
    supplement_safety_score: float = Field(..., ge=0, le=100)
    estimated_daily_calories: float = Field(..., ge=0)
    combined_confidence: float = Field(..., ge=0, le=1)
    recommendations: List[RecommendationItem] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    signals: Dict[str, float] = Field(default_factory=dict)
