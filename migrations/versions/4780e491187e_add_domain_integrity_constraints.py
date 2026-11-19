"""Add explicit database-level domain validation constraints.

Revision ID: 4780e491187e
Revises: 8aa139f84f09
"""
from alembic import op

revision = "4780e491187e"
down_revision = "8aa139f84f09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table keeps this migration portable to SQLite development DBs.
    with op.batch_alter_table("organisations") as batch:
        batch.create_check_constraint(
            "ck_organisation_type",
            "type IN ('pharmacy', 'pmv', 'hospital', 'hmo', 'donor', 'chw')",
        )
    with op.batch_alter_table("users") as batch:
        batch.create_check_constraint(
            "ck_user_role",
            "role IN ('admin', 'pharmacy', 'pmv', 'hospital', 'clinician', 'hmo', 'patient')",
        )
    with op.batch_alter_table("screenings") as batch:
        batch.create_check_constraint("ck_screening_systolic_range", "systolic BETWEEN 40 AND 300")
        batch.create_check_constraint("ck_screening_diastolic_range", "diastolic BETWEEN 20 AND 200")
        batch.create_check_constraint("ck_screening_systolic_gt_diastolic", "systolic > diastolic")
        batch.create_check_constraint(
            "ck_screening_result",
            "result IN ('positive', 'negative', 'inconclusive')",
        )
    with op.batch_alter_table("referrals") as batch:
        batch.create_check_constraint(
            "ck_referral_urgency",
            "urgency IN ('routine', 'urgent', 'emergency')",
        )
    with op.batch_alter_table("appointments") as batch:
        batch.create_check_constraint(
            "ck_appointment_status",
            "status IN ('proposed', 'booked', 'attended', 'missed', 'cancelled')",
        )
        batch.create_check_constraint(
            "ck_appointment_positive_duration",
            "slot_end > slot_start",
        )
    with op.batch_alter_table("follow_up_plans") as batch:
        batch.create_check_constraint(
            "ck_followup_status",
            "status IN ('pending', 'met', 'missed', 'cancelled')",
        )


def downgrade() -> None:
    with op.batch_alter_table("follow_up_plans") as batch:
        batch.drop_constraint("ck_followup_status", type_="check")
    with op.batch_alter_table("appointments") as batch:
        batch.drop_constraint("ck_appointment_positive_duration", type_="check")
        batch.drop_constraint("ck_appointment_status", type_="check")
    with op.batch_alter_table("referrals") as batch:
        batch.drop_constraint("ck_referral_urgency", type_="check")
    with op.batch_alter_table("screenings") as batch:
        batch.drop_constraint("ck_screening_result", type_="check")
        batch.drop_constraint("ck_screening_systolic_gt_diastolic", type_="check")
        batch.drop_constraint("ck_screening_diastolic_range", type_="check")
        batch.drop_constraint("ck_screening_systolic_range", type_="check")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_role", type_="check")
    with op.batch_alter_table("organisations") as batch:
        batch.drop_constraint("ck_organisation_type", type_="check")
