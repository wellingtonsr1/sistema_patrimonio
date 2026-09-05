from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class Permission(Base):
    """
    Permissão granular no padrão `modulo.acao` (ex: `patrimonio.criar`).

    O nome é a chave canônica usada nas verificações de autorização
    (`require_permission`); `module` e `label` servem para agrupar e
    apresentar as permissões na interface de gestão de perfis.
    """
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)   # ex: patrimonio.criar
    module = Column(String(50), nullable=False, index=True)               # ex: Patrimônio
    label = Column(String(150), nullable=False)                           # ex: Cadastrar patrimônio
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Permission(id={self.id}, name='{self.name}')>"