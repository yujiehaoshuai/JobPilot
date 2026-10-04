"""建立 Agent、岗位、审批和任务索引表；不修改 Phase 1 的旧表。"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    """迁移定义保持固定，未来修改模型时另建迁移版本。"""
    op.create_table("pending_actions", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False), sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("digest", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False), sa.UniqueConstraint("run_id", "job_id", name="uq_action_run_job"))
    op.create_table("agent_candidates", sa.Column("id", sa.String(), primary_key=True),
                    sa.Column("data", sa.Text(), nullable=False))
    op.create_table("agent_jobs", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False), sa.Column("source_job_id", sa.String(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False, unique=True), sa.Column("data", sa.Text(), nullable=False),
        sa.UniqueConstraint("source", "source_job_id", name="uq_agent_job_source"))
    op.create_table("agent_applications", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("candidate_id", sa.String(), sa.ForeignKey("agent_candidates.id"), nullable=False),
        sa.Column("job_id", sa.String(), sa.ForeignKey("agent_jobs.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("data", sa.Text(), nullable=False),
        sa.UniqueConstraint("candidate_id", "job_id", name="uq_agent_application"))
    op.create_table("agent_runs", sa.Column("id", sa.String(), primary_key=True),
                    sa.Column("status", sa.String(), nullable=False), sa.Column("data", sa.Text(), nullable=False))


def downgrade():
    """降级会删除 Agent 数据；生产环境必须先备份并由用户明确决定。"""
    for name in ["agent_runs", "agent_applications", "agent_jobs", "agent_candidates", "pending_actions"]:
        op.drop_table(name)
