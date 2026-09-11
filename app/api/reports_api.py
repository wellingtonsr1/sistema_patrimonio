from fastapi import APIRouter, Depends, Response, Query
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import require_permission
from app.services.dashboard_service import DashboardService
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Relatórios e Dashboard"])


@router.get("/dashboard-stats", dependencies=[Depends(require_permission("relatorios.visualizar"))])
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Retorna dados resumidos e consolidados para o dashboard"""
    stats = DashboardService.get_stats(db)
    # Remove objetos complexos ORM do retorno JSON da API se necessário
    return {
        "total_assets": stats["total_assets"],
        "total_value": stats["total_value"],
        "status_counts": stats["status_counts"],
        "category_distribution": stats["category_distribution"],
        "total_custodians": stats["total_custodians"],
        "total_locations": stats["total_locations"],
        "total_movements": stats["total_movements"],
        "active_maintenances": stats["active_maintenances"],
    }


@router.get("/inventory/csv", dependencies=[Depends(require_permission("relatorios.exportar"))])
def export_inventory_csv(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    custodian_id: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    maintenance_status: Optional[str] = Query(None),
    purchase_date_from: Optional[str] = Query(None),
    purchase_date_to: Optional[str] = Query(None),
):
    """Exporta o inventário filtrado em formato CSV"""
    # Converter IDs de string para int (ou None se vazio)
    loc_id = int(location_id) if location_id and location_id.strip().isdigit() else None
    cust_id = int(custodian_id) if custodian_id and custodian_id.strip().isdigit() else None
    
    # Converter datas
    date_from = datetime.strptime(purchase_date_from, "%Y-%m-%d") if purchase_date_from else None
    date_to = datetime.strptime(purchase_date_to, "%Y-%m-%d") if purchase_date_to else None
    
    csv_content = ReportService.generate_inventory_csv(
        db, search=search, status=status, category=category,
        location_id=loc_id, custodian_id=cust_id,
        brand=brand, model=model, department=department,
        maintenance_status=maintenance_status,
        purchase_date_from=date_from, purchase_date_to=date_to
    )
    
    filename = "inventario_patrimonio"
    if search or status or category or loc_id or cust_id or brand or model or department or maintenance_status or date_from or date_to:
        filename += "_filtrado"
    filename += ".csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/inventory/excel", dependencies=[Depends(require_permission("relatorios.exportar"))])
def export_inventory_excel(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    custodian_id: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    maintenance_status: Optional[str] = Query(None),
    purchase_date_from: Optional[str] = Query(None),
    purchase_date_to: Optional[str] = Query(None),
):
    """Exporta o inventário filtrado em formato Excel (.xlsx)"""
    # Converter IDs de string para int (ou None se vazio)
    loc_id = int(location_id) if location_id and location_id.strip().isdigit() else None
    cust_id = int(custodian_id) if custodian_id and custodian_id.strip().isdigit() else None
    
    # Converter datas
    date_from = datetime.strptime(purchase_date_from, "%Y-%m-%d") if purchase_date_from else None
    date_to = datetime.strptime(purchase_date_to, "%Y-%m-%d") if purchase_date_to else None
    
    excel_content = ReportService.generate_inventory_excel(
        db, search=search, status=status, category=category,
        location_id=loc_id, custodian_id=cust_id,
        brand=brand, model=model, department=department,
        maintenance_status=maintenance_status,
        purchase_date_from=date_from, purchase_date_to=date_to
    )
    
    filename = "inventario_patrimonio"
    if search or status or category or loc_id or cust_id or brand or model or department or maintenance_status or date_from or date_to:
        filename += "_filtrado"
    filename += ".xlsx"
    
    return Response(
        content=excel_content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/inventory/pdf", dependencies=[Depends(require_permission("relatorios.exportar"))])
def export_inventory_pdf(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    custodian_id: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    maintenance_status: Optional[str] = Query(None),
    purchase_date_from: Optional[str] = Query(None),
    purchase_date_to: Optional[str] = Query(None),
):
    """Exporta o inventário filtrado em formato PDF"""
    # Converter IDs de string para int (ou None se vazio)
    loc_id = int(location_id) if location_id and location_id.strip().isdigit() else None
    cust_id = int(custodian_id) if custodian_id and custodian_id.strip().isdigit() else None
    
    # Converter datas
    date_from = datetime.strptime(purchase_date_from, "%Y-%m-%d") if purchase_date_from else None
    date_to = datetime.strptime(purchase_date_to, "%Y-%m-%d") if purchase_date_to else None
    
    pdf_content = ReportService.generate_inventory_pdf(
        db, search=search, status=status, category=category,
        location_id=loc_id, custodian_id=cust_id,
        brand=brand, model=model, department=department,
        maintenance_status=maintenance_status,
        purchase_date_from=date_from, purchase_date_to=date_to
    )
    
    filename = "inventario_patrimonio"
    if search or status or category or loc_id or cust_id or brand or model or department or maintenance_status or date_from or date_to:
        filename += "_filtrado"
    filename += ".pdf"
    
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/movements/csv", dependencies=[Depends(require_permission("relatorios.exportar"))])
def export_movements_csv(db: Session = Depends(get_db)):
    """Exporta a trilha de fluxo de movimentação em formato CSV"""
    csv_content = ReportService.generate_movements_csv(db)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=historico_movimentacoes.csv"}
    )


@router.get("/custodians/csv", dependencies=[Depends(require_permission("relatorios.exportar"))])
def export_custodians_csv(db: Session = Depends(get_db)):
    """Exporta todos os colaboradores em CSV (formato compatível com a importação)"""
    csv_content = ReportService.generate_custodians_csv(db)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=colaboradores.csv"}
    )
