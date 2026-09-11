from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, desc, and_
from app.models.asset import Asset
from app.models.movement import Movement
from app.models.location import Location
from app.models.custodian import Custodian
from app.models.maintenance import Maintenance
from app.models.enums import AssetStatus, AssetCondition, MovementType, MaintenanceStatus
from app.schemas.asset import AssetCreate, AssetUpdate


class AssetService:
    @staticmethod
    def get_all(
        db: Session,
        search: Optional[str] = None,
        status: Optional[AssetStatus] = None,
        category: Optional[str] = None,
        location_id: Optional[int] = None,
        custodian_id: Optional[int] = None,
        brand: Optional[str] = None,
        model: Optional[str] = None,
        department: Optional[str] = None,
        maintenance_status: Optional[str] = None,
        purchase_date_from: Optional[datetime] = None,
        purchase_date_to: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Asset], int]:
        query = db.query(Asset).options(
            joinedload(Asset.location),
            joinedload(Asset.custodian),
            joinedload(Asset.maintenances)
        )

        if search:
            search_filter = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    # Campos do equipamento
                    Asset.tag.ilike(search_filter),
                    Asset.name.ilike(search_filter),
                    Asset.brand.ilike(search_filter),
                    Asset.model.ilike(search_filter),
                    Asset.serial_number.ilike(search_filter),
                    Asset.invoice_number.ilike(search_filter),
                    # Colaborador relacionado
                    Asset.custodian.has(Custodian.name.ilike(search_filter)),
                    # Localização relacionada (todos os campos)
                    Asset.location.has(
                        or_(
                            Location.name.ilike(search_filter),
                            Location.branch.ilike(search_filter),
                            Location.building.ilike(search_filter),
                            Location.floor.ilike(search_filter),
                            Location.room.ilike(search_filter),
                            Location.department.ilike(search_filter),
                            Location.manager_name.ilike(search_filter),
                            Location.description.ilike(search_filter)
                        )
                    )
                )
            )

        if status:
            query = query.filter(Asset.status == status)

        if category:
            query = query.filter(Asset.category == category)

        if location_id:
            query = query.filter(Asset.location_id == location_id)

        if custodian_id:
            query = query.filter(Asset.custodian_id == custodian_id)

        # Novos filtros avançados
        if brand:
            query = query.filter(Asset.brand.ilike(f"%{brand}%"))

        if model:
            query = query.filter(Asset.model.ilike(f"%{model}%"))

        if department:
            query = query.filter(Asset.location.has(Location.department == department))

        if maintenance_status == "open":
            # Equipamentos com manutenção em andamento
            query = query.filter(Asset.maintenances.any(Maintenance.status == MaintenanceStatus.IN_PROGRESS))
        elif maintenance_status == "closed":
            # Equipamentos sem manutenção aberta (ou com todas finalizadas)
            query = query.filter(
                ~Asset.maintenances.any(Maintenance.status == MaintenanceStatus.IN_PROGRESS)
            )

        if purchase_date_from:
            query = query.filter(Asset.purchase_date >= purchase_date_from)

        if purchase_date_to:
            query = query.filter(Asset.purchase_date <= purchase_date_to)

        total = query.count()
        assets = query.order_by(desc(Asset.created_at)).offset(skip).limit(limit).all()
        return assets, total

    @staticmethod
    def get_by_id(db: Session, asset_id: int) -> Optional[Asset]:
        return db.query(Asset).options(
            joinedload(Asset.location),
            joinedload(Asset.custodian),
            joinedload(Asset.movements),
            joinedload(Asset.maintenances)
        ).filter(Asset.id == asset_id).first()

    @staticmethod
    def get_by_tag(db: Session, tag: str) -> Optional[Asset]:
        return db.query(Asset).options(
            joinedload(Asset.location),
            joinedload(Asset.custodian)
        ).filter(Asset.tag == tag.strip().upper()).first()

    @staticmethod
    def create(db: Session, data: AssetCreate) -> Asset:
        tag = data.tag.strip().upper()
        if AssetService.get_by_tag(db, tag):
            raise ValueError(f"Já existe um equipamento com o tombamento '{tag}'")

        serial_number = data.serial_number.strip() if data.serial_number else None
        if serial_number:
            existing = db.query(Asset).filter(Asset.serial_number == serial_number).first()
            if existing:
                raise ValueError(f"Já existe um equipamento com o número de série '{serial_number}'")

        # Define status inicial baseado na alocação
        initial_status = AssetStatus.IN_USE if data.initial_custodian_id else AssetStatus.AVAILABLE

        asset = Asset(
            tag=tag,
            name=data.name.strip(),
            category=data.category,
            brand=data.brand,
            model=data.model,
            serial_number=serial_number,
            specifications=data.specifications,
            purchase_date=data.purchase_date or datetime.now(),
            purchase_value=data.purchase_value or 0.0,
            invoice_number=data.invoice_number,
            supplier=data.supplier,
            warranty_expiry=data.warranty_expiry,
            condition=data.condition,
            status=initial_status,
            location_id=data.initial_location_id,
            custodian_id=data.initial_custodian_id,
            notes=data.notes
        )
        db.add(asset)
        db.flush()

        # Obter snapshots para a gravação da movimentação inicial de aquisição
        location_name = None
        if data.initial_location_id:
            loc = db.query(Location).filter(Location.id == data.initial_location_id).first()
            if loc:
                location_name = f"{loc.branch} - {loc.department} ({loc.name})"

        custodian_name = None
        if data.initial_custodian_id:
            cust = db.query(Custodian).filter(Custodian.id == data.initial_custodian_id).first()
            if cust:
                custodian_name = f"{cust.name} ({cust.registration_code})"

        # Grava o primeiro registro no fluxo de movimentação (ENTRADA_AQUISICAO)
        initial_movement = Movement(
            asset_id=asset.id,
            movement_type=MovementType.ACQUISITION,
            timestamp=datetime.now(),
            origin_location_name="Fornecedor / Entrada Inicial",
            origin_custodian_name="Almoxarifado Geral",
            destination_location_id=data.initial_location_id,
            destination_location_name=location_name or "Estoque Central",
            destination_custodian_id=data.initial_custodian_id,
            destination_custodian_name=custodian_name,
            previous_status=None,
            new_status=initial_status,
            previous_condition=None,
            new_condition=data.condition,
            reason=f"Tombamento inicial e incorporação ao patrimônio (NF: {data.invoice_number or 'N/A'})",
            operator_name=data.initial_operator or "Sistema",
            term_code=f"TR-INIC-{datetime.now().year}-{asset.id:04d}",
            notes="Registro automático de cadastro inicial do bem."
        )
        db.add(initial_movement)
        db.commit()
        db.refresh(asset)
        return asset

    @staticmethod
    def update(db: Session, asset_id: int, data: AssetUpdate) -> Optional[Asset]:
        asset = AssetService.get_by_id(db, asset_id)
        if not asset:
            return None

        if data.serial_number:
            serial_number = data.serial_number.strip()
            existing = db.query(Asset).filter(
                Asset.serial_number == serial_number,
                Asset.id != asset_id
            ).first()
            if existing:
                raise ValueError(f"Já existe um equipamento com o número de série '{serial_number}'")

        old_condition = asset.condition

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(asset, key, value)

        # Se houve alteração de condição, grava no fluxo
        if data.condition and data.condition != old_condition:
            movement = Movement(
                asset_id=asset.id,
                movement_type=MovementType.STATUS_UPDATE,
                timestamp=datetime.now(),
                origin_location_id=asset.location_id,
                origin_location_name=asset.location.name if asset.location else None,
                origin_custodian_id=asset.custodian_id,
                origin_custodian_name=asset.custodian.name if asset.custodian else None,
                destination_location_id=asset.location_id,
                destination_location_name=asset.location.name if asset.location else None,
                destination_custodian_id=asset.custodian_id,
                destination_custodian_name=asset.custodian.name if asset.custodian else None,
                previous_status=asset.status,
                new_status=asset.status,
                previous_condition=old_condition,
                new_condition=data.condition,
                reason="Vistoria técnica / Atualização de estado de conservação",
                operator_name="Sistema",
                notes=f"Estado de conservação alterado de {old_condition.label} para {data.condition.label}."
            )
            db.add(movement)

        db.commit()
        db.refresh(asset)
        return asset

    @staticmethod
    def calculate_depreciation(asset: Asset, annual_rate: float = 0.20) -> dict:
        """
        Calcula a depreciação linear contábil estimada do bem.
        Padrão: 20% ao ano (5 anos de vida útil para equipamentos de TI).
        """
        if not asset.purchase_date or not asset.purchase_value:
            return {
                "initial_value": asset.purchase_value or 0.0,
                "current_value": asset.purchase_value or 0.0,
                "depreciated_amount": 0.0,
                "depreciation_percent": 0.0,
                "age_months": 0
            }

        now = datetime.now()
        months = max(0, (now.year - asset.purchase_date.year) * 12 + (now.month - asset.purchase_date.month))
        monthly_rate = annual_rate / 12.0
        total_depreciation_rate = min(1.0, months * monthly_rate)
        
        depreciated_amount = round(asset.purchase_value * total_depreciation_rate, 2)
        current_value = round(max(0.0, asset.purchase_value - depreciated_amount), 2)
        percent = round(total_depreciation_rate * 100, 1)

        return {
            "initial_value": asset.purchase_value,
            "current_value": current_value,
            "depreciated_amount": depreciated_amount,
            "depreciation_percent": percent,
            "age_months": months
        }
