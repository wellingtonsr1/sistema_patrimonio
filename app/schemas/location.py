from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class LocationBase(BaseModel):
    name: str
    branch: str
    building: Optional[str] = None
    floor: Optional[str] = None
    room: Optional[str] = None
    department: str
    manager_name: Optional[str] = None
    description: Optional[str] = None


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    branch: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[str] = None
    room: Optional[str] = None
    department: Optional[str] = None
    manager_name: Optional[str] = None
    description: Optional[str] = None


class LocationRead(LocationBase):
    id: int
    created_at: datetime
    assets_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)
