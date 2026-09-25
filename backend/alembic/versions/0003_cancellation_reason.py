"""bookings.cancellation_reason — optional cancel-cause field (contract delta 2026-09-23)

Nullable enum column: 'hold_expired' | 'customer' | NULL.
- salon-integration's hold-expiry sweep sets 'hold_expired' (reflective).
- Customer POST /bookings/{id}/cancel success sets 'customer'.

Revision ID: 0003_cancellation_reason
Revises: 0002_masters_bookings
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_cancellation_reason"
down_revision: Union[str, None] = "0002_masters_bookings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("cancellation_reason", sa.String(length=32), nullable=True),
    )
    # Base.metadata naming convention renders this as ck_bookings_cancellation_reason
    # (same rendering the ORM model's CheckConstraint gets via create_all).
    op.create_check_constraint(
        "cancellation_reason",
        "bookings",
        "cancellation_reason is null "
        "or cancellation_reason in ('hold_expired', 'customer')",
    )


def downgrade() -> None:
    # Naming convention applies to drops too — bare name renders as
    # ck_bookings_cancellation_reason (same as upgrade()).
    op.drop_constraint("cancellation_reason", "bookings", type_="check")
    op.drop_column("bookings", "cancellation_reason")
