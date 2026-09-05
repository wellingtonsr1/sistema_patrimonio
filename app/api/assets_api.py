from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.asset import AssetCreate, AssetUpdate, AssetRead
from app.schemas.movement import MovementRead
from app.models.enums import AssetStatus, AssetCategory
from app.services.asset_service import AssetService
from app.services.movement_service import MovementService
from app.services.import_service import parse_csv, preview_import, execute_import
from app.api.deps import _client_ip, require_permission
from app.services.audit_service import ACTION_CREATE, ACTION_UPDATE, ACTION_IMPORT, write_change_audit

router = APIRouter(prefix="/assets", tags=["Bens e Equipamentos"])

_ASSET_FIELDS = [
    "tag", "name", "category", "brand", "model", "serial_number",
    "specifications", "purchase_date", "purchase_value", "invoice_number",
    "supplier", "warranty_expiry", "condition", "status",
    "location_id", "custodian_id", "notes",
]


def _asset_snapshot(asset) -> dict:
    """Snapshot serializável de um bem para a trilha de auditoria."""
    data = {f: getattr(asset, f, None) for f in _ASSET_FIELDS}
    for key in ("purchase_date", "warranty_expiry"):
        if data.get(key):
            data[key] = data[key].strftime("%Y-%m-%d")
    if data.get("category") is not None:
        data["category"] = data["category"].value
    if data.get("condition") is not None:
        data["condition"] = data["condition"].value
    if data.get("status") is not None:
        data["status"] = data["status"].value
    return data


@router.get("", response_model=List[AssetRead], dependencies=[Depends(require_permission("patrimonio.visualizar"))])
def list_assets(
    search: Optional[str] = Query(None, description="Busca por tag, nome, modelo, série ou NF"),
    status_filter: Optional[AssetStatus] = Query(None, alias="status"),
    category: Optional[AssetCategory] = Query(None),
    location_id: Optional[int] = Query(None),
    custodian_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista todos os equipamentos com suporte a filtros e paginação (patrimonio.visualizar)"""
    assets, _ = AssetService.get_all(
        db, search=search, status=status_filter, category=category,
        location_id=location_id, custodian_id=custodian_id, skip=skip, limit=limit
    )
    return assets


@router.get("/{asset_id}", response_model=AssetRead, dependencies=[Depends(require_permission("patrimonio.visualizar"))])
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    """Retorna detalhes completos de um equipamento por ID (patrimonio.visualizar)"""
    asset = AssetService.get_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    return asset


@router.get("/tag/{tag}", response_model=AssetRead, dependencies=[Depends(require_permission("patrimonio.visualizar"))])
def get_asset_by_tag(tag: str, db: Session = Depends(get_db)):
    """Busca um equipamento pelo seu código de tombamento / Tag (patrimonio.visualizar)"""
    asset = AssetService.get_by_tag(db, tag)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Equipamento com tombamento '{tag}' não encontrado")
    return asset


@router.get("/{asset_id}/timeline", response_model=List[MovementRead], dependencies=[Depends(require_permission("patrimonio.visualizar"))])
def get_asset_timeline(asset_id: int, db: Session = Depends(get_db)):
    """Retorna toda a linha do tempo / fluxo de movimentação do equipamento (patrimonio.visualizar)"""
    asset = AssetService.get_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    return MovementService.get_timeline_for_asset(db, asset_id)


@router.get("/{asset_id}/depreciation", dependencies=[Depends(require_permission("patrimonio.visualizar"))])
def get_asset_depreciation(asset_id: int, db: Session = Depends(get_db)):
    """Calcula a depreciação linear contábil do equipamento (patrimonio.visualizar)"""
    asset = AssetService.get_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    return AssetService.calculate_depreciation(asset)


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("patrimonio.criar"))])
def create_asset(data: AssetCreate, request: Request, db: Session = Depends(get_db)):
    """Cadastra um novo equipamento no patrimônio e registra o evento de entrada no fluxo (patrimonio.criar)"""
    try:
        asset = AssetService.create(db, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_CREATE,
        module="Patrimônio",
        resource="Asset",
        resource_ref=asset.tag,
        resource_id=asset.id,
        ip_address=_client_ip(request),
        after=_asset_snapshot(asset),
        description=f"Cadastro do bem {asset.tag} - {asset.name}",
    )
    return asset


@router.put("/{asset_id}", response_model=AssetRead, dependencies=[Depends(require_permission("patrimonio.editar"))])
def update_asset(asset_id: int, data: AssetUpdate, request: Request, db: Session = Depends(get_db)):
    """Atualiza os dados cadastrais do equipamento (patrimonio.editar)"""
    before_asset = AssetService.get_by_id(db, asset_id)
    if not before_asset:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    before = _asset_snapshot(before_asset)
    try:
        asset = AssetService.update(db, asset_id, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not asset:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_UPDATE,
        module="Patrimônio",
        resource="Asset",
        resource_ref=asset.tag,
        resource_id=asset.id,
        ip_address=_client_ip(request),
        before=before,
        after=_asset_snapshot(asset),
    )
    return asset


@router.post("/import/csv", dependencies=[Depends(require_permission("patrimonio.criar"))])
def import_csv_api(
    request: Request,
    file: UploadFile = File(...),
    skip_duplicates: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Importa equipamentos em massa via CSV (patrimonio.criar)"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser CSV (.csv)")

    content = file.file.read().decode("utf-8-sig")  # BOM-safe
    rows, parse_errors = parse_csv(content)

    if parse_errors and not rows:
        raise HTTPException(status_code=422, detail={"errors": parse_errors})

    result = execute_import(rows, db, skip_duplicates=skip_duplicates)
    result["parse_errors"] = parse_errors

    from app.services.audit_service import write_audit
    write_audit(
        db,
        user=request.state.user,
        action=ACTION_IMPORT,
        module="Patrimônio",
        resource="Asset",
        resource_ref=file.filename,
        ip_address=_client_ip(request),
        description=f"Importação CSV: {result.get('imported', 0)} importados, "
                    f"{result.get('skipped', 0)} ignorados, {len(result.get('errors', []))} erros",
        new_data={"imported": result.get("imported", 0), "skipped": result.get("skipped", 0)},
    )
    return result