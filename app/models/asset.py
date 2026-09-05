from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import AssetStatus, AssetCondition, AssetCategory


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    tag = Column(String(50), unique=True, index=True, nullable=False)        # Número de Tombamento / Tag / Plaqueta
    name = Column(String(150), nullable=False, index=True)                   # Nome / Identificação do Equipamento
    category = Column(Enum(AssetCategory), nullable=False, default=AssetCategory.OTHER)
    brand = Column(String(100), nullable=True)                               # Marca / Fabricante
    model = Column(String(100), nullable=True)                               # Modelo
    serial_number = Column(String(100), unique=True, nullable=True, index=True) # Número de Série
    specifications = Column(Text, nullable=True)                             # Especificações técnicas detalhadas

    # Dados Fiscais / Aquisição
    purchase_date = Column(DateTime, nullable=True)                          # Data da compra
    purchase_value = Column(Float, nullable=False, default=0.0)              # Valor de aquisição (R$)
    invoice_number = Column(String(100), nullable=True)                      # Número da Nota Fiscal
    supplier = Column(String(150), nullable=True)                            # Fornecedor / Loja
    warranty_expiry = Column(DateTime, nullable=True)                        # Fim da garantia

    # Estado e Status Atual
    status = Column(Enum(AssetStatus), nullable=False, default=AssetStatus.AVAILABLE)
    condition = Column(Enum(AssetCondition), nullable=False, default=AssetCondition.NEW)
    
    # Localização e Responsável atuais
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    custodian_id = Column(Integer, ForeignKey("custodians.id"), nullable=True)

    # Metadados
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    location = relationship("Location", back_populates="assets")
    custodian = relationship("Custodian", back_populates="assets")
    movements = relationship("Movement", back_populates="asset", cascade="all, delete-orphan", order_by="desc(Movement.timestamp)")
    maintenances = relationship("Maintenance", back_populates="asset", cascade="all, delete-orphan", order_by="desc(Maintenance.start_date)")

    def __repr__(self):
        return f"<Asset(id={self.id}, tag='{self.tag}', name='{self.name}', status='{self.status}')>"
