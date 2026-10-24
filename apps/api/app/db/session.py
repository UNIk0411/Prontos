from pathlib import Path
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def build_engine(database_url: str, db_path: str) -> Engine:
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
        elif database_url.startswith('postgresql://'):
            database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
        return create_engine(database_url, pool_pre_ping=True, future=True)

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


engine = build_engine(settings.database_url, settings.db_path)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
