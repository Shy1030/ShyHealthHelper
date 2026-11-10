from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, root_validator, validator


class ProfileUpdate(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=30)
    sex: Optional[Literal["female", "male", "other"]] = None
    birth_year: Optional[int] = Field(default=None, ge=1900, le=date.today().year)
    height_cm: Optional[float] = Field(default=None, ge=80, le=250)
    weight_kg: Optional[float] = Field(default=None, ge=25, le=300)
    activity_level: Optional[
        Literal["sedentary", "light", "moderate", "active", "very_active"]
    ] = None
    goal: Optional[Literal["lose", "maintain", "gain"]] = None
    target_weight_kg: Optional[float] = Field(default=None, ge=25, le=300)
    target_date: Optional[date] = None
    injuries: Optional[str] = Field(default=None, max_length=500)

    @validator("nickname", "injuries")
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class PeriodCreate(BaseModel):
    start_date: date
    end_date: Optional[date] = None
    flow: Literal["light", "medium", "heavy"] = "medium"
    symptoms: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=500)

    @root_validator(skip_on_failure=True)
    def check_range(cls, values):
        start = values.get("start_date")
        end = values.get("end_date")
        if end is not None and start is not None:
            if end < start:
                raise ValueError("结束日期不能早于开始日期")
            if (end - start).days + 1 > 15:
                raise ValueError("单次经期不能超过 15 天，请检查日期")
        return values

    @validator("symptoms", "notes")
    def strip_text(cls, value):
        return value.strip()


class PeriodUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    flow: Optional[Literal["light", "medium", "heavy"]] = None
    symptoms: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=500)


class BodyRecordCreate(BaseModel):
    record_date: date = Field(default_factory=date.today)
    weight_kg: Optional[float] = Field(default=None, ge=25, le=300)
    body_fat_pct: Optional[float] = Field(default=None, ge=1, le=70)
    muscle_kg: Optional[float] = Field(default=None, ge=0, le=150)
    waist_cm: Optional[float] = Field(default=None, ge=30, le=250)
    sleep_hours: Optional[float] = Field(default=None, ge=0, le=24)
    resting_hr: Optional[int] = Field(default=None, ge=30, le=220)
    steps: Optional[int] = Field(default=None, ge=0, le=200000)
    notes: str = Field(default="", max_length=300)
    source: Literal["manual", "xiaomi", "screenshot"] = "manual"

    @root_validator(skip_on_failure=True)
    def require_measurement(cls, values):
        keys = (
            "weight_kg",
            "body_fat_pct",
            "muscle_kg",
            "waist_cm",
            "sleep_hours",
            "resting_hr",
            "steps",
        )
        if all(values.get(key) is None for key in keys):
            raise ValueError("请至少填写一项身体数据")
        return values

    @validator("notes")
    def strip_text(cls, value):
        return value.strip()


class ExerciseLogCreate(BaseModel):
    log_date: date = Field(default_factory=date.today)
    start_time: Optional[str] = Field(default=None, max_length=10)
    activity: str = Field(default="运动", min_length=1, max_length=40)
    duration_min: Optional[float] = Field(default=None, ge=0, le=1440)
    calories: Optional[float] = Field(default=None, ge=0, le=20000)
    distance_km: Optional[float] = Field(default=None, ge=0, le=2000)
    steps: Optional[int] = Field(default=None, ge=0, le=300000)
    avg_heart_rate: Optional[int] = Field(default=None, ge=0, le=250)
    notes: str = Field(default="", max_length=300)
    source: Literal["manual", "screenshot", "xiaomi"] = "manual"

    @validator("activity", "notes")
    def strip_text(cls, value):
        return value.strip()


class ExerciseDescribeRequest(BaseModel):
    description: str = Field(min_length=2, max_length=1000)
    log_date: date = Field(default_factory=date.today)

    @validator("description")
    def strip_description(cls, value):
        return value.strip()


class ExercisePlanRequest(BaseModel):
    preferences: str = Field(default="", max_length=1000)

    @validator("preferences")
    def strip_preferences(cls, value):
        return value.strip()


class MealRecommendRequest(BaseModel):
    target_date: date = Field(default_factory=date.today, alias="date")
    meal_type: Optional[Literal["breakfast", "lunch", "dinner", "snack"]] = None

    class Config:
        allow_population_by_field_name = True


class AISettingsUpdate(BaseModel):
    api_key: Optional[str] = Field(default=None, max_length=300)
    base_url: Optional[str] = Field(default=None, max_length=300)
    model: Optional[str] = Field(default=None, max_length=80)
    vision_model: Optional[str] = Field(default=None, max_length=80)

    @validator("api_key", "base_url", "model", "vision_model")
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    @validator("message")
    def strip_message(cls, value):
        return value.strip()


class XiaomiLoginRequest(BaseModel):
    username: str = Field(default="", max_length=100)
    password: str = Field(default="", max_length=200)
    region: Literal["cn", "abroad"] = "cn"
    captcha: Optional[str] = Field(default=None, max_length=20)
    twofa_code: Optional[str] = Field(default=None, max_length=20)
    attempt_id: Optional[str] = Field(default=None, max_length=64)

    @validator("username", "password", "captcha", "twofa_code", "attempt_id")
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @root_validator(skip_on_failure=True)
    def require_credentials(cls, values):
        if not values.get("attempt_id") and (
            not values.get("username") or not values.get("password")
        ):
            raise ValueError("请输入小米账号和密码")
        return values


class FinanceCreate(BaseModel):
    record_date: date = Field(default_factory=date.today)
    type: Literal["expense", "income"]
    amount: float = Field(gt=0, le=10_000_000)
    category: str = Field(min_length=1, max_length=20)
    note: str = Field(default="", max_length=200)
    source: Literal["web", "wechat", "manual"] = "web"
    external_id: Optional[str] = Field(default=None, max_length=100)

    @validator("category", "note")
    def strip_text(cls, value):
        return value.strip()
