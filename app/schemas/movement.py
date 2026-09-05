from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import MovementType, AssetStatus, AssetCondition


class MovementCreate(BaseModel):
    asset_id: int
    movement_type: MovementType
    destination_location_id: Optional[int] = None
    destination_custodian_id: Optional[int] = None
    new_condition: Optional[AssetCondition] = None
    reason: str = Field(..., min_length=3, description="Justificativa obrigatória da movimentação")
    operator_name: str = Field("Operador do Sistema", description="Nome de quem realizou o registro")
    notes: Optional[str] = None
    generate_term: bool = True  # Se deve gerar código de termo de cautela


class MovementRead(BaseModel):
    id: int
    movement_uuid: str
    asset_id: int
    movement_type: MovementType
    timestamp: datetime
    
    origin_location_id: Optional[int] = None
    origin_location_name: Optional[str] = None
    origin_custodian_id: Optional[int] = None
    origin_custodian_name: Optional[str] = None

    destination_location_id: Optional[int] = None
    destination_location_name: Optional[str] = None
    destination_custodian_id: Optional[int] = None
    destination_custodian_name: Optional[str] = None

    previous_status: Optional[AssetStatus] = None
    new_status: AssetStatus
    previous_condition: Optional[AssetCondition] = None
    new_condition: Optional[AssetCondition] = None

    reason: str
    operator_name: str
    term_code: Optional[str] = None
    term_signed: bool
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MovementFilter(BaseModel):
    asset_id: Optional[int] = None
    movement_type: Optional[MovementType] = None
    custodian_id: Optional[int] = None
    location_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
