"""E2E test fixtures: seed data, httpx AsyncClient, data factories."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from og_scraper.api.app import create_app
from og_scraper.api.deps import get_db
from og_scraper.models.document import Document
from og_scraper.models.extracted_data import ExtractedData
from og_scraper.models.operator import Operator
from og_scraper.models.review_queue import ReviewQueue
from og_scraper.models.state import State
from og_scraper.models.well import Well


def _docker_available():
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker daemon not available",
)

STATES_DATA = [
    ("TX", "Texas", "Railroad Commission of Texas", "42"),
    ("NM", "New Mexico", "Oil Conservation Division", "30"),
    ("ND", "North Dakota", "Industrial Commission", "33"),
    ("OK", "Oklahoma", "Corporation Commission", "35"),
    ("CO", "Colorado", "Energy & Carbon Management Commission", "05"),
    ("WY", "Wyoming", "Oil & Gas Conservation Commission", "49"),
    ("LA", "Louisiana", "SONRIS", "17"),
    ("PA", "Pennsylvania", "Dept of Environmental Protection", "37"),
    ("CA", "California", "CalGEM", "04"),
    ("AK", "Alaska", "Oil & Gas Conservation Commission", "50"),
]


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed the database with 10 states and return the session."""
    for code, name, agency, api_prefix in STATES_DATA:
        state = State(
            code=code,
            name=name,
            agency_name=agency,
            api_state_code=api_prefix,
            tier=1,
        )
        db_session.add(state)
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def seeded_wells(seeded_db):
    """Seed DB with states, operators, and wells across 3 states."""
    db = seeded_db

    # Create operators
    ops = {}
    for code, op_name in [("TX", "Devon Energy"), ("OK", "Continental Resources"), ("CO", "Noble Energy")]:
        op = Operator(name=op_name, normalized_name=op_name.lower(), state_code=code)
        db.add(op)
        await db.flush()
        ops[code] = op

    # Create wells
    wells = {}
    for i, (code, lat, lng) in enumerate(
        [
            ("TX", 31.97, -102.07),
            ("TX", 32.45, -101.94),
            ("OK", 35.46, -97.52),
            ("OK", 36.12, -96.78),
            ("CO", 39.74, -104.99),
        ]
    ):
        well = Well(
            api_number=f"{STATES_DATA[[s[0] for s in STATES_DATA].index(code)][3]}001{i:05d}0000",
            well_name=f"Test Well {code}-{i}",
            operator_id=ops[code].id,
            state_code=code,
            county=f"Test County {i}",
            latitude=lat,
            longitude=lng,
            well_status="active",
        )
        db.add(well)
        wells[f"{code}-{i}"] = well
    await db.flush()

    return {"db": db, "operators": ops, "wells": wells}


@pytest_asyncio.fixture
async def seeded_documents(seeded_wells):
    """Seed DB with documents linked to wells."""
    db = seeded_wells["db"]
    wells = seeded_wells["wells"]
    docs = {}

    for key, well in wells.items():
        doc = Document(
            well_id=well.id,
            state_code=well.state_code,
            doc_type="production_report",
            status="stored",
            source_url=f"https://example.com/{key}.pdf",
            confidence_score=0.88,
        )
        db.add(doc)
        docs[key] = doc
    await db.flush()

    return {**seeded_wells, "documents": docs}


@pytest_asyncio.fixture
async def seeded_review_items(seeded_documents):
    """Seed DB with review queue items."""
    db = seeded_documents["db"]
    docs = seeded_documents["documents"]
    reviews = {}

    for key, doc in list(docs.items())[:2]:
        # Create extracted data
        ed = ExtractedData(
            document_id=doc.id,
            data={"api_number": "42001000010000", "operator_name": "Test Op"},
            extraction_method="regex",
        )
        db.add(ed)
        await db.flush()

        review = ReviewQueue(
            document_id=doc.id,
            extracted_data_id=ed.id,
            status="pending",
            reason="Medium confidence",
            document_confidence=0.72,
        )
        db.add(review)
        reviews[key] = review
    await db.flush()

    return {**seeded_documents, "reviews": reviews}


@pytest_asyncio.fixture
async def client(seeded_db):
    """httpx AsyncClient against the FastAPI app with seeded DB."""
    app = create_app()

    async def override_get_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_with_wells(seeded_wells):
    """httpx AsyncClient with wells seeded."""
    db = seeded_wells["db"]
    app = create_app()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_with_documents(seeded_documents):
    """httpx AsyncClient with documents seeded."""
    db = seeded_documents["db"]
    app = create_app()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_with_reviews(seeded_review_items):
    """httpx AsyncClient with review items seeded."""
    db = seeded_review_items["db"]
    app = create_app()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
