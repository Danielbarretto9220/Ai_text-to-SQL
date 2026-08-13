"""Shared PostgreSQL connection handling for the app and workers."""

import os

import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


def get_connection():
    """Create a raw psycopg2 connection to the PostgreSQL database using env vars.

    Used by the existing hand-written SQL modules (metadata_loader.py,
    document_builder.py, reindex_embeddings.py, vector_search.py).
    """

    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def get_engine():
    """Create a SQLAlchemy engine using the same env vars as get_connection().

    Used by app/db/models.py for ORM-based access to meta.*. Built via
    URL.create() rather than an f-string DSN so special characters in
    DB_PASSWORD (e.g. "@") are percent-encoded correctly.
    """

    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME"),
    )

    return create_engine(url)


def get_session() -> Session:
    """Create a new SQLAlchemy ORM session bound to get_engine()."""

    return sessionmaker(bind=get_engine())()
