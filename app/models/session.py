from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class UserSession(Base):
    """
    Sessão de autenticação armazenada no banco (revogável no servidor).

    O cookie guarda apenas o token aleatório; o banco armazena somente o
    hash SHA-256 do token, nunca o token em texto puro. A sessão expira
    no servidor (expires_at) e pode ser revogada a qualquer momento
    (logout), mesmo que o cookie ainda exista no cliente.
    """
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)  # sha256 hex do token
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

    # Relacionamentos
    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<UserSession(id={self.id}, user_id={self.user_id}, expires_at='{self.expires_at}')>"