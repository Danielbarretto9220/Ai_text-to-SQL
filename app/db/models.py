"""
SQLAlchemy ORM models for the meta.* schema.

Mirrors the live DDL in METADATA/01-17_*.sql column-for-column (verified
against information_schema + pg_constraint, not just the SQL source).
METADATA/*.sql remains the source of truth for schema changes — these
models are not used to create/migrate the schema (no Base.metadata.create_all()
call anywhere), only to query/write it with typed objects instead of raw
tuples. If the DDL changes, update both.

Usage:
    from app.db.session import get_session
    from app.db.models import MetaTable

    with get_session() as session:
        loans_table = session.query(MetaTable).filter_by(table_name="loans").first()
        print(loans_table.business_description)
        for column in loans_table.columns:
            print(column.column_name, column.data_type)

See enterprise-text-to-sql-architecture.md §1.2.
"""

from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, BigInteger, CheckConstraint, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db.session import get_session


class Base(DeclarativeBase):
    pass


class MetaTable(Base):
    """meta.tables — one row per warehouse table/view (METADATA/02, 03, 07)."""

    __tablename__ = "tables"
    __table_args__ = {"schema": "meta"}

    table_id: Mapped[int] = mapped_column(primary_key=True)
    schema_name: Mapped[str] = mapped_column(Text, nullable=False)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[Optional[str]] = mapped_column(Text)
    business_description: Mapped[Optional[str]] = mapped_column(Text)
    row_count_estimate: Mapped[Optional[int]] = mapped_column(BigInteger)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    columns: Mapped[list["MetaColumn"]] = relationship(back_populates="table")

    def __repr__(self) -> str:
        return f"<MetaTable {self.schema_name}.{self.table_name}>"


class MetaColumn(Base):
    """meta.columns — one row per column of a meta.tables row (METADATA/02, 04, 08, 09, 10)."""

    __tablename__ = "columns"
    __table_args__ = {"schema": "meta"}

    column_id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[Optional[int]] = mapped_column(ForeignKey("meta.tables.table_id"))
    column_name: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[Optional[str]] = mapped_column(Text)
    nullable: Mapped[Optional[bool]] = mapped_column()
    is_pk: Mapped[Optional[bool]] = mapped_column(server_default=text("false"))
    is_fk: Mapped[Optional[bool]] = mapped_column(server_default=text("false"))
    fk_ref_table: Mapped[Optional[str]] = mapped_column(Text)
    fk_ref_column: Mapped[Optional[str]] = mapped_column(Text)
    business_description: Mapped[Optional[str]] = mapped_column(Text)
    business_synonyms: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    sample_values: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    table: Mapped[Optional["MetaTable"]] = relationship(back_populates="columns")

    def __repr__(self) -> str:
        return f"<MetaColumn {self.column_name}>"


class MetaRelationship(Base):
    """meta.relationships — FK-derived join paths between warehouse tables (METADATA/02, 05)."""

    __tablename__ = "relationships"
    __table_args__ = {"schema": "meta"}

    relationship_id: Mapped[int] = mapped_column(primary_key=True)
    from_table: Mapped[Optional[str]] = mapped_column(Text)
    from_column: Mapped[Optional[str]] = mapped_column(Text)
    to_table: Mapped[Optional[str]] = mapped_column(Text)
    to_column: Mapped[Optional[str]] = mapped_column(Text)
    relationship_type: Mapped[Optional[str]] = mapped_column(Text)
    verified: Mapped[Optional[bool]] = mapped_column(server_default=text("false"))
    source: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<MetaRelationship {self.from_table}.{self.from_column} -> {self.to_table}.{self.to_column}>"


class MetaBusinessGlossary(Base):
    """meta.business_glossary — business term -> table/column/synonym mapping (METADATA/02, 06)."""

    __tablename__ = "business_glossary"
    __table_args__ = {"schema": "meta"}

    term_id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[Optional[str]] = mapped_column(Text)
    maps_to_tables: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    maps_to_columns: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    synonyms: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))

    def __repr__(self) -> str:
        return f"<MetaBusinessGlossary {self.term}>"


class MetaQueryPattern(Base):
    """meta.query_patterns — few-shot NL question -> SQL template bank (METADATA/11, 12)."""

    __tablename__ = "query_patterns"
    __table_args__ = {"schema": "meta"}

    pattern_id: Mapped[int] = mapped_column(primary_key=True)
    intent_description: Mapped[Optional[str]] = mapped_column(Text)
    example_question: Mapped[Optional[str]] = mapped_column(Text)
    sql_template: Mapped[Optional[str]] = mapped_column(Text)
    tables_used: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))

    def __repr__(self) -> str:
        return f"<MetaQueryPattern {self.example_question!r}>"


class MetaDocumentEmbedding(Base):
    """meta.document_embeddings — RAG documents + pgvector embeddings (METADATA/02; written by workers/reindex_embeddings.py)."""

    __tablename__ = "document_embeddings"
    __table_args__ = {"schema": "meta"}

    document_id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_type: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384))
    # Python attribute can't be named "metadata" — that's reserved by
    # DeclarativeBase for the schema registry. DB column name is unaffected.
    metadata_json: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<MetaDocumentEmbedding {self.document_id}>"


class MetaChangeLog(Base):
    """meta.change_log — audit trail written by the log_change() trigger (METADATA/13)."""

    __tablename__ = "change_log"
    __table_args__ = {"schema": "meta"}

    change_id: Mapped[int] = mapped_column(primary_key=True)
    schema_name: Mapped[str] = mapped_column(Text, nullable=False)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[Optional[int]] = mapped_column()
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(Text, server_default=text("current_user"))
    changed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    old_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    def __repr__(self) -> str:
        return f"<MetaChangeLog {self.table_name}#{self.record_id} {self.operation}>"


class MetaPromptVersion(Base):
    """meta.prompt_versions — versioned LLM system prompts (METADATA/14, 15)."""

    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_name", "version_number"),
        {"schema": "meta"},
    )

    version_id: Mapped[int] = mapped_column(primary_key=True)
    prompt_name: Mapped[str] = mapped_column(Text, nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[Optional[bool]] = mapped_column(server_default=text("false"))
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<MetaPromptVersion {self.prompt_name} v{self.version_number}>"


class MetaBusinessRule(Base):
    """meta.business_rules — guardrail rules for app/validation/guardrails.py (METADATA/16, 17)."""

    __tablename__ = "business_rules"
    __table_args__ = (
        UniqueConstraint("rule_name"),
        CheckConstraint("severity IN ('error', 'warning')", name="chk_business_rules_severity"),
        CheckConstraint(
            "rule_type IN ('forbidden_aggregation', 'required_filter', 'value_constraint', "
            "'join_constraint', 'pii_exposure')",
            name="chk_business_rules_type",
        ),
        {"schema": "meta"},
    )

    rule_id: Mapped[int] = mapped_column(primary_key=True)
    rule_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    applies_to_tables: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    applies_to_columns: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    rule_logic: Mapped[dict] = mapped_column(JSONB, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'error'"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"<MetaBusinessRule {self.rule_name}>"


def main():
    """Smoke-test every model against the live database."""

    print("Connecting to PostgreSQL...")

    session = get_session()

    print("Connected successfully.\n")

    try:
        counts = {
            "Tables": session.query(MetaTable).count(),
            "Columns": session.query(MetaColumn).count(),
            "Relationships": session.query(MetaRelationship).count(),
            "Glossary terms": session.query(MetaBusinessGlossary).count(),
            "Query patterns": session.query(MetaQueryPattern).count(),
            "Document embeddings": session.query(MetaDocumentEmbedding).count(),
            "Change log entries": session.query(MetaChangeLog).count(),
            "Prompt versions": session.query(MetaPromptVersion).count(),
            "Business rules": session.query(MetaBusinessRule).count(),
        }

        print("ORM models loaded successfully.")
        print("--------------------------------")
        for label, count in counts.items():
            print(f"{label:<20}: {count}")

        loans_table = session.query(MetaTable).filter_by(table_name="loans").first()
        if loans_table:
            print(f"\nExample relationship(): loans table has {len(loans_table.columns)} columns")

    finally:
        session.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
