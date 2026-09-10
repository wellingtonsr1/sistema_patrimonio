"""
Testes da Navbar (cabeçalho superior do SisPatrimônio).

Verifica a estrutura de três áreas (logo | menus centralizados | ações à direita):
- presença de todos os elementos exigidos (nenhum menu removido);
- que os menus principais ficam no container central (`navbarMain`);
- que a área de ações (Ajuda, usuário e tema) está agrupada FORA do collapse;
- que o CSS com as regras de distribuição é servido e contém as regras esperadas.
"""

MENUS = [
    "Dashboard",
    "Equipamentos",
    "Fluxo & Movimentação",
    "Colaboradores",
    "Locais",
    "Manutenções",
    "Relatórios",
    "Administração",
]


# ============================================================================
# TRÊS ÁREAS DA NAVBAR
# ============================================================================

def test_navbar_three_areas_render(client):
    """Logo à esquerda, menus no centro e ações à direita estão presentes."""
    resp = client.get("/")
    assert resp.status_code == 200
    page = resp.text

    # Área esquerda: logo/marca
    assert 'class="navbar-brand' in page
    assert 'class="navbar-brand-logo"' in page
    assert "/static/img/Logo_IPMjp.png" in page
    assert "SisPatrimônio" in page
    assert "PRO" in page

    # Área central: collapse de navegação com o menu principal
    assert 'id="navbarMain"' in page
    assert 'class="navbar-nav' in page

    # Área direita: Ajuda, usuário e alternador de tema
    assert 'class="navbar-actions' in page
    assert 'href="/ajuda"' in page
    assert "bi-person-circle" in page
    assert 'id="darkToggle"' in page
    assert "dropdown-menu-end" in page


# ============================================================================
# ESTRUTURA: MENUS NO CENTRO / AÇÕES FORA DO COLLAPSE
# ============================================================================

def test_navbar_menus_inside_central_collapse(client):
    """Todos os menus principais estão no container central (entre o collapse e as ações)."""
    page = client.get("/").text
    start = page.index('id="navbarMain"')
    end = page.index('class="navbar-actions')
    center = page[start:end]

    for menu in MENUS:
        assert menu in center, f"menu '{menu}' ausente da área central da Navbar"

    # Ajuda NÃO pode estar dentro do collapse central: pertence à área direita
    assert 'href="/ajuda"' not in center


def test_navbar_right_actions_grouped_outside_collapse(client):
    """A área de ações vem depois do collapse e reúne Ajuda, usuário e tema."""
    page = client.get("/").text

    brand = page.index('class="navbar-brand')
    main = page.index('id="navbarMain"')
    actions = page.index('class="navbar-actions')
    toggle = page.index('id="darkToggle"')
    assert brand < main < actions < toggle

    right = page[actions:page.index("<main")]
    assert 'href="/ajuda"' in right
    assert "bi-person-circle" in right
    assert 'id="darkToggle"' in right
    assert "dropdown-menu-end" in right


# ============================================================================
# CSS DAS ÁREAS (regressão da distribuição)
# ============================================================================

def test_navbar_css_served_with_layout_rules(client):
    """O CSS é servido e contém as regras das três áreas (colunas 1fr nas laterais)."""
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
    css = resp.text

    assert ".app-navbar .navbar-actions" in css
    assert ".navbar-brand" in css
    assert "flex: 1 1 0" in css
    assert "clamp(.35rem, .6vw, .8rem)" in css
    # Ajuda continua oculta na barra superior em telas pequenas (< 1200px)
    assert ".app-navbar .navbar-quick-actions" in css
    assert ".navbar-quick-actions { display: none !important; }" in css