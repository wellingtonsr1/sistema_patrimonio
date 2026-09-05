from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.custodian import CustodianCreate, CustodianUpdate, CustodianRead
from app.schemas.asset import AssetRead
from app.services.custodian_service import CustodianService
from app.services.custodian_import_service import parse_custodian_csv, execute_custodian_import
from app.api.deps import _client_ip, require_permission
from app.services.audit_service import ACTION_CREATE, ACTION_UPDATE, ACTION_IMPORT, write_change_audit, write_audit

router = APIRouter(prefix="/custodians", tags=["Colaboradores e Responsáveis"])


def _custodian_snapshot(c) -> dict:
    return {
        "registration_code": c.registration_code,
        "name": c.name,
        "email": c.email,
        "cpf": c.cpf,
        "role": c.role,
        "department": c.department,
        "is_active": c.is_active,
    }


@router.get("", response_model=List[CustodianRead], dependencies=[Depends(require_permission("colaboradores.visualizar"))])
def list_custodians(active_only: bool = False, db: Session = Depends(get_db)):
    """Lista todos os colaboradores cadastrados (colaboradores.visualizar)"""
    custodians = CustodianService.get_all(db, active_only=active_only)
    for c in custodians:
        c.active_assets_count = CustodianService.count_assigned_assets(db, c.id)
    return custodians


@router.get("/{custodian_id}", response_model=CustodianRead, dependencies=[Depends(require_permission("colaboradores.visualizar"))])
def get_custodian(custodian_id: int, db: Session = Depends(get_db)):
    """Retorna detalhes de um colaborador (colaboradores.visualizar)"""
    custodian = CustodianService.get_by_id(db, custodian_id)
    if not custodian:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado")
    custodian.active_assets_count = CustodianService.count_assigned_assets(db, custodian.id)
    return custodian


@router.get("/{custodian_id}/assets", response_model=List[AssetRead], dependencies=[Depends(require_permission("colaboradores.visualizar"))])
def get_custodian_assets(custodian_id: int, db: Session = Depends(get_db)):
    """Lista os equipamentos sob a custódia deste colaborador (colaboradores.visualizar)"""
    custodian = CustodianService.get_by_id(db, custodian_id)
    if not custodian:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado")
    return CustodianService.get_assigned_assets(db, custodian_id)


@router.post("", response_model=CustodianRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("colaboradores.criar"))])
def create_custodian(data: CustodianCreate, request: Request, db: Session = Depends(get_db)):
    """Cadastra um novo colaborador (colaboradores.criar)"""
    try:
        custodian = CustodianService.create(db, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_CREATE,
        module="Colaboradores",
        resource="Custodian",
        resource_ref=custodian.registration_code,
        resource_id=custodian.id,
        ip_address=_client_ip(request),
        after=_custodian_snapshot(custodian),
        description=f"Cadastro do colaborador {custodian.name} ({custodian.registration_code})",
    )
    return custodian


@router.post("/import/csv", dependencies=[Depends(require_permission("colaboradores.criar"))])
def import_custodians_csv(
    request: Request,
    file: UploadFile = File(...),
    skip_duplicates: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Importa colaboradores em massa via CSV (colaboradores.criar)"""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser CSV (.csv)")

    content = file.file.read().decode("utf-8-sig")  # BOM-safe
    rows, parse_errors = parse_custodian_csv(content)

    if parse_errors and not rows:
        raise HTTPException(status_code=422, detail={"errors": parse_errors})

    result = execute_custodian_import(rows, db, skip_duplicates=skip_duplicates)
    result["parse_errors"] = parse_errors

    write_audit(
        db,
        user=request.state.user,
        action=ACTION_IMPORT,
        module="Colaboradores",
        resource="Custodian",
        resource_ref=file.filename,
        ip_address=_client_ip(request),
        description=f"Importação CSV de colaboradores: {result.get('imported', 0)} importados, "
                    f"{result.get('skipped', 0)} ignorados, {len(result.get('errors', []))} erros",
        new_data={"imported": result.get("imported", 0), "skipped": result.get("skipped", 0)},
    )
    return result


@router.put("/{custodian_id}", response_model=CustodianRead, dependencies=[Depends(require_permission("colaboradores.editar"))])
def update_custodian(custodian_id: int, data: CustodianUpdate, request: Request, db: Session = Depends(get_db)):
    """Atualiza os dados de um colaborador (colaboradores.editar)"""
    before_c = CustodianService.get_by_id(db, custodian_id)
    if not before_c:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado")
    before = _custodian_snapshot(before_c)
    try:
        custodian = CustodianService.update(db, custodian_id, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not custodian:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado")
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_UPDATE,
        module="Colaboradores",
        resource="Custodian",
        resource_ref=custodian.registration_code,
        resource_id=custodian.id,
        ip_address=_client_ip(request),
        before=before,
        after=_custodian_snapshot(custodian),
    )
    return custodian