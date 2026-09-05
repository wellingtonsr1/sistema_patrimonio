from datetime import datetime
import uuid
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import MovementType, AssetStatus, AssetCondition


class Movement(Base):
    """
    Gravação imutável do fluxo de movimentação de cada equipamento.
    Armazena o histórico auditável de cada transferência, alocação,
    manutenção, devolução ou baixa, incluindo snapshots de origem e destino.
    """
    __tablename__ = "movements"

    id = Column(Integer, primary_key=True, index=True)
    movement_uuid = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()), index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    movement_type = Column(Enum(MovementType), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Origem (Snapshots e Foreign Keys)
    origin_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    origin_location_name = Column(String(150), nullable=True)
    origin_custodian_id = Column(Integer, ForeignKey("custodians.id"), nullable=True)
    origin_custodian_name = Column(String(150), nullable=True)

    # Destino (Snapshots e Foreign Keys)
    destination_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    destination_location_name = Column(String(150), nullable=True)
    destination_custodian_id = Column(Integer, ForeignKey("custodians.id"), nullable=True)
    destination_custodian_name = Column(String(150), nullable=True)

    # Transições de Status e Condição
    previous_status = Column(Enum(AssetStatus), nullable=True)
    new_status = Column(Enum(AssetStatus), nullable=False)
    previous_condition = Column(Enum(AssetCondition), nullable=True)
    new_condition = Column(Enum(AssetCondition), nullable=True)

    # Dados da Operação & Termo de Responsabilidade
    reason = Column(String(255), nullable=False)                            # Justificativa obrigatória
    operator_name = Column(String(100), nullable=False, default="Sistema")  # Operador responsável pelo registro
    term_code = Column(String(50), nullable=True, index=True)               # Código único do Termo (ex: TR-2026-0001)
    term_signed = Column(Boolean, default=False)                            # Se termo foi assinado/aceito
    notes = Column(Text, nullable=True)                                     # Observações detalhadas
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    asset = relationship("Asset", back_populates="movements")
    origin_location = relationship("Location", foreign_keys=[origin_location_id])
    destination_location = relationship("Location", foreign_keys=[destination_location_id])
    origin_custodian = relationship("Custodian", foreign_keys=[origin_custodian_id])
    destination_custodian = relationship("Custodian", foreign_keys=[destination_custodian_id])

    def __repr__(self):
        return (
            f"<Movement(id={self.id}, asset_id={self.asset_id}, "
            f"type='{self.movement_type}', timestamp='{self.timestamp}')>"
        )
