from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from database.models import Base


_engine = None
_SessionLocal = None


def init_db(database_url: str = "sqlite:///borsabot.db") -> None:
    global _engine, _SessionLocal
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_engine(
        database_url,
        connect_args=connect_args,
        echo=False,
    )
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


@contextmanager
def get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Veritabanı henüz başlatılmadı. init_db() çağırın.")
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
