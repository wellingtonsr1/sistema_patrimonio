"""
Serviço da integração Active Directory / Samba AD do SisPatrimônio Pro.

A integração é uma EXTENSÃO da arquitetura existente — não a substitui:

- O AD autentica a identidade e fornece grupos; o RBAC (perfis e permissões)
  continua sendo 100% do SisPatrimônio.
- Mapeamento: Grupo AD → Perfil EXISTENTE (tabela ad_group_roles). Nunca há
  permissões diretas do AD.
- Provisionamento: SOMENTE após confirmar grupo AD autorizado/mapeado. No
  primeiro login autorizado cria apenas o usuário do sistema
  (users.auth_provider='ad') e o vínculo com o colaborador existente
  (custodians) por e-mail — nunca duplica colaborador. Usuário do domínio
  sem grupo mapeado NÃO é criado no banco (apenas auditado e acesso negado).
- Perfis atribuídos via AD são marcados em user_roles.assigned_by='ad' para
  coexistir com atribuições manuais ('local'), que nunca são removidas.
- Toda ação relevante é registrada na trilha de auditoria existente.

Cada usuário autentica no AD com a própria conta/senha (bind direto, sem
conta de serviço); nenhuma senha é persistida, logada ou auditada.
"""

import logging
import re
import uuid
from datetime import datetime
from typing import List, Optional, Set

from sqlalchemy.orm import Session

from app.models.ad_group_role import ADGroupRole
from app.models.ad_settings import ADSettings
from app.models.custodian import Custodian
from app.models.user import User
from app.models.user_role import UserRole
from app.services import ad_ldap
from app.services.ad_ldap import ADUser, ADError
from app.services.audit_service import write_audit
from app.services.permission_service import get_role_by_id, get_user_roles

logger = logging.getLogger(__name__)

PROVIDER_LOCAL = "local"
PROVIDER_AD = "ad"


class ADNotConfiguredError(Exception):
    """Integração AD desabilitada ou incompleta (sem servidor/base DN)."""


class ADAuthenticationError(Exception):
    """Credenciais AD inválidas (não revela detalhes técnicos ao usuário)."""


class ADUnavailableError(Exception):
    """AD indisponível (timeout, rede, TLS) — falha de comunicação."""


class ADNoProfileError(Exception):
    """
    Usuário autenticado no AD, mas sem perfil autorizado: grupos não mapeados
    (ou conta desabilitada conforme política). Não recebe acesso ao sistema.
    """


# ============================================================================
# CONFIGURAÇÃO (singleton ad_settings id=1; env como fallback)
# ============================================================================

def get_ad_settings(db: Session) -> ADSettings:
    """Retorna a configuração AD (singleton id=1), criando-a se necessário."""
    settings = db.query(ADSettings).filter(ADSettings.id == 1).first()
    if settings is None:
        settings = ADSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _effective_settings(db: Session) -> ADSettings:
    """
    Configuração efetiva: linha do banco (tela Integração AD) com fallback
    para as variáveis de ambiente AD_* (config.py) nos campos vazios.
    """
    settings = get_ad_settings(db)
    from app import config

    if not settings.server:
        settings.server = config.AD_SERVER
    if not settings.port:
        settings.port = config.AD_PORT
    if not settings.base_dn:
        settings.base_dn = config.AD_BASE_DN
    if not settings.search_dn:
        settings.search_dn = config.AD_USER_DN or None
    # bind_user: campo mantido no modelo por compatibilidade, mas sem função
    # na autenticação (cada usuário autentica com a própria conta).
    if settings.use_ldaps is False and config.AD_USE_SSL:
        settings.use_ldaps = True
    return settings


def ad_enabled(db: Session) -> bool:
    """Integração AD ativa (habilitada na tela e com servidor/base DN válidos)."""
    s = _effective_settings(db)
    return bool(s.enabled and s.server and s.base_dn)


# ============================================================================
# MAPEAMENTO GRUPO AD → PERFIL EXISTENTE
# ============================================================================

def get_group_mappings(db: Session) -> List[ADGroupRole]:
    return db.query(ADGroupRole).order_by(ADGroupRole.priority, ADGroupRole.group_name).all()


def upsert_group_mapping(db: Session, group_name: str, role_id: int, priority: int = 10) -> ADGroupRole:
    group_name = (group_name or "").strip()
    if not group_name:
        raise ValueError("Informe o nome do grupo AD.")
    if get_role_by_id(db, role_id) is None:
        raise ValueError("Perfil não encontrado.")
    mapping = (
        db.query(ADGroupRole).filter(ADGroupRole.group_name == group_name).first()
    )
    if mapping:
        mapping.role_id = role_id
        mapping.priority = priority
    else:
        mapping = ADGroupRole(group_name=group_name, role_id=role_id, priority=priority)
        db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


def delete_group_mapping(db: Session, mapping_id: int) -> None:
    mapping = db.query(ADGroupRole).filter(ADGroupRole.id == mapping_id).first()
    if mapping:
        db.delete(mapping)
        db.commit()


def _group_dn_to_name(dn: str) -> str:
    return ad_ldap._extract_common_name(dn)


def resolve_role_for_groups(db: Session, group_dns: List[str]) -> tuple:
    """
    Política determinística para usuário em vários grupos mapeados:
    1. apenas grupos ativos configurados na tela são considerados;
    2. menor `priority` vence (empate: ordem de criação/id);
    3. configuração group_role_priority (CSV de nomes de grupos) pode
       sobrepor a prioridade numérica.

    Retorna (role_id ou None, group_name_vencedor ou None, todos_grupos_mapeados).
    Nunca escolhe aleatoriamente e nunca concede privilégio sem regra clara.
    """
    mappings = {m.group_name: m for m in get_group_mappings(db) if m.is_active}
    user_groups = [g for g in (_group_dn_to_name(d) for d in group_dns) if g]
    matched = [m for g, m in mappings.items() if g in user_groups]
    if not matched:
        return (None, None, matched)

    # Prioridade opcional configurada por CSV (ordem explícita do admin)
    custom_order = [
        g.strip() for g in (_effective_settings(db).group_role_priority or "").split(",")
        if g.strip()
    ]
    if custom_order:
        rank = {g: i for i, g in enumerate(custom_order)}
        matched.sort(key=lambda m: rank.get(m.group_name, len(rank) + m.priority))
    else:
        matched.sort(key=lambda m: (m.priority, m.id))
    winner = matched[0]
    return (winner.role_id, winner.group_name, matched)


# ============================================================================
# PROVISIONAMENTO / VÍNCULO / SINCRONIZAÇÃO
# ============================================================================

def _find_user_by_identity(db: Session, ad_user: ADUser) -> Optional[User]:
    """
    Localiza o usuário do sistema correspondente à identidade AD, em ordem
    de estabilidade: objectGUID → username → e-mail. Nunca pelo nome.
    """
    if ad_user.guid:
        by_guid = (
            db.query(User).filter(User.ad_object_guid == ad_user.guid).first()
        )
        if by_guid:
            return by_guid
    by_username = db.query(User).filter(User.username == ad_user.username).first()
    if by_username:
        return by_username
    if ad_user.email:
        return db.query(User).filter(User.email == ad_user.email).first()
    return None


def find_linked_custodian(db: Session, ad_user: ADUser) -> Optional[Custodian]:
    """
    Localiza o COLABORADOR existente para vincular (nunca cria duplicado):
    e-mail (único no cadastro) e, como alternativa explícita, username
    correspondendo à matrícula. Nunca vincula cegamente por nome.
    """
    if ad_user.email:
        custodian = db.query(Custodian).filter(Custodian.email == ad_user.email).first()
        if custodian:
            return custodian
    return db.query(Custodian).filter(Custodian.registration_code == ad_user.username).first()


def _assign_ad_role(db: Session, user: User, role_id: int, group_name: str) -> tuple:
    """
    Garante o perfil do mapeamento no usuário (assigned_by='ad'), preservando
    perfis atribuídos manualmente. Retorna (criou?, perfil anterior).
    """
    from app.models.role import Role

    role = get_role_by_id(db, role_id)
    if role is None:
        return (False, None)
    existing = {
        ur.role_id: ur
        for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()
    }
    previous_role_name = None
    previous = existing.get(role_id)
    if previous is not None:
        previous_role_name = (
            db.query(Role).filter(Role.id == role_id).first().name
            if previous.assigned_by == "ad" else None
        )
        if previous.assigned_by == "ad":
            return (False, previous_role_name)
        # Já tem o perfil manualmente — nada a fazer, apenas registrar
        return (False, None)
    # Remove perfis anteriores atribuídos via AD (troca de grupo) e adiciona o novo
    for ur in list(existing.values()):
        if ur.assigned_by == "ad":
            db.delete(ur)
    db.add(UserRole(user_id=user.id, role_id=role_id, assigned_by="ad"))
    db.commit()
    return (True, previous_role_name)


def _upsert_ad_user(db: Session, settings: ADSettings, ad_user: ADUser, ip: Optional[str]) -> User:
    """
    Atualiza (ou provisiona) o usuário do sistema a partir do AD, aplicando
    APENAS os campos permitidos (username, nome, e-mail, identificador AD).
    Não toca em matrícula, bens, movimentações ou histórico (patrimônio).
    """
    user = _find_user_by_identity(db, ad_user)
    created = False
    if user is None:
        if not settings.auto_create_user:
            # Conta inexistente e provisionamento desabilitado: acesso negado.
            # Auditoria obrigatória (toda tentativa AD deve ser registrada);
            # usuário NÃO é criado. Mensagem genérica ao usuário final.
            write_audit(
                db, user=None, username=ad_user.username,
                action=ACTION_AD_NO_MAPPING, module="Integração AD", resource="Login",
                resource_ref=ad_user.username, ip_address=ip, result=RESULT_DENIED,
                new_data={
                    "nome": ad_user.display_name,
                    "identificador_ad": ad_user.guid,
                    "grupos": ad_ldap.get_user_groups(settings, ad_user),
                    "motivo": "PROVISIONAMENTO_DESABILITADO",
                },
                description=(
                    f"Login AD autorizado por grupo mapeado para {ad_user.username}, "
                    "porém o provisionamento automático está desabilitado e a conta "
                    "não existe no SisPatrimônio; acesso negado e nenhum usuário criado."
                ),
            )
            raise ADNoProfileError(
                "Seu usuário foi autenticado, mas não possui acesso ao SisPatrimônio."
            )
        user = User(
            username=ad_user.username,
            # Sem senha local utilizável (provedor externo); hash inválido bloqueia login local
            password_hash="!ad-external",
            auth_provider=PROVIDER_AD,
            is_active=True,
        )
        db.add(user)
        db.flush()
        created = True

    # Campos que o AD pode atualizar (identidade básica)
    user.full_name = ad_user.display_name or user.full_name
    user.email = ad_user.email or user.email
    user.ad_object_guid = ad_user.guid or user.ad_object_guid
    user.ad_dn = ad_user.dn or user.ad_dn
    user.ad_last_sync = datetime.utcnow()
    if user.auth_provider != PROVIDER_AD:
        user.auth_provider = PROVIDER_AD
    db.commit()
    db.refresh(user)

    if created:
        write_audit(
            db,
            user=user,
            action=ACTION_AD_PROVISIONED,
            module="Integração AD",
            resource="User",
            resource_id=user.id,
            resource_ref=user.username,
            ip_address=ip,
            description=f"Usuário {user.username} provisionado via Active Directory.",
        )
    return user


def _link_custodian(db: Session, user: User, ad_user: ADUser, ip: Optional[str]) -> None:
    """Vincula o usuário ao colaborador existente (armazena custodian_id em users é evitado;
    a ligação é registrada por e-mail/matrícula no momento do provisionamento e reaproveitada."""
    custodian = find_linked_custodian(db, ad_user)
    if custodian is None:
        return  # sem colaborador correspondente: nada é criado automaticamente
    write_audit(
        db,
        user=user,
        action=ACTION_AD_CUSTODIAN_LINKED,
        module="Integração AD",
        resource="Custodian",
        resource_id=custodian.id,
        resource_ref=custodian.registration_code,
        ip_address=ip,
        description=f"Usuário {user.username} vinculado ao colaborador "
                    f"{custodian.name} ({custodian.registration_code}) via AD.",
    )


def authenticate_and_sync(db: Session, username: str, password: str, ip: Optional[str] = None) -> User:
    """
    Fluxo completo de login AD (usado pelo ADAuthProvider):

    1. autentica no AD (senha NUNCA persistida/logada);
    2. valida status da conta (desabilitada → negado, conforme política);
    3. obtém grupos e resolve o perfil pelo mapeamento Grupo→Perfil ANTES de
       qualquer provisionamento (a autenticação AD NÃO concede acesso);
    4. sem grupo autorizado/mapeado → NÃO cria usuário, colaborador, perfil,
       permissões ou sessão: registra SOMENTE na auditoria e nega o acesso;
    5. autorizado → provisiona/atualiza o usuário, vincula o colaborador
       existente e aplica o perfil EXISTENTE (assigned_by='ad'), preservando
       os perfis manuais;
    6. registra auditoria e retorna o User para a sessão normal do sistema.

    Levanta ADAuthenticationError / ADError->ADUnavailableError /
    ADNoProfileError conforme o caso (mensagens genéricas ao usuário final).
    """
    settings = _effective_settings(db)
    if not ad_enabled(db):
        raise ADNotConfiguredError("Integração AD desabilitada ou incompleta.")

    try:
        ad_user = ad_ldap.authenticate_ad(settings, username, password)
    except ADError as exc:
        logger.warning("Falha de comunicação com o AD: %s", exc)
        write_audit(
            db, user=None, username=username,
            action=ACTION_AD_UNAVAILABLE, module="Integração AD", resource="Login",
            resource_ref=username, ip_address=ip, result=RESULT_FAILURE,
            description="Falha de comunicação com o Active Directory.",
        )
        raise ADUnavailableError("Não foi possível conectar ao Active Directory.") from exc

    if ad_user is None:
        write_audit(
            db, user=None, username=username,
            action=ACTION_AD_LOGIN_FAILED, module="Integração AD", resource="Login",
            resource_ref=username, ip_address=ip, result=RESULT_FAILURE,
            description="Falha de autenticação no Active Directory (credenciais inválidas).",
        )
        raise ADAuthenticationError("Usuário ou senha inválidos.")

    # Conta desabilitada no AD → login NEGADO (histórico/colaborador preservados)
    if not ad_user.enabled:
        write_audit(
            db, user=None, username=username,
            action=ACTION_AD_ACCOUNT_DISABLED, module="Integração AD", resource="Login",
            resource_ref=username, ip_address=ip, result=RESULT_DENIED,
            description="Conta desabilitada no Active Directory; acesso negado.",
        )
        raise ADAuthenticationError("Sua conta do Active Directory está desabilitada.")

    # Grupos → perfil (determinístico) — resolvido ANTES de provisionar:
    # autenticar no AD NÃO concede acesso; apenas um grupo explicitamente
    # autorizado/mapeado para um perfil EXISTENTE o concede.
    group_names = ad_ldap.get_user_groups(settings, ad_user)
    role_id, winner_group, matched = resolve_role_for_groups(db, ad_user.groups)

    if role_id is None:
        # Usuário do domínio com conta AD válida, porém SEM grupo autorizado:
        # NÃO criar usuário no SisPatrimônio, NÃO criar colaborador/perfil/
        # permissões/sessão — apenas registrar a tentativa na auditoria.
        write_audit(
            db, user=None, username=ad_user.username,
            action=ACTION_AD_NO_MAPPING, module="Integração AD", resource="Login",
            resource_ref=ad_user.username, ip_address=ip, result=RESULT_DENIED,
            new_data={
                "nome": ad_user.display_name,
                "identificador_ad": ad_user.guid,
                "grupos": group_names,
                "grupos_autorizados": "NENHUM",
                "perfil": "NENHUM",
                "motivo": "NENHUM_GRUPO_AD_MAPEADO",
            },
            description=(
                f"Autenticação AD bem-sucedida para {ad_user.username}, porém sem grupo "
                "autorizado/mapeado; acesso negado e nenhum usuário criado no SisPatrimônio."
            ),
        )
        raise ADNoProfileError(
            "Seu usuário foi autenticado, mas não possui um perfil autorizado no SisPatrimônio."
        )

    # Autorizado: provisiona/atualiza o usuário e vincula o colaborador existente.
    user = _upsert_ad_user(db, settings, ad_user, ip)
    _link_custodian(db, user, ad_user, ip)

    write_audit(
        db, user=user,
        action=ACTION_AD_GROUP_SYNC, module="Integração AD", resource="ADGroup",
        resource_ref=user.username, ip_address=ip,
        new_data={"grupos": group_names},
        description=f"Grupos AD identificados: {', '.join(group_names) if group_names else '(nenhum)'}",
    )

    assigned, previous_role = _assign_ad_role(db, user, role_id, winner_group)
    role = get_role_by_id(db, role_id)

    write_audit(
        db, user=user,
        action=ACTION_AD_LOGIN_AUTHORIZED, module="Integração AD", resource="Login",
        resource_ref=user.username, ip_address=ip, result=RESULT_SUCCESS,
        new_data={
            "grupos": group_names,
            "grupo_autorizado": winner_group,
            "perfil": role.name if role else str(role_id),
        },
        description=(
            f"Login AD autorizado para {user.username} — grupo '{winner_group}' mapeado "
            f"para o perfil '{role.name if role else role_id}'."
        ),
    )

    if assigned:
        write_audit(
            db, user=user,
            action=ACTION_AD_ROLE_SYNCED, module="Integração AD", resource="UserRole",
            resource_id=role_id, resource_ref=user.username, ip_address=ip,
            previous_data={"perfil": previous_role} if previous_role else None,
            new_data={"perfil": role.name if role else str(role_id), "grupo": winner_group},
            description=f"Perfil '{role.name if role else role_id}' atribuído ao usuário "
                        f"{user.username} pelo grupo AD '{winner_group}'.",
        )
    elif previous_role:
        write_audit(
            db, user=user,
            action=ACTION_AD_ROLE_SYNCED, module="Integração AD", resource="UserRole",
            resource_id=role_id, resource_ref=user.username, ip_address=ip,
            new_data={"perfil": previous_role, "grupo": winner_group},
            description=f"Perfil via AD já aplicado ao usuário {user.username}.",
        )
    return user


# ============================================================================
# AÇÕES DE AUDITORIA ESPECÍFICAS DA INTEGRAÇÃO
# (constantes definidas em audit_service.py — fonte única)
# ============================================================================

from app.services.audit_service import (  # noqa: E402
    ACTION_AD_ACCOUNT_DISABLED,
    ACTION_AD_CUSTODIAN_LINKED,
    ACTION_AD_GROUP_SYNC,
    ACTION_AD_LOGIN,
    ACTION_AD_LOGIN_AUTHORIZED,
    ACTION_AD_LOGIN_FAILED,
    ACTION_AD_NO_MAPPING,
    ACTION_AD_PROVISIONED,
    ACTION_AD_ROLE_SYNCED,
    ACTION_AD_UNAVAILABLE,
    RESULT_DENIED,
    RESULT_FAILURE,
    RESULT_SUCCESS,
)
