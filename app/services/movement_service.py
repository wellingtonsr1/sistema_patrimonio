from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from app.models.asset import Asset
from app.models.movement import Movement
from app.models.location import Location
from app.models.custodian import Custodian
from app.models.enums import MovementType, AssetStatus, AssetCondition
from app.schemas.movement import MovementCreate, MovementFilter
from app.config import COMPANY_NAME, COMPANY_CNPJ, COMPANY_ADDRESS


class MovementService:
    @staticmethod
    def create_movement(db: Session, data: MovementCreate) -> Movement:
        """
        Executa e grava de forma atômica uma nova movimentação de equipamento,
        atualizando o estado atual do bem e registrando a trilha de auditoria completa.
        """
        asset = db.query(Asset).filter(Asset.id == data.asset_id).first()
        if not asset:
            raise ValueError(f"Equipamento com ID {data.asset_id} não encontrado.")

        if asset.status == AssetStatus.WRITTEN_OFF and data.movement_type != MovementType.ACQUISITION:
            raise ValueError("Não é possível movimentar um equipamento que já foi baixado/descartado.")

        # Guardar snapshots da situação anterior
        prev_status = asset.status
        prev_condition = asset.condition
        prev_location_id = asset.location_id
        prev_custodian_id = asset.custodian_id

        prev_location_name = None
        if asset.location:
            prev_location_name = f"{asset.location.branch} - {asset.location.department} ({asset.location.name})"
        
        prev_custodian_name = None
        if asset.custodian:
            prev_custodian_name = f"{asset.custodian.name} ({asset.custodian.registration_code})"

        # Obter referências do novo destino
        new_location = None
        new_location_name = None
        if data.destination_location_id:
            new_location = db.query(Location).filter(Location.id == data.destination_location_id).first()
            if new_location:
                new_location_name = f"{new_location.branch} - {new_location.department} ({new_location.name})"

        new_custodian = None
        new_custodian_name = None
        if data.destination_custodian_id:
            new_custodian = db.query(Custodian).filter(Custodian.id == data.destination_custodian_id).first()
            if new_custodian:
                new_custodian_name = f"{new_custodian.name} ({new_custodian.registration_code})"

        # Determinar novo status e atualizar campos do Ativo conforme o Tipo de Movimentação
        m_type = data.movement_type

        if m_type == MovementType.ALLOCATION:
            if not data.destination_custodian_id:
                raise ValueError("Para alocação/cautela é obrigatório selecionar o colaborador de destino.")
            new_status = AssetStatus.IN_USE
            asset.custodian_id = data.destination_custodian_id
            if data.destination_location_id:
                asset.location_id = data.destination_location_id

        elif m_type == MovementType.RETURN_STOCK:
            new_status = AssetStatus.AVAILABLE
            asset.custodian_id = None
            if data.destination_location_id:
                asset.location_id = data.destination_location_id

        elif m_type == MovementType.TRANSFER:
            if not data.destination_location_id:
                raise ValueError("Para transferência de setor é obrigatório selecionar o local de destino.")
            asset.location_id = data.destination_location_id
            if data.destination_custodian_id:
                asset.custodian_id = data.destination_custodian_id
            new_status = AssetStatus.IN_USE if asset.custodian_id else AssetStatus.AVAILABLE

        elif m_type == MovementType.MAINTENANCE_OUT:
            new_status = AssetStatus.IN_MAINTENANCE
            if data.destination_location_id:
                asset.location_id = data.destination_location_id

        elif m_type == MovementType.MAINTENANCE_IN:
            new_status = AssetStatus.AVAILABLE
            if data.destination_location_id:
                asset.location_id = data.destination_location_id
            if data.destination_custodian_id:
                asset.custodian_id = data.destination_custodian_id
                new_status = AssetStatus.IN_USE

        elif m_type == MovementType.WRITE_OFF:
            new_status = AssetStatus.WRITTEN_OFF
            asset.custodian_id = None
            if not data.new_condition:
                data.new_condition = AssetCondition.UNSERVICEABLE

        elif m_type == MovementType.STATUS_UPDATE:
            new_status = asset.status
            new_location_name = prev_location_name
            new_custodian_name = prev_custodian_name

        else:
            new_status = asset.status

        # Atualiza status e condição no ativo
        asset.status = new_status
        if data.new_condition:
            asset.condition = data.new_condition
        asset.updated_at = datetime.now()

        # Gera termo de responsabilidade sequencial
        term_code = None
        if data.generate_term or m_type in [MovementType.ALLOCATION, MovementType.RETURN_STOCK]:
            count_year = db.query(Movement).filter(
                Movement.movement_type.in_([MovementType.ALLOCATION, MovementType.RETURN_STOCK])
            ).count() + 1
            term_code = f"TR-{datetime.now().year}-{count_year:05d}"

        # Criação do registro imutável no log de fluxo de movimentações
        movement = Movement(
            asset_id=asset.id,
            movement_type=data.movement_type,
            timestamp=datetime.now(),
            origin_location_id=prev_location_id,
            origin_location_name=prev_location_name or "Não definido",
            origin_custodian_id=prev_custodian_id,
            origin_custodian_name=prev_custodian_name or "Nenhum / Estoque",
            destination_location_id=data.destination_location_id or prev_location_id,
            destination_location_name=new_location_name or prev_location_name,
            destination_custodian_id=data.destination_custodian_id if m_type != MovementType.RETURN_STOCK else None,
            destination_custodian_name=new_custodian_name if m_type != MovementType.RETURN_STOCK else "Almoxarifado / Estoque",
            previous_status=prev_status,
            new_status=new_status,
            previous_condition=prev_condition,
            new_condition=data.new_condition or prev_condition,
            reason=data.reason.strip(),
            operator_name=data.operator_name.strip(),
            term_code=term_code,
            term_signed=False,
            notes=data.notes
        )

        db.add(movement)
        db.commit()
        db.refresh(movement)
        return movement

    @staticmethod
    def get_by_id(db: Session, movement_id: int) -> Optional[Movement]:
        return db.query(Movement).options(
            joinedload(Movement.asset),
            joinedload(Movement.origin_location),
            joinedload(Movement.destination_location),
            joinedload(Movement.origin_custodian),
            joinedload(Movement.destination_custodian)
        ).filter(Movement.id == movement_id).first()

    @staticmethod
    def get_by_uuid(db: Session, movement_uuid: str) -> Optional[Movement]:
        return db.query(Movement).options(
            joinedload(Movement.asset),
            joinedload(Movement.origin_location),
            joinedload(Movement.destination_location),
            joinedload(Movement.origin_custodian),
            joinedload(Movement.destination_custodian)
        ).filter(Movement.movement_uuid == movement_uuid).first()

    @staticmethod
    def get_timeline_for_asset(db: Session, asset_id: int) -> List[Movement]:
        """
        Retorna toda a linha do tempo / histórico de movimentação do equipamento,
        ordenada cronologicamente (da mais recente para a mais antiga).
        """
        return db.query(Movement).options(
            joinedload(Movement.origin_location),
            joinedload(Movement.destination_location),
            joinedload(Movement.origin_custodian),
            joinedload(Movement.destination_custodian)
        ).filter(Movement.asset_id == asset_id).order_by(desc(Movement.timestamp)).all()

    @staticmethod
    def get_all_movements(
        db: Session,
        filters: Optional[MovementFilter] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Movement], int]:
        query = db.query(Movement).options(
            joinedload(Movement.asset),
            joinedload(Movement.origin_location),
            joinedload(Movement.destination_location),
            joinedload(Movement.origin_custodian),
            joinedload(Movement.destination_custodian)
        )

        if filters:
            if filters.asset_id:
                query = query.filter(Movement.asset_id == filters.asset_id)
            if filters.movement_type:
                query = query.filter(Movement.movement_type == filters.movement_type)
            if filters.custodian_id:
                query = query.filter(
                    (Movement.origin_custodian_id == filters.custodian_id) |
                    (Movement.destination_custodian_id == filters.custodian_id)
                )
            if filters.location_id:
                query = query.filter(
                    (Movement.origin_location_id == filters.location_id) |
                    (Movement.destination_location_id == filters.location_id)
                )
            if filters.start_date:
                query = query.filter(Movement.timestamp >= filters.start_date)
            if filters.end_date:
                query = query.filter(Movement.timestamp <= filters.end_date)

        total = query.count()
        items = query.order_by(desc(Movement.timestamp)).offset(skip).limit(limit).all()
        return items, total

    @staticmethod
    def get_term_details(db: Session, movement_id: int) -> Optional[Dict[str, Any]]:
        """
        Estrutura todos os dados necessários para renderização e impressão
        do Termo de Entrega e Responsabilidade (Cautela) ou Devolução.
        """
        movement = MovementService.get_by_id(db, movement_id)
        if not movement:
            return None

        asset = movement.asset
        custodian = movement.destination_custodian or movement.origin_custodian

        return {
            "company": {
                "name": COMPANY_NAME,
                "cnpj": COMPANY_CNPJ,
                "address": COMPANY_ADDRESS,
            },
            "term_code": movement.term_code or f"TR-{movement.timestamp.year}-{movement.id:05d}",
            "movement_type": movement.movement_type.value,
            "date": movement.timestamp.strftime("%d/%m/%Y às %H:%M"),
            "operator": movement.operator_name,
            "reason": movement.reason,
            "notes": movement.notes or "",
            "asset": {
                "id": asset.id,
                "tag": asset.tag,
                "name": asset.name,
                "brand": asset.brand or "N/A",
                "model": asset.model or "N/A",
                "serial_number": asset.serial_number or "N/A",
                "category": asset.category.value,
                "condition": movement.new_condition.value if movement.new_condition else asset.condition.value,
                "specifications": asset.specifications or "N/A"
            },
            "custodian": {
                "name": custodian.name if custodian else movement.destination_custodian_name or "Almoxarifado / Estoque",
                "registration_code": custodian.registration_code if custodian else "N/A",
                "role": custodian.role if custodian else "N/A",
                "department": custodian.department if custodian else "N/A",
                "email": custodian.email if custodian else "N/A",
                "cpf": custodian.cpf if custodian and custodian.cpf else "N/A"
            },
            "location": {
                "name": movement.destination_location_name or "Almoxarifado / Estoque"
            }
        }
