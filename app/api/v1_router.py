from fastapi import APIRouter, Depends

from app.api.auth_api import router as auth_router
from app.api.assets_api import router as assets_router
from app.api.movements_api import router as movements_router
from app.api.custodians_api import router as custodians_router
from app.api.locations_api import router as locations_router
from app.api.reports_api import router as reports_router
from app.api.deps import require_api_auth

api_v1_router = APIRouter(prefix="/api/v1")

# Rotas públicas de autenticação (login/logout; /me exige sessão por conta própria)
api_v1_router.include_router(auth_router)

# Todos os demais roteadores exigem autenticação (sessão válida via cookie).
# Isso cobre mutações (POST/PUT), consultas sensíveis e exportações de dados.
for _router in (
    assets_router,
    movements_router,
    custodians_router,
    locations_router,
    reports_router,
):
    api_v1_router.include_router(_router, dependencies=[Depends(require_api_auth)])