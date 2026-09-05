"""SQLAlchemy engine / session management (SQLAlchemy 2.0 style).

Development/test runs on SQLite; production targets PostgreSQL via DATABASE_URL.
"""
from collections.abc import Generator
from datetime import UTC

from sqlalchemy import DateTime, create_engine, event, types
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class UTCDateTime(types.TypeDecorator):
    """Always store naive-UTC, always return tz-aware UTC — portable across SQLite/Postgres."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:

            value = value.replace(tzinfo=UTC)
        return value

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)

if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
