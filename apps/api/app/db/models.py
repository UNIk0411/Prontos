from datetime import datetime
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default='viewer')
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class Organization(Base):
    __tablename__ = 'organizations'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    cpu_quota: Mapped[float] = mapped_column(Float, nullable=False, default=16.0)
    memory_quota: Mapped[float] = mapped_column(Float, nullable=False, default=12.0)
    budget_quota: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class Worker(Base):
    __tablename__ = 'workers'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    cpu_capacity: Mapped[float] = mapped_column(Float, nullable=False)
    memory_capacity: Mapped[float] = mapped_column(Float, nullable=False)
    supported_workloads: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default='online')
    current_allocations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    health: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Experiment(Base):
    __tablename__ = 'experiments'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    estimated_runtime: Mapped[float] = mapped_column(Float, nullable=False)
    cpu: Mapped[float] = mapped_column(Float, nullable=False)
    memory: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline: Mapped[str | None] = mapped_column(String, nullable=True)
    budget: Mapped[float] = mapped_column(Float, nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dataset_ref: Mapped[str] = mapped_column(String, nullable=False)
    config_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default='ready')
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    jobs: Mapped[list['Job']] = relationship(back_populates='experiment')


class Job(Base):
    __tablename__ = 'jobs'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey('experiments.id'), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(ForeignKey('workers.id'), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu: Mapped[float] = mapped_column(Float, nullable=False)
    memory: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    output_artifacts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cache_status: Mapped[str | None] = mapped_column(String, nullable=True)
    scheduler_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    experiment: Mapped['Experiment'] = relationship(back_populates='jobs')
