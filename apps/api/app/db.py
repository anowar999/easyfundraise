from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

_s = get_settings()
engine = create_engine(
    _s.database_url,
    pool_pre_ping=True,
    pool_size=_s.db_pool_size,
    max_overflow=_s.db_max_overflow,
    pool_recycle=1800,  # recycle connections every 30 min (load balancers and PgBouncer drop idle ones)
    connect_args={"options": f"-c statement_timeout={_s.db_statement_timeout_ms}"} if _s.db_statement_timeout_ms else {},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
