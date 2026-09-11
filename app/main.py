import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_NAME, APP_DESCRIPTION, APP_VERSION
from app.database import init_db, SessionLocal
from app.api.v1_router import api_v1_router
from app.api.deps import require_web_auth
from app.services.auth_service import ensure_admin_user
from app.services.permission_service import ensure_default_roles
from app.web.routes import web_router, templates
from app.web.admin_routes import admin_router
from app.web.help_routes import help_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa o banco de dados e cria as tabelas automaticamente
    init_db()
    # Cria o usuário administrador inicial (se AUTH_ADMIN_PASSWORD estiver definida)
    # e faz o seed idempotente de perfis/permissões padrão
    db = SessionLocal()
    try:
        ensure_admin_user(db)
        ensure_default_roles(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan
)

# Monta arquivos estáticos (CSS, JS, Imagens)
STATIC_DIR = Path(__file__).parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Inclui rotas da API REST
app.include_router(api_v1_router)

# Inclui rotas da Interface Web (todas exigem login, exceto /login e /logout)
app.include_router(web_router, dependencies=[Depends(require_web_auth)])

# Inclui rotas administrativas e de perfil (todas exigem login)
app.include_router(admin_router, dependencies=[Depends(require_web_auth)])

# Inclui a Central de Ajuda / Manual (exige login; conteúdo admin é protegido por permissão)
app.include_router(help_router, dependencies=[Depends(require_web_auth)])


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Handler central de HTTPException:
    - Respostas com headers (ex: redirect 303 do login) são preservadas.
    - APIs (/api/*) respondem JSON (contrato REST).
    - Páginas web ganham páginas amigáveis 403 e 404.
    """
    if exc.headers:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if exc.status_code == 403:
        return templates.TemplateResponse(
            request=request,
            name="403.html",
            context={},
            status_code=403,
        )
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            context={},
            status_code=404,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", tags=["Sistema"])
def health_check():
    """Health check aprimorado: verifica aplicação, banco de dados e AD (se habilitado)."""
    from sqlalchemy import text
    from app.services.ad_service import ad_enabled, get_ad_settings
    from app.services.ad_ldap import test_connection, ADError
    from app.config import AD_SERVER
    
    # Verificação da aplicação (se chegou aqui, está saudável)
    app_status = "ok"
    
    # Verificação do banco de dados
    db_status = "ok"
    db_exception = None
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as e:
        db_status = "warning"
        db_exception = str(e)
        logger.warning("Health check - banco de dados indisponível: %s", e)
    
    # Verificação do AD (somente se habilitado)
    ad_status = "not_applicable"
    ad_message = None
    
    if AD_SERVER and AD_SERVER.strip():
        # AD configurado via variável de ambiente
        try:
            ad_settings = get_ad_settings(SessionLocal())
            SessionLocal().close()
            if ad_enabled(SessionLocal()):
                # AD habilitado - testar conectividade
                try:
                    conn_result = test_connection(ad_settings)
                    if conn_result.get("ok"):
                        ad_status = "ok"
                    else:
                        ad_status = "warning"
                        ad_message = conn_result.get("message", "Falha na conexão com AD")
                except Exception as e:
                    ad_status = "warning"
                    ad_message = "Falha ao verificar AD"
                    logger.warning("Health check - falha na verificação AD: %s", e)
            else:
                ad_status = "not_applicable"
                ad_message = "AD configurado mas não habilitado"
        except Exception as e:
            ad_status = "not_applicable"
            ad_message = "Não foi possível carregar configuração do AD"
            logger.warning("Health check - erro ao carregar configuração AD: %s", e)
    else:
        ad_status = "not_applicable"
        ad_message = "Integração AD não configurada"
    
    # Determinar status global
    if db_status == "warning" or ad_status == "warning":
        global_status = "degraded"
    else:
        global_status = "healthy"
    
    return {
        "status": global_status,
        "application": app_status,
        "database": db_status,
        "ad": ad_status,
    }
