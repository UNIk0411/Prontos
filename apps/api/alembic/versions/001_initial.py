from alembic import op
import sqlalchemy as sa


revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'workers',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('cpu_capacity', sa.Float(), nullable=False),
        sa.Column('memory_capacity', sa.Float(), nullable=False),
        sa.Column('supported_workloads', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='online'),
        sa.Column('current_allocations', sa.JSON(), nullable=True),
        sa.Column('health', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'experiments',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=False),
        sa.Column('estimated_runtime', sa.Float(), nullable=False),
        sa.Column('cpu', sa.Float(), nullable=False),
        sa.Column('memory', sa.Float(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('deadline', sa.String(), nullable=True),
        sa.Column('budget', sa.Float(), nullable=False),
        sa.Column('dependencies', sa.JSON(), nullable=False),
        sa.Column('dataset_ref', sa.String(), nullable=False),
        sa.Column('config_hash', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='ready'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('(CURRENT_TIMESTAMP)')),
    )
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('experiment_id', sa.String(), sa.ForeignKey('experiments.id'), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('queued_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('cpu', sa.Float(), nullable=False),
        sa.Column('memory', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('progress', sa.Float(), nullable=False, server_default='0'),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('output_artifacts', sa.JSON(), nullable=True),
        sa.Column('cache_status', sa.String(), nullable=True),
        sa.Column('scheduler_metadata', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('jobs')
    op.drop_table('experiments')
    op.drop_table('workers')
