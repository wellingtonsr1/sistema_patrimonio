"""
Endpoints de autenticação da API REST.

- POST /api/v1/auth/login  → autentica e define o cookie de sessão
- POST /api/v1/auth/logout → revoga a sessão no servidor
- GET  /api/v1/auth/me     → dados do usuário autenticado (exige sessão)

Os demais roteadores de /api/v1 são protegidos por require_api_auth e por
permissões específicas (require_permission).
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import _client_ip, require_api_auth
from app.config import AUTH_COOKIE_NAME
from app.database import get_db
from app.schemas.user import UserWithPermissions
from app.services.audit_service import (
    ACTION_LOGIN,
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_LOCKED,
    ACTION_LOGOUT,
    RESULT_FAILURE,
    RESULT_LOCKED,
    RESULT_SUCCESS,
    write_audit,
)
from app.services.auth_provider import resolve_authentication
from app.services.auth_service import AccountLockedError
from app.services.ad_service import (
    ADAuthenticationError,
    ADNoProfileError,
    ADUnavailableError,
)
from app.services.permission_service import get_user_permission_names
from app.services.session_service import (
    clear_session_cookie,
    create_session,
    get_session_user,
    revoke_session,
    set_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _user_with_permissions(db: Session, user) -> UserWithPermissions:
    """Monta a resposta com as permissões efetivas do usuário."""
    data = UserWithPermissions.model_validate(user)
    data.permissions = sorted(get_user_permission_names(db, user))
    return data


@router.post("/login")
def api_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Autentica um usuário e estabelece a sessão via cookie."""
    ip = _client_ip(request)
    try:
        user = resolve_authentication(db, username, password)
    except AccountLockedError as err:
        write_audit(
            db,
            user=None,
            username=username,
            action=ACTION_LOGIN_LOCKED,
            module="Autenticação",
            resource="Login",
            resource_ref=username,
            ip_address=ip,
            result=RESULT_LOCKED,
            description=f"Login bloqueado por excesso de tentativas (até {err.locked_until:%d/%m/%Y %H:%M} UTC)",
        )
        raise HTTPException(
            status_code=423,
            detail="Conta temporariamente bloqueada por excesso de tentativas de login. Tente novamente mais tarde.",
        )
    except (ADUnavailableError, ADAuthenticationError, ADNoProfileError) as ad_exc:
        # Falhas específicas do AD: auditoria já registrada no serviço da
        # integração; aqui apenas o status/mensagem genérica para o cliente.
        status_code = 503 if isinstance(ad_exc, ADUnavailableError) else 401
        raise HTTPException(status_code=status_code, detail=str(ad_exc))

    if not user:
        write_audit(
            db,
            user=None,
            username=username,
            action=ACTION_LOGIN_FAILED,
            module="Autenticação",
            resource="Login",
            resource_ref=username,
            ip_address=ip,
            result=RESULT_FAILURE,
            description="Tentativa de login com credenciais inválidas",
        )
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")

    write_audit(
        db,
        user=user,
        action=ACTION_LOGIN,
        module="Autenticação",
        resource="Login",
        resource_ref=user.username,
        ip_address=ip,
        result=RESULT_SUCCESS,
        description="Login realizado com sucesso",
    )

    token = create_session(db, user.id)
    set_session_cookie(response, token)
    return {
        "message": "Login realizado com sucesso",
        "user": _user_with_permissions(db, user),
    }


@router.post("/logout", dependencies=[Depends(require_api_auth)])
def api_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Revoga a sessão atual no servidor e remove o cookie."""
    user = getattr(request.state, "user", None)
    write_audit(
        db,
        user=user,
        action=ACTION_LOGOUT,
        module="Autenticação",
        resource="Logout",
        resource_ref=user.username if user else None,
        ip_address=_client_ip(request),
        result=RESULT_SUCCESS,
        description="Logout realizado",
    )
    revoke_session(db, request.cookies.get(AUTH_COOKIE_NAME))
    clear_session_cookie(response)
    return {"message": "Logout realizado com sucesso"}


@router.get("/me", dependencies=[Depends(require_api_auth)])
def api_me(request: Request, db: Session = Depends(get_db)):
    """Retorna os dados e permissões do usuário autenticado."""
    user = get_session_user(db, request.cookies.get(AUTH_COOKIE_NAME))
    return _user_with_permissions(db, user)