from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.movement import MovementCreate, MovementRead, MovementFilter
from app.models.enums import MovementType
from app.services.movement_service import MovementService
from app.api.deps import _client_ip, require_permission
from app.services.audit_service import ACTION_MOVEMENT, write_change_audit

router = APIRouter(prefix="/movements", tags=["Fluxo de Movimentação"])


@router.get("", response_model=List[MovementRead], dependencies=[Depends(require_permission("movimentacao.visualizar"))])
def list_movements(
    asset_id: Optional[int] = Query(None),
    movement_type: Optional[MovementType] = Query(None),
    custodian_id: Optional[int] = Query(None),
    location_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Consulta o histórico global de movimentações (movimentacao.visualizar)"""
    filters = MovementFilter(
        asset_id=asset_id,
        movement_type=movement_type,
        custodian_id=custodian_id,
        location_id=location_id,
        start_date=start_date,
        end_date=end_date
    )
    movements, _ = MovementService.get_all_movements(db, filters=filters, skip=skip, limit=limit)
    return movements


@router.get("/{movement_id}", response_model=MovementRead, dependencies=[Depends(require_permission("movimentacao.visualizar"))])
def get_movement(movement_id: int, db: Session = Depends(get_db)):
    """Retorna detalhes de uma movimentação específica (movimentacao.visualizar)"""
    movement = MovementService.get_by_id(db, movement_id)
    if not movement:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada")
    return movement


@router.get("/{movement_id}/term", dependencies=[Depends(require_permission("movimentacao.visualizar"))])
def get_movement_term(movement_id: int, db: Session = Depends(get_db)):
    """Retorna a estrutura do Termo de Responsabilidade/Cautela (movimentacao.visualizar)"""
    term_data = MovementService.get_term_details(db, movement_id)
    if not term_data:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada")
    return term_data


@router.post("", response_model=MovementRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("movimentacao.criar"))])
def record_movement(data: MovementCreate, request: Request, db: Session = Depends(get_db)):
    """
    Registra uma nova movimentação no fluxo de um equipamento (movimentacao.criar):
    - Alocação / Cautela a Colaborador
    - Transferência de Prédio/Setor
    - Envio / Retorno de Manutenção
    - Devolução ao Estoque
    - Baixa / Descarte
    """
    try:
        movement = MovementService.create_movement(db, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    asset = movement.asset
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_MOVEMENT,
        module="Movimentação",
        resource="Movement",
        resource_ref=asset.tag if asset else None,
        resource_id=movement.id,
        ip_address=_client_ip(request),
        before={
            "status": movement.previous_status.value if movement.previous_status else None,
            "condition": movement.previous_condition.value if movement.previous_condition else None,
        },
        after={
            "status": movement.new_status.value,
            "condition": movement.new_condition.value if movement.new_condition else None,
            "tipo": movement.movement_type.value,
            "motivo": movement.reason,
            "termo": movement.term_code,
        },
        description=f"Movimentação {movement.movement_type.label} do bem {asset.tag if asset else movement.asset_id}",
    )
    return movement