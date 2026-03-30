"""Initial schema with all 8 tables, triggers, indexes, and state seed data.

Revision ID: 001
Revises:
Create Date: 2026-03-28

"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Extensions ---
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- Enum Types ---
    doc_type_enum = postgresql.ENUM(
        "well_permit",
        "completion_report",
        "production_report",
        "spacing_order",
        "pooling_order",
        "plugging_report",
        "inspection_record",
        "incident_report",
        "unknown",
        "other",
        name="doc_type_enum",
        create_type=False,
    )
    document_status_enum = postgresql.ENUM(
        "discovered",
        "downloading",
        "downloaded",
        "classifying",
        "classified",
        "extracting",
        "extracted",
        "normalized",
        "stored",
        "flagged_for_review",
        "download_failed",
        "classification_failed",
        "extraction_failed",
        name="document_status_enum",
        create_type=False,
    )
    scrape_job_status_enum = postgresql.ENUM(
        "pending",
        "running",
        "completed",
        "failed",
        "cancelled",
        name="scrape_job_status_enum",
        create_type=False,
    )
    review_status_enum = postgresql.ENUM(
        "pending",
        "approved",
        "rejected",
        "corrected",
        name="review_status_enum",
        create_type=False,
    )
    well_status_enum = postgresql.ENUM(
        "active",
        "inactive",
        "plugged",
        "permitted",
        "drilling",
        "completed",
        "shut_in",
        "temporarily_abandoned",
        "unknown",
        name="well_status_enum",
        create_type=False,
    )

    doc_type_enum.create(op.get_bind(), checkfirst=True)
    document_status_enum.create(op.get_bind(), checkfirst=True)
    scrape_job_status_enum.create(op.get_bind(), checkfirst=True)
    review_status_enum.create(op.get_bind(), checkfirst=True)
    well_status_enum.create(op.get_bind(), checkfirst=True)

    # --- Table 1: states ---
    op.create_table(
        "states",
        sa.Column("code", sa.VARCHAR(2), primary_key=True),
        sa.Column("name", sa.VARCHAR(100), nullable=False),
        sa.Column("api_state_code", sa.VARCHAR(2), unique=True, nullable=False),
        sa.Column("tier", sa.SMALLINT(), nullable=False),
        sa.Column("last_scraped_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_states"),
    )

    # --- Table 2: operators ---
    op.create_table(
        "operators",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            primary_key=True,
        ),
        sa.Column("name", sa.VARCHAR(500), nullable=False),
        sa.Column("normalized_name", sa.VARCHAR(500), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("state_operator_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_operators"),
    )
    op.create_index("idx_operators_normalized_name", "operators", ["normalized_name"])
    op.create_index(
        "idx_operators_name_trgm",
        "operators",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index("idx_operators_search", "operators", ["search_vector"], postgresql_using="gin")

    # --- Table 3: wells ---
    op.create_table(
        "wells",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            primary_key=True,
        ),
        sa.Column("api_number", sa.VARCHAR(14), nullable=False),
        sa.Column("api_10", sa.VARCHAR(10), sa.Computed("LEFT(api_number, 10)"), nullable=True),
        sa.Column("well_name", sa.VARCHAR(500), nullable=True),
        sa.Column("well_number", sa.VARCHAR(100), nullable=True),
        sa.Column(
            "operator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operators.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "state_code",
            sa.VARCHAR(2),
            sa.ForeignKey("states.code"),
            nullable=False,
        ),
        sa.Column("county", sa.VARCHAR(255), nullable=True),
        sa.Column("basin", sa.VARCHAR(255), nullable=True),
        sa.Column("field_name", sa.VARCHAR(255), nullable=True),
        sa.Column("lease_name", sa.VARCHAR(500), nullable=True),
        sa.Column("latitude", sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column("longitude", sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326, from_text="ST_GeomFromEWKT"),
            nullable=True,
        ),
        sa.Column(
            "well_status",
            well_status_enum,
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("well_type", sa.VARCHAR(50), nullable=True),
        sa.Column("spud_date", sa.DATE(), nullable=True),
        sa.Column("completion_date", sa.DATE(), nullable=True),
        sa.Column("total_depth", sa.INTEGER(), nullable=True),
        sa.Column("true_vertical_depth", sa.INTEGER(), nullable=True),
        sa.Column("lateral_length", sa.INTEGER(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("alternate_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_wells"),
        sa.UniqueConstraint("api_number", "state_code", name="uq_wells_api_state"),
    )
    op.create_index("idx_wells_api_number", "wells", ["api_number"])
    op.create_index("idx_wells_api_10", "wells", ["api_10"])
    op.create_index(
        "idx_wells_api_trgm",
        "wells",
        ["api_number"],
        postgresql_using="gin",
        postgresql_ops={"api_number": "gin_trgm_ops"},
    )
    op.create_index("idx_wells_operator", "wells", ["operator_id"])
    op.create_index("idx_wells_state_county", "wells", ["state_code", "county"])
    op.create_index("idx_wells_status", "wells", ["well_status"])
    op.create_index(
        "idx_wells_lease_trgm",
        "wells",
        ["lease_name"],
        postgresql_using="gin",
        postgresql_ops={"lease_name": "gin_trgm_ops"},
    )
    op.create_index("idx_wells_location_gist", "wells", ["location"], postgresql_using="gist")
    op.create_index("idx_wells_search", "wells", ["search_vector"], postgresql_using="gin")
    op.create_index("idx_wells_metadata_gin", "wells", ["metadata"], postgresql_using="gin")
    op.create_index("idx_wells_alt_ids_gin", "wells", ["alternate_ids"], postgresql_using="gin")

    # --- Table 4: scrape_jobs (created before documents due to FK) ---
    op.create_table(
        "scrape_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            primary_key=True,
        ),
        sa.Column(
            "state_code",
            sa.VARCHAR(2),
            sa.ForeignKey("states.code"),
            nullable=True,
        ),
        sa.Column(
            "status",
            scrape_job_status_enum,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("job_type", sa.VARCHAR(50), nullable=False, server_default="full"),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("total_documents", sa.INTEGER(), server_default="0", nullable=False),
        sa.Column("documents_found", sa.INTEGER(), server_default="0", nullable=False),
        sa.Column("documents_downloaded", sa.INTEGER(), server_default="0", nullable=False),
        sa.Column("documents_processed", sa.INTEGER(), server_default="0", nullable=False),
        sa.Column("documents_failed", sa.INTEGER(), server_default="0", nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("errors", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_scrape_jobs"),
    )
    op.create_index("idx_scrape_jobs_status", "scrape_jobs", ["status"])
    op.create_index("idx_scrape_jobs_state", "scrape_jobs", ["state_code"])

    # --- Table 5: documents ---
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            primary_key=True,
        ),
        sa.Column(
            "well_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wells.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "state_code",
            sa.VARCHAR(2),
            sa.ForeignKey("states.code"),
            nullable=False,
        ),
        sa.Column(
            "scrape_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scrape_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("doc_type", doc_type_enum, server_default="other", nullable=False),
        sa.Column("status", document_status_enum, server_default="discovered", nullable=False),
        sa.Column("source_url", sa.TEXT(), nullable=False),
        sa.Column("file_path", sa.TEXT(), nullable=True),
        sa.Column("file_hash", sa.VARCHAR(64), unique=True, nullable=True),
        sa.Column("file_format", sa.VARCHAR(20), nullable=True),
        sa.Column("file_size_bytes", sa.BIGINT(), nullable=True),
        sa.Column("confidence_score", sa.NUMERIC(5, 4), nullable=True),
        sa.Column("ocr_confidence", sa.NUMERIC(5, 4), nullable=True),
        sa.Column("classification_method", sa.VARCHAR(50), nullable=True),
        sa.Column("document_date", sa.DATE(), nullable=True),
        sa.Column("scraped_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("raw_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
    )
    op.create_index("idx_documents_state_type", "documents", ["state_code", "doc_type"])
    op.create_index("idx_documents_well", "documents", ["well_id"])
    op.create_index("idx_documents_scrape_job", "documents", ["scrape_job_id"])
    op.create_index("idx_documents_date", "documents", ["document_date"])
    op.create_index("idx_documents_status", "documents", ["status"])
    op.create_index("idx_documents_source_url", "documents", ["source_url"], postgresql_using="hash")
    op.create_index("idx_documents_search", "documents", ["search_vector"], postgresql_using="gin")
    op.create_index("idx_documents_metadata_gin", "documents", ["raw_metadata"], postgresql_using="gin")

    # --- Table 6: extracted_data ---
    op.create_table(
        "extracted_data",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            primary_key=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "well_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wells.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("data_type", sa.VARCHAR(50), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("field_confidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confidence_score", sa.NUMERIC(5, 4), nullable=True),
        sa.Column("extractor_used", sa.VARCHAR(100), nullable=True),
        sa.Column("extraction_version", sa.VARCHAR(20), nullable=True),
        sa.Column("reporting_period_start", sa.DATE(), nullable=True),
        sa.Column("reporting_period_end", sa.DATE(), nullable=True),
        sa.Column("extracted_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_extracted_data"),
    )
    op.create_index("idx_extracted_document", "extracted_data", ["document_id"])
    op.create_index("idx_extracted_well", "extracted_data", ["well_id"])
    op.create_index("idx_extracted_data_type", "extracted_data", ["data_type"])
    op.create_index("idx_extracted_period", "extracted_data", ["reporting_period_start", "reporting_period_end"])
    op.create_index("idx_extracted_data_gin", "extracted_data", ["data"], postgresql_using="gin")
    op.create_index("idx_extracted_confidence_gin", "extracted_data", ["field_confidence"], postgresql_using="gin")

    # --- Table 7: review_queue ---
    op.create_table(
        "review_queue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            primary_key=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "extracted_data_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extracted_data.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("status", review_status_enum, server_default="pending", nullable=False),
        sa.Column("reason", sa.TEXT(), nullable=False),
        sa.Column("flag_details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("document_confidence", sa.NUMERIC(5, 4), nullable=True),
        sa.Column("field_confidences", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("reviewed_by", sa.VARCHAR(100), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("corrections", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.TEXT(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_review_queue"),
    )
    op.create_index("idx_review_status", "review_queue", ["status"])
    op.create_index("idx_review_document", "review_queue", ["document_id"])

    # --- Table 8: data_corrections ---
    op.create_table(
        "data_corrections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            primary_key=True,
        ),
        sa.Column(
            "extracted_data_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extracted_data.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "review_queue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("review_queue.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("field_path", sa.VARCHAR(255), nullable=False),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=False),
        sa.Column("corrected_by", sa.VARCHAR(100), nullable=True),
        sa.Column("corrected_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_data_corrections"),
    )
    op.create_index("idx_corrections_extracted_data", "data_corrections", ["extracted_data_id"])
    op.create_index("idx_corrections_review_queue", "data_corrections", ["review_queue_id"])

    # --- Trigger: PostGIS location auto-sync ---
    op.execute("""
        CREATE OR REPLACE FUNCTION wells_location_update() RETURNS trigger AS $$
        BEGIN
            IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
                NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_wells_location_update
            BEFORE INSERT OR UPDATE OF latitude, longitude
            ON wells FOR EACH ROW EXECUTE FUNCTION wells_location_update();
    """)

    # --- Trigger: Wells full-text search vector ---
    op.execute("""
        CREATE OR REPLACE FUNCTION wells_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.api_number, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.well_name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.lease_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.county, '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(NEW.basin, '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(NEW.field_name, '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_wells_search_vector_update
            BEFORE INSERT OR UPDATE OF api_number, well_name, lease_name, county, basin, field_name
            ON wells FOR EACH ROW EXECUTE FUNCTION wells_search_vector_update();
    """)

    # --- Trigger: Operators full-text search vector ---
    op.execute("""
        CREATE OR REPLACE FUNCTION operators_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.normalized_name, '')), 'A');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_operators_search_vector_update
            BEFORE INSERT OR UPDATE OF name, normalized_name
            ON operators FOR EACH ROW EXECUTE FUNCTION operators_search_vector_update();
    """)

    # --- Trigger: Documents full-text search vector ---
    op.execute("""
        CREATE OR REPLACE FUNCTION documents_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.doc_type::text, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.state_code, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_documents_search_vector_update
            BEFORE INSERT OR UPDATE OF doc_type, state_code
            ON documents FOR EACH ROW EXECUTE FUNCTION documents_search_vector_update();
    """)

    # --- Seed: 10 supported states ---
    op.execute("""
        INSERT INTO states (code, name, api_state_code, tier, config, created_at, updated_at)
        VALUES
            ('TX', 'Texas', '42', 1, '{}'::jsonb, now(), now()),
            ('NM', 'New Mexico', '30', 1, '{}'::jsonb, now(), now()),
            ('ND', 'North Dakota', '33', 1, '{}'::jsonb, now(), now()),
            ('OK', 'Oklahoma', '35', 1, '{}'::jsonb, now(), now()),
            ('CO', 'Colorado', '05', 1, '{}'::jsonb, now(), now()),
            ('WY', 'Wyoming', '49', 2, '{}'::jsonb, now(), now()),
            ('LA', 'Louisiana', '17', 2, '{}'::jsonb, now(), now()),
            ('PA', 'Pennsylvania', '37', 2, '{}'::jsonb, now(), now()),
            ('CA', 'California', '04', 2, '{}'::jsonb, now(), now()),
            ('AK', 'Alaska', '50', 2, '{}'::jsonb, now(), now());
    """)


def downgrade() -> None:
    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS trg_documents_search_vector_update ON documents")
    op.execute("DROP FUNCTION IF EXISTS documents_search_vector_update()")
    op.execute("DROP TRIGGER IF EXISTS trg_operators_search_vector_update ON operators")
    op.execute("DROP FUNCTION IF EXISTS operators_search_vector_update()")
    op.execute("DROP TRIGGER IF EXISTS trg_wells_search_vector_update ON wells")
    op.execute("DROP FUNCTION IF EXISTS wells_search_vector_update()")
    op.execute("DROP TRIGGER IF EXISTS trg_wells_location_update ON wells")
    op.execute("DROP FUNCTION IF EXISTS wells_location_update()")

    # Drop tables in reverse dependency order
    op.drop_table("data_corrections")
    op.drop_table("review_queue")
    op.drop_table("extracted_data")
    op.drop_table("documents")
    op.drop_table("scrape_jobs")
    op.drop_table("wells")
    op.drop_table("operators")
    op.drop_table("states")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS well_status_enum")
    op.execute("DROP TYPE IF EXISTS review_status_enum")
    op.execute("DROP TYPE IF EXISTS scrape_job_status_enum")
    op.execute("DROP TYPE IF EXISTS document_status_enum")
    op.execute("DROP TYPE IF EXISTS doc_type_enum")
