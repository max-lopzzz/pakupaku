"""
main.py
-------
PakuPaku FastAPI application.

Route groups:
  /auth       — register, login
  /users      — profile, onboarding, preferences
  /foods      — USDA search and detail (via usda.py)
  /logs       — food log CRUD + daily summary
  /recipes    — custom recipe CRUD
"""

from datetime import date
from typing import Optional, List
import uuid

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, cast, Date

from database import get_db
from models import User, FoodLog, Recipe, RecipeIngredient
from schemas import (
    RegisterRequest, LoginRequest, TokenResponse,
    UserResponse, UserUpdateRequest,
    NutritionProfileRequest, NutritionProfileResponse, CustomGoalsRequest,
    FoodLogCreateRequest, FoodLogResponse, DailySummaryResponse,
    RecipeCreateRequest, RecipeUpdateRequest, RecipeResponse,
)
from auth import hash_password, verify_password, create_access_token, get_current_user
from usda import search_foods, get_food, get_foods_bulk, extract_nutrients
from nutrition_calculator import (
    calc_body_fat_navy, calc_bmr, interpolate_bmr_hrt,
    apply_metabolic_conditions, calc_tdee, calc_goal_adjustment,
    calc_macros, hrt_navy_blend_t,
)

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Override the docs security scheme to show a simple Bearer token field
http_bearer = HTTPBearer()

# ─────────────────────────────────────────────
#  APP
# ─────────────────────────────────────────────

app = FastAPI(
    title="PakuPaku API",
    description="Inclusive calorie and nutrition tracking API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
#  AUTH ROUTES
# ─────────────────────────────────────────────

@app.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new account and return an access token."""

    # Check email uniqueness
    existing_email = await db.execute(
        select(User).where(User.email == payload.email)
    )
    if existing_email.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered.")

    # Check username uniqueness
    existing_username = await db.execute(
        select(User).where(User.username == payload.username)
    )
    if existing_username.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken.")

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.flush()   # assigns user.id without committing

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@app.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Verify credentials and return an access token."""

    result = await db.execute(select(User).where(User.email == payload.email))
    user   = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


# ─────────────────────────────────────────────
#  USER ROUTES
# ─────────────────────────────────────────────

@app.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the current user's profile."""
    return current_user


@app.patch("/users/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update username or safe_mode preference."""
    if payload.username is not None:
        # Check new username isn't taken
        existing = await db.execute(
            select(User).where(
                User.username == payload.username,
                User.id != current_user.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Username already taken.")
        current_user.username = payload.username

    if payload.safe_mode is not None:
        current_user.safe_mode = payload.safe_mode

    await db.flush()
    return current_user


# ─────────────────────────────────────────────
#  ONBOARDING ROUTES
# ─────────────────────────────────────────────

@app.post("/users/me/onboarding/calculate", response_model=NutritionProfileResponse)
async def onboarding_calculate(
    payload: NutritionProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run nutrition_calculator.py with the user's inputs, save the results
    to their profile, and return the calculated targets.
    """
    # Determine Navy blend factor
    navy_blend_t = None
    if payload.navy_profile == "blend" and payload.hrt_type and payload.hrt_months is not None:
        navy_blend_t = hrt_navy_blend_t(payload.hrt_type, payload.hrt_months)

    # Body fat %
    try:
        body_fat_pct = calc_body_fat_navy(
            payload.height_cm,
            payload.waist_cm,
            payload.neck_cm,
            payload.hip_cm,
            profile=payload.navy_profile,
            hrt_blend_t=navy_blend_t,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # BMR
    if payload.hormonal_profile == "hrt" and payload.hrt_type and payload.hrt_months is not None:
        bmr = interpolate_bmr_hrt(
            payload.weight_kg, payload.height_cm, payload.age,
            payload.hrt_type, payload.hrt_months, body_fat_pct,
        )
    else:
        try:
            bmr = calc_bmr(
                payload.weight_kg, payload.height_cm, payload.age,
                profile=payload.hormonal_profile,
                body_fat_pct=body_fat_pct,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Metabolic conditions
    condition_keys   = payload.metabolic_conditions or []
    condition_result = apply_metabolic_conditions(bmr, condition_keys)
    adjusted_bmr     = condition_result["adjusted_bmr"]

    # Block deficit if eating disorder history
    goal = payload.goal
    pace = payload.pace_kg_per_week
    if "eating_disorder_history" in condition_keys and goal == "lose":
        goal = "maintain"
        pace = 0.0

    # TDEE + goal adjustment
    tdee                    = calc_tdee(adjusted_bmr, payload.activity_level)
    goal_kcal, pace_warning = calc_goal_adjustment(goal, pace)
    target_kcal             = tdee + goal_kcal

    macros = calc_macros(target_kcal, payload.weight_kg, body_fat_pct, goal)

    # Persist to user profile
    current_user.weight_kg           = payload.weight_kg
    current_user.height_cm           = payload.height_cm
    current_user.age                  = payload.age
    current_user.hormonal_profile     = payload.hormonal_profile
    current_user.hrt_type             = payload.hrt_type
    current_user.hrt_months           = payload.hrt_months
    current_user.navy_profile         = payload.navy_profile
    current_user.waist_cm             = payload.waist_cm
    current_user.neck_cm              = payload.neck_cm
    current_user.hip_cm               = payload.hip_cm
    current_user.activity_level       = payload.activity_level
    current_user.goal                 = goal
    current_user.pace_kg_per_week     = pace
    current_user.metabolic_conditions = ",".join(condition_keys) if condition_keys else None
    current_user.body_fat_pct         = body_fat_pct
    current_user.bmr                  = bmr
    current_user.tdee                 = tdee
    current_user.target_kcal          = target_kcal
    current_user.protein_g            = macros["protein_g"]
    current_user.fat_g                = macros["fat_g"]
    current_user.carbs_g              = macros["carbs_g"]
    current_user.uses_custom_goals    = False

    await db.flush()

    return NutritionProfileResponse(
        body_fat_pct      = round(body_fat_pct, 1),
        bmr               = round(bmr),
        tdee              = round(tdee),
        target_kcal       = round(target_kcal),
        protein_g         = macros["protein_g"],
        fat_g             = macros["fat_g"],
        carbs_g           = macros["carbs_g"],
        requires_consult  = condition_result["requires_consult"],
        condition_notes   = condition_result["condition_notes"],
        pace_warning      = pace_warning or None,
    )


@app.post("/users/me/onboarding/custom", response_model=UserResponse)
async def onboarding_custom(
    payload: CustomGoalsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save dietitian-provided goals directly, bypassing calculation."""
    current_user.custom_kcal       = payload.custom_kcal
    current_user.custom_protein    = payload.custom_protein
    current_user.custom_fat        = payload.custom_fat
    current_user.custom_carbs      = payload.custom_carbs
    current_user.uses_custom_goals = True
    await db.flush()
    return current_user


# ─────────────────────────────────────────────
#  FOOD (USDA) ROUTES
# ─────────────────────────────────────────────

@app.get("/foods/search")
async def food_search(
    query:       str,
    page_size:   int          = Query(10,  ge=1, le=50),
    page_number: int          = Query(1,   ge=1),
    data_types:  Optional[str] = Query(None, description="Comma-separated data types"),
    _: User = Depends(get_current_user),   # require auth
):
    """
    Search the USDA FoodData Central database.
    Returns raw USDA results — nutrients are per 100g.
    """
    dt_list = [d.strip() for d in data_types.split(",")] if data_types else None
    return await search_foods(query, page_size, page_number, dt_list)


@app.get("/foods/{fdc_id}")
async def food_detail(
    fdc_id:   int,
    format:   str = Query("abridged", description="abridged or full"),
    _: User = Depends(get_current_user),
):
    """Get full details for a single food item by FDC ID."""
    food = await get_food(fdc_id, format=format)
    return extract_nutrients(food)


@app.post("/foods/bulk")
async def food_bulk(
    fdc_ids: List[int],
    _: User = Depends(get_current_user),
):
    """Fetch up to 20 foods at once by FDC ID list."""
    foods = await get_foods_bulk(fdc_ids)
    return [extract_nutrients(f) for f in foods]


# ─────────────────────────────────────────────
#  FOOD LOG ROUTES
# ─────────────────────────────────────────────

@app.post("/logs", response_model=FoodLogResponse, status_code=status.HTTP_201_CREATED)
async def create_log(
    payload:      FoodLogCreateRequest,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Log a food entry for the current user."""
    log = FoodLog(
        user_id    = current_user.id,
        fdc_id     = payload.fdc_id,
        recipe_id  = payload.recipe_id,
        food_name  = payload.food_name,
        brand_name = payload.brand_name,
        amount_g   = payload.amount_g,
        calories   = payload.calories,
        protein_g  = payload.protein_g,
        fat_g      = payload.fat_g,
        carbs_g    = payload.carbs_g,
        fiber_g    = payload.fiber_g,
        sugar_g    = payload.sugar_g,
        sodium_mg  = payload.sodium_mg,
        meal       = payload.meal,
        log_date   = payload.log_date or date.today(),
    )
    db.add(log)
    await db.flush()
    return log


@app.get("/logs", response_model=List[FoodLogResponse])
async def get_logs(
    log_date:     Optional[date] = Query(None, description="Filter by date (YYYY-MM-DD). Defaults to today."),
    current_user: User           = Depends(get_current_user),
    db:           AsyncSession   = Depends(get_db),
):
    """Return all food log entries for a given date (default: today)."""
    target_date = log_date or date.today()
    result = await db.execute(
        select(FoodLog).where(
            FoodLog.user_id  == current_user.id,
            FoodLog.log_date == target_date,
        ).order_by(FoodLog.logged_at)
    )
    return result.scalars().all()


@app.get("/logs/summary", response_model=DailySummaryResponse)
async def get_daily_summary(
    log_date:     Optional[date] = Query(None),
    current_user: User           = Depends(get_current_user),
    db:           AsyncSession   = Depends(get_db),
):
    """
    Return aggregated macro totals for a given day plus remaining
    amounts vs the user's targets.
    """
    target_date = log_date or date.today()

    result = await db.execute(
        select(
            func.sum(FoodLog.calories).label("total_calories"),
            func.sum(FoodLog.protein_g).label("total_protein"),
            func.sum(FoodLog.fat_g).label("total_fat"),
            func.sum(FoodLog.carbs_g).label("total_carbs"),
            func.sum(FoodLog.fiber_g).label("total_fiber"),
            func.count(FoodLog.id).label("entries"),
        ).where(
            FoodLog.user_id  == current_user.id,
            FoodLog.log_date == target_date,
        )
    )
    row = result.one()

    # Determine which targets to use
    if current_user.uses_custom_goals:
        kcal_target    = current_user.custom_kcal
        protein_target = current_user.custom_protein
        fat_target     = current_user.custom_fat
        carbs_target   = current_user.custom_carbs
    else:
        kcal_target    = current_user.target_kcal
        protein_target = current_user.protein_g
        fat_target     = current_user.fat_g
        carbs_target   = current_user.carbs_g

    def remaining(total, target):
        if total is None or target is None:
            return None
        return round(target - total, 1)

    return DailySummaryResponse(
        log_date           = target_date,
        total_calories     = round(row.total_calories,  1) if row.total_calories  else 0.0,
        total_protein      = round(row.total_protein,   1) if row.total_protein   else 0.0,
        total_fat          = round(row.total_fat,       1) if row.total_fat       else 0.0,
        total_carbs        = round(row.total_carbs,     1) if row.total_carbs     else 0.0,
        total_fiber        = round(row.total_fiber,     1) if row.total_fiber     else 0.0,
        entries            = row.entries or 0,
        kcal_remaining     = remaining(row.total_calories, kcal_target),
        protein_remaining  = remaining(row.total_protein,  protein_target),
        fat_remaining      = remaining(row.total_fat,      fat_target),
        carbs_remaining    = remaining(row.total_carbs,    carbs_target),
    )


@app.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(
    log_id:       uuid.UUID,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Delete a food log entry. Only the owner can delete their own entries."""
    result = await db.execute(
        select(FoodLog).where(
            FoodLog.id      == log_id,
            FoodLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found.")
    await db.delete(log)


# ─────────────────────────────────────────────
#  RECIPE ROUTES
# ─────────────────────────────────────────────

def _compute_recipe_totals(ingredients, servings: float) -> dict:
    """Sum nutrient values across all ingredients and divide by servings."""
    def safe_sum(field):
        values = [getattr(i, field) for i in ingredients if getattr(i, field) is not None]
        return round(sum(values) / servings, 2) if values else None

    return {
        "total_calories":  safe_sum("calories"),
        "total_protein_g": safe_sum("protein_g"),
        "total_fat_g":     safe_sum("fat_g"),
        "total_carbs_g":   safe_sum("carbs_g"),
        "total_fiber_g":   safe_sum("fiber_g"),
    }


@app.post("/recipes", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    payload:      RecipeCreateRequest,
    current_user: User           = Depends(get_current_user),
    db:           AsyncSession   = Depends(get_db),
):
    """Create a new custom recipe with ingredients."""
    recipe = Recipe(
        user_id     = current_user.id,
        name        = payload.name,
        description = payload.description,
        servings    = payload.servings,
    )
    db.add(recipe)
    await db.flush()   # assigns recipe.id

    ingredient_objs = []
    for ing in payload.ingredients:
        obj = RecipeIngredient(
            recipe_id  = recipe.id,
            fdc_id     = ing.fdc_id,
            food_name  = ing.food_name,
            brand_name = ing.brand_name,
            amount_g   = ing.amount_g,
            calories   = ing.calories,
            protein_g  = ing.protein_g,
            fat_g      = ing.fat_g,
            carbs_g    = ing.carbs_g,
            fiber_g    = ing.fiber_g,
        )
        db.add(obj)
        ingredient_objs.append(obj)

    await db.flush()

    totals = _compute_recipe_totals(ingredient_objs, payload.servings)
    recipe.total_calories  = totals["total_calories"]
    recipe.total_protein_g = totals["total_protein_g"]
    recipe.total_fat_g     = totals["total_fat_g"]
    recipe.total_carbs_g   = totals["total_carbs_g"]
    recipe.total_fiber_g   = totals["total_fiber_g"]

    await db.flush()
    return recipe


@app.get("/recipes", response_model=List[RecipeResponse])
async def list_recipes(
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Return all recipes created by the current user."""
    result = await db.execute(
        select(Recipe).where(Recipe.user_id == current_user.id)
        .order_by(Recipe.created_at.desc())
    )
    return result.scalars().all()


@app.get("/recipes/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(
    recipe_id:    uuid.UUID,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Get a single recipe by ID."""
    result = await db.execute(
        select(Recipe).where(
            Recipe.id      == recipe_id,
            Recipe.user_id == current_user.id,
        )
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    return recipe


@app.patch("/recipes/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(
    recipe_id:    uuid.UUID,
    payload:      RecipeUpdateRequest,
    current_user: User           = Depends(get_current_user),
    db:           AsyncSession   = Depends(get_db),
):
    """Update a recipe's name, description, servings, or ingredients."""
    result = await db.execute(
        select(Recipe).where(
            Recipe.id      == recipe_id,
            Recipe.user_id == current_user.id,
        )
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    if payload.name        is not None: recipe.name        = payload.name
    if payload.description is not None: recipe.description = payload.description
    if payload.servings    is not None: recipe.servings    = payload.servings

    if payload.ingredients is not None:
        # Delete existing ingredients and replace
        existing = await db.execute(
            select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id)
        )
        for ing in existing.scalars().all():
            await db.delete(ing)

        await db.flush()

        ingredient_objs = []
        for ing in payload.ingredients:
            obj = RecipeIngredient(
                recipe_id  = recipe.id,
                fdc_id     = ing.fdc_id,
                food_name  = ing.food_name,
                brand_name = ing.brand_name,
                amount_g   = ing.amount_g,
                calories   = ing.calories,
                protein_g  = ing.protein_g,
                fat_g      = ing.fat_g,
                carbs_g    = ing.carbs_g,
                fiber_g    = ing.fiber_g,
            )
            db.add(obj)
            ingredient_objs.append(obj)

        await db.flush()

        totals = _compute_recipe_totals(ingredient_objs, recipe.servings)
        recipe.total_calories  = totals["total_calories"]
        recipe.total_protein_g = totals["total_protein_g"]
        recipe.total_fat_g     = totals["total_fat_g"]
        recipe.total_carbs_g   = totals["total_carbs_g"]
        recipe.total_fiber_g   = totals["total_fiber_g"]

    await db.flush()
    return recipe


@app.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    recipe_id:    uuid.UUID,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Delete a recipe and all its ingredients."""
    result = await db.execute(
        select(Recipe).where(
            Recipe.id      == recipe_id,
            Recipe.user_id == current_user.id,
        )
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    await db.delete(recipe)