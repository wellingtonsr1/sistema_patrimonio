"""
Camada de provedores de autenticação.

A autenticação não fica acoplada a um único mecanismo: os pontos de login
usam `get_auth_provider()`, que hoje retorna o provedor local. A futura
integração com Active Directory/LDAP deverá implementar um novo provedor
(ADAuthProvider) e ativá-lo via AUTH_PROVIDER=ad — sem alterar os pontos
de login, sessão ou os endpoints protegidos.
"""

from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy.orm import Session

from app.config import AUTH_PROVIDER
from app.models.user import User


class AuthProvider(ABC):
    """Contrato comum de autenticação. Retorna o User autenticado ou None."""

    name: str = "base"

    @abstractmethod
    def authenticate(self, db: Session, username: str, password: str) -> Optional[User]:
        raise NotImplementedError


class LocalAuthProvider(AuthProvider):
    """Autenticação local com usuário/senha armazenados no banco."""

    name = "local"

    def authenticate(self, db: Session, username: str, password: str) -> Optional[User]:
        # Importa aqui para evitar ciclo de importação entre módulos de serviço
        from app.services.auth_service import authenticate as _local_authenticate
        return _local_authenticate(db, username, password)


class ADAuthProvider(AuthProvider):
    """
    Provedor de autenticação via Active Directory / LDAP / LDAPS.

    Delega ao serviço da integração (ad_service.authenticate_and_sync), que
    autentica no diretório, resolve o perfil pelo mapeamento Grupo AD → Perfil
    EXISTENTE, provisiona/vincula o usuário e registra auditoria. A senha NUNCA
    é persistida ou logada.
    """

    name = "ad"

    def authenticate(self, db: Session, username: str, password: str) -> Optional[User]:
        from app.services import ad_service
        return ad_service.authenticate_and_sync(db, username, password)


def get_auth_provider(name: Optional[str] = None) -> AuthProvider:
    """Retorna o provedor de autenticação ativo (padrão: local)."""
    provider_name = (name or AUTH_PROVIDER).strip().lower()
    if provider_name == "local":
        return LocalAuthProvider()
    if provider_name in ("ad", "ldap", "ldaps"):
        return ADAuthProvider()
    raise ValueError(f"Provedor de autenticação desconhecido: '{provider_name}'")


def resolve_authentication(db: Session, username: str, password: str) -> Optional[User]:
    """
    Resolve o login entre os provedores, preservando 100% o acesso local:

    1. Usuário EXISTENTE local (auth_provider='local', ex: admin) →
       autenticação local atual (jamais migra para AD).
    2. Demais casos, com a integração AD habilitada → Active Directory
       (autentica, sincroniza perfil e provisiona na 1ª entrada).
    3. AD desabilitado/indisponível para o usuário → comportamento local
       (None), sem falha silenciosa: erros tipados do AD são propagados.

    Usuários AD autenticam SEMPRE pelo AD (nunca por senha local).
    """
    from app.services import ad_service

    username = (username or "").strip()
    existing = (
        db.query(User).filter(User.username == username).first()
        if username else None
    )

    # 1) Contas locais existentes continuam usando a autenticação atual
    if existing is not None and existing.auth_provider == ad_service.PROVIDER_LOCAL:
        return LocalAuthProvider().authenticate(db, username, password)

    # 2/3) AD quando habilitado; caso contrário, caminho local (compatibilidade)
    if ad_service.ad_enabled(db):
        return ADAuthProvider().authenticate(db, username, password)

    if existing is not None and existing.auth_provider == ad_service.PROVIDER_AD:
        # Usuário AD com integração desabilitada: sem senha local utilizável.
        return None
    return LocalAuthProvider().authenticate(db, username, password)