from pydantic import BaseModel, Field

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    duration_minutes: int = Field(gt=0)
    price: int = Field(ge=0)
    price_type: str = Field(default="fixed", pattern="^(fixed|variable_advance)$")
    is_active: bool = True


class ServicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    price: int | None = Field(default=None, ge=0)
    price_type: str | None = Field(default=None, pattern="^(fixed|variable_advance)$")
    is_active: bool | None = None


class BarberIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    photo_url: str | None = Field(default=None, max_length=500)
    bio: str = ""
    specialties: list[str] = Field(default_factory=list)
    is_active: bool = True


class BarberPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    photo_url: str | None = Field(default=None, max_length=500)
    bio: str | None = None
    specialties: list[str] | None = None
    is_active: bool | None = None


class ScheduleRow(BaseModel):
    weekday: int = Field(ge=0, le=6)
    open_time: str = Field(pattern=TIME_PATTERN)
    close_time: str = Field(pattern=TIME_PATTERN)
    is_closed: bool = False
