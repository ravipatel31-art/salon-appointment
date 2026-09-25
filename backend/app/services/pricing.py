"""Pricing / advance rules (AGENTS.md):

- Fixed services: total = price (+ addons); advance = ceil(total * 0.5); balance = total - advance.
- Hair color (price_type=variable_advance): advance = ₹100 flat online.
- Duration: service.duration + sum(addon durations) minutes.
- Amounts are rupees everywhere except razorpay_amount (paise).
"""

from __future__ import annotations

import math

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Service, ServiceAddon

FLAT_ADVANCE_RUPEES = 100  # hair color online advance


def resolve_addons(db: Session, addon_ids: list[str] | None) -> list[ServiceAddon]:
    """Deduplicate, drop blanks, load active add-on rows (400 on unknown/inactive)."""
    rows: list[ServiceAddon] = []
    seen: set[str] = set()
    for raw in addon_ids or []:
        key = raw.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        row = db.get(ServiceAddon, key)
        if row is None or not row.is_active:
            raise HTTPException(status_code=400, detail="unknown_addon")
        rows.append(row)
    return rows


def duration_minutes(service: Service, addons: list[ServiceAddon]) -> int:
    return service.duration_minutes + sum(a.duration_minutes for a in addons)


def compute_amounts(
    service: Service, addons: list[ServiceAddon]
) -> tuple[int, int, int]:
    """Return (total, advance, balance) in rupees."""
    total = service.price + sum(a.price for a in addons)
    if service.price_type == "variable_advance":
        advance = FLAT_ADVANCE_RUPEES
    else:
        advance = math.ceil(total * 0.5)
    balance = total - advance
    return total, advance, balance
