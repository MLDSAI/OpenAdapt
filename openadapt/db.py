"""
db.py

This module provides functionality for connecting to and interacting with
the database.

"""

import sqlalchemy as sa
from dictalchemy import DictableModel
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData
from sqlalchemy.ext.declarative import declarative_base

from openadapt.config import DB_ECHO, DB_URL
from openadapt.utils import EMPTY, row2dict


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class BaseModel(DictableModel):
    """The base model for database tables."""

    __abstract__ = True

    def __repr__(self):
        """Return a string representation of the model object."""
        params = ", ".join(
            f"{k}={v!r}"  # !r converts value to string using repr (adds quotes)
            for k, v in row2dict(self, follow=False).items()
            if v not in EMPTY
        )
        return f"{self.__class__.__name__}({params})"


def get_engine():
    """Create and return a database engine."""
    engine = sa.create_engine(
        DB_URL,
        echo=DB_ECHO,
    )
    return engine


def get_base(engine):
    """Create and return the base model with the provided engine."""
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    Base = declarative_base(
        cls=BaseModel,
        bind=engine,
        metadata=metadata,
    )
    return Base


engine = get_engine()
Base = get_base(engine)
Session = sessionmaker(bind=engine)
