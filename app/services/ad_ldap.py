"""
Camada de protocolo LDAP/LDAPS para Active Directory (Microsoft AD e Samba AD).

Usa exclusivamente LDAP padrão (ldap3) — nenhum recurso proprietário:

- Autenticação: simples bind DIRETO com a conta do usuário informada no
  login (UPN derivado da Base DN, UPN digitado ou DOMÍNIO\\sam). Atributos e
  grupos são lidos na MESMA conexão autenticada. Sem conta de serviço.
  Funciona igualmente no Microsoft AD e no Samba AD DC.
- Atributos lidos (padronizados): sAMAccountName, mail, displayName/cn,
  objectGUID (binário → string canônica), userAccountControl (conta
  desabilitada) e memberOf (grupos).
- Sempre respeita timeout; LDAPS valida o certificado por padrão
  (verify_tls=False desativa, para ambientes com CA própria não publicada).

Nenhum dado sensível (senha) é logado ou retornado por esta camada.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from ldap3 import (
    ALL,
    SIMPLE,
    SUBTREE,
    Connection,
    Server,
    Tls,
)
from ldap3.core.exceptions import LDAPBindError, LDAPException

from app.models.ad_settings import ADSettings

logger = logging.getLogger(__name__)

# userAccountControl: bit 2 (0x2) = ACCOUNTDISABLE (padrão em MS AD e Samba AD)
UAC_DISABLED_BIT = 0x0002

_USER_ATTRS = [
    "sAMAccountName",
    "mail",
    "displayName",
    "cn",
    "objectGUID",
    "userAccountControl",
    "memberOf",
    "distinguishedName",
]


class ADError(Exception):
    """Falha de comunicação/configuração com o AD (não revela detalhes ao usuário)."""


@dataclass
class ADUser:
    """Atributos básicos de um usuário AD (apenas dados padrão LDAP)."""
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    dn: Optional[str] = None
    guid: Optional[str] = None
    enabled: bool = True
    groups: List[str] = field(default_factory=list)


def _canonical_guid(guid_bytes) -> Optional[str]:
    """Converte o objectGUID binário na forma canônica (string com hífens).

    Layout binário Windows: Data1 (4 bytes LE), Data2 (2 LE), Data3 (2 LE),
    Data4 (8 bytes inalterados). ldap3 já decodifica GUIDs como string quando
    possível; tratamos ambos os formatos.
    """
    if guid_bytes is None:
        return None
    if isinstance(guid_bytes, str):
        return guid_bytes if guid_bytes.strip() else None
    try:
        b = bytes(guid_bytes)
        if len(b) != 16:
            return None
        h = b.hex()
        d1 = h[6:8] + h[4:6] + h[2:4] + h[0:2]
        d2 = h[10:12] + h[8:10]
        d3 = h[14:16] + h[12:14]
        d4 = h[16:32]
        return f"{d1}-{d2}-{d3}-{d4[:4]}-{d4[4:]}".lower()
    except Exception:
        return None


def _build_server(settings: ADSettings) -> Server:
    """Monta o objeto Server ldap3 (LDAPS preferencial) a partir das settings."""
    use_ssl = bool(settings.use_ldaps)
    port = settings.port or (636 if use_ssl else 389)
    tls = None
    if use_ssl:
        # verify_tls=False apenas quando o admin explicitamente optar por não
        # validar o certificado (ambiente sem CA publicada). Nunca é o padrão.
        tls = Tls(validate=1 if settings.verify_tls else 0)  # 1=REQUIRED (valida)
    return Server(
        settings.server,
        port=port,
        use_ssl=use_ssl,
        tls=tls,
        get_info=ALL,
        connect_timeout=settings.timeout_seconds or 10,
    )


def _connect(settings: ADSettings, username: str, password: str) -> Connection:
    """Abre conexão com bind SIMPLE. Levanta ADError em qualquer falha."""
    if not settings.server or not settings.base_dn:
        raise ADError("Integração AD não configurada (servidor/base DN ausentes).")
    try:
        conn = Connection(
            _build_server(settings),
            user=username or None,
            password=password or "",
            authentication=SIMPLE,
            auto_bind=True,
            receive_timeout=settings.timeout_seconds or 10,
        )
        return conn
    except LDAPBindError:
        # Bind recusado pelo diretório (credencial inválida) é repropagado
        # como está: o chamador distingue "senha errada" (401) de
        # indisponibilidade (503). A mensagem nunca contém a senha.
        raise
    except LDAPException as exc:
        raise ADError(f"Falha de conexão/bind LDAP: {exc}") from exc
    except Exception as exc:  # sockets, TLS, DNS...
        raise ADError(f"Falha de rede ao contatar o AD: {exc}") from exc


def _search_service_account(settings: ADSettings, conn: Connection, username: str) -> Optional[ADUser]:
    """Busca o usuário por sAMAccountName usando a conexão já autenticada.

    O nome vem da época em que a busca usava uma conta de serviço dedicada;
    hoje recebe a própria conexão do usuário (bind direto). Mantida com o
    mesmo nome/assinatura por compatibilidade com os chamadores existentes.
    """
    search_base = settings.search_dn or settings.base_dn
    filtro = f"(&(objectClass=person)(sAMAccountName={_escape(username)}))"
    # ldap3.Connection.search() retorna bool (True = sucesso); usar conn.entries
    ok = conn.search(
        search_base, filtro, search_scope=SUBTREE, attributes=_USER_ATTRS
    )
    if not ok:
        # Log seguro (sem credenciais) para distinguir "usuário não encontrado"
        # de falha operacional da busca (ex.: base DN inexistente/incorreta).
        _res = getattr(conn, "result", None) or {}
        logger.warning(
            "Busca LDAP sem resultado para usuário '%s' em %s: %s (%s)",
            username, search_base, _res.get("description"), _res.get("message"),
        )
        return None
    for entry in conn.entries:
        if (_to_str(entry, "sAMAccountName") or "").lower() == username.lower():
            return _entry_to_aduser(entry)
    return None


def test_connection(settings: ADSettings) -> dict:
    """
    Testa a conectividade com o servidor AD (usado pela tela Integração AD).

    Valida: resolução do host, abertura da conexão (TCP/TLS) e leitura do
    RootDSE. NÃO usa conta de serviço: cada usuário autentica com a própria
    conta/senha no login. Nunca retorna nem registra credenciais.
    """
    result = {"ok": False, "message": "", "server_info": ""}
    if not settings.server or not settings.base_dn:
        result["message"] = "Servidor e Base DN são obrigatórios."
        return result
    try:
        server = _build_server(settings)
        # Sem bind: valida handshake TCP/TLS e tenta ler o RootDSE (get_info=ALL
        # faz a leitura no open()). Servidores que bloqueiam leitura anônima do
        # diretório NÃO falham o teste — conectividade é o que está sendo testado.
        conn = Connection(server, auto_bind=False)
        conn.open()
        try:
            info = getattr(conn, "info", None)
            naming = list(getattr(info, "naming_contexts", None) or []) if info else []
        finally:
            conn.unbind()
        base_ok = any(
            (n or "").strip().lower() == settings.base_dn.strip().lower()
            for n in naming
        ) if naming else None  # None = servidor não expõe naming contexts anonimamente
        if base_ok is True:
            result["message"] = (
                "Conectividade OK: servidor acessível e Base DN confirmada "
                "(cada usuário autentica com a própria conta no login)."
            )
        elif base_ok is False:
            result["message"] = (
                "Servidor acessível, porém a Base DN informada não foi exposta "
                "pelo diretório — confira o valor digitado."
            )
            result["server_info"] = f"{settings.server}:{settings.port} ({'LDAPS' if settings.use_ldaps else 'LDAP'})"
            return result
        else:
            result["message"] = (
                "Conectividade OK: servidor acessível (leitura anônima do "
                "diretório não permitida). Cada usuário autentica com a "
                "própria conta no login."
            )
        result["ok"] = True
        result["server_info"] = f"{settings.server}:{settings.port} ({'LDAPS' if settings.use_ldaps else 'LDAP'})"
        return result
    except Exception as exc:
        result["message"] = f"Falha ao conectar: {exc}"
        logger.warning("Teste de conexão AD falhou: %s", exc)
        return result


def _escape(value: str) -> str:
    """Escapa caracteres especiais de filtro LDAP (RFC 4515)."""
    replacements = {
        "\\": "\\5c", "*": "\\2a", "(": "\\28", ")": "\\29", "\x00": "\\00",
    }
    return "".join(replacements.get(ch, ch) for ch in (value or ""))


def _to_str(entry, attr: str) -> Optional[str]:
    try:
        v = entry[attr].value
        return str(v).strip() if v is not None else None
    except Exception:
        return None


def _entry_to_aduser(entry) -> ADUser:
    uac = entry["userAccountControl"].value if "userAccountControl" in entry else None
    try:
        uac_int = int(uac)
    except (TypeError, ValueError):
        uac_int = 0
    member_of = []
    try:
        raw = entry["memberOf"].values
        member_of = [str(g) for g in raw]
    except Exception:
        pass
    # objectGUID: ldap3 expõe os bytes crus em raw_values (lista); .value pode
    # vir formatado como string quando o schema foi lido (get_info=ALL).
    _guid_raw = None
    if "objectGUID" in entry:
        _attr = entry["objectGUID"]
        _guid_raw = _attr.raw_values[0] if getattr(_attr, "raw_values", None) else _attr.value
    return ADUser(
        username=_to_str(entry, "sAMAccountName") or "",
        display_name=_to_str(entry, "displayName") or _to_str(entry, "cn"),
        email=_to_str(entry, "mail"),
        dn=_to_str(entry, "distinguishedName"),
        guid=_canonical_guid(_guid_raw),
        enabled=(uac_int & UAC_DISABLED_BIT) == 0,
        groups=member_of,
    )


def _extract_common_name(dn: str) -> str:
    """Extrai o CN de um DN de grupo (padrão em MS AD e Samba AD)."""
    for part in (dn or "").split(","):
        part = part.strip()
        if part.lower().startswith("cn="):
            return part[3:].strip()
    return dn or ""


def _normalize_username(username: str, base_dn: str) -> str:
    """Normaliza o nome de usuário para o bind direto no AD (sem inventar formatos).

    - ``usuario``                    → ``usuario@dominio`` (UPN derivado da Base DN)
    - ``usuario@empresa.local``      → mantido (UPN explícito)
    - ``EMPRESA\\usuario``           → mantido (formato DOMAIN\\sam aceito pelo bind SIMPLE)

    O UPN derivado usa a Base DN configurada (DC=empresa,DC=local →
    empresa.local), que é o domínio do controlador consultado.
    """
    username = (username or "").strip()
    if "@" in username or "\\" in username:
        return username  # já é UPN ou DOMAIN\sam: não transforma
    domain = ".".join(
        part[3:] for part in (base_dn or "").split(",")
        if part.strip().lower().startswith("dc=")
    )
    return f"{username}@{domain}" if domain else username


def authenticate_ad(settings: ADSettings, username: str, password: str) -> Optional[ADUser]:
    """
    Autentica no AD com a PRÓPRIA CONTA do usuário (sem conta de serviço).

    Fluxo: bind SIMPLE direto com o usuário informado (UPN derivado da Base DN,
    UPN digitado ou DOMÍNIO\\sam) + senha → mesma conexão autenticada busca os
    próprios atributos/grupos → ADUser. Retorna None para credenciais
    inválidas (bind recusado). Levanta ADError quando o diretório está
    indisponível ou mal configurado.
    """
    username = (username or "").strip()
    if not username or not password:
        return None

    bind_principal = _normalize_username(username, settings.base_dn)
    try:
        conn = _connect(settings, bind_principal, password)
    except LDAPBindError:
        # Bind recusado pelo diretório = credencial inválida (não é 503)
        logger.info("Bind AD recusado para o usuário informado (credencial inválida).")
        return None

    try:
        # Atributos e grupos lidos NA MESMA conexão autenticada do usuário.
        # SAM exato primeiro; se o usuário digitou UPN/DOMÍNIO\\sam, procura pelo
        # sAMAccountName correspondente.
        sam = username.split("@", 1)[0].split("\\")[-1]
        user = _search_service_account(settings, conn, sam)
        if user is None:
            # Bind OK mas busca sem resultado: conta existe, porém não é
            # visível na base configurada (ex.: base/OU incorreta) — não é
            # "senha incorreta" nem indisponibilidade.
            raise ADError(
                "Conta autenticada no AD, mas não localizada na base configurada "
                "(verifique Base DN / DN de busca de usuários)."
            )
        return user
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


def get_user_groups(settings: ADSettings, ad_user: ADUser) -> List[str]:
    """Nomes (CN) dos grupos do usuário a partir de memberOf (via authenticate_ad)."""
    return [_extract_common_name(g) for g in (ad_user.groups or [])]


def _now_utc() -> datetime:
    return datetime.utcnow()
