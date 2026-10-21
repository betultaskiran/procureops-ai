import pytest
from app.db.session import engine
from app.core.rate_limit import reset_rate_limit_store


@pytest.fixture(autouse=True)
async def cleanup_db_connections():
    reset_rate_limit_store()
    yield
    await engine.dispose()
    reset_rate_limit_store()
