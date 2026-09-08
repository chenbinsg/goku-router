from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

DATABASE_URL = settings.database_url

# The pool is sized for the router's actual shape: every completion writes a
# request_logs row, so concurrent callers are concurrent connections. The sizing
# used to sit in the non-sqlite branch only, which left the sqlite default of
# 5 + 10 in place — and SQLAlchemy 2.0 uses a QueuePool for file-backed sqlite
# too, so that default is a real ceiling rather than a formality. Six workflow
# nodes running in parallel filled it, waited out pool_timeout and came back as
# "All LLM providers are currently unavailable", which reads like an outage and
# is a connection queue.
engine_kwargs = {
    "pool_size": 20,
    "max_overflow": 40,
    "pool_timeout": 30,
    "pool_recycle": 1800,
}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
