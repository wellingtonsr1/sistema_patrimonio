"""
Rotas da Central de Ajuda / Manual.

- GET /ajuda            → página central (pesquisa, categorias, artigos e FAQ)
- GET /ajuda/{article_id} → página de um artigo específico

Artigos administrativos (audience="admin") só são exibidos/abertos para
usuários com alguma permissão administrativa. O restante do conteúdo é
acessível a qualquer usuário autenticado.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.services import help_service
from app.web.routes import templates

help_router = APIRouter(include_in_schema=False)


def _has_admin_perms(request: Request) -> bool:
    """Alguma permissão administrativa (usuários/perfis/auditoria)."""
    perms = set(getattr(request.state, "_permissions", None) or set())
    return bool(
        perms & {"usuarios.visualizar", "perfis.visualizar", "auditoria.visualizar"}
    )


@help_router.get("/ajuda", response_class=HTMLResponse)
def ajuda_index(request: Request):
    categories = help_service.get_categories()
    articles = help_service.get_articles()
    faq = help_service.get_faq()
    return templates.TemplateResponse(
        request=request,
        name="ajuda/index.html",
        context={
            "categories": categories,
            "articles": articles,
            "faq": faq,
            "search_index": json.dumps(
                help_service.serialize_search_index(), ensure_ascii=False
            ),
            "has_admin_perms": _has_admin_perms(request),
            "active_tab": "ajuda",
        },
    )


@help_router.get("/ajuda/{article_id}", response_class=HTMLResponse)
def ajuda_article(request: Request, article_id: str):
    article = help_service.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Artigo não encontrado")
    if article.get("audience") == "admin" and not _has_admin_perms(request):
        raise HTTPException(
            status_code=403, detail="Conteúdo disponível apenas para administradores"
        )

    related = [
        a for a in help_service.get_articles() if a["id"] in article.get("related", [])
    ]
    return templates.TemplateResponse(
        request=request,
        name="ajuda/article.html",
        context={"article": article, "related": related, "active_tab": "ajuda"},
    )