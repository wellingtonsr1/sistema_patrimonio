from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)  # Ex: "Matriz - TI - Sala dos Servidores"
    branch = Column(String(100), nullable=False)                         # Ex: "Matriz SP"
    building = Column(String(100), nullable=True)                       # Ex: "Edifício Central"
    floor = Column(String(50), nullable=True)                           # Ex: "5º Andar"
    room = Column(String(50), nullable=True)                            # Ex: "Sala 502"
    department = Column(String(100), nullable=False)                    # Ex: "Tecnologia da Informação"
    manager_name = Column(String(100), nullable=True)                   # Responsável pelo setor
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    assets = relationship("Asset", back_populates="location")

    def __repr__(self):
        return f"<Location(id={self.id}, name='{self.name}', department='{self.department}')>"
