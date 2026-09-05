from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.custodian import Custodian
from app.models.asset import Asset
from app.models.enums import AssetStatus
from app.schemas.custodian import CustodianCreate, CustodianUpdate


class CustodianService:
    @staticmethod
    def get_all(db: Session, active_only: bool = False) -> List[Custodian]:
        query = db.query(Custodian)
        if active_only:
            query = query.filter(Custodian.is_active == True)
        return query.order_by(Custodian.name).all()

    @staticmethod
    def get_by_id(db: Session, custodian_id: int) -> Optional[Custodian]:
        return db.query(Custodian).filter(Custodian.id == custodian_id).first()

    @staticmethod
    def get_by_registration_code(db: Session, code: str) -> Optional[Custodian]:
        return db.query(Custodian).filter(Custodian.registration_code == code).first()

    @staticmethod
    def create(db: Session, data: CustodianCreate) -> Custodian:
        if CustodianService.get_by_registration_code(db, data.registration_code):
            raise ValueError("Matrícula já cadastrada")
        if db.query(Custodian).filter(Custodian.email == data.email).first():
            raise ValueError("E-mail já cadastrado")

        custodian = Custodian(
            registration_code=data.registration_code,
            name=data.name,
            email=data.email,
            cpf=data.cpf,
            role=data.role,
            department=data.department,
            is_active=data.is_active,
        )
        db.add(custodian)
        db.commit()
        db.refresh(custodian)
        return custodian

    @staticmethod
    def update(db: Session, custodian_id: int, data: CustodianUpdate) -> Optional[Custodian]:
        custodian = CustodianService.get_by_id(db, custodian_id)
        if not custodian:
            return None

        if data.registration_code is not None and data.registration_code != custodian.registration_code:
            if CustodianService.get_by_registration_code(db, data.registration_code):
                raise ValueError("Matrícula já cadastrada")
        if data.email is not None and data.email != custodian.email:
            if db.query(Custodian).filter(Custodian.email == data.email).first():
                raise ValueError("E-mail já cadastrado")

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(custodian, key, value)

        db.commit()
        db.refresh(custodian)
        return custodian

    @staticmethod
    def get_assigned_assets(db: Session, custodian_id: int) -> List[Asset]:
        """Retorna os equipamentos atualmente sob posse/custódia do colaborador"""
        return db.query(Asset).filter(
            Asset.custodian_id == custodian_id,
            Asset.status != AssetStatus.WRITTEN_OFF
        ).all()

    @staticmethod
    def count_assigned_assets(db: Session, custodian_id: int) -> int:
        return db.query(func.count(Asset.id)).filter(
            Asset.custodian_id == custodian_id,
            Asset.status != AssetStatus.WRITTEN_OFF
        ).scalar() or 0
