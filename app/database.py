"""
Database Configuration
Location: app/database.py
"""

import logging
from sqlalchemy import create_engine, pool, event
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings

logger = logging.getLogger(__name__)

# ========== ENGINE ==========
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=pool.QueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)


# ========== SESSION ==========
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)


# ========== EVENT: CONNECTION ==========
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """
    Initialise la connexion DB (psycopg2 level)
    """
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("SET timezone TO 'UTC'")
        cursor.close()
    except Exception as e:
        logger.warning(f"Timezone setup failed: {e}")


# ========== EVENT: DISPOSE ==========
@event.listens_for(engine, "engine_disposed")
def receive_engine_disposed(engine):
    logger.info("Database engine disposed")


# ========== DEPENDENCY ==========
def get_db() -> Session:
    """
    FastAPI dependency
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# ========== INIT DB ==========
def init_db():
    """
    Create tables
    """
    from app.models import Base

    try:
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise


# ========== CLOSE DB ==========
def close_db():
    """
    Shutdown DB engine
    """
    try:
        engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database: {e}")