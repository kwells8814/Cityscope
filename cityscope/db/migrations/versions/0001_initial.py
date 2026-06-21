"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-21

Creates the curated-config tables (city_alias, city_feed, gazetteer_city,
zip_code) and the operational city_fetch table. Hand-written to match
cityscope/db/models.py; once your DB is live you can use
`alembic revision --autogenerate` for subsequent changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "city_alias",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city_key", sa.String(length=80), nullable=False),
        sa.Column("subreddit", sa.String(length=120), nullable=False),
        sa.UniqueConstraint("city_key", "subreddit", name="uq_alias"),
    )
    op.create_index("ix_city_alias_city_key", "city_alias", ["city_key"])

    op.create_table(
        "city_feed",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city_key", sa.String(length=80), nullable=False),
        sa.Column("paper", sa.String(length=160), nullable=False),
        sa.Column("feed_url", sa.String(length=500), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("city_key", "feed_url", name="uq_feed"),
    )
    op.create_index("ix_city_feed_city_key", "city_feed", ["city_key"])

    op.create_table(
        "gazetteer_city",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("region", sa.String(length=20), nullable=False),
    )

    op.create_table(
        "zip_code",
        sa.Column("zip", sa.String(length=10), primary_key=True),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("region", sa.String(length=20), nullable=False),
    )

    op.create_table(
        "city_fetch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city_key", sa.String(length=120), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("region", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("happening_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("city_key", name="uq_city_fetch"),
    )
    op.create_index("ix_city_fetch_city_key", "city_fetch", ["city_key"])
    op.create_index("ix_city_fetch_fetched_at", "city_fetch", ["fetched_at"])


def downgrade() -> None:
    op.drop_table("city_fetch")
    op.drop_table("zip_code")
    op.drop_table("gazetteer_city")
    op.drop_index("ix_city_feed_city_key", table_name="city_feed")
    op.drop_table("city_feed")
    op.drop_index("ix_city_alias_city_key", table_name="city_alias")
    op.drop_table("city_alias")
