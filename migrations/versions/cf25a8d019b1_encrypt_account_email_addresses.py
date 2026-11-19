"""add encrypted account email storage

Revision ID: cf25a8d019b1
Revises: bcdcc75076a1
Create Date: 2026-11-18
"""
from alembic import op
import sqlalchemy as sa


revision = "cf25a8d019b1"
down_revision = "bcdcc75076a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_ciphertext", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_ciphertext")
