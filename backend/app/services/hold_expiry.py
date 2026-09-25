"""Hold-expiry sweep — releases unpaid booking holds after the 12-minute TTL.

Contract/AGENTS rule: ``pending_payment`` holds expire in 12 minutes
(``expires_at``). Expired holds are transitioned to ``cancelled`` with reason
``hold_expired`` (``cancellation_reason`` column set when present — see the
CONTRACT_CHANGE proposal; status alone is contract-valid).

Mechanisms:
- ``sweep_expired_holds(db=None)`` — the core sweep; callable from anywhere
  (webhook endpoint does an on-read sweep, create_order does a best-effort sweep,
  tests call it directly).
- ``start_hold_expiry_worker()`` — optional background daemon thread (idempotent),
  auto-started on import unless ``HOLD_EXPIRY_WORKER=0`` or running under pytest.
  Interval: ``HOLD_EXPIRY_INTERVAL_SECONDS`` (default 30).

Owned by salon-integration (phase 3/6).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import MetaData, Table, inspect, update
from sqlalchemy.orm import Session

logger = logging.getLogger("app.hold_expiry")

_REASON_COLUMN = "cancellation_reason"
_REASON_HOLD_EXPIRED = "hold_expired"

_worker_lock = threading.Lock()
_worker_started = False


def sweep_expired_holds(db: Optional[Session] = None) -> int:
    """Cancel ``pending_payment`` bookings whose ``expires_at`` has passed.

    Returns the number of holds released. Missing table/columns → 0.
    When ``db`` is None a private session is opened and committed/closed;
    otherwise the caller owns commit/close (partial-request safe).
    Raises on unexpected database errors so callers can decide to fail/retry.
    """
    own_session = db is None
    session = db
    if own_session:
        from app.db import SessionLocal

        session = SessionLocal()
    assert session is not None
    try:
        bind = session.get_bind()
        try:
            if not inspect(bind).has_table("bookings"):
                return 0
            table = Table("bookings", MetaData(), autoload_with=bind)
        except Exception:  # noqa: BLE001 — table not created yet (pre-migration)
            logger.debug("hold sweep: bookings table unavailable", exc_info=True)
            return 0

        if "status" not in table.c or "expires_at" not in table.c:
            logger.debug("hold sweep: bookings table missing status/expires_at columns")
            return 0

        now = datetime.now(timezone.utc)
        values: dict = {"status": "cancelled"}
        if _REASON_COLUMN in table.c:
            values[_REASON_COLUMN] = _REASON_HOLD_EXPIRED

        stmt = (
            update(table)
            .where(table.c["status"] == "pending_payment")
            .where(table.c["expires_at"] <= now)
            .values(**values)
        )
        result = session.execute(stmt)
        count = int(result.rowcount or 0)
        session.commit()
        if count:
            logger.info("hold sweep: cancelled %d expired pending_payment hold(s)", count)
        return count
    except Exception:
        if own_session:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        raise
    finally:
        if own_session:
            session.close()


def start_hold_expiry_worker(interval_seconds: Optional[float] = None) -> bool:
    """Start the background sweep thread (idempotent). Returns True if running."""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return True
        if interval_seconds is None:
            try:
                interval_seconds = float(os.getenv("HOLD_EXPIRY_INTERVAL_SECONDS", "30"))
            except ValueError:
                interval_seconds = 30.0
        thread = threading.Thread(
            target=_worker_loop,
            args=(interval_seconds,),
            name="hold-expiry-worker",
            daemon=True,
        )
        thread.start()
        _worker_started = True
        logger.info("hold-expiry worker started (interval=%.1fs)", interval_seconds)
        return True


def _worker_loop(interval_seconds: float) -> None:
    # Sleep first: let the app finish startup/migrations before the first sweep.
    while True:
        time.sleep(interval_seconds)
        try:
            sweep_expired_holds()
        except Exception:  # noqa: BLE001 — worker must never die
            logger.warning("hold-expiry sweep failed", exc_info=True)


def _auto_start_worker() -> None:
    flag = os.getenv("HOLD_EXPIRY_WORKER", "1").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return
    if "pytest" in sys.modules:
        return  # tests drive sweeps explicitly
    try:
        start_hold_expiry_worker()
    except Exception:  # noqa: BLE001
        logger.debug("hold-expiry worker auto-start skipped", exc_info=True)


_auto_start_worker()
