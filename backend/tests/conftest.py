from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db, get_session_factory
from app.main import app


def _make_test_engine() -> Engine:
    """Return a SQLite in-memory engine that shares one connection across
    sessions, so schema created on one session is visible to others."""
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture
def _engine() -> Generator[Engine, None, None]:
    engine = _make_test_engine()
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(_engine: Engine) -> Generator[Session, None, None]:
    TestingSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(_engine: Engine) -> Generator[TestClient, None, None]:
    TestingSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: TestingSession
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_session_factory, None)
