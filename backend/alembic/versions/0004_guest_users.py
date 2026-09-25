"""guest booking users — users.is_guest + nullable email (phase 8, contract 2026-09-24)

Guest checkout (POST /bookings without Bearer) find-or-creates a customer by
phone. New pure-guest rows carry ``is_guest=true``, a random unusable
``password_hash`` and ``email=NULL`` (chosen scheme: **nullable email**, not a
synthetic unique address — UNIQUE permits multiple NULLs on PostgreSQL).

Revision ID: 0004_guest_users
Revises: 0003_cancellation_reason
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_guest_users"
down_revision: Union[str, None] = "0003_cancellation_reason"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_guest", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column(
        "users", "email", existing_type=sa.String(length=255), nullable=True
    )


def downgrade() -> None:
    # Backfill synthetic addresses so the NOT NULL unique constraint can be restored.
    op.execute(
        "UPDATE users SET email = 'guest+' || id || '@guest.invalid' "
        "WHERE email IS NULL"
    )
    op.alter_column(
        "users", "email", existing_type=sa.String(length=255), nullable=False
    )
    op.drop_column("users", "is_guest")
