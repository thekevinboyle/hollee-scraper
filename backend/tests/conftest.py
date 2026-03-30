"""Shared test fixtures using testcontainers PostgreSQL+PostGIS."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from og_scraper.models import Base


@pytest.fixture(scope="session")
def postgres_container():
    """Spin up a real PostgreSQL+PostGIS container for integration tests."""
    with PostgresContainer(
        image="postgis/postgis:16-3.4",
        username="test",
        password="test",
        dbname="test_ogdocs",
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
async def engine(postgres_container):
    """Create async engine against the testcontainer, enable extensions, and create all tables."""
    url = postgres_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
    eng = create_async_engine(url, echo=False)

    # Enable required extensions and create all tables
    async with eng.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        # Create the location auto-sync trigger function
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION wells_location_update() RETURNS trigger AS $$
            BEGIN
                IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
                    NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))

        # Create the wells full-text search trigger function
        await conn.execute(text("""
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
        """))

        # Create the operators full-text search trigger function
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION operators_search_vector_update() RETURNS trigger AS $$
            BEGIN
                NEW.search_vector :=
                    setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
                    setweight(to_tsvector('english', COALESCE(NEW.normalized_name, '')), 'A');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))

        # Create the documents full-text search trigger function
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION documents_search_vector_update() RETURNS trigger AS $$
            BEGIN
                NEW.search_vector :=
                    setweight(to_tsvector('english', COALESCE(NEW.doc_type::text, '')), 'A') ||
                    setweight(to_tsvector('english', COALESCE(NEW.state_code, '')), 'B');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))

        # Create all tables from models
        await conn.run_sync(Base.metadata.create_all)

        # Create triggers (must happen after tables exist)
        await conn.execute(text("""
            CREATE TRIGGER trg_wells_location_update
                BEFORE INSERT OR UPDATE OF latitude, longitude
                ON wells FOR EACH ROW EXECUTE FUNCTION wells_location_update();
        """))
        await conn.execute(text("""
            CREATE TRIGGER trg_wells_search_vector_update
                BEFORE INSERT OR UPDATE OF api_number, well_name, lease_name, county, basin, field_name
                ON wells FOR EACH ROW EXECUTE FUNCTION wells_search_vector_update();
        """))
        await conn.execute(text("""
            CREATE TRIGGER trg_operators_search_vector_update
                BEFORE INSERT OR UPDATE OF name, normalized_name
                ON operators FOR EACH ROW EXECUTE FUNCTION operators_search_vector_update();
        """))
        await conn.execute(text("""
            CREATE TRIGGER trg_documents_search_vector_update
                BEFORE INSERT OR UPDATE OF doc_type, state_code
                ON documents FOR EACH ROW EXECUTE FUNCTION documents_search_vector_update();
        """))

    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    """Provide an async session that rolls back after each test."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
