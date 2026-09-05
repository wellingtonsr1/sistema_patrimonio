"""
Serviço de RBAC (Role-Based Access Control).

- Catálogo canônico de permissões (PERMISSION_CATALOG) no padrão
  `modulo.acao` (ex: `patrimonio.criar`).
- Seed idempotente de permissões e perfis padrão (ensure_default_roles).
- Helpers de consulta: permissões de um usuário, perfis de um usuário,
  permissões de um perfil, atribuição/remoção de perfis.

Regra de ouro: DENY BY DEFAULT — um usuário só executa uma operação se
possuir explicitamente a permissão. A única exceção é `User.is_admin`
(superusuário), que preserva o comportamento do administrador inicial
e ignora as verificações (bypass total, auditado).
"""

from typing import Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_role import UserRole

# ============================================================================
# CATÁLOGO DE PERMISSÕES (fonte única da verdade)
# ============================================================================

PERMISSION_CATALOG: List[dict] = [
    # --- Patrimônio (bens e equipamentos) ---
    {"name": "patrimonio.visualizar", "module": "Patrimônio", "label": "Visualizar patrimônio", "description": "Consultar bens, detalhes, timeline e fichas técnicas."},
    {"name": "patrimonio.criar", "module": "Patrimônio", "label": "Cadastrar patrimônio", "description": "Cadastrar novos bens e importar via CSV."},
    {"name": "patrimonio.editar", "module": "Patrimônio", "label": "Editar patrimônio", "description": "Editar dados cadastrais de bens (ficha, fiscal, notas)."},
    {"name": "patrimonio.excluir", "module": "Patrimônio", "label": "Excluir patrimônio", "description": "Exclusão definitiva de registros patrimoniais."},

    # --- Movimentação ---
    {"name": "movimentacao.visualizar", "module": "Movimentação", "label": "Visualizar movimentações", "description": "Consultar histórico, trilha de auditoria de fluxo e termos."},
    {"name": "movimentacao.criar", "module": "Movimentação", "label": "Registrar movimentação", "description": "Alocar, transferir, devolver, enviar/retornar de manutenção e dar baixa."},
    {"name": "movimentacao.editar", "module": "Movimentação", "label": "Editar movimentação", "description": "Corrigir dados de movimentações registradas."},
    {"name": "movimentacao.cancelar", "module": "Movimentação", "label": "Cancelar movimentação", "description": "Cancelar movimentação ou termo gerado (reservado)."},

    # --- Manutenção ---
    {"name": "manutencao.visualizar", "module": "Manutenção", "label": "Visualizar manutenções", "description": "Consultar ordens de serviço, diagnósticos e histórico de reparos."},
    {"name": "manutencao.criar", "module": "Manutenção", "label": "Abrir manutenção", "description": "Abrir ordem de serviço (preventiva, corretiva, upgrade)."},
    {"name": "manutencao.editar", "module": "Manutenção", "label": "Editar manutenção", "description": "Atualizar diagnóstico, peças e informações técnicas da OS."},
    {"name": "manutencao.finalizar", "module": "Manutenção", "label": "Finalizar manutenção", "description": "Concluir OS com solução aplicada e custos."},

    # --- Colaboradores (custodiantes) ---
    {"name": "colaboradores.visualizar", "module": "Colaboradores", "label": "Visualizar colaboradores", "description": "Consultar colaboradores e bens sob custódia."},
    {"name": "colaboradores.criar", "module": "Colaboradores", "label": "Cadastrar colaboradores", "description": "Cadastrar colaboradores e importar via CSV."},
    {"name": "colaboradores.editar", "module": "Colaboradores", "label": "Editar colaboradores", "description": "Editar dados cadastrais de colaboradores."},

    # --- Locais / departamentos ---
    {"name": "locais.visualizar", "module": "Locais", "label": "Visualizar locais", "description": "Consultar locais, prédios, salas e departamentos."},
    {"name": "locais.criar", "module": "Locais", "label": "Cadastrar locais", "description": "Cadastrar novos locais e departamentos."},
    {"name": "locais.editar", "module": "Locais", "label": "Editar locais", "description": "Editar dados de locais e departamentos."},

    # --- Usuários (administração) ---
    {"name": "usuarios.visualizar", "module": "Usuários", "label": "Visualizar usuários", "description": "Listar e pesquisar usuários do sistema."},
    {"name": "usuarios.criar", "module": "Usuários", "label": "Criar usuários", "description": "Cadastrar novos usuários."},
    {"name": "usuarios.editar", "module": "Usuários", "label": "Editar usuários", "description": "Editar dados, perfis e redefinir senha de usuários."},
    {"name": "usuarios.bloquear", "module": "Usuários", "label": "Bloquear/desbloquear usuários", "description": "Ativar, desativar, bloquear e desbloquear usuários."},

    # --- Perfis (administração) ---
    {"name": "perfis.visualizar", "module": "Perfis", "label": "Visualizar perfis", "description": "Listar perfis e suas permissões."},
    {"name": "perfis.criar", "module": "Perfis", "label": "Criar perfis", "description": "Criar novos perfis."},
    {"name": "perfis.editar", "module": "Perfis", "label": "Editar perfis", "description": "Alterar nome, descrição e permissões de perfis."},
    {"name": "perfis.excluir", "module": "Perfis", "label": "Excluir perfis", "description": "Excluir perfis sem usuários associados."},

    # --- Relatórios ---
    {"name": "relatorios.visualizar", "module": "Relatórios", "label": "Visualizar relatórios", "description": "Acessar dashboard, inventário e relatórios."},
    {"name": "relatorios.exportar", "module": "Relatórios", "label": "Exportar relatórios", "description": "Exportar inventário, movimentações e colaboradores (CSV/Excel)."},

    # --- Auditoria ---
    {"name": "auditoria.visualizar", "module": "Auditoria", "label": "Visualizar auditoria", "description": "Consultar a trilha de auditoria do sistema."},
]

# Perfis padrão (seed idempotente). Cada perfil referencia permissões pelo nome.
DEFAULT_ROLES: List[dict] = [
    {
        "name": "Administrador",
        "description": "Acesso total ao sistema: gerencia usuários, perfis, permissões, auditoria e todos os módulos.",
        "is_system": True,
        "permissions": [p["name"] for p in PERMISSION_CATALOG],
    },
    {
        "name": "Gestor de TI",
        "description": "Visualiza patrimônio, cadastra e edita equipamentos, movimenta, registra manutenção e gera relatórios de TI. Não altera configurações críticas nem permissões.",
        "is_system": True,
        "permissions": [
            "patrimonio.visualizar", "patrimonio.criar", "patrimonio.editar",
            "movimentacao.visualizar", "movimentacao.criar",
            "manutencao.visualizar", "manutencao.criar", "manutencao.editar", "manutencao.finalizar",
            "colaboradores.visualizar", "locais.visualizar",
            "relatorios.visualizar", "relatorios.exportar",
        ],
    },
    {
        "name": "Técnico de TI",
        "description": "Consulta equipamentos, registra manutenção, diagnósticos e peças, e consulta o histórico. Não exclui patrimônio nem administra usuários.",
        "is_system": True,
        "permissions": [
            "patrimonio.visualizar",
            "movimentacao.visualizar",
            "manutencao.visualizar", "manutencao.criar", "manutencao.editar", "manutencao.finalizar",
            "colaboradores.visualizar",
            "relatorios.visualizar",
        ],
    },
    {
        "name": "Patrimônio",
        "description": "Cadastra, edita e movimenta bens, realiza inventário, gera termos e relatórios patrimoniais.",
        "is_system": True,
        "permissions": [
            "patrimonio.visualizar", "patrimonio.criar", "patrimonio.editar",
            "movimentacao.visualizar", "movimentacao.criar",
            "colaboradores.visualizar", "colaboradores.criar", "colaboradores.editar",
            "locais.visualizar",
            "relatorios.visualizar", "relatorios.exportar",
        ],
    },
    {
        "name": "Almoxarifado",
        "description": "Controla estoque, registra entradas e saídas e consulta equipamentos em estoque.",
        "is_system": True,
        "permissions": [
            "patrimonio.visualizar",
            "movimentacao.visualizar", "movimentacao.criar",
            "colaboradores.visualizar", "locais.visualizar",
            "relatorios.visualizar",
        ],
    },
    {
        "name": "Auditor",
        "description": "Somente leitura: visualiza patrimônio, movimentações, histórico, auditoria e gera relatórios. Não altera dados.",
        "is_system": True,
        "permissions": [
            "patrimonio.visualizar",
            "movimentacao.visualizar",
            "manutencao.visualizar",
            "colaboradores.visualizar", "locais.visualizar",
            "relatorios.visualizar", "relatorios.exportar",
            "auditoria.visualizar",
        ],
    },
    {
        "name": "Consulta",
        "description": "Somente leitura dos módulos explicitamente autorizados (acesso mínimo padrão).",
        "is_system": True,
        "permissions": [
            "patrimonio.visualizar",
            "movimentacao.visualizar",
            "manutencao.visualizar",
            "colaboradores.visualizar", "locais.visualizar",
            "relatorios.visualizar",
        ],
    },
]


# ============================================================================
# SEED IDEMPOTENTE
# ============================================================================

def ensure_default_roles(db: Session) -> None:
    """
    Cria (se ainda não existirem) o catálogo de permissões e os perfis
    padrão. É idempotente: não duplica registros e não altera perfis que
    já existam. Também garante que usuários `is_admin` recebam o perfil
    Administrador (compatibilidade com o flag legado).
    """
    # 1. Permissões
    existing = {p.name: p for p in db.query(Permission).all()}
    for item in PERMISSION_CATALOG:
        if item["name"] not in existing:
            perm = Permission(
                name=item["name"],
                module=item["module"],
                label=item["label"],
                description=item["description"],
            )
            db.add(perm)
            existing[item["name"]] = perm
    db.flush()

    # 2. Perfis padrão
    for role_def in DEFAULT_ROLES:
        role = db.query(Role).filter(Role.name == role_def["name"]).first()
        if not role:
            role = Role(
                name=role_def["name"],
                description=role_def["description"],
                is_system=role_def["is_system"],
            )
            db.add(role)
            db.flush()
        # Sincroniza permissões do perfil apenas se ele estiver vazio (recém-criado
        # ou sem permissões), preservando ajustes feitos pelo administrador.
        has_perms = (
            db.query(RolePermission).filter(RolePermission.role_id == role.id).first()
        )
        if not has_perms:
            for perm_name in role_def["permissions"]:
                perm = existing.get(perm_name)
                if perm:
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    db.commit()

    # 3. Usuários legados com is_admin=True recebem o perfil Administrador
    admin_role = db.query(Role).filter(Role.name == "Administrador").first()
    if admin_role:
        for user in db.query(User).filter(User.is_admin == True).all():  # noqa: E712
            already = (
                db.query(UserRole)
                .filter(UserRole.user_id == user.id, UserRole.role_id == admin_role.id)
                .first()
            )
            if not already:
                db.add(UserRole(user_id=user.id, role_id=admin_role.id))
        db.commit()


# ============================================================================
# HELPERS DE CONSULTA
# ============================================================================

def get_user_permission_names(db: Session, user: Optional[User]) -> Set[str]:
    """Permissões efetivas do usuário (união dos perfis). Admin = todas."""
    if user is None:
        return set()
    if user.is_admin:
        return {p["name"] for p in PERMISSION_CATALOG}

    names = set()
    rows = (
        db.query(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id)
        .all()
    )
    names.update(name for (name,) in rows)
    return names


def user_has_permission(db: Session, user: Optional[User], permission: str) -> bool:
    """Verifica se o usuário possui a permissão (deny by default; admin ignora)."""
    if user is None:
        return False
    if user.is_admin:
        return True
    return permission in get_user_permission_names(db, user)


def get_user_role_names(db: Session, user: Optional[User]) -> List[str]:
    """Nomes dos perfis atribuídos ao usuário."""
    if user is None:
        return []
    rows = (
        db.query(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id)
        .order_by(Role.name)
        .all()
    )
    return [name for (name,) in rows]


def get_user_roles(db: Session, user: User) -> List[Role]:
    """Objetos Role atribuídos ao usuário."""
    return (
        db.query(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id)
        .order_by(Role.name)
        .all()
    )


def assign_role(db: Session, user: User, role: Role) -> None:
    """Atribui um perfil a um usuário (idempotente)."""
    exists = (
        db.query(UserRole)
        .filter(UserRole.user_id == user.id, UserRole.role_id == role.id)
        .first()
    )
    if not exists:
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()


def remove_role(db: Session, user: User, role: Role) -> None:
    """Remove um perfil de um usuário."""
    db.query(UserRole).filter(
        UserRole.user_id == user.id, UserRole.role_id == role.id
    ).delete(synchronize_session=False)
    db.commit()


# ============================================================================
# HELPERS DE PERFIS
# ============================================================================

def get_all_roles(db: Session) -> List[Role]:
    return db.query(Role).order_by(Role.name).all()


def get_role_by_name(db: Session, name: str) -> Optional[Role]:
    return db.query(Role).filter(Role.name == name).first()


def get_role_by_id(db: Session, role_id: int) -> Optional[Role]:
    return db.query(Role).filter(Role.id == role_id).first()


def get_role_permission_names(db: Session, role: Role) -> Set[str]:
    rows = (
        db.query(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == role.id)
        .all()
    )
    return {name for (name,) in rows}


def create_role(db: Session, name: str, description: Optional[str] = None) -> Role:
    name = (name or "").strip()
    if not name:
        raise ValueError("O nome do perfil não pode ser vazio.")
    if get_role_by_name(db, name):
        raise ValueError(f"Já existe um perfil com o nome '{name}'.")
    role = Role(name=name, description=description or None, is_system=False)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def update_role(
    db: Session,
    role: Role,
    name: Optional[str] = None,
    description: Optional[str] = None,
    permission_names: Optional[Iterable[str]] = None,
) -> Role:
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("O nome do perfil não pode ser vazio.")
        duplicate = get_role_by_name(db, name)
        if duplicate and duplicate.id != role.id:
            raise ValueError(f"Já existe um perfil com o nome '{name}'.")
        role.name = name
    if description is not None:
        role.description = description or None

    if permission_names is not None:
        wanted = set(permission_names)
        current = {
            rp.permission.name: rp
            for rp in (
                db.query(RolePermission)
                .join(Permission, Permission.id == RolePermission.permission_id)
                .filter(RolePermission.role_id == role.id)
                .all()
            )
        }
        for perm_name in wanted - set(current.keys()):
            perm = db.query(Permission).filter(Permission.name == perm_name).first()
            if perm:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        for perm_name, rp in current.items():
            if perm_name not in wanted:
                db.delete(rp)

    db.commit()
    db.refresh(role)
    return role


def delete_role(db: Session, role: Role) -> None:
    """Exclui um perfil. Perfis de sistema ou com usuários não podem ser excluídos."""
    if role.is_system:
        raise ValueError("Perfis padrão do sistema não podem ser excluídos.")
    assigned = (
        db.query(UserRole).filter(UserRole.role_id == role.id).count()
    )
    if assigned:
        raise ValueError(
            f"O perfil '{role.name}' está atribuído a {assigned} usuário(s); "
            "remova as atribuições antes de excluí-lo."
        )
    db.delete(role)
    db.commit()