from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    """
    Usuário do sistema.

    O campo `auth_provider` registra a origem da conta ("local" hoje;
    "ad" ficará reservado para a futura integração com Active Directory).
    Nunca armazena a senha em texto puro — apenas `password_hash`
    (PBKDF2-HMAC-SHA256 com salt por usuário).
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)                    # pbkdf2_sha256$iter$salt$hash
    full_name = Column(String(150), nullable=True)
    email = Column(String(150), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)                              # flag simples; RBAC completo fica para depois
    auth_provider = Column(String(20), default="local", nullable=False)    # local | ad (futuro)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Proteção contra força bruta (preenchidos pela autenticação)
    failed_login_attempts = Column(Integer, default=0, nullable=False)   # tentativas falhas consecutivas
    locked_until = Column(DateTime, nullable=True)                       # bloqueio temporário por excesso de tentativas

    # Relacionamentos
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', provider='{self.auth_provider}')>"