"""
Serviço de trilha de auditoria.

Registra ações importantes (login, falha de login, logout, criações,
alterações, bloqueios, resets de senha, mudanças de perfil/permissão,
movimentações patrimoniais e acessos negados) com ator, IP, módulo,
recurso, resultado e dados anteriores/posteriores (JSON).

A auditoria é somente-leitura para usuários comuns: não existe rota de
escrita/exclusão e a visualização exige `auditoria.visualizar`.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User

# Ações normalizadas
ACTION_LOGIN = "LOGIN"
ACTION_LOGIN_FAILED = "LOGIN_FALHA"
ACTION_LOGIN_LOCKED = "LOGIN_BLOQUEADO"
ACTION_LOGOUT = "LOGOUT"
ACTION_CREATE = "CRIACAO"
ACTION_UPDATE = "ALTERACAO"
ACTION_DELETE = "EXCLUSAO"
ACTION_BLOCK = "BLOQUEIO"
ACTION_UNBLOCK = "DESBLOQUEIO"
ACTION_PASSWORD_RESET = "RESET_SENHA"
ACTION_PASSWORD_CHANGE = "TROCA_SENHA"
ACTION_PROFILE_CHANGE = "ALTERACAO_PERFIL"
ACTION_ROLE_CREATE = "CRIACAO_PERFIL"
ACTION_ROLE_UPDATE = "ALTERACAO_PERFIL_PERMISSOES"
ACTION_ROLE_DELETE = "EXCLUSAO_PERFIL"
ACTION_MOVEMENT = "MOVIMENTACAO"
ACTION_MAINTENANCE = "MANUTENCAO"
ACTION_IMPORT = "IMPORTACAO"
ACTION_ACCESS_DENIED = "ACESSO_NEGADO"

# Integração Active Directory (ações detalhadas vivem em ad_service)
ACTION_AD_LOGIN = "LOGIN_AD"
ACTION_AD_LOGIN_AUTHORIZED = "LOGIN_AD_AUTORIZADO"
ACTION_AD_LOGIN_FAILED = "LOGIN_AD_FALHA"
ACTION_AD_ACCOUNT_DISABLED = "CONTA_AD_DESABILITADA"
ACTION_AD_PROVISIONED = "USUARIO_AD_PROVISIONADO"
ACTION_AD_CUSTODIAN_LINKED = "USUARIO_AD_VINCULADO_COLABORADOR"
ACTION_AD_GROUP_SYNC = "GRUPOS_AD_IDENTIFICADOS"
ACTION_AD_NO_MAPPING = "GRUPO_AD_SEM_MAPEAMENTO"
ACTION_AD_ROLE_SYNCED = "PERFIL_SINCRONIZADO_AD"
ACTION_AD_GROUP_CONFLICT = "CONFLITO_GRUPOS_AD"
ACTION_AD_UNAVAILABLE = "FALHA_COMUNICACAO_AD"
ACTION_AD_SETTINGS_UPDATED = "ALTERACAO_CONFIG_AD"
ACTION_AD_CONNECTION_TESTED = "TESTE_CONEXAO_AD"

# Rótulos em linguagem natural exibidos na interface.
# A ação gravada na trilha continua sendo o identificador (ex.: "RESET_SENHA").
ACTION_LABELS: Dict[str, str] = {
    # Ações gerais
    ACTION_LOGIN: "Login",
    ACTION_LOGIN_FAILED: "Falha de Login",
    ACTION_LOGIN_LOCKED: "Login Bloqueado",
    ACTION_LOGOUT: "Logout",
    ACTION_CREATE: "Criação",
    ACTION_UPDATE: "Alteração",
    ACTION_DELETE: "Exclusão",
    ACTION_BLOCK: "Bloqueio",
    ACTION_UNBLOCK: "Desbloqueio",
    ACTION_PASSWORD_RESET: "Redefinição de Senha",
    ACTION_PASSWORD_CHANGE: "Troca de Senha",
    ACTION_PROFILE_CHANGE: "Alteração de Perfil",
    ACTION_ROLE_CREATE: "Criação de Perfil",
    ACTION_ROLE_UPDATE: "Alteração de Permissões do Perfil",
    ACTION_ROLE_DELETE: "Exclusão de Perfil",
    ACTION_MOVEMENT: "Movimentação",
    ACTION_MAINTENANCE: "Manutenção",
    ACTION_IMPORT: "Importação",
    ACTION_ACCESS_DENIED: "Acesso Negado",
    # Integração Active Directory
    ACTION_AD_LOGIN: "Login (AD)",
    ACTION_AD_LOGIN_AUTHORIZED: "Login AD Autorizado",
    ACTION_AD_LOGIN_FAILED: "Falha de Login AD",
    ACTION_AD_ACCOUNT_DISABLED: "Conta AD Desabilitada",
    ACTION_AD_PROVISIONED: "Usuário AD Provisionado",
    ACTION_AD_CUSTODIAN_LINKED: "Usuário AD Vinculado a Colaborador",
    ACTION_AD_GROUP_SYNC: "Grupos AD Identificados",
    ACTION_AD_NO_MAPPING: "Grupo AD sem Mapeamento",
    ACTION_AD_ROLE_SYNCED: "Perfil Sincronizado pelo AD",
    ACTION_AD_GROUP_CONFLICT: "Conflito de Grupos AD",
    ACTION_AD_UNAVAILABLE: "Falha de Comunicação com o AD",
    ACTION_AD_SETTINGS_UPDATED: "Alteração de Configuração do AD",
    ACTION_AD_CONNECTION_TESTED: "Teste de Conexão com o AD",
}

# Resultados
RESULT_SUCCESS = "SUCCESS"
RESULT_FAILURE = "FAILURE"
RESULT_DENIED = "DENIED"
RESULT_LOCKED = "LOCKED"


def action_label(action: Optional[str]) -> str:
    """Converte a ação da trilha em rótulo de interface.

    Ações desconhecidas (novas, gravadas por versões futuras) caem num
    rótulo legível gerado a partir do próprio identificador, evitando que
    um `SNAKE_CASE` chegue à tela.
    """
    if not action:
        return ""
    return ACTION_LABELS.get(action) or " ".join(
        word.capitalize() for word in action.split("_") if word
    )


def _to_json(data: Any) -> Optional[str]:
    if data is None:
        return None
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"unserializable": str(data)}, ensure_ascii=False)


def write_audit(
    db: Session,
    *,
    user: Optional[User],
    action: str,
    module: Optional[str] = None,
    resource: Optional[str] = None,
    resource_id: Optional[int] = None,
    resource_ref: Optional[str] = None,
    ip_address: Optional[str] = None,
    result: str = RESULT_SUCCESS,
    description: Optional[str] = None,
    previous_data: Optional[Dict[str, Any]] = None,
    new_data: Optional[Dict[str, Any]] = None,
    username: Optional[str] = None,
) -> AuditLog:
    """
    Grava um registro na trilha de auditoria.

    `username` permite registrar o nome de usuário mesmo quando o usuário
    não existe ou não autenticou (ex: falha de login, conta bloqueada).
    """
    entry = AuditLog(
        timestamp=datetime.utcnow(),
        user_id=user.id if user else None,
        username=username or (user.username if user else None),
        action=action,
        module=module,
        resource=resource,
        resource_id=resource_id,
        resource_ref=resource_ref,
        ip_address=ip_address,
        result=result,
        description=description,
        previous_data=_to_json(previous_data),
        new_data=_to_json(new_data),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def write_change_audit(
    db: Session,
    *,
    user: Optional[User],
    action: str,
    module: str,
    resource: str,
    resource_ref: Optional[str] = None,
    resource_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
) -> AuditLog:
    """
    Grava auditoria de CRIACAO/ALTERACAO comparando dados anteriores e
    posteriores; a descrição lista automaticamente os campos alterados.
    """
    before = before or {}
    after = after or {}
    changes = changed_fields(before, after)
    if description is None:
        if changes:
            description = "Campos alterados: " + ", ".join(sorted(changes.keys()))
        else:
            description = "Nenhuma alteração de campo registrada"
    return write_audit(
        db,
        user=user,
        action=action,
        module=module,
        resource=resource,
        resource_ref=resource_ref,
        resource_id=resource_id,
        ip_address=ip_address,
        result=RESULT_SUCCESS,
        description=description,
        previous_data=before or None,
        new_data=after or None,
    )


def changed_fields(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Retorna apenas os campos efetivamente alterados entre dois dicionários:
    {"campo": {"de": valor_anterior, "para": valor_novo}}.
    """
    changes: Dict[str, Dict[str, Any]] = {}
    all_keys = set(before) | set(after)
    for key in all_keys:
        old, new = before.get(key), after.get(key)
        if old != new:
            changes[key] = {"de": old, "para": new}
    return changes


def get_audit_logs(
    db: Session,
    *,
    search: Optional[str] = None,
    module: Optional[str] = None,
    action: Optional[str] = None,
    result: Optional[str] = None,
    user_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 200,
) -> List[AuditLog]:
    """Consulta a trilha de auditoria com filtros (ordenada da mais recente)."""
    query = db.query(AuditLog)

    if module:
        query = query.filter(AuditLog.module == module)
    if action:
        query = query.filter(AuditLog.action == action)
    if result:
        query = query.filter(AuditLog.result == result)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            (AuditLog.username.ilike(term))
            | (AuditLog.resource_ref.ilike(term))
            | (AuditLog.description.ilike(term))
        )

    return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()


def get_distinct_modules(db: Session) -> List[str]:
    rows = db.query(AuditLog.module).distinct().order_by(AuditLog.module).all()
    return [m for (m,) in rows if m]


def get_distinct_actions(db: Session) -> List[str]:
    rows = db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    return [a for (a,) in rows if a]