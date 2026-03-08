from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class UserNutritionProfile(BaseModel):
    goal: Literal["fat_loss", "maintenance", "muscle_gain", "recomp"] = "fat_loss"
    target_calories: Optional[float] = Field(default=2000, ge=800, le=5000)
    target_protein_g: Optional[float] = Field(default=140, ge=30, le=320)
    workout_day: bool = False
    meal_window: Optional[Literal["breakfast", "lunch", "dinner", "snack"]] = None


class MealScanInput(BaseModel):
    meal_name: Optional[str] = None
    calories: float = Field(..., ge=0, le=4000)
    protein_g: float = Field(..., ge=0, le=350)
    carbs_g: float = Field(..., ge=0, le=500)
    fat_g: float = Field(..., ge=0, le=250)
    fiber_g: float = Field(default=0, ge=0, le=120)
    sugar_g: float = Field(default=0, ge=0, le=250)
    sodium_mg: float = Field(default=0, ge=0, le=10000)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    scan_source: Optional[Literal["camera", "manual", "barcode", "ocr"]] = "camera"
    flags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_nutrition_totals(self) -> "MealScanInput":
        macro_calories = (self.protein_g * 4.0) + (self.carbs_g * 4.0) + (self.fat_g * 9.0)
        if self.calories > 0 and macro_calories > (self.calories * 1.9):
            raise ValueError(
                "Meal macros are inconsistent with calories. Check scan extraction values."
            )
        return self
