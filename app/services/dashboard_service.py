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
            "total_custodians": total_custodians,
            "total_locations": total_locations,
            "total_movements": total_movements,
            "active_maintenances": active_maintenances,
            "recent_movements": recent_movements,
            "recent_assets": recent_assets
        }
