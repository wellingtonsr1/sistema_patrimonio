from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.enums import MaintenanceType, MaintenanceStatus


class MaintenanceCreate(BaseModel):
    asset_id: int
    maintenance_type: MaintenanceType = MaintenanceType.CORRECTIVE
    provider_name: Optional[str] = None
    description: str
    cost: float = 0.0
    start_date: Optional[datetime] = None


class MaintenanceUpdate(BaseModel):
    status: Optional[MaintenanceStatus] = None
    solution: Optional[str] = None
    cost: Optional[float] = None
    end_date: Optional[datetime] = None
    provider_name: Optional[str] = None


class MaintenanceRead(BaseModel):
    id: int
    asset_id: int
    maintenance_type: MaintenanceType
    status: MaintenanceStatus
    provider_name: Optional[str] = None
    description: str
    solution: Optional[str] = None
    cost: float
    start_date: datetime
    end_date: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
