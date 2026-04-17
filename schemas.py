"""
schemas.py
----------
Pydantic v1 schemas for PakuPaku API request/response validation.
All schemas are compatible with Python 3.8.

Schema families:
  - Auth         (register, login, token)
  - User         (profile, onboarding, update)
  - FoodLog      (create, response, daily summary)
  - Recipe       (create, update, response)
  - RecipeIngredient
  - NutritionProfile (onboarding calculator input/output)
"""

import uuid
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, validator


def _validate_username(value: str) -> str:
    value = value.strip()
    if not value.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Username can only contain letters, numbers, hyphens, and underscores.")
    return value


# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:    EmailStr
    username: str    = Field(..., min_length=3, max_length=50)
    password: str    = Field(..., min_length=8)

    @validator("username")
    def username_alphanumeric(cls, v):
        return _validate_username(v)


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None


# ─────────────────────────────────────────────
#  NUTRITION ONBOARDING
# ─────────────────────────────────────────────

class CustomGoalsRequest(BaseModel):
    """For users who already have goals from a dietitian."""
    custom_kcal:    float = Field(..., gt=0)
    custom_protein: float = Field(..., gt=0)
    custom_fat:     float = Field(..., gt=0)
    custom_carbs:   float = Field(..., gt=0)


class NutritionProfileRequest(BaseModel):
    """
    Full onboarding input — mirrors nutrition_calculator.py inputs.
    Either this or CustomGoalsRequest is submitted during onboarding.
    """
    # Biometrics
    weight_kg: float = Field(..., gt=0, le=500)
    height_cm: float = Field(..., gt=0, le=300)
    age:        int  = Field(..., gt=0, le=120)
    birthday:   Optional[date] = None   # stored for future age recalculation

    # Hormonal profile
    hormonal_profile: str = Field(..., description=(
        "One of: male, female, average, katch, hrt"
    ))
    hrt_type:   Optional[str] = Field(None, description="estrogen or testosterone")
    hrt_months: Optional[int] = Field(None, ge=0)

    # Body shape
    navy_profile: str = Field(..., description=(
        "One of: male, female, average, blend"
    ))
    waist_cm: float = Field(..., gt=0)
    neck_cm:  float = Field(..., gt=0)
    hip_cm:   Optional[float] = Field(None, gt=0)

    # Activity & goal
    activity_level:   str   = Field(..., description=(
        "One of: sedentary, light, moderate, very_active, extreme"
    ))
    goal:             str   = Field(..., description="One of: lose, maintain, gain")
    pace_kg_per_week: float = Field(0.0, ge=0.0)

    # Metabolic conditions
    metabolic_conditions: Optional[List[str]] = Field(default_factory=list)

    @validator("hormonal_profile")
    def validate_hormonal_profile(cls, v):
        valid = {"male", "female", "average", "katch", "hrt"}
        if v not in valid:
            raise ValueError(f"hormonal_profile must be one of {valid}")
        return v

    @validator("navy_profile")
    def validate_navy_profile(cls, v):
        valid = {"male", "female", "average", "blend"}
        if v not in valid:
            raise ValueError(f"navy_profile must be one of {valid}")
        return v

    @validator("activity_level")
    def validate_activity_level(cls, v):
        valid = {"sedentary", "light", "moderate", "very_active", "extreme"}
        if v not in valid:
            raise ValueError(f"activity_level must be one of {valid}")
        return v

    @validator("goal")
    def validate_goal(cls, v):
        valid = {"lose", "maintain", "gain"}
        if v not in valid:
            raise ValueError(f"goal must be one of {valid}")
        return v

    @validator("hrt_type")
    def validate_hrt_type(cls, v):
        if v is not None and v not in {"estrogen", "testosterone"}:
            raise ValueError("hrt_type must be 'estrogen' or 'testosterone'")
        return v


class NutritionProfileResponse(BaseModel):
    """Calculated nutrition targets returned after onboarding."""
    body_fat_pct: Optional[float]
    bmr:          Optional[float]
    tdee:         Optional[float]
    target_kcal:  Optional[float]
    protein_g:    Optional[float]
    fat_g:        Optional[float]
    carbs_g:      Optional[float]
    requires_consult: bool = False
    condition_notes:  List[dict] = Field(default_factory=list)
    pace_warning:     Optional[str] = None

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
#  USER
# ─────────────────────────────────────────────

class UserResponse(BaseModel):
    """Public-facing user object — never exposes hashed_password."""
    id:         uuid.UUID
    email:      str
    username:   str
    created_at: datetime
    safe_mode:      bool
    email_verified: bool

    # Biometrics (set during onboarding)
    weight_kg:    Optional[float]
    height_cm:    Optional[float]
    age:          Optional[int]
    birthday:     Optional[date]
    body_fat_pct: Optional[float]

    # Nutrition targets (None if onboarding not completed)
    target_kcal:  Optional[float]
    protein_g:    Optional[float]
    fat_g:        Optional[float]
    carbs_g:      Optional[float]
    uses_custom_goals: bool
    is_premium:        bool

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Partial update — all fields optional."""
    username:  Optional[str]  = Field(None, min_length=3, max_length=50)
    safe_mode: Optional[bool] = None

    @validator("username")
    def username_alphanumeric(cls, v):
        if v is None:
            return v
        return _validate_username(v)


# ─────────────────────────────────────────────
#  FOOD LOG
# ─────────────────────────────────────────────

class FoodLogCreateRequest(BaseModel):
    """Log a single food entry."""
    # One of spoonacular_id or recipe_id must be provided
    spoonacular_id: Optional[int]       = None
    recipe_id:      Optional[uuid.UUID] = None

    food_name:  str   = Field(..., min_length=1, max_length=255)
    brand_name: Optional[str] = Field(None, max_length=255)
    amount_g:   float = Field(..., gt=0, description="Portion size in grams")

    # Nutrients (scaled to amount_g, not per 100g)
    calories:  Optional[float] = Field(None, ge=0)
    protein_g: Optional[float] = Field(None, ge=0)
    fat_g:     Optional[float] = Field(None, ge=0)
    carbs_g:   Optional[float] = Field(None, ge=0)
    fiber_g:   Optional[float] = Field(None, ge=0)
    sugar_g:   Optional[float] = Field(None, ge=0)
    sodium_mg: Optional[float] = Field(None, ge=0)

    meal:     Optional[str]  = Field(None, max_length=50)
    log_date: Optional[date] = None   # defaults to today if not provided
    # spoonacular_id and recipe_id are both optional — custom foods have neither


class FoodLogResponse(BaseModel):
    id:             uuid.UUID
    user_id:        uuid.UUID
    log_date:       date
    logged_at:      datetime
    spoonacular_id: Optional[int]
    recipe_id:      Optional[uuid.UUID]
    food_name:  str
    brand_name: Optional[str]
    amount_g:   float
    calories:   Optional[float]
    protein_g:  Optional[float]
    fat_g:      Optional[float]
    carbs_g:    Optional[float]
    fiber_g:    Optional[float]
    sugar_g:    Optional[float]
    sodium_mg:  Optional[float]
    meal:       Optional[str]

    class Config:
        from_attributes = True


class DailySummaryResponse(BaseModel):
    """Aggregated totals for a single day."""
    log_date:      date
    total_calories: Optional[float]
    total_protein:  Optional[float]
    total_fat:      Optional[float]
    total_carbs:    Optional[float]
    total_fiber:    Optional[float]
    entries:        int
    # How the totals compare to the user's targets (None if no targets set)
    kcal_remaining:    Optional[float]
    protein_remaining: Optional[float]
    fat_remaining:     Optional[float]
    carbs_remaining:   Optional[float]


# ─────────────────────────────────────────────
#  RECIPE INGREDIENT
# ─────────────────────────────────────────────

class RecipeIngredientRequest(BaseModel):
    spoonacular_id: Optional[int]  = None
    food_name:  str            = Field(..., min_length=1, max_length=255)
    brand_name: Optional[str]  = Field(None, max_length=255)
    amount_g:   float          = Field(..., gt=0)
    calories:   Optional[float] = Field(None, ge=0)
    protein_g:  Optional[float] = Field(None, ge=0)
    fat_g:      Optional[float] = Field(None, ge=0)
    carbs_g:    Optional[float] = Field(None, ge=0)
    fiber_g:    Optional[float] = Field(None, ge=0)


class RecipeIngredientResponse(BaseModel):
    id:             uuid.UUID
    recipe_id:      uuid.UUID
    spoonacular_id: Optional[int]
    food_name:  str
    brand_name: Optional[str]
    amount_g:   float
    calories:   Optional[float]
    protein_g:  Optional[float]
    fat_g:      Optional[float]
    carbs_g:    Optional[float]
    fiber_g:    Optional[float]

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
#  RECIPE
# ─────────────────────────────────────────────

class RecipeCreateRequest(BaseModel):
    name:        str  = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    servings:    float = Field(1.0, gt=0)
    ingredients: List[RecipeIngredientRequest] = Field(..., min_items=1)


class RecipeUpdateRequest(BaseModel):
    name:        Optional[str]   = Field(None, min_length=1, max_length=255)
    description: Optional[str]   = None
    servings:    Optional[float] = Field(None, gt=0)
    ingredients: Optional[List[RecipeIngredientRequest]] = None


class RecipeResponse(BaseModel):
    id:          uuid.UUID
    user_id:     uuid.UUID
    name:        str
    description: Optional[str]
    servings:    float
    created_at:  datetime
    updated_at:  datetime

    # Per-serving totals (auto-calculated from ingredients)
    total_calories:  Optional[float]
    total_protein_g: Optional[float]
    total_fat_g:     Optional[float]
    total_carbs_g:   Optional[float]
    total_fiber_g:   Optional[float]

    ingredients: List[RecipeIngredientResponse]

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
#  BODY MEASUREMENTS
# ─────────────────────────────────────────────

class BodyMeasurementCreate(BaseModel):
    measured_at: Optional[date]  = None
    weight_kg:   Optional[float] = Field(None, gt=0)
    height_cm:   Optional[float] = Field(None, gt=0)
    waist_cm:    Optional[float] = Field(None, gt=0)
    neck_cm:     Optional[float] = Field(None, gt=0)
    hip_cm:      Optional[float] = Field(None, gt=0)

    @validator("weight_kg", "waist_cm", "neck_cm", "hip_cm", pre=True, always=True)
    def at_least_one_field(cls, v, values):
        return v  # individual field validation only; cross-field check below

    @validator("hip_cm", always=True)
    def require_at_least_one(cls, v, values):
        if all(values.get(f) is None for f in ("weight_kg", "waist_cm", "neck_cm")) and v is None:
            raise ValueError("Provide at least one measurement.")
        return v


class BodyMeasurementResponse(BaseModel):
    id:           uuid.UUID
    user_id:      uuid.UUID
    measured_at:  date
    weight_kg:    Optional[float]
    height_cm:    Optional[float]
    waist_cm:     Optional[float]
    neck_cm:      Optional[float]
    hip_cm:       Optional[float]
    body_fat_pct: Optional[float]

    class Config:
        from_attributes = True
