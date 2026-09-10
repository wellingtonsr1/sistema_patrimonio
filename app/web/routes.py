from typing import Optional
from datetime import datetime
import logging
from urllib.parse import quote
from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.config import APP_NAME, APP_VERSION, COMPANY_NAME, COMPANY_CNPJ, COMPANY_ADDRESS, AUTH_COOKIE_NAME
from app.models.enums import AssetStatus, AssetCondition, AssetCategory, MovementType, MaintenanceType, MaintenanceStatus
from app.schemas.asset import AssetCreate, AssetUpdate
from app.schemas.movement import MovementCreate, MovementFilter
from app.schemas.custodian import CustodianCreate, CustodianUpdate
from app.schemas.location import LocationCreate
from app.schemas.maintenance import MaintenanceCreate, MaintenanceUpdate
from app.services.asset_service import AssetService
from app.services.movement_service import MovementService
from app.services.import_service import parse_csv, preview_import, execute_import
from app.services.custodian_import_service import parse_custodian_csv, preview_custodian_import, execute_custodian_import
from app.services.location_import_service import parse_locations_csv, preview_locations_import, execute_locations_import
from app.services.custodian_service import CustodianService
from app.services.location_service import LocationService
from app.services.maintenance_service import MaintenanceService
from app.services.dashboard_service import DashboardService
from app.services.report_service import ReportService
from app.api.deps import _client_ip, get_current_user, require_permission
from app.config import AUTH_ADMIN_PASSWORD
from app.models.user import User
from app.models.user_role import UserRole
from app.services.auth_provider import resolve_authentication
from app.services.auth_service import AccountLockedError, create_user
from app.services.permission_service import (
    ensure_default_roles,
    get_role_by_name,
    assign_role,
)
from app.services.ad_service import (
    ADAuthenticationError,
    ADNoProfileError,
    ADUnavailableError,
)
from app.services.permission_service import get_user_permission_names, get_user_role_names
from app.services.audit_service import (
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_MOVEMENT,
    ACTION_MAINTENANCE,
    ACTION_IMPORT,
    ACTION_LOGIN,
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_LOCKED,
    ACTION_LOGOUT,
    RESULT_SUCCESS,
    RESULT_FAILURE,
    RESULT_LOCKED,
    write_audit,
    write_change_audit,
)
from app.services.session_service import (
    create_session,
    revoke_session,
    set_session_cookie,
    clear_session_cookie,
)

# Configuração do Jinja2 Templates
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _inject_current_user(request: Request) -> dict:
    """
    Disponibiliza o usuário autenticado, seus perfis e suas permissões para
    todos os templates (menu dinâmico, botões condicionais via `can()`).

    As permissões/perfis são pré-computados pelas dependências de auth
    (request.state._permissions/_roles). O fallback abre uma sessão própria
    apenas se ainda não houver cache (defensivo, com tolerância a falhas).
    """
    user = getattr(request.state, "user", None)
    permissions = set(getattr(request.state, "_permissions", None) or set())
    roles = list(getattr(request.state, "_roles", None) or [])
    if user is not None and not getattr(request.state, "_permissions", None):
        try:
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                permissions = get_user_permission_names(db, user)
                roles = get_user_role_names(db, user)
            finally:
                db.close()
        except Exception:
            permissions, roles = set(), []
    return {
        "current_user": user,
        "user_permissions": permissions,
        "user_roles": roles,
        "can": lambda perm: perm in permissions,
    }


templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
    context_processors=[_inject_current_user],
)

logger = logging.getLogger("sispatrimonio.web")

# Injeta variáveis globais nos templates
templates.env.globals["app_name"] = APP_NAME
templates.env.globals["app_version"] = APP_VERSION
templates.env.globals["company_name"] = COMPANY_NAME
templates.env.globals["current_year"] = datetime.now().year

web_router = APIRouter(include_in_schema=False)


# ==========================================
# AUTENTICAÇÃO (páginas de login/logout)
# ==========================================
def _safe_next_url(value: str) -> str:
    """Permite apenas redirecionamentos internos (evita open redirect)."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


@web_router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "", db: Session = Depends(get_db)):
    """Exibe a tela de login. Se já autenticado, redireciona para a home."""
    if get_current_user(request, db):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"next": next, "error": ""},
    )


@web_router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
    db: Session = Depends(get_db),
):
    """Processa o login via formulário e estabelece a sessão."""
    ip = _client_ip(request)
    ad_error_message = None
    try:
        user = resolve_authentication(db, username, password)
    except (ADUnavailableError, ADAuthenticationError, ADNoProfileError) as ad_exc:
        # Erros específicos da integração AD: mensagem clara e genérica ao
        # usuário; detalhes técnicos ficam apenas no log do servidor.
        user = None
        ad_error_message = str(ad_exc)
        logger.warning("Falha de login AD para '%s': %s", username, type(ad_exc).__name__)
    except AccountLockedError:
        write_audit(
            db,
            user=None,
            username=username,
            action=ACTION_LOGIN_LOCKED,
            module="Autenticação",
            resource="Login",
            resource_ref=username,
            ip_address=ip,
            result=RESULT_LOCKED,
            description="Login bloqueado por excesso de tentativas",
        )
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "next": next,
                "error": "Conta temporariamente bloqueada por excesso de tentativas de login. Tente novamente mais tarde.",
            },
        )

    if not user:
        if ad_error_message:
            # Falha específica do AD (indisponibilidade, credencial ou perfil):
            # mensagem já amigável; a auditoria específica foi registrada no
            # serviço da integração. Não duplica LOGIN_FALHA local.
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"next": next, "error": ad_error_message},
            )
        write_audit(
            db,
            user=None,
            username=username,
            action=ACTION_LOGIN_FAILED,
            module="Autenticação",
            resource="Login",
            resource_ref=username,
            ip_address=ip,
            result=RESULT_FAILURE,
            description="Tentativa de login com credenciais inválidas",
        )
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"next": next, "error": "Usuário ou senha inválidos"},
        )

    write_audit(
        db,
        user=user,
        action=ACTION_LOGIN,
        module="Autenticação",
        resource="Login",
        resource_ref=user.username,
        ip_address=ip,
        result=RESULT_SUCCESS,
        description="Login realizado com sucesso",
    )

    token = create_session(db, user.id)
    response = RedirectResponse(
        url=_safe_next_url(next), status_code=status.HTTP_303_SEE_OTHER
    )
    set_session_cookie(response, token)
    return response


@web_router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """Revoga a sessão no servidor e remove o cookie."""
    user = get_current_user(request, db)
    write_audit(
        db,
        user=user,
        action=ACTION_LOGOUT,
        module="Autenticação",
        resource="Logout",
        resource_ref=user.username if user else None,
        ip_address=_client_ip(request),
        result=RESULT_SUCCESS,
        description="Logout realizado",
    )
    token = request.cookies.get(AUTH_COOKIE_NAME)
    revoke_session(db, token)
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookie(response)
    return response


# ==========================================
# DASHBOARD
# ==========================================
@web_router.get("/", response_class=HTMLResponse)
def view_dashboard(request: Request, db: Session = Depends(get_db)):
    stats = DashboardService.get_stats(db)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"stats": stats, "active_tab": "dashboard"}
    )


# ==========================================
# BENS / EQUIPAMENTOS (ASSETS)
# ==========================================
def _asset_audit_snapshot(asset) -> dict:
    """Snapshot serializável de um bem para a trilha de auditoria."""
    data = {
        "tag": asset.tag, "name": asset.name, "brand": asset.brand, "model": asset.model,
        "serial_number": asset.serial_number, "purchase_value": asset.purchase_value,
        "invoice_number": asset.invoice_number, "supplier": asset.supplier,
        "location_id": asset.location_id, "custodian_id": asset.custodian_id, "notes": asset.notes,
    }
    if asset.category is not None:
        data["category"] = asset.category.value
    if asset.condition is not None:
        data["condition"] = asset.condition.value
    if asset.status is not None:
        data["status"] = asset.status.value
    return data


@web_router.get("/assets", response_class=HTMLResponse, dependencies=[Depends(require_permission("patrimonio.visualizar"))])
def list_assets(
    request: Request,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    location_id: Optional[int] = None,
    custodian_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    status_enum = AssetStatus(status_filter) if status_filter and status_filter in [e.value for e in AssetStatus] else None
    cat_enum = AssetCategory(category_filter) if category_filter and category_filter in [e.value for e in AssetCategory] else None

    assets, total = AssetService.get_all(
        db, search=search, status=status_enum, category=cat_enum,
        location_id=location_id, custodian_id=custodian_id, limit=200
    )
    locations = LocationService.get_all(db)
    custodians = CustodianService.get_all(db, active_only=True)

    return templates.TemplateResponse(
        request=request,
        name="assets/list.html",
        context={
            "assets": assets,
            "total": total,
            "search": search or "",
            "selected_status": status_filter or "",
            "selected_category": category_filter or "",
            "selected_location": location_id or "",
            "selected_custodian": custodian_id or "",
            "locations": locations,
            "custodians": custodians,
            "categories": AssetCategory,
            "statuses": AssetStatus,
            "active_tab": "assets"
        }
    )


@web_router.get("/assets/import", response_class=HTMLResponse, dependencies=[Depends(require_permission("patrimonio.criar"))])
def form_import_assets(request: Request):
    """Exibe o formulário de importação CSV"""
    return templates.TemplateResponse(
        request=request,
        name="assets/import.html",
        context={"active_tab": "assets"}
    )


@web_router.post("/assets/import", response_class=HTMLResponse, dependencies=[Depends(require_permission("patrimonio.criar"))])
def process_import_assets(
    request: Request,
    file: UploadFile = File(...),
    skip_duplicates: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Processa o upload e exibe pré-visualização da importação"""
    if not file.filename or not file.filename.endswith(".csv"):
        return templates.TemplateResponse(
            request=request,
            name="assets/import.html",
            context={
                "active_tab": "assets",
                "error": "Arquivo inválido. Envie um arquivo .csv",
            }
        )

    content = file.file.read().decode("utf-8-sig")
    rows, parse_errors = parse_csv(content)

    if not rows and parse_errors:
        return templates.TemplateResponse(
            request=request,
            name="assets/import.html",
            context={
                "active_tab": "assets",
                "error": "Erros ao ler o arquivo CSV:",
                "parse_errors": parse_errors,
            }
        )

    preview = preview_import(rows, db)

    return templates.TemplateResponse(
        request=request,
        name="assets/import.html",
        context={
            "active_tab": "assets",
            "show_preview": True,
            "preview": preview,
            "csv_rows": rows,
            "parse_errors": parse_errors,
            "skip_duplicates": skip_duplicates,
            "filename": file.filename,
        }
    )


@web_router.post("/assets/import/confirm", dependencies=[Depends(require_permission("patrimonio.criar"))])
def confirm_import_assets(
    request: Request,
    csv_data: str = Form(...),
    skip_duplicates: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Confirma e executa a importação"""
    import json
    import html as html_mod
    try:
        # Decodifica entidades HTML que o textarea pode ter inserido
        decoded = html_mod.unescape(csv_data)
        rows = json.loads(decoded)
        if not isinstance(rows, list):
            raise ValueError("Dados inválidos: esperado uma lista de registros")
    except (json.JSONDecodeError, ValueError) as e:
        return templates.TemplateResponse(
            request=request,
            name="assets/import.html",
            context={
                "active_tab": "assets",
                "show_result": True,
                "result": {
                    "imported": 0,
                    "skipped": 0,
                    "errors": [f"Erro ao processar dados: {str(e)}"],
                    "total_processed": 0,
                },
            }
        )

    try:
        result = execute_import(rows, db, skip_duplicates=skip_duplicates)
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="assets/import.html",
            context={
                "active_tab": "assets",
                "show_result": True,
                "result": {
                    "imported": 0,
                    "skipped": 0,
                    "errors": [f"Erro na importação: {str(e)}"],
                    "total_processed": 0,
                },
            }
        )

    write_audit(
        db,
        user=request.state.user,
        action=ACTION_IMPORT,
        module="Patrimônio",
        resource="Asset",
        resource_ref="importacao-csv",
        ip_address=_client_ip(request),
        description=f"Importação CSV de bens: {result.get('imported', 0)} importados, "
                    f"{result.get('skipped', 0)} ignorados, {len(result.get('errors', []))} erros",
        new_data={"imported": result.get("imported", 0), "skipped": result.get("skipped", 0)},
    )

    return templates.TemplateResponse(
        request=request,
        name="assets/import.html",
        context={
            "active_tab": "assets",
            "show_result": True,
            "result": result,
        }
    )


@web_router.get("/assets/new", response_class=HTMLResponse, dependencies=[Depends(require_permission("patrimonio.criar"))])
def form_new_asset(request: Request, error: Optional[str] = None, db: Session = Depends(get_db)):
    locations = LocationService.get_all(db)
    custodians = CustodianService.get_all(db, active_only=True)
    return templates.TemplateResponse(
        request=request,
        name="assets/form.html",
        context={
            "locations": locations,
            "custodians": custodians,
            "categories": AssetCategory,
            "conditions": AssetCondition,
            "error": error or "",
            "active_tab": "assets"
        }
    )


@web_router.post("/assets/new", dependencies=[Depends(require_permission("patrimonio.criar"))])
def create_asset_form(
    request: Request,
    tag: str = Form(...),
    name: str = Form(...),
    category: str = Form(...),
    brand: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    serial_number: Optional[str] = Form(None),
    specifications: Optional[str] = Form(None),
    purchase_date: Optional[str] = Form(None),
    purchase_value: float = Form(0.0),
    invoice_number: Optional[str] = Form(None),
    supplier: Optional[str] = Form(None),
    warranty_expiry: Optional[str] = Form(None),
    condition: str = Form(AssetCondition.NEW.value),
    location_id: Optional[int] = Form(None),
    custodian_id: Optional[int] = Form(None),
    operator_name: str = Form("Operador"),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    dt_purchase = datetime.strptime(purchase_date, "%Y-%m-%d") if purchase_date else None
    dt_warranty = datetime.strptime(warranty_expiry, "%Y-%m-%d") if warranty_expiry else None

    create_data = AssetCreate(
        tag=tag,
        name=name,
        category=AssetCategory(category),
        brand=brand or None,
        model=model or None,
        serial_number=serial_number or None,
        specifications=specifications or None,
        purchase_date=dt_purchase,
        purchase_value=purchase_value,
        invoice_number=invoice_number or None,
        supplier=supplier or None,
        warranty_expiry=dt_warranty,
        condition=AssetCondition(condition),
        initial_location_id=location_id if location_id and location_id > 0 else None,
        initial_custodian_id=custodian_id if custodian_id and custodian_id > 0 else None,
        initial_operator=operator_name,
        notes=notes or None
    )

    try:
        asset = AssetService.create(db, create_data)
    except ValueError as err:
        return RedirectResponse(url=f"/assets/new?error={quote(str(err))}", status_code=status.HTTP_303_SEE_OTHER)
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_CREATE,
        module="Patrimônio",
        resource="Asset",
        resource_ref=asset.tag,
        resource_id=asset.id,
        ip_address=_client_ip(request),
        after=_asset_audit_snapshot(asset),
        description=f"Cadastro do bem {asset.tag} - {asset.name}",
    )
    return RedirectResponse(url=f"/assets/{asset.id}?created=true", status_code=status.HTTP_303_SEE_OTHER)


@web_router.get("/assets/{asset_id}", response_class=HTMLResponse, dependencies=[Depends(require_permission("patrimonio.visualizar"))])
def view_asset_detail(request: Request, asset_id: int, db: Session = Depends(get_db)):
    asset = AssetService.get_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    timeline = MovementService.get_timeline_for_asset(db, asset_id)
    deprec = AssetService.calculate_depreciation(asset)

    return templates.TemplateResponse(
        request=request,
        name="assets/detail.html",
        context={
            "asset": asset,
            "timeline": timeline,
            "depreciation": deprec,
            "active_tab": "assets"
        }
    )


# ==========================================
# FLUXO DE MOVIMENTAÇÃO (MOVEMENTS)
# ==========================================
@web_router.get("/movements", response_class=HTMLResponse, dependencies=[Depends(require_permission("movimentacao.visualizar"))])
def list_movements_view(
    request: Request,
    movement_type: Optional[str] = None,
    asset_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    m_type_enum = MovementType(movement_type) if movement_type and movement_type in [e.value for e in MovementType] else None
    filters = MovementFilter(movement_type=m_type_enum, asset_id=asset_id)
    movements, total = MovementService.get_all_movements(db, filters=filters, limit=200)

    return templates.TemplateResponse(
        request=request,
        name="movements/list.html",
        context={
            "movements": movements,
            "total": total,
            "selected_type": movement_type or "",
            "movement_types": MovementType,
            "active_tab": "movements"
        }
    )


@web_router.get("/movements/new", response_class=HTMLResponse, dependencies=[Depends(require_permission("movimentacao.criar"))])
def form_new_movement(
    request: Request,
    asset_id: Optional[int] = None,
    m_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    assets, _ = AssetService.get_all(db, limit=500)
    # Filtra apenas ativos não baixados para nova movimentação
    active_assets = [a for a in assets if a.status != AssetStatus.WRITTEN_OFF]
    locations = LocationService.get_all(db)
    custodians = CustodianService.get_all(db, active_only=True)

    selected_asset = AssetService.get_by_id(db, asset_id) if asset_id else None

    return templates.TemplateResponse(
        request=request,
        name="movements/new.html",
        context={
            "assets": active_assets,
            "selected_asset": selected_asset,
            "locations": locations,
            "custodians": custodians,
            "movement_types": MovementType,
            "conditions": AssetCondition,
            "prefill_type": m_type or "",
            "active_tab": "movements"
        }
    )


@web_router.post("/movements/new", dependencies=[Depends(require_permission("movimentacao.criar"))])
def create_movement_form(
    request: Request,
    asset_id: int = Form(...),
    movement_type: str = Form(...),
    destination_location_id: Optional[int] = Form(None),
    destination_custodian_id: Optional[int] = Form(None),
    new_condition: Optional[str] = Form(None),
    reason: str = Form(...),
    operator_name: str = Form("Operador"),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    cond_enum = AssetCondition(new_condition) if new_condition and new_condition in [e.value for e in AssetCondition] else None

    movement_data = MovementCreate(
        asset_id=asset_id,
        movement_type=MovementType(movement_type),
        destination_location_id=destination_location_id if destination_location_id and destination_location_id > 0 else None,
        destination_custodian_id=destination_custodian_id if destination_custodian_id and destination_custodian_id > 0 else None,
        new_condition=cond_enum,
        reason=reason,
        operator_name=operator_name,
        notes=notes or None,
        generate_term=True
    )

    try:
        movement = MovementService.create_movement(db, movement_data)
    except ValueError as err:
        return RedirectResponse(url=f"/movements/new?asset_id={asset_id}&error={quote(str(err))}", status_code=status.HTTP_303_SEE_OTHER)

    asset_tag = movement.asset.tag if movement.asset else None
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_MOVEMENT,
        module="Movimentação",
        resource="Movement",
        resource_ref=asset_tag,
        resource_id=movement.id,
        ip_address=_client_ip(request),
        before={
            "status": movement.previous_status.value if movement.previous_status else None,
            "condition": movement.previous_condition.value if movement.previous_condition else None,
        },
        after={
            "status": movement.new_status.value,
            "condition": movement.new_condition.value if movement.new_condition else None,
            "tipo": movement.movement_type.value,
            "motivo": movement.reason,
            "termo": movement.term_code,
        },
        description=f"Movimentação {movement.movement_type.value} do bem {asset_tag or movement.asset_id}",
    )

    # Se for alocação ou devolução, redireciona para o termo gerado
    if movement.movement_type in [MovementType.ALLOCATION, MovementType.RETURN_STOCK]:
        return RedirectResponse(url=f"/movements/{movement.id}/term", status_code=status.HTTP_303_SEE_OTHER)

    return RedirectResponse(url=f"/assets/{asset_id}?moved=true", status_code=status.HTTP_303_SEE_OTHER)


@web_router.get("/movements/{movement_id}/term", response_class=HTMLResponse, dependencies=[Depends(require_permission("movimentacao.visualizar"))])
def view_movement_term(request: Request, movement_id: int, db: Session = Depends(get_db)):
    """Renderiza a página para visualização e impressão do Termo de Responsabilidade/Cautela"""
    term_data = MovementService.get_term_details(db, movement_id)
    if not term_data:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada")

    return templates.TemplateResponse(
        request=request,
        name="movements/term.html",
        context={
            "term": term_data,
            "movement_id": movement_id
        }
    )


# ==========================================
# COLABORADORES (CUSTODIANS)
# ==========================================
def _custodian_audit_snapshot(c) -> dict:
    return {
        "registration_code": c.registration_code,
        "name": c.name,
        "email": c.email,
        "cpf": c.cpf,
        "role": c.role,
        "department": c.department,
        "is_active": c.is_active,
    }


@web_router.get("/custodians", response_class=HTMLResponse, dependencies=[Depends(require_permission("colaboradores.visualizar"))])
def list_custodians_view(request: Request, db: Session = Depends(get_db)):
    custodians = CustodianService.get_all(db)
    for c in custodians:
        c.active_assets_count = CustodianService.count_assigned_assets(db, c.id)

    return templates.TemplateResponse(
        request=request,
        name="custodians/list.html",
        context={"custodians": custodians, "active_tab": "custodians"}
    )


@web_router.get("/custodians/new", response_class=HTMLResponse, dependencies=[Depends(require_permission("colaboradores.criar"))])
def form_new_custodian(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        request=request,
        name="custodians/form.html",
        context={"error": error or "", "active_tab": "custodians"}
    )


@web_router.post("/custodians/new", dependencies=[Depends(require_permission("colaboradores.criar"))])
def create_custodian_form(
    request: Request,
    registration_code: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    cpf: Optional[str] = Form(None),
    role: str = Form(...),
    department: str = Form(...),
    db: Session = Depends(get_db)
):
    custodian_data = CustodianCreate(
        registration_code=registration_code,
        name=name,
        email=email,
        cpf=cpf or None,
        role=role,
        department=department,
        is_active=True
    )
    try:
        custodian = CustodianService.create(db, custodian_data)
    except ValueError as err:
        return RedirectResponse(url=f"/custodians/new?error={quote(str(err))}", status_code=status.HTTP_303_SEE_OTHER)
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_CREATE,
        module="Colaboradores",
        resource="Custodian",
        resource_ref=custodian.registration_code,
        resource_id=custodian.id,
        ip_address=_client_ip(request),
        after=_custodian_audit_snapshot(custodian),
        description=f"Cadastro do colaborador {custodian.name} ({custodian.registration_code})",
    )
    return RedirectResponse(url="/custodians", status_code=status.HTTP_303_SEE_OTHER)


@web_router.get("/custodians/{custodian_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_permission("colaboradores.editar"))])
def form_edit_custodian(request: Request, custodian_id: int, error: Optional[str] = None, success: Optional[str] = None, db: Session = Depends(get_db)):
    """Exibe o formulário de edição de um colaborador existente.

    A matrícula (registration_code) é o identificador do colaborador e é
    exibida somente para leitura: ela não pode ser alterada pela interface
    de edição, preservando o vínculo dos bens custodiados.
    """
    custodian = CustodianService.get_by_id(db, custodian_id)
    if not custodian:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado")
    return templates.TemplateResponse(
        request=request,
        name="custodians/form.html",
        context={
            "custodian": custodian,
            "error": error or "",
            "success": success or "",
            "active_tab": "custodians"
        }
    )


@web_router.post("/custodians/{custodian_id}/edit", dependencies=[Depends(require_permission("colaboradores.editar"))])
def update_custodian_form(
    request: Request,
    custodian_id: int,
    name: str = Form(...),
    email: str = Form(...),
    cpf: Optional[str] = Form(None),
    role: str = Form(...),
    department: str = Form(...),
    db: Session = Depends(get_db)
):
    """Salva a edição de um colaborador existente.

    Recebe apenas os campos editáveis (nome, e-mail, CPF, cargo e
    departamento). O identificador (id/matrícula) NÃO é aceito do formulário,
    portanto nunca pode ser alterado pela interface. A atualização é feita
    in-place pelo ID, preservando os relacionamentos de custódia dos bens.
    """
    before_c = CustodianService.get_by_id(db, custodian_id)
    if not before_c:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado")
    before = _custodian_audit_snapshot(before_c)
    update_data = CustodianUpdate(
        name=name,
        email=email,
        cpf=cpf or None,
        role=role,
        department=department,
    )
    try:
        custodian = CustodianService.update(db, custodian_id, update_data)
    except ValueError as err:
        return RedirectResponse(url=f"/custodians/{custodian_id}/edit?error={quote(str(err))}", status_code=status.HTTP_303_SEE_OTHER)
    if not custodian:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado")
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_UPDATE,
        module="Colaboradores",
        resource="Custodian",
        resource_ref=custodian.registration_code,
        resource_id=custodian.id,
        ip_address=_client_ip(request),
        before=before,
        after=_custodian_audit_snapshot(custodian),
        description=f"Edição do colaborador {custodian.name} ({custodian.registration_code})",
    )
    return RedirectResponse(url=f"/custodians/{custodian_id}/edit?success={quote('Colaborador atualizado com sucesso.')}", status_code=status.HTTP_303_SEE_OTHER)


@web_router.get("/custodians/import", response_class=HTMLResponse, dependencies=[Depends(require_permission("colaboradores.criar"))])
def form_import_custodians(request: Request):
    """Exibe o formulário de importação CSV de colaboradores"""
    return templates.TemplateResponse(
        request=request,
        name="custodians/import.html",
        context={"active_tab": "custodians"}
    )


@web_router.post("/custodians/import", response_class=HTMLResponse, dependencies=[Depends(require_permission("colaboradores.criar"))])
def process_import_custodians(
    request: Request,
    file: UploadFile = File(...),
    skip_duplicates: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Processa o upload e exibe pré-visualização da importação"""
    if not file.filename or not file.filename.endswith(".csv"):
        return templates.TemplateResponse(
            request=request,
            name="custodians/import.html",
            context={
                "active_tab": "custodians",
                "error": "Arquivo inválido. Envie um arquivo .csv",
            }
        )

    content = file.file.read().decode("utf-8-sig")
    rows, parse_errors = parse_custodian_csv(content)

    if not rows and parse_errors:
        return templates.TemplateResponse(
            request=request,
            name="custodians/import.html",
            context={
                "active_tab": "custodians",
                "error": "Erros ao ler o arquivo CSV:",
                "parse_errors": parse_errors,
            }
        )

    preview = preview_custodian_import(rows, db)

    return templates.TemplateResponse(
        request=request,
        name="custodians/import.html",
        context={
            "active_tab": "custodians",
            "show_preview": True,
            "preview": preview,
            "csv_rows": rows,
            "parse_errors": parse_errors,
            "skip_duplicates": skip_duplicates,
            "filename": file.filename,
        }
    )


@web_router.post("/custodians/import/confirm", dependencies=[Depends(require_permission("colaboradores.criar"))])
def confirm_import_custodians(
    request: Request,
    csv_data: str = Form(...),
    skip_duplicates: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Confirma e executa a importação de colaboradores"""
    import json
    import html as html_mod
    try:
        # Decodifica entidades HTML que o textarea pode ter inserido
        decoded = html_mod.unescape(csv_data)
        rows = json.loads(decoded)
        if not isinstance(rows, list):
            raise ValueError("Dados inválidos: esperado uma lista de registros")
    except (json.JSONDecodeError, ValueError) as e:
        return templates.TemplateResponse(
            request=request,
            name="custodians/import.html",
            context={
                "active_tab": "custodians",
                "show_result": True,
                "result": {
                    "imported": 0,
                    "skipped": 0,
                    "errors": [f"Erro ao processar dados: {str(e)}"],
                    "total_processed": 0,
                },
            }
        )

    try:
        result = execute_custodian_import(rows, db, skip_duplicates=skip_duplicates)
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="custodians/import.html",
            context={
                "active_tab": "custodians",
                "show_result": True,
                "result": {
                    "imported": 0,
                    "skipped": 0,
                    "errors": [f"Erro na importação: {str(e)}"],
                    "total_processed": 0,
                },
            }
        )

    write_audit(
        db,
        user=request.state.user,
        action=ACTION_IMPORT,
        module="Colaboradores",
        resource="Custodian",
        resource_ref="importacao-csv",
        ip_address=_client_ip(request),
        description=f"Importação CSV de colaboradores: {result.get('imported', 0)} importados, "
                    f"{result.get('skipped', 0)} ignorados, {len(result.get('errors', []))} erros",
        new_data={"imported": result.get("imported", 0), "skipped": result.get("skipped", 0)},
    )

    return templates.TemplateResponse(
        request=request,
        name="custodians/import.html",
        context={
            "active_tab": "custodians",
            "show_result": True,
            "result": result,
        }
    )


@web_router.get("/custodians/{custodian_id}", response_class=HTMLResponse, dependencies=[Depends(require_permission("colaboradores.visualizar"))])
def view_custodian_detail(request: Request, custodian_id: int, db: Session = Depends(get_db)):
    custodian = CustodianService.get_by_id(db, custodian_id)
    if not custodian:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado")

    assigned_assets = CustodianService.get_assigned_assets(db, custodian_id)

    return templates.TemplateResponse(
        request=request,
        name="custodians/detail.html",
        context={
            "custodian": custodian,
            "assets": assigned_assets,
            "active_tab": "custodians"
        }
    )


# ==========================================
# LOCAIS E DEPARTAMENTOS (LOCATIONS)
# ==========================================
@web_router.get("/locations", response_class=HTMLResponse, dependencies=[Depends(require_permission("locais.visualizar"))])
def list_locations_view(request: Request, db: Session = Depends(get_db)):
    locations = LocationService.get_all(db)
    for loc in locations:
        loc.assets_count = LocationService.count_assets(db, loc.id)

    return templates.TemplateResponse(
        request=request,
        name="locations/list.html",
        context={"locations": locations, "active_tab": "locations"}
    )


@web_router.get("/locations/import", response_class=HTMLResponse, dependencies=[Depends(require_permission("locais.criar"))])
def form_import_locations(request: Request):
    """Exibe o formulário de importação CSV de locais"""
    return templates.TemplateResponse(
        request=request,
        name="locations/import.html",
        context={"active_tab": "locations"},
    )


@web_router.post("/locations/import", response_class=HTMLResponse, dependencies=[Depends(require_permission("locais.criar"))])
def process_import_locations(
    request: Request,
    file: UploadFile = File(...),
    skip_duplicates: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Processa o upload e exibe pré-visualização da importação"""
    if not file.filename or not file.filename.endswith(".csv"):
        return templates.TemplateResponse(
            request=request,
            name="locations/import.html",
            context={
                "active_tab": "locations",
                "error": "Arquivo inválido. Envie um arquivo .csv",
            }
        )

    content = file.file.read().decode("utf-8-sig")
    rows, parse_errors = parse_locations_csv(content)

    if not rows and parse_errors:
        return templates.TemplateResponse(
            request=request,
            name="locations/import.html",
            context={
                "active_tab": "locations",
                "error": "Erros ao ler o arquivo CSV:",
                "parse_errors": parse_errors,
            }
        )

    preview = preview_locations_import(rows, db)

    return templates.TemplateResponse(
        request=request,
        name="locations/import.html",
        context={
            "active_tab": "locations",
            "show_preview": True,
            "preview": preview,
            "csv_rows": rows,
            "parse_errors": parse_errors,
            "skip_duplicates": skip_duplicates,
            "filename": file.filename,
        }
    )


@web_router.post("/locations/import/confirm", dependencies=[Depends(require_permission("locais.criar"))])
def confirm_import_locations(
    request: Request,
    csv_data: str = Form(...),
    skip_duplicates: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Confirma e executa a importação de locais"""
    import json
    import html as html_mod
    try:
        decoded = html_mod.unescape(csv_data)
        rows = json.loads(decoded)
        if not isinstance(rows, list):
            raise ValueError("Dados inválidos: esperado uma lista de registros")
    except (json.JSONDecodeError, ValueError) as e:
        return templates.TemplateResponse(
            request=request,
            name="locations/import.html",
            context={
                "active_tab": "locations",
                "show_result": True,
                "result": {
                    "imported": 0,
                    "skipped": 0,
                    "errors": [f"Erro ao processar dados: {str(e)}"],
                    "total_processed": 0,
                },
            }
        )

    try:
        result = execute_locations_import(rows, db, skip_duplicates=skip_duplicates)
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="locations/import.html",
            context={
                "active_tab": "locations",
                "show_result": True,
                "result": {
                    "imported": 0,
                    "skipped": 0,
                    "errors": [f"Erro na importação: {str(e)}"],
                    "total_processed": 0,
                },
            }
        )

    write_audit(
        db,
        user=request.state.user,
        action=ACTION_IMPORT,
        module="Locais",
        resource="Location",
        resource_ref="importacao-csv",
        ip_address=_client_ip(request),
        description=f"Importação CSV de locais: {result.get('imported', 0)} criados, "
                    f"{result.get('skipped', 0)} ignorados, {len(result.get('errors', []))} erros",
        new_data={"imported": result.get("imported", 0), "skipped": result.get("skipped", 0)},
    )

    return templates.TemplateResponse(
        request=request,
        name="locations/import.html",
        context={
            "active_tab": "locations",
            "show_result": True,
            "result": result,
        }
    )


@web_router.get("/locations/new", response_class=HTMLResponse, dependencies=[Depends(require_permission("locais.criar"))])
def form_new_location(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        request=request,
        name="locations/form.html",
        context={"error": error or "", "active_tab": "locations"}
    )


@web_router.post("/locations/new", dependencies=[Depends(require_permission("locais.criar"))])
def create_location_form(
    request: Request,
    name: str = Form(...),
    branch: str = Form(...),
    building: Optional[str] = Form(None),
    floor: Optional[str] = Form(None),
    room: Optional[str] = Form(None),
    department: str = Form(...),
    manager_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    loc_data = LocationCreate(
        name=name,
        branch=branch,
        building=building or None,
        floor=floor or None,
        room=room or None,
        department=department,
        manager_name=manager_name or None,
        description=description or None
    )
    try:
        loc = LocationService.create(db, loc_data)
    except ValueError as err:
        return RedirectResponse(url=f"/locations/new?error={quote(str(err))}", status_code=status.HTTP_303_SEE_OTHER)
    write_change_audit(
        db,
        user=request.state.user,
        action=ACTION_CREATE,
        module="Locais",
        resource="Location",
        resource_ref=loc.name,
        resource_id=loc.id,
        ip_address=_client_ip(request),
        after={"name": loc.name, "branch": loc.branch, "department": loc.department},
        description=f"Cadastro do local {loc.name}",
    )
    return RedirectResponse(url="/locations", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
# MANUTENÇÕES (MAINTENANCES)
# ==========================================
@web_router.get("/maintenances", response_class=HTMLResponse, dependencies=[Depends(require_permission("manutencao.visualizar"))])
def list_maintenances_view(request: Request, db: Session = Depends(get_db)):
    maintenances = MaintenanceService.get_all(db)
    return templates.TemplateResponse(
        request=request,
        name="maintenances/list.html",
        context={"maintenances": maintenances, "active_tab": "maintenances"}
    )


@web_router.get("/maintenances/new", response_class=HTMLResponse, dependencies=[Depends(require_permission("manutencao.criar"))])
def form_new_maintenance(request: Request, asset_id: Optional[int] = None, db: Session = Depends(get_db)):
    assets, _ = AssetService.get_all(db, limit=500)
    active_assets = [a for a in assets if a.status != AssetStatus.WRITTEN_OFF]
    selected_asset = AssetService.get_by_id(db, asset_id) if asset_id else None

    return templates.TemplateResponse(
        request=request,
        name="maintenances/new.html",
        context={
            "assets": active_assets,
            "selected_asset": selected_asset,
            "maintenance_types": MaintenanceType,
            "active_tab": "maintenances"
        }
    )


@web_router.post("/maintenances/new", dependencies=[Depends(require_permission("manutencao.criar"))])
def create_maintenance_form(
    request: Request,
    asset_id: int = Form(...),
    maintenance_type: str = Form(...),
    provider_name: Optional[str] = Form(None),
    description: str = Form(...),
    cost: float = Form(0.0),
    operator_name: str = Form("Técnico"),
    db: Session = Depends(get_db)
):
    maint_data = MaintenanceCreate(
        asset_id=asset_id,
        maintenance_type=MaintenanceType(maintenance_type),
        provider_name=provider_name or None,
        description=description,
        cost=cost
    )
    maint = MaintenanceService.create(db, maint_data, operator=operator_name)
    asset_tag = maint.asset.tag if maint.asset else None
    write_audit(
        db,
        user=request.state.user,
        action=ACTION_MAINTENANCE,
        module="Manutenção",
        resource="Maintenance",
        resource_ref=asset_tag,
        resource_id=maint.id,
        ip_address=_client_ip(request),
        new_data={
            "tipo": maint.maintenance_type.value,
            "status": maint.status.value,
            "descricao": maint.description,
            "custo": maint.cost,
        },
        description=f"Abertura de ordem de serviço {maint.maintenance_type.value} para o bem {asset_tag or asset_id}",
    )
    return RedirectResponse(url=f"/assets/{asset_id}?maintenance_started=true", status_code=status.HTTP_303_SEE_OTHER)


@web_router.post("/maintenances/{maintenance_id}/complete", dependencies=[Depends(require_permission("manutencao.finalizar"))])
def complete_maintenance_form(
    request: Request,
    maintenance_id: int,
    solution: str = Form(...),
    cost: float = Form(0.0),
    operator_name: str = Form("Técnico"),
    db: Session = Depends(get_db)
):
    update_data = MaintenanceUpdate(
        solution=solution,
        cost=cost
    )
    maint = MaintenanceService.complete_maintenance(db, maintenance_id, update_data, operator=operator_name)
    asset_id = maint.asset_id if maint else ""
    if maint:
        asset_tag = maint.asset.tag if maint.asset else None
        write_audit(
            db,
            user=request.state.user,
            action=ACTION_MAINTENANCE,
            module="Manutenção",
            resource="Maintenance",
            resource_ref=asset_tag,
            resource_id=maint.id,
            ip_address=_client_ip(request),
            before={"status": "EM_ANDAMENTO", "custo": maint.cost},
            after={"status": maint.status.value, "custo": maint.cost, "solucao": maint.solution},
            description=f"Finalização da ordem de serviço {maint.id} do bem {asset_tag or asset_id}",
        )
    return RedirectResponse(url=f"/assets/{asset_id}?maintenance_completed=true", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
# RELATÓRIOS
# ==========================================
@web_router.get("/reports/inventory", response_class=HTMLResponse, dependencies=[Depends(require_permission("relatorios.visualizar"))])
def view_inventory_report(request: Request, db: Session = Depends(get_db)):
    assets, total = AssetService.get_all(db, limit=1000)
    for a in assets:
        a.deprec_info = AssetService.calculate_depreciation(a)

    return templates.TemplateResponse(
        request=request,
        name="reports/inventory.html",
        context={
            "assets": assets,
            "total": total,
            "active_tab": "reports"
        }
    )


@web_router.get("/reports/movements", response_class=HTMLResponse, dependencies=[Depends(require_permission("relatorios.visualizar"))])
def view_movements_report(request: Request, db: Session = Depends(get_db)):
    movements, total = MovementService.get_all_movements(db, limit=1000)
    return templates.TemplateResponse(
        request=request,
        name="reports/movements_report.html",
        context={
            "movements": movements,
            "total": total,
            "active_tab": "reports"
        }
    )


@web_router.get("/reports/custodians", response_class=HTMLResponse, dependencies=[Depends(require_permission("relatorios.visualizar"))])
def view_custodians_report(request: Request, db: Session = Depends(get_db)):
    custodians = CustodianService.get_all(db)
    for c in custodians:
        c.active_assets_count = CustodianService.count_assigned_assets(db, c.id)

    return templates.TemplateResponse(
        request=request,
        name="reports/custodians_report.html",
        context={
            "custodians": custodians,
            "total": len(custodians),
            "active_tab": "reports"
        }
    )


# ============================================================================
# PRIMEIRO ACESSO / CONFIGURAÇÃO INICIAL (somente instalação nova)
# ============================================================================

def _first_access_enabled(db: Session) -> bool:
    """
    O fluxo de primeiro acesso só é ativado quando:
    - AUTH_ADMIN_PASSWORD não está configurada (o bootstrap por variável de
      ambiente não será preparado), E
    - ainda não existe nenhum usuário no banco.

    Essa verificação é feita dentro da própria requisição, com a sessão do
    request, e a criação posterior ocorre no mesmo request/commit — o que
    impede que duas requisições concorrentes criem dois administradores
    (SQLite serializa escritas e a checagem + INSERT acontecem no mesmo
    commit; a segunda requisição verá o usuário já existente).
    """
    if AUTH_ADMIN_PASSWORD:
        return False
    return db.query(User).first() is None


@web_router.get("/setup", response_class=HTMLResponse)
def first_access_page(
    request: Request, db: Session = Depends(get_db)
):
    """Tela de configuração inicial. Só visível em instalação nova."""
    if not _first_access_enabled(db):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={"error": ""},
    )


@web_router.post("/setup", response_class=HTMLResponse)
def first_access_submit(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    password: str = Form(...),
    confirm_password: str = Form(...),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    """Processa a criação do primeiro administrador."""
    ip = _client_ip(request)

    # Revisa se a instalação ainda está em primeiro acesso (idempotente e
    # seguro contra condição de corrida: se outro request já criou o usuário,
    # redireciona para o login).
    if not _first_access_enabled(db):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    username = (username or "").strip()
    full_name = (full_name or "").strip()
    email = (email or "").strip()

    if not username:
        return templates.TemplateResponse(
            request=request,
            name="setup.html",
            context={"error": "O nome de usuário não pode ser vazio."},
        )
    if not password or len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="setup.html",
            context={"error": "A senha deve ter no mínimo 8 caracteres."},
        )
    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="setup.html",
            context={"error": "As senhas não coincidem."},
        )

    try:
        admin = create_user(
            db,
            username=username,
            password=password,
            full_name=full_name or None,
            email=email or None,
            is_admin=True,
        )
    except ValueError as err:
        return templates.TemplateResponse(
            request=request,
            name="setup.html",
            context={"error": str(err)},
        )

    # Garante catálogo de permissões e o perfil Administrador (idempotente)
    ensure_default_roles(db)

    # Vincula o perfil Administrador ao novo usuário, se ainda não estiver
    # vinculado (garante que o administrador tem as permissões esperadas).
    admin_role = get_role_by_name(db, "Administrador")
    if admin_role:
        role_assigned = (
            db.query(UserRole)
            .filter(UserRole.user_id == admin.id, UserRole.role_id == admin_role.id)
            .first()
        )
        if not role_assigned:
            assign_role(db, admin, admin_role)

    # Auditoria de criação — NUNCA registra senha, hash ou credencial.
    write_audit(
        db,
        user=admin,
        action=ACTION_CREATE,
        module="Usuários",
        resource="User",
        resource_ref=admin.username,
        resource_id=admin.id,
        ip_address=ip,
        result=RESULT_SUCCESS,
        description="Primeiro administrador criado no primeiro acesso",
        new_data={
            "username": admin.username,
            "full_name": admin.full_name,
            "email": admin.email,
            "is_admin": True,
        },
    )

    logger.info(
        "Primeiro administrador criado via setup: username=%s, ip=%s",
        admin.username,
        ip,
    )

    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)