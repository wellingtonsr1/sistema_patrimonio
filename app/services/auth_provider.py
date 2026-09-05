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
    Provedor reservado para Active Directory / LDAP / LDAPS.

    NÃO IMPLEMENTADO nesta versão. A estrutura (configurações AD_* em
    app/config.py e este provedor) existe apenas como preparação. Ativar
    AUTH_PROVIDER=ad fará o sistema recusar autenticação até que este
    provedor seja implementado, em vez de falhar silenciosamente.
    """

    name = "ad"

    def authenticate(self, db: Session, username: str, password: str) -> Optional[User]:
        raise NotImplementedError(
            "Autenticação via Active Directory/LDAP ainda não foi implementada. "
            "Use AUTH_PROVIDER=local ou implemente o ADAuthProvider."
        )


def get_auth_provider(name: Optional[str] = None) -> AuthProvider:
    """Retorna o provedor de autenticação ativo (padrão: local)."""
    provider_name = (name or AUTH_PROVIDER).strip().lower()
    if provider_name == "local":
        return LocalAuthProvider()
    if provider_name in ("ad", "ldap", "ldaps"):
        return ADAuthProvider()
    raise ValueError(f"Provedor de autenticação desconhecido: '{provider_name}'")