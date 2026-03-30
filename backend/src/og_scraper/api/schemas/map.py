"""Map-related Pydantic schemas for bounding box queries and well map points."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .enums import WellStatus


class WellMapPoint(BaseModel):
    """Minimal well data for map pin rendering. Keep payload small."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    api_number: str
    well_name: str | None = None
    operator_name: str | None = None
    latitude: float
    longitude: float
    well_status: WellStatus | None = None
    well_type: str | None = None
