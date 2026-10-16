import os

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase

from CLPainter.web.backend.app._config.settings import settings


class Base(DeclarativeBase):
    """所有数据库模型的声明基类。"""


DATABASE_PATH = Path(settings.DATA_DIR).parent / "instrument.db"

if DATABASE_PATH.exists() and not os.access(DATABASE_PATH, os.W_OK):
    DATABASE_URL = f"sqlite:///file:{DATABASE_PATH}?mode=ro&immutable=1&uri=true"
else:
    DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def configure_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
