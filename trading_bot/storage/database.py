"""Database engine and session management for SQLite / PostgreSQL."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from trading_bot.storage.models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine(db_url: str = "sqlite:///trading_bot.db") -> Engine:
    """Get or create singleton SQLAlchemy Engine."""
    global _engine, _SessionFactory
    if _engine is None:
        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        _engine = create_engine(db_url, connect_args=connect_args, echo=False)
        _SessionFactory = sessionmaker(bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return _engine


def init_db(db_url: str = "sqlite:///trading_bot.db") -> None:
    """Create all database tables if they do not exist."""
    engine = get_engine(db_url)
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session(db_url: str = "sqlite:///trading_bot.db") -> Generator[Session, None, None]:
    """Provide a transactional database session scope."""
    if _SessionFactory is None:
        get_engine(db_url)
    assert _SessionFactory is not None
    session: Session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_db_engine() -> None:
    """Reset engine and sessionmaker (used primarily in tests)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
