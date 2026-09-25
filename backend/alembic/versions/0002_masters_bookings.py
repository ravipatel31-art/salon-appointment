"""masters + bookings schema (phases 1/2/4)

Revision ID: 0002_masters_bookings
Revises: 0001_base
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_masters_bookings"
down_revision: Union[str, None] = "0001_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role in ('customer', 'admin')", name="ck_users_role"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("phone", name="uq_users_phone"),
    )

    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("price_type", sa.String(length=24), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "price_type in ('fixed', 'variable_advance')",
            name="ck_services_price_type",
        ),
        sa.CheckConstraint("price >= 0", name="ck_services_price_nonneg"),
        sa.CheckConstraint("duration_minutes > 0", name="ck_services_duration_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_services"),
        sa.UniqueConstraint("name", name="uq_services_name"),
    )

    op.create_table(
        "service_addons",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price >= 0", name="ck_service_addons_price_nonneg"),
        sa.CheckConstraint(
            "duration_minutes > 0", name="ck_service_addons_duration_positive"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_service_addons"),
    )

    op.create_table(
        "barbers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("photo_url", sa.String(length=500), nullable=True),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("specialties", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_barbers"),
    )

    op.create_table(
        "barber_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barber_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("open_time", sa.Time(), nullable=False),
        sa.Column("close_time", sa.Time(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.CheckConstraint("weekday between 0 and 6", name="ck_barber_schedules_weekday_range"),
        sa.ForeignKeyConstraint(
            ["barber_id"],
            ["barbers.id"],
            name="fk_barber_schedules_barber_id_barbers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_barber_schedules"),
        sa.UniqueConstraint("barber_id", "weekday", name="uq_barber_schedules_barber_id"),
    )
    op.create_index(
        "ix_barber_schedules_barber_id", "barber_schedules", ["barber_id"]
    )

    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_ref", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("barber_id", sa.Integer(), nullable=False),
        sa.Column("addons", sa.JSON(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("advance_amount", sa.Integer(), nullable=False),
        sa.Column("balance_amount", sa.Integer(), nullable=False),
        sa.Column("online_amount_paid", sa.Integer(), nullable=False),
        sa.Column("final_price_at_center", sa.Integer(), nullable=True),
        sa.Column("balance_due", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("razorpay_order_id", sa.String(length=64), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(length=64), nullable=True),
        sa.Column("razorpay_refund_id", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('pending_payment','confirmed','completed','cancelled','refunded','no_show')",
            name="ck_bookings_status",
        ),
        sa.CheckConstraint("advance_amount >= 0", name="ck_bookings_advance_nonneg"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_bookings_user_id_users"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name="fk_bookings_service_id_services"),
        sa.ForeignKeyConstraint(["barber_id"], ["barbers.id"], name="fk_bookings_barber_id_barbers"),
        sa.PrimaryKeyConstraint("id", name="pk_bookings"),
        sa.UniqueConstraint("booking_ref", name="uq_bookings_booking_ref"),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_barber_id", "bookings", ["barber_id"])
    op.create_index("ix_bookings_razorpay_order_id", "bookings", ["razorpay_order_id"])
    op.create_index("ix_bookings_razorpay_payment_id", "bookings", ["razorpay_payment_id"])
    op.create_index("ix_bookings_barber_window", "bookings", ["barber_id", "start_at", "end_at"])
    op.create_index("ix_bookings_user_start", "bookings", ["user_id", "start_at"])
    op.create_index("ix_bookings_status_expires", "bookings", ["status", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_bookings_status_expires", table_name="bookings")
    op.drop_index("ix_bookings_user_start", table_name="bookings")
    op.drop_index("ix_bookings_barber_window", table_name="bookings")
    op.drop_index("ix_bookings_razorpay_payment_id", table_name="bookings")
    op.drop_index("ix_bookings_razorpay_order_id", table_name="bookings")
    op.drop_index("ix_bookings_barber_id", table_name="bookings")
    op.drop_index("ix_bookings_user_id", table_name="bookings")
    op.drop_table("bookings")
    op.drop_index("ix_barber_schedules_barber_id", table_name="barber_schedules")
    op.drop_table("barber_schedules")
    op.drop_table("barbers")
    op.drop_table("service_addons")
    op.drop_table("services")
    op.drop_table("users")
