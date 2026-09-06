"""
Dependências de autenticação compartilhadas.

- require_api_auth: usado no roteador /api/v1 (protege todas as rotas de
  negócio e exportações). Retorna 401 para sessões ausentes/inválidas.
- require_web_auth: usado no roteador web. Redireciona (303) para /login
  quando não autenticado, preservando o caminho de origem via ?next=.
"""

from typing import Optional, Set

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from urllib.parse import quote

from app.config import AUTH_COOKIE_NAME
from app.database import get_db
from app.models.user import User
from app.services.session_service import get_session_user

# Caminhos web públicos (não exigem login). O /static é servido à parte
# (mount no app) e não passa por este roteador.
PUBLIC_WEB_PATHS = {"/login", "/logout", "/setup"}


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    """Retorna o usuário autenticado pela sessão (cookie), ou None."""
    token = request.cookies.get(AUTH_COOKIE_NAME)
    return get_session_user(db, token)


def require_api_auth(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """Protege endpoints da API REST. Levanta 401 quando não autenticado."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    request.state.user = user
    stash_access(request, db, user)
    return user


def require_web_auth(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    """Protege páginas web. Redireciona para /login quando não autenticado."""
    if request.url.path in PUBLIC_WEB_PATHS:
        return None

    user = get_current_user(request, db)
    if not user:
        path_with_query = request.url.path
        if request.url.query:
            path_with_query = f"{path_with_query}?{request.url.query}"
        next_url = quote(path_with_query, safe="/?=&%")
        raise HTTPException(
            status_code=303,
            headers={"Location": f"/login?next={next_url}"},
        )
    request.state.user = user
    stash_access(request, db, user)
    return user


def _client_ip(request: Request) -> Optional[str]:
    """IP do cliente (ou None em ambientes sem socket, ex: alguns testes)."""
    try:
        return request.client.host if request.client else None
    except Exception:
        return None


def get_request_permissions(
    request: Request, db: Session, user: Optional[User] = None
) -> Set[str]:
    """
    Permissões efetivas do usuário atual, cacheadas por requisição.
    Usada pelas dependências de autorização e pelos templates (menu dinâmico).
    """
    cached = getattr(request.state, "_permissions", None)
    if cached is None:
        from app.services.permission_service import get_user_permission_names
        if user is None:
            user = getattr(request.state, "user", None) or get_current_user(request, db)
        cached = get_user_permission_names(db, user) if user else set()
        request.state._permissions = cached
    return cached


def stash_access(request: Request, db: Session, user: User) -> None:
    """
    Pré-computa permissões e perfis do usuário autenticado e guarda em
    request.state (mesma sessão do request), evitando que os templates
    consultem o banco com uma sessão diferente da do usuário.
    """
    from app.services.permission_service import get_user_permission_names, get_user_role_names
    request.state._permissions = get_user_permission_names(db, user)
    request.state._roles = get_user_role_names(db, user)


def require_permission(permission: str, *, web: bool = False):
    """
    Fábrica de dependências de AUTORIZAÇÃO (deny by default).

    - Não autenticado → 401 (API) ou redirect /login (web).
    - Autenticado sem a permissão → 403, registrado na trilha de auditoria.
    - Administrador (is_admin) → bypass total (compatibilidade com o flag legado).

    Uso:
        @router.post("", dependencies=[Depends(require_permission("patrimonio.criar"))])
    """
    def dependency(request: Request, db: Session = Depends(get_db)) -> User:
        from app.services.audit_service import (
            ACTION_ACCESS_DENIED,
            RESULT_DENIED,
            write_audit,
        )
        from app.services.permission_service import user_has_permission

        user = getattr(request.state, "user", None)
        if user is None:
            user = get_current_user(request, db)
        if user is None:
            if web:
                raise HTTPException(
                    status_code=303,
                    headers={"Location": "/login"},
                )
            raise HTTPException(status_code=401, detail="Autenticação necessária")
        request.state.user = user

        if not user_has_permission(db, user, permission):
            module = permission.split(".")[0]
            write_audit(
                db,
                user=user,
                action=ACTION_ACCESS_DENIED,
                module=module,
                resource=permission,
                resource_ref=request.url.path,
                ip_address=_client_ip(request),
                result=RESULT_DENIED,
                description=f"Tentativa de acesso sem a permissão '{permission}'",
            )
            # Recarrega os atributos do usuário (o commit da auditoria os expira)
            # para que a página 403 possa exibir current_user sem erro de sessão
            # desanexada quando a sessão da requisição for encerrada.
            try:
                db.refresh(user)
            except Exception:
                pass
            raise HTTPException(
                status_code=403, detail="Permissão insuficiente para esta operação"
            )
        return user

    return dependency