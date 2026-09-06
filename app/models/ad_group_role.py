from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class ADGroupRole(Base):
    """
    Mapeamento Grupo AD → Perfil EXISTENTE do SisPatrimônio.

    O AD NÃO define permissões: apenas aponta para um perfil já cadastrado,
    que por sua vez determina as permissões (RBAC existente preservado).
    `priority` (1 = maior) resolve usuários em vários grupos mapeados.
    """
    __tablename__ = "ad_group_roles"
    __table_args__ = (
        UniqueConstraint("group_name", name="uq_ad_group_role_group"),
    )

    id = Column(Integer, primary_key=True, index=True)
    group_name = Column(String(255), unique=True, index=True, nullable=False)  # sAMAccountName/cn do grupo
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    priority = Column(Integer, nullable=False, default=10)   # menor = maior prioridade
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    role = relationship("Role")

    def __repr__(self):
        return f"<ADGroupRole(group='{self.group_name}', role_id={self.role_id}, priority={self.priority})>"
