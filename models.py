"""
models.py
---------
SQLAlchemy ORM models for PakuPaku.

Tables:
  users               — accounts, nutrition profile, preferences
  food_logs           — daily food entries per user
  recipes             — user-created custom recipes
  recipe_ingredients  — individual ingredients within a recipe
"""

import uuid
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    String, Float, Integer, Boolean, Date, DateTime,
    ForeignKey, Text, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from database import Base


# ─────────────────────────────────────────────
#  ENUMS
# ─────────────────────────────────────────────

class HormonalProfile(str, enum.Enum):
    male    = "male"
    female  = "female"
    average = "average"
    katch   = "katch"
    hrt     = "hrt"


class HRTType(str, enum.Enum):
    estrogen     = "estrogen"
    testosterone = "testosterone"


class ActivityLevel(str, enum.Enum):
    sedentary    = "sedentary"
    light        = "light"
    moderate     = "moderate"
    very_active  = "very_active"
    extreme      = "extreme"


class Goal(str, enum.Enum):
    lose     = "lose"
    maintain = "maintain"
    gain     = "gain"


class NavyProfile(str, enum.Enum):
    male    = "male"
    female  = "female"
    average = "average"
    blend   = "blend"


# ─────────────────────────────────────────────
#  USER
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    # ── Identity ─────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    verification_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    birthday: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Preferences ───────────────────────────
    safe_mode: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # If True, calorie numbers are hidden in the frontend

    # ── Biometrics ────────────────────────────
    weight_kg: Mapped[Optional[float]]  = mapped_column(Float,   nullable=True)
    height_cm: Mapped[Optional[float]]  = mapped_column(Float,   nullable=True)
    age:       Mapped[Optional[int]]    = mapped_column(Integer, nullable=True)

    # ── Hormonal profile ──────────────────────
    hormonal_profile: Mapped[Optional[HormonalProfile]] = mapped_column(
        SAEnum(HormonalProfile), nullable=True
    )
    hrt_type:   Mapped[Optional[HRTType]] = mapped_column(SAEnum(HRTType), nullable=True)
    hrt_months: Mapped[Optional[int]]     = mapped_column(Integer, nullable=True)

    # ── Body shape (Navy formula) ─────────────
    navy_profile: Mapped[Optional[NavyProfile]] = mapped_column(
        SAEnum(NavyProfile), nullable=True
    )
    waist_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    neck_cm:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hip_cm:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Activity & goal ───────────────────────
    activity_level: Mapped[Optional[ActivityLevel]] = mapped_column(
        SAEnum(ActivityLevel), nullable=True
    )
    goal: Mapped[Optional[Goal]] = mapped_column(SAEnum(Goal), nullable=True)
    pace_kg_per_week: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Metabolic conditions ──────────────────
    # Stored as a comma-separated string of condition keys, e.g.
    # "hypothyroidism_treated,pcos"
    # Kept simple for now; can be normalised into its own table later.
    metabolic_conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Calculated nutrition targets ──────────
    # These are computed by nutrition_calculator.py and cached here
    # so the frontend doesn't need to recalculate on every request.
    body_fat_pct: Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    bmr:          Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    tdee:         Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    target_kcal:  Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    protein_g:    Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    fat_g:        Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    carbs_g:      Mapped[Optional[float]]  = mapped_column(Float, nullable=True)

    # ── Custom goals (dietitian bypass) ───────
    # If set, these override the calculated targets above.
    custom_kcal:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_fat:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_carbs:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uses_custom_goals: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # ── Premium subscription ───────────────────
    # TODO: gate this behind real payment verification before going live
    is_premium: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # ── Relationships ─────────────────────────
    food_logs: Mapped[List["FoodLog"]]         = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    recipes: Mapped[List["Recipe"]]            = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    measurements: Mapped[List["BodyMeasurement"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.email})>"


# ─────────────────────────────────────────────
#  FOOD LOG
# ─────────────────────────────────────────────

class FoodLog(Base):
    __tablename__ = "food_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    logged_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    log_date: Mapped[date] = mapped_column(
        Date, default=date.today, nullable=False, index=True
    )

    # ── What was eaten ────────────────────────
    # For Spoonacular foods: spoonacular_id is set, recipe_id is None
    # For custom recipes: recipe_id is set, spoonacular_id is None
    spoonacular_id: Mapped[Optional[int]]     = mapped_column(Integer,  nullable=True)
    recipe_id:   Mapped[Optional[uuid.UUID]]  = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.id", ondelete="SET NULL"),
        nullable=True,
    )
    food_name:   Mapped[str]   = mapped_column(String(255), nullable=False)
    brand_name:  Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ── Portion ───────────────────────────────
    amount_g:    Mapped[float] = mapped_column(Float, nullable=False)
    # Nutrient values are stored per-log so they remain accurate even if
    # the USDA data is updated later.
    calories:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein_g:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_g:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs_g:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fiber_g:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sugar_g:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sodium_mg:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Meal label (optional) ─────────────────
    meal: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    # e.g. "breakfast", "lunch", "dinner", "snack" — not enforced,
    # kept flexible so users can label however they want

    # ── Relationships ─────────────────────────
    user:   Mapped["User"]          = relationship(back_populates="food_logs")
    recipe: Mapped[Optional["Recipe"]] = relationship()

    def __repr__(self) -> str:
        return f"<FoodLog {self.food_name} {self.amount_g}g on {self.log_date}>"


# ─────────────────────────────────────────────
#  RECIPE
# ─────────────────────────────────────────────

class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name:        Mapped[str]        = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    servings:    Mapped[float]      = mapped_column(Float, default=1.0, nullable=False)
    created_at:  Mapped[datetime]   = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at:  Mapped[datetime]   = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # ── Totals (per serving, auto-calculated) ─
    # Computed from ingredients and cached here for fast retrieval.
    total_calories:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_protein_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_fat_g:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_carbs_g:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_fiber_g:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Relationships ─────────────────────────
    user: Mapped["User"] = relationship(back_populates="recipes")
    ingredients: Mapped[List["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Recipe '{self.name}' by user {self.user_id}>"


# ─────────────────────────────────────────────
#  RECIPE INGREDIENT
# ─────────────────────────────────────────────

class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── Spoonacular reference ─────────────────
    spoonacular_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    food_name:  Mapped[str]        = mapped_column(String(255), nullable=False)
    brand_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ── Amount ────────────────────────────────
    amount_g: Mapped[float] = mapped_column(Float, nullable=False)

    # ── Nutrients (per amount_g, not per 100g) ─
    calories:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_g:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs_g:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fiber_g:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Relationships ─────────────────────────
    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")

    def __repr__(self) -> str:
        return f"<RecipeIngredient {self.food_name} {self.amount_g}g>"


# ─────────────────────────────────────────────
#  BODY MEASUREMENTS
# ─────────────────────────────────────────────

class BodyMeasurement(Base):
    __tablename__ = "body_measurements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    measured_at: Mapped[date] = mapped_column(
        Date, default=date.today, nullable=False, index=True
    )

    weight_kg:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height_cm:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    waist_cm:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    neck_cm:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hip_cm:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    body_fat_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Relationship ──────────────────────────
    user: Mapped["User"] = relationship(back_populates="measurements")

    def __repr__(self) -> str:
        return f"<BodyMeasurement {self.measured_at} {self.weight_kg}kg>"