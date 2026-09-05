from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.location import LocationCreate, LocationUpdate, LocationRead
from app.services.location_service import LocationService
from app.api.deps import _client_ip, require_permission
from app.services.audit_service import ACTION_CREATE, ACTION_UPDATE, write_change_audit

router = APIRouter(prefix="/locations", tags=["Locais e Departamentos"])


def _location_snapshot(loc) -> dict:
    return {
        "name": loc.name,
        "branch": loc.branch,
        "building": loc.building,
        "floor": loc.floor,
        "room": loc.room,
        "department": loc.department,
        "manager_name": loc.manager_name,
        "description": loc.description,
    }


@router.get("", response_model=List[LocationRead], dependencies=[Depends(require_permission("locais.visualizar"))])
def list_locations(db: Session = Depends(get_db)):
    """Lista todas as localizações e departamentos cadastrados (locais.visualizar)"""
    locations = LocationService.get_all(db)
    for loc in locations:
        loc.assets_count = LocationService.count_assets(db, loc.id)
    return locations


@router.get("/{location_id}", response_model=LocationRead, dependencies=[Depends(require_permission("locais.visualizar"))])
def get_location(location_id: int, db: Session = Depends(get_db)):
    """Retorna detalhes de um local específico (locais.visualizar)"""
    loc = LocationService.get_by_id(db, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Local não encontrado")
    loc.assets_count = LocationService.count_assets(db, loc.id)
    return loc


@router.post("", response_model=LocationRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("locais.criar"))])
def create_location(data: LocationCreate, request: Request, db: Session = Depends(get_db)):
    """Cadastra um novo local/departamento (locais.criar)"""
    try:
        loc = LocationService.create(db, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_CREATE,
        module="Locais",
        resource="Location",
        resource_ref=loc.name,
        resource_id=loc.id,
        ip_address=_client_ip(request),
        after=_location_snapshot(loc),
        description=f"Cadastro do local {loc.name}",
    )
    return loc


@router.put("/{location_id}", response_model=LocationRead, dependencies=[Depends(require_permission("locais.editar"))])
def update_location(location_id: int, data: LocationUpdate, request: Request, db: Session = Depends(get_db)):
    """Atualiza dados do local (locais.editar)"""
    before_loc = LocationService.get_by_id(db, location_id)
    if not before_loc:
        raise HTTPException(status_code=404, detail="Local não encontrado")
    before = _location_snapshot(before_loc)
    try:
        loc = LocationService.update(db, location_id, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not loc:
        raise HTTPException(status_code=404, detail="Local não encontrado")
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_UPDATE,
        module="Locais",
        resource="Location",
        resource_ref=loc.name,
        resource_id=loc.id,
        ip_address=_client_ip(request),
        before=before,
        after=_location_snapshot(loc),
    )
    return loc