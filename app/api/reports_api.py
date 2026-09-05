from fastapi import APIRouter, Depends, Response
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
def export_inventory_csv(db: Session = Depends(get_db)):
    """Exporta o inventário geral completo em formato CSV"""
    csv_content = ReportService.generate_inventory_csv(db)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=inventario_patrimonio.csv"}
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
