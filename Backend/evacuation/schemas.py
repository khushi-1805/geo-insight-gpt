from typing import Optional
from pydantic import BaseModel, Field


class UserLocation(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DryAreaDestination(BaseModel):
    destination_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    area_m2: float = Field(gt=0)
    distance_m: float = Field(ge=0)
    bearing_degrees: float = Field(ge=0, lt=360)
    direction: str
    flood_fraction: Optional[float] = Field(default=None, ge=0, le=1)
    building_fraction: Optional[float] = Field(default=None, ge=0, le=1)
    verification_status: str = "unverified"
    warnings: list[str] = Field(default_factory=list)


class EvacuationSearchResponse(BaseModel):
    user_location: UserLocation
    destinations: list[DryAreaDestination] = Field(default_factory=list)
    flood_data_timestamp: Optional[str] = None
    model_name: Optional[str] = None
    message: str
