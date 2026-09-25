from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BookingCreate(BaseModel):
    service_id: int
    addons: list[str] = Field(default_factory=list)
    barber_id: int
    start_at: datetime
    notes: str = ""
    # Guest checkout (CONTRACT §Bookings): required only when the request is
    # unauthenticated; ignored when a valid Bearer token is present. Kept
    # permissive here so validation can return 400 guest_identity_required
    # from the route (Flutter parity) instead of a Pydantic 422.
    guest_name: str | None = None
    guest_phone: str | None = None


class AdminBookingPatch(BaseModel):
    action: Literal["complete", "no_show"]
    final_price_at_center: int | None = Field(default=None, ge=1)
