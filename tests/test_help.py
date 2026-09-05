"""
Testes da Central de Ajuda / Manual.

Verifica: bloqueio sem login, renderização da central e de artigos,
proteção de conteúdo administrativo por permissão, busca embutida e
links de ajuda contextual nos formulários. Também serve como regressão
do menu (a ajuda não deve quebrar as páginas existentes).
"""

from app.services.auth_service import create_user
from app.services.permission_service import (
    assign_role,
    ensure_default_roles,
    get_role_by_name,
)

PASSWORD = "senha@1234"


def _make_consulta(db, username):
    ensure_default_roles(db)
    user = create_user(db, username=username, password=PASSWORD)
    role = get_role_by_name(db, "Consulta")
    assign_role(db, user, role)
    return user


# ============================================================================
# ACESSO
# ============================================================================

def test_ajuda_requires_login(unauth_client):
    resp = unauth_client.get("/ajuda", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


def test_ajuda_central_renders(client):
    resp = client.get("/ajuda")
    assert resp.status_code == 200
    assert "Ajuda e Manual" in resp.text
    assert "Pesquisar no manual" in resp.text
    assert "Perguntas frequentes" in resp.text
    assert "helpSearch" in resp.text          # busca embutida
    assert "/ajuda/movimentar-equipamento" in resp.text


def test_ajuda_article_renders(client):
    resp = client.get("/ajuda/movimentar-equipamento")
    assert resp.status_code == 200
    assert "Como movimentar um equipamento" in resp.text
    assert "Voltar à Central de Ajuda" in resp.text


def test_ajuda_article_not_found(client):
    resp = client.get("/ajuda/artigo-inexistente")
    assert resp.status_code == 404


# ============================================================================
# CONTEÚDO ADMINISTRATIVO (protegido por permissão)
# ============================================================================

def test_admin_article_hidden_for_regular_user(db_session, unauth_client):
    _make_consulta(db_session, "ajudauser")
    resp = unauth_client.post(
        "/api/v1/auth/login", data={"username": "ajudauser", "password": PASSWORD}
    )
    assert resp.status_code == 200

    # Central: artigo admin NÃO aparece para usuário sem permissão administrativa
    index = unauth_client.get("/ajuda").text
    assert "/ajuda/gerenciar-usuarios" not in index

    # Acesso direto ao artigo admin → 403
    assert unauth_client.get("/ajuda/gerenciar-usuarios").status_code == 403


def test_admin_article_visible_for_admin(client):
    index = client.get("/ajuda").text
    assert "/ajuda/gerenciar-usuarios" in index
    assert client.get("/ajuda/gerenciar-usuarios").status_code == 200


# ============================================================================
# INTEGRAÇÃO COM O LAYOUT / REGRESSÃO
# ============================================================================

def test_help_link_in_menu(client):
    page = client.get("/").text
    assert 'href="/ajuda"' in page


def test_contextual_help_links_on_forms(client):
    form_asset = client.get("/assets/new").text
    assert "/ajuda/cadastrar-equipamento" in form_asset
    assert 'data-bs-toggle="tooltip"' in form_asset

    form_movement = client.get("/movements/new").text
    assert "/ajuda/movimentar-equipamento" in form_movement

    form_maint = client.get("/maintenances/new").text
    assert "/ajuda/abrir-ordem-servico" in form_maint


def test_help_does_not_break_existing_pages(client):
    """Regressão: páginas principais continuam renderizando com o menu novo."""
    for path in ("/", "/assets", "/movements", "/custodians", "/locations",
                 "/maintenances", "/reports/inventory", "/reports/movements"):
        resp = client.get(path)
        assert resp.status_code == 200, path