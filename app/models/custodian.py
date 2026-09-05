from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class Custodian(Base):
    __tablename__ = "custodians"

    id = Column(Integer, primary_key=True, index=True)
    registration_code = Column(String(50), nullable=False, unique=True, index=True)  # Matrícula
    name = Column(String(150), nullable=False, index=True)
    email = Column(String(150), nullable=False, unique=True, index=True)
    cpf = Column(String(20), nullable=True)
    role = Column(String(100), nullable=False)                                       # Cargo
    department = Column(String(100), nullable=False)                                 # Setor
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    assets = relationship("Asset", back_populates="custodian")

    def __repr__(self):
        return f"<Custodian(id={self.id}, code='{self.registration_code}', name='{self.name}')>"
