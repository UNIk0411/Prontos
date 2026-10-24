import os
import tempfile
from pathlib import Path

import pytest


test_database = Path(tempfile.gettempdir()) / f'prontos-api-tests-{os.getpid()}.db'
os.environ['PRONTOS_DATABASE_URL'] = f'sqlite:///{test_database.as_posix()}'
os.environ['PRONTOS_ENV'] = 'development'


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    from app.db.session import engine

    engine.dispose()
    test_database.unlink(missing_ok=True)
