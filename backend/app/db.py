"""SQLAlchemy 2 engine, session factory, and FastAPI dependency.

Runtime targets PostgreSQL (AGENTS.md). Tests point DATABASE_URL at a
temporary SQLite file (see tests/conftest.py); the engine adapts driver args
for that case only.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

_connect_args: dict = {}
if _settings.database_url.startswith("sqlite"):
    # Test DB may be touched from FastAPI's threadpool.
    _connect_args = {"check_same_thread": False}

# Engine creation is lazy — no DB connection until first query.
engine = create_engine(
    _settings.database_url, pool_pre_ping=True, connect_args=_connect_args
)

if _settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_fk_pragma(dbapi_connection, connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped Session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
