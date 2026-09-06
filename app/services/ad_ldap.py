"""
Camada de protocolo LDAP/LDAPS para Active Directory (Microsoft AD e Samba AD).

Usa exclusivamente LDAP padrão (ldap3) — nenhum recurso proprietário:

- Autenticação: busca do usuário por sAMAccountName (escopo configurável) e
  simples bind com o DN encontrado. Funciona igualmente no Microsoft AD e no
  Samba AD DC.
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
from ldap3.core.exceptions import LDAPException

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
    except LDAPException as exc:
        raise ADError(f"Falha de conexão/bind LDAP: {exc}") from exc
    except Exception as exc:  # sockets, TLS, DNS...
        raise ADError(f"Falha de rede ao contatar o AD: {exc}") from exc


def _search_service_account(settings: ADSettings, conn: Connection, username: str) -> Optional[ADUser]:
    """Busca o usuário por sAMAccountName usando a conta de serviço (bind técnico)."""
    search_base = settings.search_dn or settings.base_dn
    filtro = f"(&(objectClass=person)(sAMAccountName={_escape(username)}))"
    # ldap3.Connection.search() retorna bool (True = sucesso); usar conn.entries
    ok = conn.search(
        search_base, filtro, search_scope=SUBTREE, attributes=_USER_ATTRS
    )
    if not ok:
        return None
    for entry in conn.entries:
        if _to_str(entry, "sAMAccountName") == username:
            return _entry_to_aduser(entry)
    return None


def test_connection(settings: ADSettings) -> dict:
    """
    Testa a conexão com o servidor AD (usado pela tela Integração AD).
    Usa a conta de serviço das variáveis de ambiente (AD_BIND_USER/PASSWORD),
    quando configurada; sem bind account, valida apenas a abertura da conexão.
    Nunca retorna nem registra a senha.
    """
    import os

    result = {"ok": False, "message": "", "server_info": ""}
    if not settings.server or not settings.base_dn:
        result["message"] = "Servidor e Base DN são obrigatórios."
        return result
    try:
        server = _build_server(settings)
        bind_user = os.getenv("AD_BIND_USER", "").strip()
        bind_pass = os.getenv("AD_BIND_PASSWORD", "")
        if bind_user:
            conn = Connection(
                server, user=bind_user, password=bind_pass,
                authentication=SIMPLE, auto_bind=True,
                receive_timeout=settings.timeout_seconds or 10,
            )
            who = conn.extend.standard.who_am_i()
            conn.unbind()
            result["ok"] = True
            result["message"] = f"Conexão estabelecida e bind validado ({who or bind_user})."
        else:
            # Sem conta de serviço: valida handshake TCP/TLS
            conn = Connection(server, auto_bind=False)
            conn.open()
            result["ok"] = True
            result["message"] = "Conexão com o servidor estabelecida (sem bind de serviço)."
            conn.unbind()
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
    return ADUser(
        username=_to_str(entry, "sAMAccountName") or "",
        display_name=_to_str(entry, "displayName") or _to_str(entry, "cn"),
        email=_to_str(entry, "mail"),
        dn=_to_str(entry, "distinguishedName"),
        guid=_canonical_guid(entry["objectGUID"].raw_value if "objectGUID" in entry else None),
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


def authenticate_ad(settings: ADSettings, username: str, password: str) -> Optional[ADUser]:
    """
    Autentica no AD e retorna os atributos do usuário (com grupos) em caso de
    sucesso. Retorna None para credenciais inválidas. Levanta ADError quando
    o diretório está indisponível ou mal configurado.

    Fluxo: bind de serviço (se configurado) → busca por sAMAccountName →
    simples bind com o DN do usuário (verifica a senha) → rebind de serviço
    para ler memberOf completo.
    """
    username = (username or "").strip()
    if not username or not password:
        return None

    import os
    bind_user = os.getenv("AD_BIND_USER", "").strip()
    bind_pass = os.getenv("AD_BIND_PASSWORD", "")

    # 1) Busca do usuário (requer bind técnico quando o diretório não é anônimo)
    try:
        conn = _connect(settings, bind_user, bind_pass)
    except ADError:
        raise
    try:
        user = _search_service_account(settings, conn, username)
        if user is None:
            # Usuário não existe no AD — NÃO tentar bind anônimo com DN inventado
            return None
        user_dn = user.dn
    finally:
        try:
            conn.unbind()
        except Exception:
            pass

    # 2) Verificação da senha: simples bind com o DN do usuário
    try:
        user_conn = _connect(settings, user_dn, password)
    except ADError:
        return None  # credencial inválida (bind recusado)
    try:
        # 3) Rebind de serviço para reler atributos/grupos com a conta de serviço
        if bind_user:
            try:
                svc_conn = _connect(settings, bind_user, bind_pass)
                try:
                    reloaded = _search_service_account(settings, svc_conn, username)
                    if reloaded is not None:
                        user = reloaded
                finally:
                    try:
                        svc_conn.unbind()
                    except Exception:
                        pass
            except ADError:
                pass  # usa os atributos já coletados
        user.enabled = user.enabled  # (já calculado na busca)
        return user
    finally:
        try:
            user_conn.unbind()
        except Exception:
            pass


def get_user_groups(settings: ADSettings, ad_user: ADUser) -> List[str]:
    """Nomes (CN) dos grupos do usuário a partir de memberOf (via authenticate_ad)."""
    return [_extract_common_name(g) for g in (ad_user.groups or [])]


def _now_utc() -> datetime:
    return datetime.utcnow()
