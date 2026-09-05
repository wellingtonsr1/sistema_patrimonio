from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import MaintenanceType, MaintenanceStatus


class Maintenance(Base):
    """
    Registro detalhado de manutenções preventivas, corretivas e upgrades
    de equipamentos patrimoniais.
    """
    __tablename__ = "maintenances"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    maintenance_type = Column(Enum(MaintenanceType), nullable=False, default=MaintenanceType.CORRECTIVE)
    status = Column(Enum(MaintenanceStatus), nullable=False, default=MaintenanceStatus.IN_PROGRESS)

    provider_name = Column(String(150), nullable=True)     # Assistência Técnica / Técnico Responsável
    description = Column(Text, nullable=False)             # Problema relatado / Escopo da manutenção
    solution = Column(Text, nullable=True)                 # Resolução / Peças trocadas
    cost = Column(Float, default=0.0)                      # Custo total (R$)

    start_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamento
    asset = relationship("Asset", back_populates="maintenances")

    def __repr__(self):
        return f"<Maintenance(id={self.id}, asset_id={self.asset_id}, status='{self.status}')>"
