from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class AuditLog(Base):
    """
    Trilha de auditoria de ações (login, falhas de login, criações,
    alterações, bloqueios, resets de senha, movimentações patrimoniais,
    mudanças de perfil/permissão e acessos negados).

    Registra o ator (com snapshot do username), IP, módulo, recurso,
    resultado e os dados anteriores/posteriores (JSON) para rastreabilidade.
    Não deve ser alterável/apagável por usuários comuns (apenas leitura via
    `auditoria.visualizar`; nenhuma rota de escrita existe).
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Ator (FK preservada; username é snapshot, sobrevive à exclusão do usuário)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username = Column(String(100), nullable=True)

    # Contexto da ação
    action = Column(String(50), nullable=False, index=True)       # LOGIN, CREATE, UPDATE, BLOCK, ...
    module = Column(String(50), nullable=True, index=True)        # Patrimônio, Usuários, ...
    resource = Column(String(100), nullable=True)                 # tipo de recurso (ex: Asset, User)
    resource_id = Column(Integer, nullable=True)                  # id do recurso afetado
    resource_ref = Column(String(150), nullable=True)             # referência legível (tag, matrícula, username)
    ip_address = Column(String(45), nullable=True)
    result = Column(String(20), nullable=False, default="SUCCESS")  # SUCCESS | FAILURE | DENIED | LOCKED
    description = Column(Text, nullable=True)

    # Dados anteriores / posteriores (JSON serializado)
    previous_data = Column(Text, nullable=True)
    new_data = Column(Text, nullable=True)

    # Relacionamento
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', module='{self.module}', ts='{self.timestamp}')>"