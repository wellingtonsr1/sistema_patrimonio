"""
Testes da integração Active Directory / Samba AD.

A camada de protocolo (ad_ldap) é mockada: os testes exercem o fluxo
completo de autenticação/sincronização/provisionamento/auditoria sem um
servidor AD real, garantindo que:

- login local (admin) continua funcionando;
- usuário AD válido autentica, é provisionado e recebe o perfil do mapeamento;
- senha incorreta / conta desabilitada / grupo sem mapeamento → acesso negado;
- colaborador existente nunca é duplicado;
- perfis individuais (manuais) não são removidos pela sincronização;
- eventos de auditoria AD são registrados.
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.models.ad_group_role import ADGroupRole
from app.models.custodian import Custodian
from app.models.user import User
from app.services import ad_ldap, ad_service
from app.services.ad_ldap import ADUser
from app.services.audit_service import get_audit_logs
from app.services.auth_service import create_user
from app.services.permission_service import (
    assign_role,
    ensure_default_roles,
    get_role_by_id,
    get_role_by_name,
    get_user_permission_names,
    get_user_role_names,
)

PASSWORD = "SenhaForte@123"


@pytest.fixture()
def _ad_db(db_session):
    """Catálogo de perfis/permissões garantido para os testes de AD."""
    ensure_default_roles(db_session)
    return db_session


def _enable_ad(db):
    settings = ad_service.get_ad_settings(db)
    settings.enabled = True
    settings.server = "dc01.test.local"
    settings.port = 636
    settings.use_ldaps = True
    settings.base_dn = "dc=test,dc=local"
    db.commit()
    return settings


def _map_group(db, group, role_name, priority=10):
    role = get_role_by_name(db, role_name)
    return ad_service.upsert_group_mapping(db, group, role.id, priority)


def _ad_user(groups=(), enabled=True, guid="aaaaaaaa-bbbb-cccc-dddd-eeeeffff0001",
             email="joao.silva@test.local"):
    dns = [f"CN={g},OU=Grupos,DC=test,DC=local" for g in groups]
    return ADUser(
        username="joao.silva",
        display_name="João Silva",
        email=email,
        dn="CN=João Silva,OU=Usuarios,DC=test,DC=local",
        guid=guid,
        enabled=enabled,
        groups=dns,
    )


def _mock_ldap(ad_user):
    """Mocka a camada de protocolo LDAP para retornar o ADUser informado."""
    return patch.object(ad_ldap, "authenticate_ad", return_value=ad_user, autospec=True)


def _audit_actions(db):
    return {a for (a,) in db.execute(text("SELECT action FROM audit_logs")).fetchall()}


# ============================================================================
# LOGIN LOCAL PRESERVADO
# ============================================================================

def test_local_login_still_works(_ad_db, unauth_client):
    create_user(_ad_db, username="admin", password=PASSWORD, is_admin=True)
    resp = unauth_client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["auth_provider"] == "local"


def test_local_login_wrong_password_denied(_ad_db, unauth_client):
    create_user(_ad_db, username="admin", password=PASSWORD, is_admin=True)
    resp = unauth_client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "errada@123"}
    )
    assert resp.status_code == 401


# ============================================================================
# LOGIN AD — SUCESSO, PROVISIONAMENTO E PERFIL
# ============================================================================

def test_ad_login_provisions_user_and_role(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    _map_group(_ad_db, "GRP-SISPAT-TECNICOS-TI", "Técnico de TI")

    with _mock_ldap(_ad_user(groups=("GRP-SISPAT-TECNICOS-TI",))):
        resp = unauth_client.post(
            "/api/v1/auth/login",
            data={"username": "joao.silva", "password": "Ad@Senha123"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["auth_provider"] == "ad"

    _ad_db.expire_all()
    user = _ad_db.query(User).filter(User.username == "joao.silva").first()
    assert user is not None
    assert user.ad_object_guid == "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0001"
    assert get_user_role_names(_ad_db, user) == ["Técnico de TI"]
    # Permissões exatas do perfil Técnico de TI (RBAC existente, sem sistema)
    perms = get_user_permission_names(_ad_db, user)
    assert perms == {
        "manutencao.criar", "manutencao.editar", "manutencao.finalizar",
        "manutencao.visualizar", "movimentacao.visualizar",
        "patrimonio.visualizar", "relatorios.visualizar",
        "colaboradores.visualizar",
    }


def test_ad_login_second_login_updates_without_duplicates(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    _map_group(_ad_db, "GRP-SISPAT-GESTORES-TI", "Gestor de TI")

    with _mock_ldap(_ad_user(groups=("GRP-SISPAT-GESTORES-TI",))):
        unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})
        unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})

    _ad_db.expire_all()
    assert _ad_db.query(User).filter(User.username == "joao.silva").count() == 1
    user = _ad_db.query(User).filter(User.username == "joao.silva").first()
    assert get_user_role_names(_ad_db, user) == ["Gestor de TI"]
    # Gestor de TI: permissões conforme seed atual (sem permissões de sistema)
    perms = get_user_permission_names(_ad_db, user)
    assert "patrimonio.criar" in perms and "patrimonio.excluir" not in perms
    assert "usuarios.criar" not in perms and "perfis.editar" not in perms
    assert "manutencao.finalizar" in perms


def test_ad_group_priority_deterministic(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    _map_group(_ad_db, "GRP-SISPAT-TECNICOS-TI", "Técnico de TI", priority=5)
    _map_group(_ad_db, "GRP-SISPAT-GESTORES-TI", "Gestor de TI", priority=1)

    with _mock_ldap(_ad_user(groups=("GRP-SISPAT-TECNICOS-TI", "GRP-SISPAT-GESTORES-TI"))):
        resp = unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})
    assert resp.status_code == 200
    _ad_db.expire_all()
    user = _ad_db.query(User).filter(User.username == "joao.silva").first()
    # Menor número de prioridade vence (Gestor de TI, priority=1)
    assert "Gestor de TI" in get_user_role_names(_ad_db, user)


def test_ad_manual_role_preserved_on_sync(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    _map_group(_ad_db, "GRP-SISPAT-AUDITORIA", "Auditor")
    _map_group(_ad_db, "GRP-SISPAT-TECNICOS-TI", "Técnico de TI")

    # 1º login AD provisiona o usuário com o perfil do grupo
    with _mock_ldap(_ad_user(groups=("GRP-SISPAT-TECNICOS-TI",))):
        resp = unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})
    assert resp.status_code == 200

    # Administrador atribui um perfil ADICIONAL manualmente (permissão individual)
    _ad_db.expire_all()
    user = _ad_db.query(User).filter(User.username == "joao.silva").first()
    assign_role(_ad_db, user, get_role_by_name(_ad_db, "Auditor"))

    # 2º login AD: sincronização preserva o perfil manual e mantém o do grupo
    with _mock_ldap(_ad_user(groups=("GRP-SISPAT-TECNICOS-TI",))):
        resp = unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})
    assert resp.status_code == 200
    _ad_db.expire_all()
    user = _ad_db.query(User).filter(User.username == "joao.silva").first()
    roles = set(get_user_role_names(_ad_db, user))
    assert "Auditor" in roles and "Técnico de TI" in roles


# ============================================================================
# LOGIN AD — NEGATIVAS
# ============================================================================

def test_ad_wrong_password_denied(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    _map_group(_ad_db, "GRP-SISPAT-TECNICOS-TI", "Técnico de TI")
    with patch.object(ad_ldap, "authenticate_ad", return_value=None, autospec=True):
        resp = unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "errada123"})
    assert resp.status_code == 401
    assert _ad_db.query(User).filter(User.username == "joao.silva").first() is None


def test_ad_disabled_account_denied(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    _map_group(_ad_db, "GRP-SISPAT-TECNICOS-TI", "Técnico de TI")
    with _mock_ldap(_ad_user(enabled=False, groups=("GRP-SISPAT-TECNICOS-TI",))):
        resp = unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})
    assert resp.status_code == 401
    assert "desabilitada" in resp.json()["detail"].lower()
    assert _ad_db.query(User).filter(User.username == "joao.silva").first() is None


def test_ad_unmapped_group_denied(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    with _mock_ldap(_ad_user(groups=("GRP-WIFI", "GRP-USUARIOS-DOMINIO"))):
        resp = unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})
    assert resp.status_code == 401
    # Usuário pode ter sido provisionado, mas não recebe perfil nem sessão
    _ad_db.expire_all()
    user = _ad_db.query(User).filter(User.username == "joao.silva").first()
    if user is not None:
        assert get_user_role_names(_ad_db, user) == []


def test_ad_unavailable_returns_503(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    with patch.object(ad_ldap, "authenticate_ad", side_effect=ad_ldap.ADError("timeout"), autospec=True):
        resp = unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})
    assert resp.status_code == 503


def test_ad_disabled_integration_falls_back_to_local(_ad_db, unauth_client):
    """AD não habilitado → login local funciona normalmente."""
    create_user(_ad_db, username="maria", password=PASSWORD, is_admin=False)
    resp = unauth_client.post(
        "/api/v1/auth/login", data={"username": "maria", "password": PASSWORD}
    )
    assert resp.status_code == 200


# ============================================================================
# VÍNCULO COM COLABORADOR (nunca duplica)
# ============================================================================

def _make_custodian(db, **overrides):
    data = dict(
        registration_code="MAT-1001", name="João Silva",
        email="joao.silva@test.local", cpf=None, role="Técnico",
        department="TI", is_active=True,
    )
    data.update(overrides)
    custodian = Custodian(**data)
    db.add(custodian)
    db.commit()
    return custodian


def test_ad_links_existing_custodian_without_duplication(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    _map_group(_ad_db, "GRP-SISPAT-TECNICOS-TI", "Técnico de TI")
    custodian = _make_custodian(_ad_db)

    with _mock_ldap(_ad_user(groups=("GRP-SISPAT-TECNICOS-TI",))):
        unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})

    _ad_db.expire_all()
    assert _ad_db.query(Custodian).count() == 1  # nenhum colaborador criado
    linked = get_audit_logs(_ad_db, action=ad_service.ACTION_AD_CUSTODIAN_LINKED)
    assert len(linked) == 1
    assert linked[0].resource_id == custodian.id


def test_ad_login_does_not_touch_patrimonial_data(_ad_db, unauth_client):
    """AD não sobrescreve matrícula/CPF/cargo/setor do colaborador."""
    _enable_ad(_ad_db)
    _map_group(_ad_db, "GRP-SISPAT-TECNICOS-TI", "Técnico de TI")
    custodian = _make_custodian(
        _ad_db, cpf="111.222.333-44", role="Técnico de Campo"
    )

    with _mock_ldap(_ad_user(groups=("GRP-SISPAT-TECNICOS-TI",))):
        unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})

    _ad_db.expire_all()
    custodian = _ad_db.query(Custodian).filter(Custodian.id == custodian.id).first()
    assert custodian.registration_code == "MAT-1001"
    assert custodian.cpf == "111.222.333-44"
    assert custodian.role == "Técnico de Campo"
    assert custodian.department == "TI"


# ============================================================================
# TELA ADMINISTRAÇÃO → INTEGRAÇÃO AD
# ============================================================================

def test_ad_admin_screen_visible_to_admin(_ad_db, client):
    resp = client.get("/admin/ad")
    assert resp.status_code == 200
    assert "Integração Active Directory".encode() in resp.content


def test_ad_admin_screen_forbidden_without_permission(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    create_user(_ad_db, username="comum", password=PASSWORD, is_admin=False)
    login = unauth_client.post("/api/v1/auth/login", data={"username": "comum", "password": PASSWORD})
    assert login.status_code == 200
    resp = unauth_client.get("/admin/ad")
    assert resp.status_code == 403


def test_ad_settings_and_mapping_roundtrip(_ad_db, client):
    resp = client.post(
        "/admin/ad/settings",
        data={
            "enabled": "true", "server": "dc01.test.local", "port": "636",
            "use_ldaps": "true", "verify_tls": "true", "base_dn": "dc=test,dc=local",
            "search_dn": "", "bind_user": "", "timeout_seconds": "8",
            "auto_create_user": "true", "link_by_email": "true",
            "group_role_priority": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    role = get_role_by_name(_ad_db, "Consulta")
    resp = client.post(
        "/admin/ad/mappings",
        data={"group_name": "GRP-SISPAT-CONSULTA", "role_id": role.id, "priority": "7"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    _ad_db.expire_all()
    mapping = _ad_db.query(ADGroupRole).filter(ADGroupRole.group_name == "GRP-SISPAT-CONSULTA").first()
    assert mapping is not None and mapping.role_id == role.id


# ============================================================================
# AUDITORIA
# ============================================================================

def test_ad_audit_events_recorded(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    _map_group(_ad_db, "GRP-SISPAT-TECNICOS-TI", "Técnico de TI")
    with _mock_ldap(_ad_user(groups=("GRP-SISPAT-TECNICOS-TI",))):
        unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "x12345678"})

    actions = _audit_actions(_ad_db)
    assert ad_service.ACTION_AD_LOGIN_FAILED not in actions
    for expected in (
        ad_service.ACTION_AD_PROVISIONED,
        ad_service.ACTION_AD_GROUP_SYNC,
        ad_service.ACTION_AD_ROLE_SYNCED,
    ):
        assert expected in actions, f"Evento {expected} ausente na auditoria"


def test_ad_failed_login_audited(_ad_db, unauth_client):
    _enable_ad(_ad_db)
    with patch.object(ad_ldap, "authenticate_ad", return_value=None, autospec=True):
        unauth_client.post("/api/v1/auth/login", data={"username": "joao.silva", "password": "errada123"})
    logs = get_audit_logs(_ad_db, action=ad_service.ACTION_AD_LOGIN_FAILED)
    assert len(logs) == 1
    # Nenhuma senha pode aparecer na trilha
    for log in logs:
        assert "errada123" not in (log.description or "")
        assert "errada123" not in (log.new_data or "")


# ============================================================================
# SANIDADE DA CAMADA LDAP (unidade, sem servidor)
# ============================================================================

def test_guid_canonicalization():
    from uuid import UUID

    raw = UUID("12345678-1234-1234-1234-123456789abc").bytes_le
    assert ad_ldap._canonical_guid(raw) == "12345678-1234-1234-1234-123456789abc"


def test_group_cn_extraction():
    assert ad_ldap._extract_common_name("CN=GRP-SISPAT-TI,OU=Grupos,DC=x,DC=y") == "GRP-SISPAT-TI"


def test_ad_ldap_not_configured_raises():
    class _FakeSettings:
        server = ""
        base_dn = "dc=test,dc=local"
        use_ldaps = True
        verify_tls = True
        port = 636
        timeout_seconds = 2

    with pytest.raises(ad_ldap.ADError):
        ad_ldap.authenticate_ad(_FakeSettings(), "x", "y")


# ============================================================================
# REGRESSÃO: conn.search() do ldap3 retorna bool (não tupla)
# ============================================================================

class _FakeEntry:
    """Entry LDAP falsa com acesso por chave (entry['attr'].value / .raw_value)."""

    def __init__(self, values):
        self._values = values

    def __contains__(self, key):
        return key in self._values

    def __getitem__(self, key):
        return self._values[key]


def _make_entry(sam, mail=None, display=None, guid=None, uac=512, groups=()):
    entry = _FakeEntry({
        "sAMAccountName": SimpleNamespace(value=sam),
        "mail": SimpleNamespace(value=mail),
        "displayName": SimpleNamespace(value=display),
        "cn": SimpleNamespace(value=display or sam),
        "distinguishedName": SimpleNamespace(value=f"CN={display or sam},DC=test,DC=local"),
        "objectGUID": SimpleNamespace(value=guid, raw_values=[guid] if guid is not None else []),
        "userAccountControl": SimpleNamespace(value=uac),
        "memberOf": SimpleNamespace(values=list(groups)),
    })
    return entry


class _FakeConn:
    """Conexão ldap3 falsa: search() retorna bool, como no ldap3 real."""

    def __init__(self, entries, ok=True):
        self._entries = entries
        self._ok = ok
        self.entries = []

    def search(self, *args, **kwargs):
        self.entries = list(self._entries)
        return self._ok  # bool — assinatura real do ldap3 (2.9.1)


def _fake_ad_settings():
    class _S:
        server = "dc.test.local"
        base_dn = "dc=test,dc=local"
        search_dn = None
        use_ldaps = True
        verify_tls = True
        port = 636
        timeout_seconds = 2

    return _S()


def test_search_service_account_treats_search_result_as_bool(_ad_db):
    """conn.search() retorna bool no ldap3; desempacotar levanta TypeError."""
    entry = _make_entry(
        "joao.silva", mail="joao.silva@test.local", display="João Silva",
        guid="aaaaaaaa-bbbb-cccc-dddd-eeeeffff0001",
        groups=("CN=GRP-SISPAT-TECNICOS-TI,OU=Grupos,DC=test,DC=local",),
    )
    conn = _FakeConn([entry])
    user = ad_ldap._search_service_account(_fake_ad_settings(), conn, "joao.silva")
    assert user is not None
    assert user.username == "joao.silva"
    assert user.dn == "CN=João Silva,DC=test,DC=local"
    assert user.enabled is True  # uac=512 (normal) → não desabilitado
    assert user.guid == "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0001"
    assert user.groups == ["CN=GRP-SISPAT-TECNICOS-TI,OU=Grupos,DC=test,DC=local"]


def test_search_service_account_returns_none_when_search_fails(_ad_db):
    conn = _FakeConn([], ok=False)
    assert ad_ldap._search_service_account(_fake_ad_settings(), conn, "joao.silva") is None


def test_search_service_account_returns_none_when_user_absent(_ad_db):
    entry = _make_entry("outro.usuario")
    conn = _FakeConn([entry])
    assert ad_ldap._search_service_account(_fake_ad_settings(), conn, "joao.silva") is None


@patch.dict(os.environ, {"AD_BIND_USER": "svc@empresa.local", "AD_BIND_PASSWORD": "svc-pass"})
@patch.object(ad_ldap, "_connect", autospec=True)
@patch.object(ad_ldap, "_search_service_account", autospec=True)
def test_authenticate_ad_full_flow_with_service_bind(mock_search, mock_connect, _ad_db):
    """Fluxo completo: busca via serviço → bind do usuário → grupos/atributos lidos."""
    adu = _ad_user(groups=("GRP-SISPAT-TECNICOS-TI",))

    def _search_side_effect(settings, conn, username):
        # Bind com o DN do usuário deve ter senha correta; caso contrário → None
        if conn.user == adu.dn and conn.password != "Ad@Senha123":
            return None
        return adu

    mock_search.side_effect = _search_side_effect

    def _connect_side_effect(settings, user, pw):
        # Simula o bind REAL: senha errada com o DN do usuário → bind recusado
        if user == adu.dn and pw != "Ad@Senha123":
            raise ad_ldap.ADError("credencial inválida")
        return SimpleNamespace(user=user, password=pw, unbind=lambda: None)

    mock_connect.side_effect = _connect_side_effect

    result = ad_ldap.authenticate_ad(_fake_ad_settings(), "joao.silva", "Ad@Senha123")
    assert result is not None and result.username == "joao.silva"

    # Bind com senha errada → None (credencial inválida, sem exceção)
    assert ad_ldap.authenticate_ad(_fake_ad_settings(), "joao.silva", "errada123") is None
