"""
Serviço de autenticação do SisPatrimônio Pro.

Armazenamento de senha: PBKDF2-HMAC-SHA256 (hashlib da biblioteca padrão),
com salt aleatório de 16 bytes por usuário e número de iterações
configurável (AUTH_PBKDF2_ITERATIONS, padrão OWASP 2023: 600.000).
Formato armazenado: pbkdf2_sha256$<iteracoes>$<salt_hex>$<hash_hex>.

O mecanismo de autenticação em si é desacoplado do serviço de sessão
(ver app/services/session_service.py) e do provedor (ver
app/services/auth_provider.py), de modo que a integração futura com
Active Directory/LDAP possa trocar apenas o provedor.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import (
    AUTH_ADMIN_NAME,
    AUTH_ADMIN_PASSWORD,
    AUTH_ADMIN_USERNAME,
    AUTH_LOCKOUT_SECONDS,
    AUTH_MAX_FAILED_ATTEMPTS,
    AUTH_PBKDF2_ITERATIONS,
)
from app.models.user import User

# Hash "dummy" usado quando o usuário não existe, para equalizar o tempo de
# resposta e dificultar enumeração de usuários por timing.
_DUMMY_HASH = None


class AccountLockedError(Exception):
    """
    Conta temporariamente bloqueada por excesso de tentativas de login.
    Propagada pelo provedor de autenticação até o endpoint/página de login,
    que deve responder com 423 Locked (ou mensagem equivalente na web).
    """

    def __init__(self, username: str, locked_until: datetime):
        self.username = username
        self.locked_until = locked_until
        super().__init__(
            f"Conta '{username}' temporariamente bloqueada por excesso de tentativas de login."
        )


def _get_dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("dummy-password-para-equalizar-tempo")
    return _DUMMY_HASH


def hash_password(password: str) -> str:
    """Gera o hash seguro da senha em formato pbkdf2_sha256$iter$salt$hash."""
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, AUTH_PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${AUTH_PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifica a senha contra o hash armazenado, de forma resistente a timing."""
    try:
        algo, iterations_str, salt_hex, hash_hex = stored_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations_str)
        )
        return hmac.compare_digest(derived, expected)
    except (ValueError, TypeError):
        return False


def create_user(
    db: Session,
    username: str,
    password: str,
    full_name: Optional[str] = None,
    email: Optional[str] = None,
    is_admin: bool = False,
    auth_provider: str = "local",
) -> User:
    """Cria um usuário local. Levanta ValueError em dados inválidos."""
    username = (username or "").strip()
    if not username:
        raise ValueError("O nome de usuário não pode ser vazio.")
    if not password or len(password) < 8:
        raise ValueError("A senha deve ter no mínimo 8 caracteres.")
    if db.query(User).filter(User.username == username).first():
        raise ValueError(f"Já existe um usuário com o nome '{username}'.")

    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
        email=email,
        is_admin=is_admin,
        is_active=True,
        auth_provider=auth_provider,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    """
    Autentica um usuário local. Retorna o usuário em caso de sucesso ou None.

    Comportamento de segurança:
    - Usuário inexistente: executa verificação dummy para equalizar o tempo
      de resposta (dificulta enumeração de contas por timing).
    - Senha errada: incrementa `failed_login_attempts`; ao atingir o limite
      (AUTH_MAX_FAILED_ATTEMPTS), bloqueia a conta por AUTH_LOCKOUT_SECONDS.
    - Conta bloqueada: levanta `AccountLockedError` (o chamador decide o
      status HTTP, normalmente 423).
    - Sucesso: zera o contador de falhas e atualiza `last_login`.
    """
    user = db.query(User).filter(User.username == (username or "").strip()).first()
    if user is None:
        verify_password(password or "", _get_dummy_hash())
        return None

    if user.locked_until and user.locked_until > datetime.utcnow():
        raise AccountLockedError(user.username, user.locked_until)

    if not verify_password(password or "", user.password_hash):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= AUTH_MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(seconds=AUTH_LOCKOUT_SECONDS)
            user.failed_login_attempts = 0
        db.commit()
        return None

    if not user.is_active:
        return None

    # Sucesso: zera falhas e registra o acesso
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    db.commit()
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    """
    Troca a senha do usuário (autosserviço), exigindo a senha atual.
    Levanta ValueError em senha atual incorreta ou política não atendida.
    """
    if not verify_password(current_password or "", user.password_hash):
        raise ValueError("A senha atual está incorreta.")
    if not new_password or len(new_password) < 8:
        raise ValueError("A nova senha deve ter no mínimo 8 caracteres.")
    user.password_hash = hash_password(new_password)
    # Força novo login: invalida todas as sessões existentes do usuário
    from app.models.session import UserSession
    db.query(UserSession).filter(UserSession.user_id == user.id).delete(
        synchronize_session=False
    )
    db.commit()


def reset_password(db: Session, user: User, new_password: str) -> None:
    """
    Redefine a senha de um usuário (ação administrativa). Valida a política
    de senha e invalida as sessões existentes (exige novo login).
    """
    if not new_password or len(new_password) < 8:
        raise ValueError("A nova senha deve ter no mínimo 8 caracteres.")
    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    from app.models.session import UserSession
    db.query(UserSession).filter(UserSession.user_id == user.id).delete(
        synchronize_session=False
    )
    db.commit()


def ensure_admin_user(db: Session) -> Optional[User]:
    """
    Cria o usuário administrador inicial a partir das variáveis de ambiente
    (AUTH_ADMIN_USERNAME / AUTH_ADMIN_PASSWORD), se ainda não existir.

    Sem AUTH_ADMIN_PASSWORD definida, nada é criado — o primeiro usuário
    pode ser criado via CLI: python -m app.cli create-user --username ...
    """
    if not AUTH_ADMIN_PASSWORD:
        return None
    if db.query(User).filter(User.username == AUTH_ADMIN_USERNAME).first():
        return None
    try:
        return create_user(
            db,
            username=AUTH_ADMIN_USERNAME,
            password=AUTH_ADMIN_PASSWORD,
            full_name=AUTH_ADMIN_NAME,
            is_admin=True,
        )
    except ValueError as err:
        raise ValueError(
            f"Não foi possível criar o usuário administrador '{AUTH_ADMIN_USERNAME}' "
            f"a partir das variáveis de ambiente: {err}"
        ) from err