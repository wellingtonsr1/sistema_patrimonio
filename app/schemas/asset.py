from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import AssetStatus, AssetCondition, AssetCategory
from app.schemas.location import LocationRead
from app.schemas.custodian import CustodianRead


class AssetBase(BaseModel):
    tag: str = Field(..., description="Número de tombamento único")
    name: str = Field(..., description="Nome do equipamento")
    category: AssetCategory = AssetCategory.NOTEBOOK
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    specifications: Optional[str] = None
    purchase_date: Optional[datetime] = None
    purchase_value: float = 0.0
    invoice_number: Optional[str] = None
    supplier: Optional[str] = None
    warranty_expiry: Optional[datetime] = None
    condition: AssetCondition = AssetCondition.NEW
    notes: Optional[str] = None


class AssetCreate(AssetBase):
    initial_location_id: Optional[int] = None
    initial_custodian_id: Optional[int] = None
    initial_operator: Optional[str] = "Sistema"


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[AssetCategory] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    specifications: Optional[str] = None
    purchase_date: Optional[datetime] = None
    purchase_value: Optional[float] = None
    invoice_number: Optional[str] = None
    supplier: Optional[str] = None
    warranty_expiry: Optional[datetime] = None
    condition: Optional[AssetCondition] = None
    notes: Optional[str] = None


class AssetRead(AssetBase):
    id: int
    status: AssetStatus
    location_id: Optional[int] = None
    custodian_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    location: Optional[LocationRead] = None
    custodian: Optional[CustodianRead] = None

    model_config = ConfigDict(from_attributes=True)
