from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.models.asset import Asset
from app.models.movement import Movement
from app.models.custodian import Custodian
from app.models.location import Location
from app.models.maintenance import Maintenance
from app.models.enums import AssetStatus, MaintenanceStatus


class DashboardService:
    @staticmethod
    def get_stats(db: Session) -> dict:
        total_assets = db.query(func.count(Asset.id)).scalar() or 0
        total_value = db.query(func.sum(Asset.purchase_value)).scalar() or 0.0

        status_counts = dict(
            db.query(Asset.status, func.count(Asset.id)).group_by(Asset.status).all()
        )

        category_counts = dict(
            db.query(Asset.category, func.count(Asset.id)).group_by(Asset.category).all()
        )

        total_custodians = db.query(func.count(Custodian.id)).filter(Custodian.is_active == True).scalar() or 0
        total_locations = db.query(func.count(Location.id)).scalar() or 0
        total_movements = db.query(func.count(Movement.id)).scalar() or 0
        active_maintenances = db.query(func.count(Maintenance.id)).filter(
            Maintenance.status == MaintenanceStatus.IN_PROGRESS
        ).scalar() or 0

        # Distribuição por localização
        location_distribution = db.query(
            Location.name, func.count(Asset.id)
        ).outerjoin(Asset, Asset.location_id == Location.id).group_by(Location.id).order_by(func.count(Asset.id).desc()).all()

        # Distribuição por departamento
        department_distribution = db.query(
            Location.department, func.count(Asset.id)
        ).outerjoin(Asset, Asset.location_id == Location.id).group_by(Location.department).order_by(func.count(Asset.id).desc()).all()

        # Converte resultados para dicionários
        location_dist_data = [{"location": name, "count": count} for name, count in location_distribution]
        department_dist_data = [{"department": dept, "count": count} for dept, count in department_distribution]

        # Inconsistências patrimoniais
        inconsistencies = DashboardService._get_inconsistencies(db)

        # Últimas 8 movimentações para feed de atividades
        recent_movements = db.query(Movement).order_by(desc(Movement.timestamp)).limit(8).all()

        # Bens mais recentes
        recent_assets = db.query(Asset).order_by(desc(Asset.created_at)).limit(5).all()

        return {
            "total_assets": total_assets,
            "total_value": total_value,
            "status_counts": {
                "available": status_counts.get(AssetStatus.AVAILABLE, 0),
                "in_use": status_counts.get(AssetStatus.IN_USE, 0),
                "in_maintenance": status_counts.get(AssetStatus.IN_MAINTENANCE, 0),
                "in_transit": status_counts.get(AssetStatus.IN_TRANSIT, 0),
                "written_off": status_counts.get(AssetStatus.WRITTEN_OFF, 0),
            },
            "category_distribution": [
                {"category": cat.value if hasattr(cat, 'value') else str(cat), "count": count}
                for cat, count in category_counts.items()
            ],
            "location_distribution": location_dist_data,
            "department_distribution": department_dist_data,
            "inconsistencies": inconsistencies,
            "total_custodians": total_custodians,
            "total_locations": total_locations,
            "total_movements": total_movements,
            "active_maintenances": active_maintenances,
            "recent_movements": recent_movements,
            "recent_assets": recent_assets
        }

    @staticmethod
    def _get_inconsistencies(db: Session) -> list:
        """Identifica inconsistências patrimoniais baseadas nos dados reais.

        Verifica:
        - Equipamentos sem localização
        - Equipamentos sem responsável (custodian)
        """
        inconsistencies = []

        # Equipamentos sem localização
        assets_without_location = db.query(
            Asset.id, Asset.tag, Asset.name
        ).filter(
            Asset.location_id == None
        ).all()

        if assets_without_location:
            inconsistencies.append({
                "type": "warning",
                "icon": "bi-geo-alt",
                "title": "Equipamentos sem localização",
                "count": len(assets_without_location),
                "item_list": [{"tag": a.tag, "name": a.name, "detail": "Sem localização cadastrada"} for a in assets_without_location[:10]]
            })

        # Equipamentos sem responsável
        assets_without_custodian = db.query(
            Asset.id, Asset.tag, Asset.name
        ).filter(
            Asset.custodian_id == None
        ).all()

        if assets_without_custodian:
            inconsistencies.append({
                "type": "info",
                "icon": "bi-person",
                "title": "Equipamentos sem responsável",
                "count": len(assets_without_custodian),
                "item_list": [{"tag": a.tag, "name": a.name, "detail": "Sem responsável atribuído"} for a in assets_without_custodian[:10]]
            })

        return inconsistencies
