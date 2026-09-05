"""
Rotas administrativas da interface web.

- /admin/users*      → gestão de usuários (usuarios.*)
- /admin/roles*      → gestão de perfis e permissões (perfis.*)
- /admin/audit       → trilha de auditoria (auditoria.visualizar)
- /profile/password  → troca de senha (autosserviço)

Todas exigem login (require_web_auth no app) e as permissões específicas
de cada rota (deny by default). As ações são registradas na trilha de
auditoria.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import _client_ip, require_permission
from app.services import permission_service
from app.services.audit_service import (
    ACTION_BLOCK,
    ACTION_UNBLOCK,
    ACTION_CREATE,
    ACTION_PASSWORD_RESET,
    ACTION_PASSWORD_CHANGE,
    ACTION_PROFILE_CHANGE,
    ACTION_ROLE_CREATE,
    ACTION_ROLE_UPDATE,
    ACTION_ROLE_DELETE,
    ACTION_UPDATE,
    RESULT_FAILURE,
    RESULT_SUCCESS,
    get_audit_logs,
    get_distinct_actions,
    get_distinct_modules,
    write_audit,
    write_change_audit,
)
from app.services.auth_service import change_password, create_user, reset_password
from app.web.routes import templates

admin_router = APIRouter(include_in_schema=False)


# ============================================================================
# HELPERS
# ============================================================================

def _user_has_admin_access(db: Session, user: User) -> bool:
    """Usuário é superusuário (is_admin) ou possui o perfil Administrador."""
    if user.is_admin:
        return True
    admin_role = permission_service.get_role_by_name(db, "Administrador")
    if not admin_role:
        return False
    return any(r.id == admin_role.id for r in permission_service.get_user_roles(db, user))


def _count_active_admins(db: Session) -> int:
    active_users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
    return sum(1 for u in active_users if _user_has_admin_access(db, u))


def _guard_remove_admin_access(db: Session, target: User, keeps_admin_access: bool) -> None:
    """
    Impede que o último administrador ativo perca acesso administrativo
    (evita deixar o sistema sem nenhum administrador).
    """
    if keeps_admin_access:
        return
    if _user_has_admin_access(db, target) and _count_active_admins(db) <= 1:
        raise ValueError("Não é possível remover o último administrador ativo do sistema.")


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user


def _permissions_grouped(db: Session, checked: Optional[set] = None) -> List[dict]:
    """Permissões agrupadas por módulo para a interface de perfis."""
    checked = checked or set()
    modules = []
    by_module = {}
    for perm in db.query(permission_service.Permission).order_by(permission_service.Permission.name).all():
        by_module.setdefault(perm.module, []).append(
            {"id": perm.id, "name": perm.name, "label": perm.label, "checked": perm.name in checked}
        )
    for module in sorted(by_module):
        modules.append({"module": module, "permissions": by_module[module]})
    return modules


# ============================================================================
# PÁGINA INICIAL DA ADMINISTRAÇÃO
# ============================================================================

@admin_router.get("/admin")
def admin_index(request: Request, db: Session = Depends(get_db)):
    perms = permission_service.get_user_permission_names(db, request.state.user)
    for path, perm in (("/admin/users", "usuarios.visualizar"),
                       ("/admin/roles", "perfis.visualizar"),
                       ("/admin/audit", "auditoria.visualizar")):
        if perm in perms:
            return RedirectResponse(url=path, status_code=303)
    raise HTTPException(status_code=403, detail="Acesso administrativo não autorizado")


# ============================================================================
# USUÁRIOS
# ============================================================================

@admin_router.get("/admin/users", response_class=HTMLResponse, dependencies=[Depends(require_permission("usuarios.visualizar"))])
def admin_list_users(
    request: Request,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            (User.username.ilike(term))
            | (User.full_name.ilike(term))
            | (User.email.ilike(term))
        )
    if status_filter == "active":
        query = query.filter(User.is_active == True)  # noqa: E712
    elif status_filter == "inactive":
        query = query.filter(User.is_active == False)  # noqa: E712

    users = query.order_by(User.username).all()
    for u in users:
        u.role_names = permission_service.get_user_role_names(db, u)

    return templates.TemplateResponse(
        request=request,
        name="admin/users/list.html",
        context={
            "users": users,
            "search": search or "",
            "status_filter": status_filter or "",
            "active_tab": "admin",
        },
    )


@admin_router.get("/admin/users/new", response_class=HTMLResponse, dependencies=[Depends(require_permission("usuarios.criar"))])
def admin_form_new_user(request: Request, error: Optional[str] = None, db: Session = Depends(get_db)):
    roles = permission_service.get_all_roles(db)
    return templates.TemplateResponse(
        request=request,
        name="admin/users/new.html",
        context={"roles": roles, "error": error or "", "active_tab": "admin"},
    )


@admin_router.post("/admin/users/new", response_class=HTMLResponse, dependencies=[Depends(require_permission("usuarios.criar"))])
def admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    role_ids: List[int] = Form([]),
    db: Session = Depends(get_db),
):
    try:
        user = create_user(
            db,
            username=username,
            password=password,
            full_name=full_name or None,
            email=email or None,
            is_admin=False,
        )
    except ValueError as err:
        return RedirectResponse(url=f"/admin/users/new?error={_quote(str(err))}", status_code=303)

    assigned_names = []
    for role_id in role_ids:
        role = permission_service.get_role_by_id(db, role_id)
        if role:
            permission_service.assign_role(db, user, role)
            assigned_names.append(role.name)

    write_audit(
        db,
        user=request.state.user,
        action=ACTION_CREATE,
        module="Usuários",
        resource="User",
        resource_ref=user.username,
        resource_id=user.id,
        ip_address=_client_ip(request),
        new_data={"username": user.username, "full_name": user.full_name, "email": user.email, "perfis": assigned_names},
        description=f"Criação do usuário {user.username}",
    )
    return RedirectResponse(url=f"/admin/users/{user.id}/edit?created=true", status_code=303)


@admin_router.get("/admin/users/{user_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_permission("usuarios.editar"))])
def admin_edit_user(request: Request, user_id: int, error: Optional[str] = None, success: Optional[str] = None, db: Session = Depends(get_db)):
    user = _get_user_or_404(db, user_id)
    roles = permission_service.get_all_roles(db)
    user_role_ids = {r.id for r in permission_service.get_user_roles(db, user)}
    return templates.TemplateResponse(
        request=request,
        name="admin/users/edit.html",
        context={
            "user": user,
            "roles": roles,
            "user_role_ids": user_role_ids,
            "now": datetime.utcnow(),
            "error": error or "",
            "success": success or "",
            "active_tab": "admin",
        },
    )


@admin_router.post("/admin/users/{user_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_permission("usuarios.editar"))])
def admin_update_user(
    request: Request,
    user_id: int,
    full_name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    is_active: bool = Form(False),
    role_ids: List[int] = Form([]),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    actor = request.state.user

    before_roles = set(permission_service.get_user_role_names(db, user))
    before = {"full_name": user.full_name, "email": user.email, "is_active": user.is_active, "perfis": sorted(before_roles)}

    # Guarda: o próprio usuário não pode se desativar
    if user.id == actor.id and not is_active and user.is_active:
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error={_quote('Você não pode desativar a si mesmo.')}", status_code=303)

    # Guarda: não remover o último administrador ativo (perfil Administrador
    # ou is_admin removidos, ou desativação da conta)
    new_role_names = {
        permission_service.get_role_by_id(db, rid).name
        for rid in role_ids
        if permission_service.get_role_by_id(db, rid)
    }
    keeps_admin = ("Administrador" in new_role_names) or user.is_admin
    removes_admin = _user_has_admin_access(db, user) and not keeps_admin
    deactivates = user.is_active and not is_active
    if (removes_admin or deactivates) and _count_active_admins(db) <= 1:
        return RedirectResponse(
            url=f"/admin/users/{user_id}/edit?error={_quote('Não é possível remover o último administrador ativo do sistema.')}",
            status_code=303,
        )

    user.full_name = full_name or None
    user.email = email or None
    user.is_active = is_active

    # Sincroniza perfis
    current_roles = {r.id: r for r in permission_service.get_user_roles(db, user)}
    for role_id in role_ids:
        if role_id not in current_roles:
            role = permission_service.get_role_by_id(db, role_id)
            if role:
                permission_service.assign_role(db, user, role)
    for role_id, role in current_roles.items():
        if role_id not in role_ids:
            permission_service.remove_role(db, user, role)

    db.commit()
    db.refresh(user)

    after_roles = set(permission_service.get_user_role_names(db, user))
    after = {"full_name": user.full_name, "email": user.email, "is_active": user.is_active, "perfis": sorted(after_roles)}
    write_change_audit(
        db,
        user=actor,
        action=ACTION_UPDATE,
        module="Usuários",
        resource="User",
        resource_ref=user.username,
        resource_id=user.id,
        ip_address=_client_ip(request),
        before=before,
        after=after,
        description=f"Edição do usuário {user.username}",
    )
    if before_roles != after_roles:
        write_audit(
            db,
            user=actor,
            action=ACTION_PROFILE_CHANGE,
            module="Usuários",
            resource="User",
            resource_ref=user.username,
            resource_id=user.id,
            ip_address=_client_ip(request),
            previous_data={"perfis": sorted(before_roles)},
            new_data={"perfis": sorted(after_roles)},
            description=f"Alteração de perfis do usuário {user.username}",
        )
    return RedirectResponse(url=f"/admin/users/{user_id}/edit?success={_quote('Usuário atualizado com sucesso.')}", status_code=303)


@admin_router.post("/admin/users/{user_id}/toggle-active", dependencies=[Depends(require_permission("usuarios.bloquear"))])
def admin_toggle_user_active(
    request: Request,
    user_id: int,
    action: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    actor = request.state.user

    if action == "block":
        if user.id == actor.id:
            return RedirectResponse(url=f"/admin/users/{user_id}/edit?error={_quote('Você não pode bloquear a si mesmo.')}", status_code=303)
        try:
            _guard_remove_admin_access(db, user, keeps_admin_access=False)
        except ValueError as err:
            return RedirectResponse(url=f"/admin/users/{user_id}/edit?error={_quote(str(err))}", status_code=303)
        user.is_active = False
        db.commit()
        write_audit(
            db, user=actor, action=ACTION_BLOCK, module="Usuários", resource="User",
            resource_ref=user.username, resource_id=user.id, ip_address=_client_ip(request),
            description=f"Bloqueio do usuário {user.username}",
        )
        msg = "Usuário bloqueado. Sessões ativas foram invalidadas."
    else:  # unblock
        user.is_active = True
        db.commit()
        write_audit(
            db, user=actor, action=ACTION_UNBLOCK, module="Usuários", resource="User",
            resource_ref=user.username, resource_id=user.id, ip_address=_client_ip(request),
            description=f"Desbloqueio do usuário {user.username}",
        )
        msg = "Usuário desbloqueado."
    return RedirectResponse(url=f"/admin/users/{user_id}/edit?success={_quote(msg)}", status_code=303)


@admin_router.post("/admin/users/{user_id}/reset-password", dependencies=[Depends(require_permission("usuarios.editar"))])
def admin_reset_password(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    try:
        reset_password(db, user, new_password)
    except ValueError as err:
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error={_quote(str(err))}", status_code=303)
    write_audit(
        db,
        user=request.state.user,
        action=ACTION_PASSWORD_RESET,
        module="Usuários",
        resource="User",
        resource_ref=user.username,
        resource_id=user.id,
        ip_address=_client_ip(request),
        description=f"Redefinição de senha do usuário {user.username} (sessões invalidadas)",
    )
    return RedirectResponse(
        url=f"/admin/users/{user_id}/edit?success={_quote('Senha redefinida. O usuário deverá efetuar novo login.')}",
        status_code=303,
    )


# ============================================================================
# PERFIS (ROLES)
# ============================================================================

@admin_router.get("/admin/roles", response_class=HTMLResponse, dependencies=[Depends(require_permission("perfis.visualizar"))])
def admin_list_roles(request: Request, db: Session = Depends(get_db)):
    roles = permission_service.get_all_roles(db)
    for role in roles:
        role.permission_names = sorted(permission_service.get_role_permission_names(db, role))
        role.users_count = db.query(permission_service.UserRole).filter(permission_service.UserRole.role_id == role.id).count()
    return templates.TemplateResponse(
        request=request,
        name="admin/roles/list.html",
        context={"roles": roles, "active_tab": "admin"},
    )


@admin_router.get("/admin/roles/new", response_class=HTMLResponse, dependencies=[Depends(require_permission("perfis.criar"))])
def admin_form_new_role(request: Request, error: Optional[str] = None, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="admin/roles/form.html",
        context={
            "role": None,
            "grouped_permissions": _permissions_grouped(db),
            "error": error or "",
            "active_tab": "admin",
        },
    )


@admin_router.post("/admin/roles/new", response_class=HTMLResponse, dependencies=[Depends(require_permission("perfis.criar"))])
def admin_create_role(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    permission_names: List[str] = Form([]),
    db: Session = Depends(get_db),
):
    try:
        role = permission_service.create_role(db, name, description or None)
    except ValueError as err:
        return RedirectResponse(url=f"/admin/roles/new?error={_quote(str(err))}", status_code=303)
    permission_service.update_role(db, role, permission_names=permission_names)
    write_audit(
        db,
        user=request.state.user,
        action=ACTION_ROLE_CREATE,
        module="Perfis",
        resource="Role",
        resource_ref=role.name,
        resource_id=role.id,
        ip_address=_client_ip(request),
        new_data={"name": role.name, "permissions": sorted(permission_names)},
        description=f"Criação do perfil {role.name}",
    )
    return RedirectResponse(url=f"/admin/roles/{role.id}/edit?created=true", status_code=303)


@admin_router.get("/admin/roles/{role_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_permission("perfis.editar"))])
def admin_edit_role(request: Request, role_id: int, error: Optional[str] = None, success: Optional[str] = None, db: Session = Depends(get_db)):
    role = permission_service.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    current = permission_service.get_role_permission_names(db, role)
    return templates.TemplateResponse(
        request=request,
        name="admin/roles/form.html",
        context={
            "role": role,
            "grouped_permissions": _permissions_grouped(db, current),
            "error": error or "",
            "success": success or "",
            "active_tab": "admin",
        },
    )


@admin_router.post("/admin/roles/{role_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_permission("perfis.editar"))])
def admin_update_role(
    request: Request,
    role_id: int,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    permission_names: List[str] = Form([]),
    db: Session = Depends(get_db),
):
    role = permission_service.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    before = {
        "name": role.name,
        "description": role.description,
        "permissions": sorted(permission_service.get_role_permission_names(db, role)),
    }
    try:
        permission_service.update_role(db, role, name=name, description=description or None, permission_names=permission_names)
    except ValueError as err:
        return RedirectResponse(url=f"/admin/roles/{role_id}/edit?error={_quote(str(err))}", status_code=303)
    after = {
        "name": role.name,
        "description": role.description,
        "permissions": sorted(permission_service.get_role_permission_names(db, role)),
    }
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_ROLE_UPDATE,
        module="Perfis",
        resource="Role",
        resource_ref=role.name,
        resource_id=role.id,
        ip_address=_client_ip(request),
        before=before,
        after=after,
        description=f"Alteração do perfil {role.name} (permissões e/ou dados)",
    )
    return RedirectResponse(url=f"/admin/roles/{role_id}/edit?success={_quote('Perfil atualizado com sucesso.')}", status_code=303)


@admin_router.post("/admin/roles/{role_id}/delete", dependencies=[Depends(require_permission("perfis.excluir"))])
def admin_delete_role(request: Request, role_id: int, db: Session = Depends(get_db)):
    role = permission_service.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    name = role.name
    try:
        permission_service.delete_role(db, role)
    except ValueError as err:
        return RedirectResponse(url=f"/admin/roles?error={_quote(str(err))}", status_code=303)
    write_audit(
        db,
        user=request.state.user,
        action=ACTION_ROLE_DELETE,
        module="Perfis",
        resource="Role",
        resource_ref=name,
        resource_id=role_id,
        ip_address=_client_ip(request),
        description=f"Exclusão do perfil {name}",
    )
    return RedirectResponse(url="/admin/roles?success=1", status_code=303)


# ============================================================================
# AUDITORIA
# ============================================================================

@admin_router.get("/admin/audit", response_class=HTMLResponse, dependencies=[Depends(require_permission("auditoria.visualizar"))])
def admin_audit_log(
    request: Request,
    search: Optional[str] = None,
    module: Optional[str] = None,
    action: Optional[str] = None,
    result: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    logs = get_audit_logs(
        db,
        search=search,
        module=module or None,
        action=action or None,
        result=result or None,
        limit=min(limit, 1000),
    )
    return templates.TemplateResponse(
        request=request,
        name="admin/audit/list.html",
        context={
            "logs": logs,
            "search": search or "",
            "selected_module": module or "",
            "selected_action": action or "",
            "selected_result": result or "",
            "modules": get_distinct_modules(db),
            "actions": get_distinct_actions(db),
            "active_tab": "admin",
        },
    )


# ============================================================================
# PERFIL DO USUÁRIO (TROCA DE SENHA)
# ============================================================================

@admin_router.get("/profile/password", response_class=HTMLResponse)
def profile_change_password_page(request: Request, error: Optional[str] = None, success: Optional[str] = None):
    return templates.TemplateResponse(
        request=request,
        name="profile/password.html",
        context={"error": error or "", "success": success or "", "active_tab": ""},
    )


@admin_router.post("/profile/password", response_class=HTMLResponse)
def profile_change_password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = request.state.user
    if new_password != confirm_password:
        return RedirectResponse(url="/profile/password?error=" + _quote("A confirmação da nova senha não confere."), status_code=303)
    try:
        change_password(db, user, current_password, new_password)
    except ValueError as err:
        return RedirectResponse(url="/profile/password?error=" + _quote(str(err)), status_code=303)
    write_audit(
        db,
        user=user,
        action=ACTION_PASSWORD_CHANGE,
        module="Perfil",
        resource="User",
        resource_ref=user.username,
        resource_id=user.id,
        ip_address=_client_ip(request),
        description=f"Troca de senha do próprio usuário {user.username} (sessões anteriores invalidadas)",
    )
    # A troca de senha invalida a sessão atual → novo login é obrigatório
    return RedirectResponse(url="/login", status_code=303)


def _quote(value: str) -> str:
    """Percent-encode seguro para parâmetros de URL."""
    from urllib.parse import quote
    return quote(value, safe="")