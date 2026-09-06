from datetime import datetime, timedelta

from app.config import AUTH_COOKIE_NAME
from app.models.session import UserSession
from app.services.auth_service import authenticate, create_user
from app.services.session_service import create_session


# ============================================
# BLOQUEIO SEM AUTENTICAÇÃO
# ============================================

def test_unauth_web_redirects_to_login(unauth_client):
    resp = unauth_client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")

    # Página interna também redireciona, preservando o caminho original
    resp2 = unauth_client.get("/assets?status=EM_USO", follow_redirects=False)
    assert resp2.status_code == 303
    assert "/login?next=" in resp2.headers["location"]
    assert "/assets" in resp2.headers["location"]


def test_unauth_api_mutation_returns_401(unauth_client):
    resp = unauth_client.post(
        "/api/v1/assets",
        json={"tag": "PAT-90001", "name": "X", "category": "NOTEBOOK"},
    )
    assert resp.status_code == 401


def test_unauth_api_export_returns_401(unauth_client):
    for url in (
        "/api/v1/reports/custodians/csv",
        "/api/v1/reports/inventory/csv",
        "/api/v1/reports/movements/csv",
    ):
        resp = unauth_client.get(url)
        assert resp.status_code == 401, url


def test_unauth_api_list_returns_401(unauth_client):
    # Consultas da API contêm dados sensíveis (CPF, séries, valores) → também protegidas
    assert unauth_client.get("/api/v1/assets").status_code == 401
    assert unauth_client.get("/api/v1/custodians").status_code == 401


# ============================================
# LOGIN / LOGOUT
# ============================================

def test_web_login_page_renders(unauth_client):
    resp = unauth_client.get("/login")
    assert resp.status_code == 200
    assert "Entrar" in resp.text


def test_login_invalid_credentials(unauth_client):
    resp = unauth_client.post(
        "/login",
        data={"username": "nobody", "password": "senhaerrada", "next": "/"},
    )
    assert resp.status_code == 200
    assert "Usuário ou senha inválidos" in resp.text

    resp_api = unauth_client.post(
        "/api/v1/auth/login", data={"username": "nobody", "password": "senhaerrada"}
    )
    assert resp_api.status_code == 401


def test_web_login_valid_redirects_and_grants_access(db_session, unauth_client):
    from app.services.permission_service import (
        assign_role, ensure_default_roles, get_role_by_name,
    )
    ensure_default_roles(db_session)
    user = create_user(db_session, username="webuser", password="senha@1234")
    # Deny by default: sem perfil, o usuário não acessa nada. Atribui o
    # perfil Consulta (somente leitura) para exercitar o fluxo de sessão.
    consulta = get_role_by_name(db_session, "Consulta")
    assign_role(db_session, user, consulta)

    resp = unauth_client.post(
        "/login",
        data={"username": "webuser", "password": "senha@1234", "next": "/assets"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/assets"
    # A partir daqui a sessão vale para páginas e API (conforme o perfil Consulta)
    assert unauth_client.get("/assets").status_code == 200
    assert unauth_client.get("/api/v1/assets").status_code == 200


def test_login_user_without_profile_is_denied_by_default(db_session, unauth_client):
    """Deny by default: usuário autenticado SEM perfil não acessa módulos."""
    from app.services.permission_service import ensure_default_roles
    ensure_default_roles(db_session)
    create_user(db_session, username="semperfil", password="senha@1234")

    resp = unauth_client.post(
        "/login",
        data={"username": "semperfil", "password": "senha@1234", "next": "/"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    # Página exige permissão → 403 (autenticado, mas sem permissão)
    assert unauth_client.get("/assets").status_code == 403
    # API idem → 403
    assert unauth_client.get("/api/v1/assets").status_code == 403


def test_login_next_open_redirect_blocked(db_session, unauth_client):
    create_user(db_session, username="seguro", password="senha@1234")
    resp = unauth_client.post(
        "/login",
        data={"username": "seguro", "password": "senha@1234", "next": "//evil.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_api_login_me_and_logout_flow(db_session, unauth_client):
    create_user(db_session, username="apiuser", password="senha@1234")

    login = unauth_client.post(
        "/api/v1/auth/login", data={"username": "apiuser", "password": "senha@1234"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["username"] == "apiuser"
    assert unauth_client.cookies.get(AUTH_COOKIE_NAME)

    me = unauth_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "apiuser"
    assert "password" not in me.json()

    logout = unauth_client.post("/api/v1/auth/logout")
    assert logout.status_code == 200


def test_logout_revokes_session_server_side(client):
    assert client.get("/api/v1/auth/me").status_code == 200
    token = client.cookies.get(AUTH_COOKIE_NAME)
    assert token

    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 200

    # Mesmo reenviando o cookie antigo manualmente, a sessão foi revogada no banco
    client.cookies.set(AUTH_COOKIE_NAME, token)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/", follow_redirects=False).status_code == 303


def test_web_logout_redirects_to_login(client):
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 303


# ============================================
# SESSÃO: EXPIRAÇÃO E SERVIÇO
# ============================================

def test_expired_session_rejected(db_session, unauth_client):
    user = create_user(db_session, username="expira", password="senha@1234")
    token = create_session(db_session, user.id)

    # Expira a sessão no banco
    db_session.query(UserSession).filter(UserSession.user_id == user.id).update(
        {"expires_at": datetime.utcnow() - timedelta(seconds=1)}
    )
    db_session.commit()

    unauth_client.cookies.set(AUTH_COOKIE_NAME, token)
    assert unauth_client.get("/api/v1/auth/me").status_code == 401


def test_auth_service_behavior(db_session):
    user = create_user(db_session, username="servico", password="senha@1234")
    assert user.last_login is None

    auth = authenticate(db_session, "servico", "senha@1234")
    assert auth is not None and auth.id == user.id
    db_session.refresh(user)
    assert user.last_login is not None

    assert authenticate(db_session, "servico", "senhaerrada") is None
    assert authenticate(db_session, "naoexiste", "senha@1234") is None
    assert authenticate(db_session, "", "") is None


def test_failed_and_inactive_logins_do_not_update_last_login(db_session):
    """Senha incorreta e usuário desativado NÃO alteram last_login."""
    user = create_user(db_session, username="falhas", password="senha@1234")

    # Senha incorreta: login recusado, último acesso inalterado (NULL)
    assert authenticate(db_session, "falhas", "errada@123") is None
    db_session.refresh(user)
    assert user.last_login is None

    # Usuário desativado com senha correta: recusado, último acesso inalterado
    user.is_active = False
    db_session.commit()
    assert authenticate(db_session, "falhas", "senha@1234") is None
    db_session.refresh(user)
    assert user.last_login is None

    # Reativado: login bem-sucedido registra o acesso
    user.is_active = True
    db_session.commit()
    assert authenticate(db_session, "falhas", "senha@1234") is not None
    db_session.refresh(user)
    assert user.last_login is not None


def test_create_user_validations(db_session):
    import pytest

    with pytest.raises(ValueError):
        create_user(db_session, username="x", password="curta")
    with pytest.raises(ValueError):
        create_user(db_session, username=" ", password="senha@1234")
    create_user(db_session, username="duplicado", password="senha@1234")
    with pytest.raises(ValueError):
        create_user(db_session, username="duplicado", password="outra@1234")


def test_authenticated_client_fixture_works(client):
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "testuser"
    assert client.get("/").status_code == 200
    assert client.get("/api/v1/assets").status_code == 200