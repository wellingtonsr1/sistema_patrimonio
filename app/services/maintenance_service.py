from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from app.models.maintenance import Maintenance
from app.models.asset import Asset
from app.models.enums import MaintenanceStatus, MovementType, AssetStatus
from app.schemas.maintenance import MaintenanceCreate, MaintenanceUpdate
from app.schemas.movement import MovementCreate
from app.services.movement_service import MovementService


class MaintenanceService:
    @staticmethod
    def get_all(db: Session, status: Optional[MaintenanceStatus] = None) -> List[Maintenance]:
        query = db.query(Maintenance).options(joinedload(Maintenance.asset))
        if status:
            query = query.filter(Maintenance.status == status)
        return query.order_by(Maintenance.start_date.desc()).all()

    @staticmethod
    def get_by_id(db: Session, maintenance_id: int) -> Optional[Maintenance]:
        return db.query(Maintenance).options(joinedload(Maintenance.asset)).filter(Maintenance.id == maintenance_id).first()

    @staticmethod
    def create(db: Session, data: MaintenanceCreate, operator: str = "Técnico") -> Maintenance:
        """
        Abre ordem de manutenção e envia automaticamente o bem para status EM_MANUTENCAO
        gravando o evento no fluxo de movimentação.
        """
        asset = db.query(Asset).filter(Asset.id == data.asset_id).first()
        if not asset:
            raise ValueError("Equipamento não encontrado.")

        maintenance = Maintenance(
            asset_id=data.asset_id,
            maintenance_type=data.maintenance_type,
            status=MaintenanceStatus.IN_PROGRESS,
            provider_name=data.provider_name,
            description=data.description,
            cost=data.cost,
            start_date=data.start_date or datetime.utcnow()
        )
        db.add(maintenance)
        db.flush()

        # Registra no fluxo de movimentação
        movement_in = MovementCreate(
            asset_id=data.asset_id,
            movement_type=MovementType.MAINTENANCE_OUT,
            reason=f"Abertura de OS #{maintenance.id}: {data.description}",
            operator_name=operator,
            notes=f"Prestador / Assistência: {data.provider_name or 'Interno'}",
            generate_term=False
        )
        MovementService.create_movement(db, movement_in)

        db.commit()
        db.refresh(maintenance)
        return maintenance

    @staticmethod
    def complete_maintenance(
        db: Session,
        maintenance_id: int,
        data: MaintenanceUpdate,
        operator: str = "Técnico"
    ) -> Optional[Maintenance]:
        """
        Conclui a manutenção e retorna o equipamento para status DISPONIVEL
        gravando o retorno no fluxo de movimentação.
        """
        maint = MaintenanceService.get_by_id(db, maintenance_id)
        if not maint:
            return None

        maint.status = MaintenanceStatus.COMPLETED
        maint.end_date = data.end_date or datetime.utcnow()
        if data.solution:
            maint.solution = data.solution
        if data.cost is not None:
            maint.cost = data.cost
        if data.provider_name:
            maint.provider_name = data.provider_name

        # Registra retorno da manutenção no fluxo
        movement_in = MovementCreate(
            asset_id=maint.asset_id,
            movement_type=MovementType.MAINTENANCE_IN,
            reason=f"Retorno de manutenção OS #{maint.id}. Solução: {data.solution or 'Reparo efetuado com sucesso.'}",
            operator_name=operator,
            notes=f"Custo total: R$ {maint.cost:.2f}",
            generate_term=False
        )
        MovementService.create_movement(db, movement_in)

        db.commit()
        db.refresh(maint)
        return maint
