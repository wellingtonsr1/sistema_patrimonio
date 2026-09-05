"""
Serviço de sessão (server-side).

- Ao autenticar, gera um token aleatório criptograficamente seguro
  (secrets.token_urlsafe) e guarda no banco apenas o hash SHA-256 dele.
- O cookie (HttpOnly, SameSite=Lax, Secure conforme configuração) guarda o
  token em texto puro — o banco nunca contém o token.
- A sessão expira no servidor (AUTH_SESSION_TTL) e é revogada no logout,
  o que invalida o cookie mesmo que ele ainda exista no cliente.

Desacoplado do mecanismo de autenticação (local ou AD futuro): só precisa
do id do usuário.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Response
from sqlalchemy.orm import Session

from app.config import AUTH_COOKIE_NAME, AUTH_COOKIE_SECURE, AUTH_SESSION_TTL
from app.models.session import UserSession
from app.models.user import User


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def purge_expired_sessions(db: Session) -> int:
    """Remove sessões expiradas do banco. Retorna quantas foram removidas."""
    deleted = (
        db.query(UserSession)
        .filter(UserSession.expires_at <= datetime.utcnow())
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def create_session(db: Session, user_id: int) -> str:
    """
    Cria uma nova sessão para o usuário e retorna o token (a ser gravado
    no cookie). Apenas o hash do token é persistido.
    """
    purge_expired_sessions(db)
    token = secrets.token_urlsafe(32)
    session_row = UserSession(
        token_hash=_hash_token(token),
        user_id=user_id,
        expires_at=datetime.utcnow() + timedelta(seconds=AUTH_SESSION_TTL),
    )
    db.add(session_row)
    db.commit()
    return token


def get_session_user(db: Session, token: Optional[str]) -> Optional[User]:
    """
    Retorna o usuário da sessão (token do cookie) ou None se a sessão for
    inválida, expirada ou o usuário estiver inativo.
    """
    if not token:
        return None
    return (
        db.query(User)
        .join(UserSession, UserSession.user_id == User.id)
        .filter(
            UserSession.token_hash == _hash_token(token),
            UserSession.expires_at > datetime.utcnow(),
            User.is_active == True,  # noqa: E712
        )
        .first()
    )


def revoke_session(db: Session, token: Optional[str]) -> None:
    """Revoga a sessão no servidor (logout)."""
    if not token:
        return
    db.query(UserSession).filter(UserSession.token_hash == _hash_token(token)).delete(
        synchronize_session=False
    )
    db.commit()


def set_session_cookie(response: Response, token: str) -> None:
    """Grava o cookie de sessão no response."""
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=AUTH_SESSION_TTL,
        path="/",
        httponly=True,
        samesite="lax",
        secure=AUTH_COOKIE_SECURE,
    )


def clear_session_cookie(response: Response) -> None:
    """Remove o cookie de sessão no response."""
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")