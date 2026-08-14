"""
Connectivity, the six meta.* loaders, and ORM models against live DDL.

Counts are re-derived from the loaders themselves rather than hardcoded,
per docs/API_AND_TESTING_PLAN.md B3 ("re-derive these rather than
hardcoding blindly if the data has changed") — what this file actually
checks is that every loader/model agrees on the same number, and that a
handful of known-static rows exist.
"""

from app.db.metadata_loader import (
    load_business_glossary,
    load_business_rules,
    load_column_metadata,
    load_query_patterns,
    load_relationship_metadata,
    load_table_metadata,
)
from app.db.models import (
    MetaBusinessGlossary,
    MetaBusinessRule,
    MetaColumn,
    MetaQueryFeedback,
    MetaQueryLog,
    MetaQueryPattern,
    MetaRelationship,
    MetaTable,
)
from app.db.session import get_session


def test_connectivity(db_connection):
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT 1;")
        assert cursor.fetchone() == (1,)


def test_loaders_return_rows(db_connection):
    assert len(load_table_metadata(db_connection)) >= 5
    assert len(load_column_metadata(db_connection)) >= 30
    assert len(load_relationship_metadata(db_connection)) >= 6
    assert len(load_business_glossary(db_connection)) >= 12
    assert len(load_query_patterns(db_connection)) >= 15
    assert len(load_business_rules(db_connection)) >= 8


def test_known_tables_present(db_connection):
    table_names = {row[2] for row in load_table_metadata(db_connection)}
    assert {"branches", "customers", "loan_officers", "loans", "emi_payments"} <= table_names


def test_orm_models_match_loader_counts(db_connection):
    """ORM read path (app/db/models.py) must agree with the raw-SQL
    loader path (app/db/metadata_loader.py) — both read the same
    meta.* tables, just through different access layers
    (app/db/session.py's get_session() vs. get_connection())."""

    session = get_session()
    try:
        assert session.query(MetaTable).count() == len(load_table_metadata(db_connection))
        assert session.query(MetaColumn).count() == len(load_column_metadata(db_connection))
        assert session.query(MetaRelationship).count() == len(load_relationship_metadata(db_connection))
        assert session.query(MetaBusinessGlossary).count() == len(load_business_glossary(db_connection))
        assert session.query(MetaQueryPattern).count() == len(load_query_patterns(db_connection))
        assert session.query(MetaBusinessRule.rule_id).filter(MetaBusinessRule.is_active).count() == len(
            load_business_rules(db_connection)
        )
    finally:
        session.close()


def test_orm_query_log_and_feedback_models_are_queryable():
    """METADATA/20's tables are new — just prove the ORM models resolve
    against live DDL (column names/types), not any particular row count."""

    session = get_session()
    try:
        session.query(MetaQueryLog).count()
        session.query(MetaQueryFeedback).count()
    finally:
        session.close()
