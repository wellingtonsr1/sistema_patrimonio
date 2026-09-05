"""
Testes do sistema de controle de acesso (RBAC).

Cobre: seed de perfis/permissões, deny-by-default, autorização em APIs e
páginas, menu dinâmico, bloqueio de usuário, lockout por tentativas,
auditoria e proteção contra escalação de privilégios / IDOR.
"""

import pytest

from app.models.user import User
from app.services.auth_service import create_user
from app.services.permission_service import (
    PERMISSION_CATALOG,
    assign_role,
    create_role,
    ensure_default_roles,
    get_role_by_name,
    update_role,
)
from app.services.audit_service import (
    ACTION_ACCESS_DENIED,
    ACTION_LOGIN,
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_LOCKED,
    ACTION_CREATE,
    ACTION_MOVEMENT,
)

PASSWORD = "senha@1234"


# ============================================================================
# HELPERS
# ============================================================================

def _make_user(db, username, role_names=None, is_admin=False):
    """Cria usuário com perfis (seeding idempotente do catálogo)."""
    ensure_default_roles(db)
    user = create_user(db, username=username, password=PASSWORD, is_admin=is_admin)
    for rn in role_names or []:
        role = get_role_by_name(db, rn)
        if role:
            assign_role(db, user, role)
    return user


def _login(client, username, password=PASSWORD):
    resp = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp


# ============================================================================
# SEED DO CATÁLOGO E PERFIS PADRÃO
# ============================================================================

def test_default_roles_and_permissions_seeded(db_session):
    ensure_default_roles(db_session)
    from app.models.permission import Permission
    from app.models.role import Role

    names = {p.name for p in db_session.query(Permission).all()}
    assert names == {p["name"] for p in PERMISSION_CATALOG}

    roles = {r.name for r in db_session.query(Role).all()}
    assert {"Administrador", "Gestor de TI", "Técnico de TI", "Patrimônio",
            "Almoxarifado", "Auditor", "Consulta"} <= roles

    # Administrador possui TODAS as permissões
    admin = get_role_by_name(db_session, "Administrador")
    from app.services.permission_service import get_role_permission_names
    assert get_role_permission_names(db_session, admin) == {p["name"] for p in PERMISSION_CATALOG}

    # Auditor: somente leitura (nenhuma permissão de criação/edição)
    auditor = get_role_by_name(db_session, "Auditor")
    auditor_perms = get_role_permission_names(db_session, auditor)
    assert "patrimonio.criar" not in auditor_perms
    assert "patrimonio.editar" not in auditor_perms
    assert "movimentacao.criar" not in auditor_perms
    assert "usuarios.visualizar" not in auditor_perms


def test_seed_is_idempotent(db_session):
    ensure_default_roles(db_session)
    ensure_default_roles(db_session)
    from app.models.permission import Permission
    from app.models.role import Role
    assert db_session.query(Permission).count() == len(PERMISSION_CATALOG)
    assert db_session.query(Role).count() == 7


# ============================================================================
# AUTORIZAÇÃO NA API (deny by default)
# ============================================================================

def test_api_admin_can_access_everything(client, db_session):
    assert client.get("/api/v1/assets").status_code == 200
    assert client.get("/api/v1/custodians").status_code == 200
    assert client.get("/api/v1/reports/inventory/csv").status_code == 200
    assert client.post("/api/v1/assets", json={
        "tag": "PAT-RBAC-01", "name": "Teste", "category": "NOTEBOOK"
    }).status_code == 201


def test_api_consulta_can_read_but_not_mutate(db_session, unauth_client):
    _make_user(db_session, "consulta1", role_names=["Consulta"])
    _login(unauth_client, "consulta1")

    assert unauth_client.get("/api/v1/assets").status_code == 200
    assert unauth_client.get("/api/v1/custodians").status_code == 200

    # Mutações → 403 (mesmo estando autenticado)
    assert unauth_client.post("/api/v1/assets", json={
        "tag": "PAT-RBAC-02", "name": "X", "category": "NOTEBOOK"
    }).status_code == 403
    assert unauth_client.post("/api/v1/movements", json={
        "asset_id": 1, "movement_type": "ALOCACAO_CAUTELA", "reason": "x"
    }).status_code == 403
    assert unauth_client.post("/api/v1/custodians", json={
        "registration_code": "MAT-X", "name": "Y", "email": "y@x.com",
        "role": "R", "department": "D"
    }).status_code == 403


def test_api_tecnico_cannot_create_asset_or_export(db_session, unauth_client):
    _make_user(db_session, "tecnico1", role_names=["Técnico de TI"])
    _login(unauth_client, "tecnico1")

    assert unauth_client.get("/api/v1/assets").status_code == 200
    # Técnico não cadastra patrimônio (sem patrimonio.criar)
    assert unauth_client.post("/api/v1/assets", json={
        "tag": "PAT-RBAC-03", "name": "X", "category": "NOTEBOOK"
    }).status_code == 403
    # Técnico não exporta relatórios (sem relatorios.exportar)
    assert unauth_client.get("/api/v1/reports/inventory/csv").status_code == 403


def test_api_gestor_can_create_asset(db_session, unauth_client):
    _make_user(db_session, "gestor1", role_names=["Gestor de TI"])
    _login(unauth_client, "gestor1")

    resp = unauth_client.post("/api/v1/assets", json={
        "tag": "PAT-RBAC-04", "name": "Notebook Gestor", "category": "NOTEBOOK"
    })
    assert resp.status_code == 201
    asset_id = resp.json()["id"]
    # Pode editar (patrimonio.editar)
    assert unauth_client.put(f"/api/v1/assets/{asset_id}", json={"notes": "editado"}).status_code == 200
    # NÃO possui auditoria.visualizar (não há endpoint, mas a permissão não existe)
    from app.services.permission_service import get_user_permission_names
    user = db_session.query(User).filter(User.username == "gestor1").first()
    assert "auditoria.visualizar" not in get_user_permission_names(db_session, user)
    # Gestor não gerencia usuários (sem usuarios.*)
    assert unauth_client.get("/api/v1/reports/dashboard-stats").status_code == 200


def test_api_auditor_read_only(db_session, unauth_client):
    _make_user(db_session, "auditor1", role_names=["Auditor"])
    _login(unauth_client, "auditor1")

    assert unauth_client.get("/api/v1/assets").status_code == 200
    assert unauth_client.get("/api/v1/movements").status_code == 200
    assert unauth_client.get("/api/v1/reports/inventory/csv").status_code == 200  # exportar liberado ao Auditor
    assert unauth_client.post("/api/v1/assets", json={
        "tag": "PAT-RBAC-05", "name": "X", "category": "NOTEBOOK"
    }).status_code == 403


def test_api_403_not_404_for_unauthorized_ids(db_session, unauth_client):
    """Sem permissão → 403 mesmo para IDs inexistentes (evita enumeração)."""
    _make_user(db_session, "semver1", role_names=[])
    _login(unauth_client, "semver1")

    # Sem patrimonio.visualizar: 403 para qualquer ID (não revela existência)
    assert unauth_client.get("/api/v1/assets/1").status_code == 403
    assert unauth_client.get("/api/v1/assets/99999").status_code == 403

    # Com visualizar (Consulta): 404 para inexistente, 200 para existente
    from app.services.asset_service import AssetService
    from app.schemas.asset import AssetCreate
    from app.models.enums import AssetCategory
    AssetService.create(db_session, AssetCreate(
        tag="PAT-IDOR-01", name="Bem", category=AssetCategory.NOTEBOOK
    ))
    _make_user(db_session, "consulta2", role_names=["Consulta"])
    unauth_client2 = unauth_client
    _login(unauth_client2, "consulta2")
    assert unauth_client2.get("/api/v1/assets/99999").status_code == 404
    assert unauth_client2.get("/api/v1/assets/1").status_code == 200


# ============================================================================
# AUTORIZAÇÃO NA WEB
# ============================================================================

def test_web_page_403_without_permission(db_session, unauth_client):
    _make_user(db_session, "semver2", role_names=[])
    _login(unauth_client, "semver2")
    assert unauth_client.get("/assets").status_code == 403
    assert unauth_client.get("/custodians").status_code == 403


def test_web_menu_dynamic_by_role(db_session, unauth_client):
    # Técnico de TI: vê Manutenções, NÃO vê Administração nem botão Novo Bem
    _make_user(db_session, "tecnico2", role_names=["Técnico de TI"])
    _login(unauth_client, "tecnico2")
    page = unauth_client.get("/").text
    assert "Manutenções" in page
    assert "Administração" not in page
    assert "/admin/users" not in page
    assert "Novo Bem" not in page          # sem patrimonio.criar
    assert "Movimentar" not in page        # sem movimentacao.criar


def test_web_menu_shows_admin_for_admin(client):
    page = client.get("/").text
    assert "Administração" in page
    assert "/admin/users" in page
    assert "Novo Bem" in page


def test_web_action_buttons_hidden_without_permission(db_session, unauth_client):
    _make_user(db_session, "consulta3", role_names=["Consulta"])
    _login(unauth_client, "consulta3")
    page = unauth_client.get("/assets").text
    assert "Novo Equipamento" not in page   # sem patrimonio.criar
    assert "Importar CSV" not in page
    assert page.count('title="Movimentar"') == 0


# ============================================================================
# ESCALAÇÃO DE PRIVILÉGIOS — TELAS ADMINISTRATIVAS
# ============================================================================

def test_admin_pages_require_permission(db_session, unauth_client):
    _make_user(db_session, "consulta4", role_names=["Consulta"])
    _login(unauth_client, "consulta4")

    assert unauth_client.get("/admin/users").status_code == 403
    assert unauth_client.get("/admin/users/new").status_code == 403
    assert unauth_client.get("/admin/roles").status_code == 403
    assert unauth_client.get("/admin/audit").status_code == 403

    # Tentativa de criar usuário via formulário → 403
    assert unauth_client.post("/admin/users/new", data={
        "username": "hacker", "password": "senha@1234", "role_ids": []
    }).status_code == 403

    # Tentativa de mudar o próprio perfil via rota admin → 403
    user = db_session.query(User).filter(User.username == "consulta4").first()
    assert unauth_client.post(f"/admin/users/{user.id}/edit", data={
        "full_name": "Hacker", "is_active": "true", "role_ids": []
    }).status_code == 403


def test_user_cannot_grant_self_admin_permissions(db_session, unauth_client):
    """IDOR/BOLA: manipulação de IDs não concede permissões."""
    _make_user(db_session, "consulta5", role_names=["Consulta"])
    user = db_session.query(User).filter(User.username == "consulta5").first()
    _login(unauth_client, "consulta5")

    # Não pode alterar perfil de NENHUM usuário (nem o próprio) sem usuarios.editar
    assert unauth_client.post(f"/admin/users/{user.id}/edit", data={
        "full_name": "X", "is_active": "true", "role_ids": []
    }).status_code == 403
    # Não pode resetar senha
    assert unauth_client.post(f"/admin/users/{user.id}/reset-password", data={
        "new_password": "nova@1234"
    }).status_code == 403


# ============================================================================
# BLOQUEIO DE USUÁRIO
# ============================================================================

def test_block_user_invalidates_session_and_login(db_session, client):
    _make_user(db_session, "vitima", role_names=["Consulta"])
    resp = client.post("/api/v1/auth/login", data={"username": "vitima", "password": PASSWORD})
    assert resp.status_code == 200
    token = resp.cookies.get("session")

    # Volta a agir como o administrador (o login da vítima sobrescreveu o cookie)
    resp_admin = client.post("/api/v1/auth/login", data={"username": "testuser", "password": "teste@1234"})
    assert resp_admin.status_code == 200

    user = db_session.query(User).filter(User.username == "vitima").first()
    block = client.post(f"/admin/users/{user.id}/toggle-active", data={"action": "block"},
                        follow_redirects=False)
    assert block.status_code == 303

    # Sessão revogada imediatamente (is_active=False invalida a sessão)
    client.cookies.clear()
    client.cookies.set("session", token)
    assert client.get("/api/v1/auth/me").status_code == 401

    # Login bloqueado
    resp2 = client.post("/api/v1/auth/login", data={"username": "vitima", "password": PASSWORD})
    assert resp2.status_code == 401


def test_unblock_restores_access(db_session, client):
    _make_user(db_session, "vitima2", role_names=["Consulta"])
    user = db_session.query(User).filter(User.username == "vitima2").first()
    client.post(f"/admin/users/{user.id}/toggle-active", data={"action": "block"})
    client.post(f"/admin/users/{user.id}/toggle-active", data={"action": "unblock"})

    resp = client.post("/api/v1/auth/login", data={"username": "vitima2", "password": PASSWORD})
    assert resp.status_code == 200


def test_cannot_block_self(client):
    from urllib.parse import unquote
    me = client.get("/api/v1/auth/me").json()
    resp = client.post(f"/admin/users/{me['id']}/toggle-active", data={"action": "block"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "não pode bloquear a si mesmo" in unquote(resp.headers["location"])


# ============================================================================
# LOCKOUT POR TENTATIVAS EXCESSIVAS
# ============================================================================

def test_lockout_after_failed_attempts(db_session, unauth_client):
    _make_user(db_session, "alvo", role_names=["Consulta"])

    # 5 tentativas erradas → conta bloqueada
    for _ in range(5):
        resp = unauth_client.post(
            "/api/v1/auth/login", data={"username": "alvo", "password": "errada@123"}
        )
        assert resp.status_code == 401

    # 6ª tentativa COM SENHA CORRETA → 423 Locked
    resp = unauth_client.post(
        "/api/v1/auth/login", data={"username": "alvo", "password": PASSWORD}
    )
    assert resp.status_code == 423

    from app.models.audit_log import AuditLog
    locked = db_session.query(AuditLog).filter(AuditLog.action == ACTION_LOGIN_LOCKED).count()
    assert locked >= 1
    failed = db_session.query(AuditLog).filter(AuditLog.action == ACTION_LOGIN_FAILED).count()
    assert failed >= 5


# ============================================================================
# AUDITORIA
# ============================================================================

def _audit_rows(db_session):
    from app.models.audit_log import AuditLog
    return db_session.query(AuditLog).all()


def test_audit_records_login_success_and_failure(db_session, unauth_client):
    _make_user(db_session, "audituser", role_names=["Consulta"])

    unauth_client.post("/api/v1/auth/login", data={"username": "audituser", "password": "errada@123"})
    unauth_client.post("/api/v1/auth/login", data={"username": "audituser", "password": PASSWORD})

    rows = _audit_rows(db_session)
    actions = [r.action for r in rows]
    assert ACTION_LOGIN_FAILED in actions
    assert ACTION_LOGIN in actions
    failed = [r for r in rows if r.action == ACTION_LOGIN_FAILED][0]
    assert failed.username == "audituser"
    assert failed.result == "FAILURE"
    success = [r for r in rows if r.action == ACTION_LOGIN][0]
    assert success.result == "SUCCESS"


def test_audit_records_mutation_and_access_denied(db_session, client):
    # Mutação registrada
    resp = client.post("/api/v1/assets", json={
        "tag": "PAT-AUD-01", "name": "Bem auditado", "category": "NOTEBOOK"
    })
    assert resp.status_code == 201

    from app.models.audit_log import AuditLog
    rows = db_session.query(AuditLog).all()
    creates = [r for r in rows if r.action == ACTION_CREATE and r.module == "Patrimônio"]
    assert creates, "deveria haver auditoria de criação de bem"
    assert creates[0].resource_ref == "PAT-AUD-01"

    # Acesso negado registrado (usuário sem permissão tentando usar a API)
    from app.services.permission_service import ensure_default_roles
    ensure_default_roles(db_session)
    _make_user(db_session, "semperm", role_names=[])
    resp2 = client.post("/api/v1/auth/login", data={"username": "semperm", "password": PASSWORD})
    token = resp2.cookies.get("session")
    client.cookies.set("session", token)
    assert client.post("/api/v1/assets", json={
        "tag": "PAT-AUD-02", "name": "X", "category": "NOTEBOOK"
    }).status_code == 403

    denied = db_session.query(AuditLog).filter(AuditLog.action == ACTION_ACCESS_DENIED).all()
    assert denied, "acesso negado deveria ser auditado"
    assert denied[-1].username == "semperm"


def test_audit_records_movement(db_session, client):
    # Cria colaborador para alocação válida
    cust = client.post("/api/v1/custodians", json={
        "registration_code": "MAT-AUD", "name": "Custodiante", "email": "cust@org.gov.br",
        "role": "Analista", "department": "TI",
    })
    assert cust.status_code == 201
    cust_id = cust.json()["id"]

    resp = client.post("/api/v1/assets", json={
        "tag": "PAT-AUD-03", "name": "Bem movimentado", "category": "NOTEBOOK"
    })
    asset_id = resp.json()["id"]
    move = client.post("/api/v1/movements", json={
        "asset_id": asset_id,
        "movement_type": "ALOCACAO_CAUTELA",
        "destination_custodian_id": cust_id,
        "reason": "Teste de auditoria",
        "operator_name": "Tester",
    })
    assert move.status_code == 201

    from app.models.audit_log import AuditLog
    movements = db_session.query(AuditLog).filter(AuditLog.action == ACTION_MOVEMENT).all()
    assert movements
    assert movements[0].module == "Movimentação"
    assert movements[0].resource_ref == "PAT-AUD-03"


# ============================================================================
# TROCA DE SENHA (AUTOSERVIÇO)
# ============================================================================

def test_password_change_self_service(db_session, unauth_client):
    _make_user(db_session, "troca", role_names=["Consulta"])
    _login(unauth_client, "troca")

    resp = unauth_client.post("/profile/password", data={
        "current_password": PASSWORD,
        "new_password": "novaSenha@123",
        "confirm_password": "novaSenha@123",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"   # sessão revogada → novo login

    # Senha antiga não funciona mais
    resp2 = unauth_client.post("/api/v1/auth/login", data={"username": "troca", "password": PASSWORD})
    assert resp2.status_code == 401
    # Senha nova funciona
    resp3 = unauth_client.post("/api/v1/auth/login", data={"username": "troca", "password": "novaSenha@123"})
    assert resp3.status_code == 200


def test_password_change_wrong_current_rejected(db_session, unauth_client):
    _make_user(db_session, "troca2", role_names=["Consulta"])
    _login(unauth_client, "troca2")
    resp = unauth_client.post("/profile/password", data={
        "current_password": "errada@123",
        "new_password": "novaSenha@123",
        "confirm_password": "novaSenha@123",
    }, follow_redirects=False)
    assert resp.status_code == 303
    from urllib.parse import unquote
    assert "senha atual está incorreta" in unquote(resp.headers["location"])


# ============================================================================
# ADMIN: CRIAR / EDITAR USUÁRIOS COM PERFIS
# ============================================================================

def test_admin_creates_user_with_roles(db_session, client):
    resp = client.post("/admin/users/new", data={
        "username": "novato",
        "password": PASSWORD,
        "full_name": "Novato",
        "email": "novato@org.gov.br",
        "role_ids": [],  # sem perfis inicialmente (menor privilégio)
    }, follow_redirects=False)
    assert resp.status_code == 303

    user = db_session.query(User).filter(User.username == "novato").first()
    assert user is not None
    assert user.is_admin is False
    from app.services.permission_service import get_user_permission_names
    assert get_user_permission_names(db_session, user) == set()  # deny by default

    # Auditoria da criação
    from app.models.audit_log import AuditLog
    assert db_session.query(AuditLog).filter(AuditLog.action == ACTION_CREATE,
                                             AuditLog.module == "Usuários",
                                             AuditLog.resource_ref == "novato").count() >= 1


def test_admin_assigns_role_and_user_gains_permission(db_session, client):
    _make_user(db_session, "promovido", role_names=[])
    user = db_session.query(User).filter(User.username == "promovido").first()

    consulta = get_role_by_name(db_session, "Consulta")
    resp = client.post(f"/admin/users/{user.id}/edit", data={
        "full_name": "Promovido",
        "is_active": "true",
        "role_ids": [str(consulta.id)],
    }, follow_redirects=False)
    assert resp.status_code == 303

    from app.services.permission_service import get_user_permission_names
    perms = get_user_permission_names(db_session, user)
    assert "patrimonio.visualizar" in perms
    assert "patrimonio.criar" not in perms

    # Auditoria de alteração de perfil
    from app.models.audit_log import AuditLog
    from app.services.audit_service import ACTION_PROFILE_CHANGE
    assert db_session.query(AuditLog).filter(AuditLog.action == ACTION_PROFILE_CHANGE,
                                             AuditLog.resource_ref == "promovido").count() >= 1


def test_admin_reset_password(db_session, client):
    _make_user(db_session, "esquecido", role_names=["Consulta"])
    user = db_session.query(User).filter(User.username == "esquecido").first()

    resp = client.post(f"/admin/users/{user.id}/reset-password", data={
        "new_password": "NovaSenha@456"
    }, follow_redirects=False)
    assert resp.status_code == 303

    # Senha antiga falha, nova funciona
    assert client.post("/api/v1/auth/login", data={"username": "esquecido", "password": PASSWORD}).status_code == 401
    assert client.post("/api/v1/auth/login", data={"username": "esquecido", "password": "NovaSenha@456"}).status_code == 200


def test_admin_block_unblock_user(db_session, client):
    _make_user(db_session, "bloqueavel", role_names=["Consulta"])
    user = db_session.query(User).filter(User.username == "bloqueavel").first()

    client.post(f"/admin/users/{user.id}/toggle-active", data={"action": "block"}, follow_redirects=False)
    db_session.refresh(user)
    assert user.is_active is False
    assert client.post("/api/v1/auth/login", data={"username": "bloqueavel", "password": PASSWORD}).status_code == 401

    client.post(f"/admin/users/{user.id}/toggle-active", data={"action": "unblock"}, follow_redirects=False)
    db_session.refresh(user)
    assert user.is_active is True


# ============================================================================
# PROTEÇÃO DO ÚLTIMO ADMINISTRADOR
# ============================================================================

def test_last_admin_cannot_be_removed(db_session, unauth_client):
    # Cria um "chefe" com poder de bloquear mas SEM acesso administrativo
    ensure_default_roles(db_session)
    boss_role = create_role(db_session, "Bloqueador", "Pode bloquear usuários")
    update_role(db_session, boss_role, permission_names=["usuarios.bloquear"])
    _make_user(db_session, "chefe", role_names=["Bloqueador"])
    chefe = db_session.query(User).filter(User.username == "chefe").first()

    # Cria um superusuário extra (além do admin2) para testar a proteção
    superadmin = create_user(db_session, username="superadmin", password=PASSWORD, is_admin=True)
    # Segundo administrador
    admin2 = create_user(db_session, username="admin2", password=PASSWORD, is_admin=True)

    _login(unauth_client, "chefe")

    # 1) Bloqueia o superadmin — ainda resta admin2 como administrador ativo
    resp = unauth_client.post(f"/admin/users/{superadmin.id}/toggle-active",
                              data={"action": "block"}, follow_redirects=False)
    assert resp.status_code == 303
    from urllib.parse import unquote
    assert "último administrador" not in unquote(resp.headers["location"])

    # 2) Bloqueia admin2 — seria o último administrador ativo → rejeitado
    resp2 = unauth_client.post(f"/admin/users/{admin2.id}/toggle-active",
                               data={"action": "block"}, follow_redirects=False)
    assert resp2.status_code == 303
    assert "último administrador" in unquote(resp2.headers["location"])
    db_session.refresh(admin2)
    assert admin2.is_active is True  # permanece ativo


# ============================================================================
# ADMIN: GESTÃO DE PERFIS
# ============================================================================

def test_role_crud_and_system_role_protection(db_session, client):
    ensure_default_roles(db_session)  # garante o catálogo de permissões no banco de teste
    # Criar perfil
    resp = client.post("/admin/roles/new", data={
        "name": "Auditoria Especial",
        "description": "Perfil de teste",
        "permission_names": ["auditoria.visualizar", "relatorios.visualizar"],
    }, follow_redirects=False)
    assert resp.status_code == 303

    role = get_role_by_name(db_session, "Auditoria Especial")
    assert role is not None
    from app.services.permission_service import get_role_permission_names
    assert get_role_permission_names(db_session, role) == {"auditoria.visualizar", "relatorios.visualizar"}

    # Editar permissões
    resp2 = client.post(f"/admin/roles/{role.id}/edit", data={
        "name": "Auditoria Especial",
        "permission_names": ["auditoria.visualizar"],
    }, follow_redirects=False)
    assert resp2.status_code == 303
    assert get_role_permission_names(db_session, role) == {"auditoria.visualizar"}

    # Excluir perfil customizado
    resp3 = client.post(f"/admin/roles/{role.id}/delete", follow_redirects=False)
    assert resp3.status_code == 303
    assert get_role_by_name(db_session, "Auditoria Especial") is None

    # Perfil de sistema NÃO pode ser excluído
    from urllib.parse import unquote
    system_role = get_role_by_name(db_session, "Consulta")
    resp4 = client.post(f"/admin/roles/{system_role.id}/delete", follow_redirects=False)
    assert resp4.status_code == 303
    assert "Perfis padrão" in unquote(resp4.headers["location"])
    assert get_role_by_name(db_session, "Consulta") is not None


# ============================================================================
# /auth/me EXPÕE PERMISSÕES
# ============================================================================

def test_me_includes_permissions(db_session, unauth_client):
    _make_user(db_session, "perfisuser", role_names=["Consulta"])
    _login(unauth_client, "perfisuser")
    me = unauth_client.get("/api/v1/auth/me").json()
    assert "patrimonio.visualizar" in me["permissions"]
    assert "patrimonio.criar" not in me["permissions"]
    assert "password" not in me