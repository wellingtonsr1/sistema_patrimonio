# SisPatrimônio Pro — Guia de Manutenção

> Respostas práticas para as perguntas mais comuns de manutenção, apontando para
> **arquivos e componentes reais** do repositório. Referência rápida — o contexto
> completo está em `ARQUITETURA_E_MANUTENCAO.md` e o mapa de tudo, em
> `INVENTARIO_TECNICO.md`.

---

## Como alterar uma tela (página web)

1. **Template** → `app/web/templates/<módulo>/<página>.html` (ex.: `assets/list.html`).
2. **Handler** → `app/web/routes.py` (telas de negócio) ou `app/web/admin_routes.py`
   (administração) ou `app/web/help_routes.py` (ajuda).
3. **Menu/botões condicionais** → no template, usar `can('modulo.acao')` — fornecida pelo
   context processor `_inject_current_user` em `app/web/routes.py`.
4. **Menu global/layout** → `app/web/templates/base.html`.
5. Lembre-se: a permissão da rota é validada no backend
   (`dependencies=[Depends(require_permission("modulo.acao"))]` no handler) — esconder o
   botão no template é apenas apresentação.

## Como alterar uma rota (API ou web)

- **API REST** → `app/api/<dominio>_api.py` (prefixo do roteador + funções);
  o roteador precisa estar incluído em `app/api/v1_router.py` (roteadores de negócio
  já entram com `require_api_auth`).
- **Web** → `app/web/routes.py` / `admin_routes.py` / `help_routes.py`.
- **Permissão da rota** → `require_permission("modulo.acao")` (fábrica em `app/api/deps.py`).
- **Novo roteador web** → incluir em `app/main.py` com
  `dependencies=[Depends(require_web_auth)]`.

## Como adicionar uma permissão

1. Acrescentar o item em `PERMISSION_CATALOG` — `app/services/permission_service.py`
   (padrão `modulo.acao`; o seed `ensure_default_roles` cria no startup e no CLI).
2. Incluir no `DEFAULT_ROLES` apenas se o perfil padrão deva nascer com ela
   (afeta somente perfis recém-criados sem permissões).
3. Atribuir a perfis existentes pela tela **Administração → Perfis & Permissões**
   (`/admin/roles/{id}/edit` → `admin_routes.py::admin_update_role` → `update_role`).
4. Proteger as rotas com `require_permission("modulo.acao")` e exibir com `can(...)`.

## Como alterar um perfil

- Pela tela: `Administração → Perfis & Permissões` (rotas `/admin/roles*` em
  `app/web/admin_routes.py`; serviço `permission_service.create_role/update_role/delete_role`).
- Por código: `permission_service.update_role(db, role, name=..., permission_names=[...])`.
- Regras já codificadas: perfis `is_system=True` não podem ser excluídos; perfis com
  usuários atribuídos também não (`delete_role` levanta `ValueError`).

## Onde está o login?

- **API** → `app/api/auth_api.py` (`POST /api/v1/auth/login`, `logout`, `GET /me`).
- **Web** → `app/web/routes.py::login_submit` + `app/web/templates/login.html`.
- **Decisão local × AD** → `app/services/auth_provider.py::resolve_authentication`.
- **Senha/lockout** → `app/services/auth_service.py`. **Sessão/cookie** →
  `app/services/session_service.py`.

## Onde está a integração AD?

| Aspecto | Arquivo |
|---|---|
| Protocolo LDAP/LDAPS (bind, busca, atributos, GUID, UAC) | `app/services/ad_ldap.py` |
| Regras (mapeamento, provisionamento, sincronização, auditoria) | `app/services/ad_service.py` (`authenticate_and_sync` é o fluxo completo) |
| Tela de configuração e mapeamentos | `app/web/admin_routes.py` (seção "INTEGRAÇÃO ACTIVE DIRECTORY") + `app/web/templates/admin/ad/settings.html` |
| Modelos | `app/models/ad_settings.py`, `app/models/ad_group_role.py` |
| Colunas AD em `users` | `app/models/user.py` + `_ensure_schema_migrations` em `app/database.py` |
| Testes | `tests/test_ad.py` (LDAP mockado) |

Regra que **não** pode ser quebrada: autenticação AD não concede acesso; somente grupo
mapeado para perfil existente; sem mapeamento → nada é criado no banco, apenas auditoria
(`GRUPO_AD_SEM_MAPEAMENTO`).

## Onde está a auditoria?

- **Serviço** → `app/services/audit_service.py` (`write_audit`, `write_change_audit`,
  constantes de ações, `get_audit_logs`).
- **Modelo/tabela** → `app/models/audit_log.py` (`audit_logs`).
- **Tela de consulta** → `app/web/admin_routes.py::admin_audit_log` (`/admin/audit`) +
  `app/web/templates/admin/audit/list.html` (permissão `auditoria.visualizar`).
- Não existe rota de escrita/exclusão — a trilha é somente-leitura.

## Onde estão os modelos?

`app/models/` — um arquivo por entidade; todos registrados em `app/models/__init__.py`
(necessário para `Base.metadata.create_all`). Enums em `app/models/enums.py`.

## Onde estão os logs técnicos? (diferente da auditoria)

- **Auditoria de negócio** → tabela `audit_logs` (consultada em `/admin/audit`) — ações dos usuários.
- **Logs técnicos** → `app/logging_config.py::configure_logging` (chamado por `run.py`):
  - `data/logs/app.log` — INFO e abaixo (funcionamento normal);
  - `data/logs/app.error.log` — WARNING e acima (erros/exceções);
  - rotação: 5 MB por arquivo, 5 backups; formato `data | nível | logger | mensagem`;
  - `uvicorn.access` suprimido para WARNING (evita ruído).
- Diagnóstico: erro 500 em uma página → ver primeiro `app.error.log`; a auditoria registra
  ações autorizadas/negadas, não stack traces.

## Onde está o banco?

- **Arquivo** → `data/patrimonio.db` (SQLite; ajustável via `DATABASE_URL` em `app/config.py`).
- **Engine/sessões** → `app/database.py` (`engine`, `SessionLocal`, `get_db`).
- **Criação/migração leve** → `init_db()` e `_ensure_schema_migrations()` no mesmo arquivo.
- **Dados de demo** → `python seed_demo.py` (⚠️ executa `drop_all` — apaga os dados).

## Onde ficam as configurações?

`app/config.py` — único ponto. Variáveis de ambiente documentadas em
`ARQUITETURA_E_MANUTENCAO.md` §17 (`AUTH_*`, `AD_*`, `DATABASE_URL`, `APP_*`).
A configuração do AD também pode ser feita pela tela `/admin/ad` (tabela `ad_settings`),
com as variáveis de ambiente como fallback dos campos vazios.

## Como executar o sistema

```bash
pip install -r requirements.txt
python run.py                 # http://127.0.0.1:8000 · Swagger em /docs
```

### Criação do primeiro administrador

O SisPatrimônio Pro possui **três formas** de criar o primeiro administrador:

**1. Via interface web (Primeiro Acesso)** — recomendado para instalações novas:
- Se não houver usuários no banco e `AUTH_ADMIN_PASSWORD` não estiver definida, a tela de login exibe um link "Primeiro acesso"
- Acesse `/setup` e preencha: nome, usuário, e-mail e senha (mínimo 8 caracteres)
- O sistema cria o administrador e osperfis padrão automaticamente
- `/setup` fica inacessível assim que existir qualquer usuário (redirect para `/login`)

**2. Via variável de ambiente** (criação automática no start):
```bash
export AUTH_ADMIN_PASSWORD='SenhaForte@123'
python run.py
```

**3. Via CLI** (criação manual):
```bash
python -m app.cli create-user --username admin --password 'SenhaForte@123' --admin
```

## Como executar os testes

```bash
pytest -v          # 156 testes (12 arquivos); SQLite em memória; LDAP mockado
pytest tests/test_ad.py -v          # apenas AD
pytest tests/test_rbac.py -v        # apenas RBAC
```

> **Estado atual (registrado, não corrigido nesta documentação):** 3 testes falham com o
> mesmo erro latente — `NameError: ACTION_MOVEMENT` em `movement_service.get_timeline_for_asset`
> (a função também passou a retornar dicts, quebrando testes antigos que esperavam objetos ORM).
> **Impacto real: as páginas de detalhes do bem (`/assets/{id}`) podem falhar com erro 500.**
> Detalhes em `ARQUITETURA_E_MANUTENCAO.md` §18 item 11 e §19.

---

## Tarefas comuns (passo a passo)

### Criar um usuário administrador
CLI: `python -m app.cli create-user --username X --admin` — em `app/cli.py`.

### Proteger um novo endpoint
```python
from app.api.deps import require_permission
@router.post("/algo", dependencies=[Depends(require_permission("modulo.acao"))])
def criar(...): ...
```

### Adicionar um artigo na Central de Ajuda
Item em `ARTICLES` (e opcionalmente `CATEGORIES`) em `app/services/help_service.py`;
artigos `audience="admin"` exigem permissão administrativa para serem vistos.

### Trocar a empresa do Termo de Responsabilidade
Constantes `COMPANY_NAME`, `COMPANY_CNPJ`, `COMPANY_ADDRESS` em `app/config.py`
(consumidas por `movement_service.get_term_details` e o template `movements/term.html`).

### Adicionar coluna em tabela existente
1. Adicionar a coluna no modelo (`app/models/...`).
2. Adicionar o `ALTER TABLE ADD COLUMN` condicional em `_ensure_schema_migrations`
   (`app/database.py`) — sem isso, bancos existentes não recebem a coluna.
3. Se for coluna de auditoria de negócio, ajustar os snapshots `_asset_snapshot` /
   `_custodian_audit_snapshot` nas rotas.

### Exportação CSV nova
1. Método em `ReportService` (`app/services/report_service.py`) — separador `;`, `utf-8-sig`.
2. Rota em `app/api/reports_api.py` com `require_permission("relatorios.exportar")`.

### Ajustar o comportamento do tema claro/escuro
`app/web/static/js/main.js` (`initDarkMode`, `toggleDarkMode`, `applyTheme`) e
`app/web/static/css/style.css` (`[data-theme="dark"]`).

### Ajustar a página de Etiquetas
Handler `assets_labels` em `app/web/routes.py` (rota `/assets/labels`, permissão
`patrimonio.visualizar`); template `app/web/templates/assets/labels.html` (seleção em lote
via URL `?selected=`, folha renderizada client-side, QR gerado com a mesma chamada qrcodejs
da ficha); layout/impressão no bloco "ETIQUETAS DE PATRIMÔNIO" de `style.css` (grade A4,
`@media print`). Não altera dados — somente leitura. O link do menu fica em
`base.html`, dentro do dropdown "Equipamentos" (desktop) e no drawer lateral (mobile).

### Alterar conteúdo da Central de Ajuda
Tudo em `app/services/help_service.py`: artigos em `ARTICLES`, perguntas em `FAQ`,
cards em `CATEGORIES`. Nenhum código de rota precisa mudar para editar conteúdo.

---

## Problemas conhecidos (registrados — ver detalhes em ARQUITETURA §18)

1. **`NameError` latente em `movement_service.get_timeline_for_asset`** (constantes
   `ACTION_MOVEMENT`/`ACTION_MAINTENANCE` não importadas): detalhes do bem
   (`/assets/{id}`), endpoint de timeline e CLI `show` podem falhar com 500.
2. **Sem proteção CSRF** nos formulários web (mitigado parcialmente por `SameSite=Lax`).
3. **`AUTH_PROVIDER` inerte** — o login real usa `resolve_authentication()`.
4. **`seed_demo.py` apaga o banco** (`drop_all`) — nunca apontar para o banco real.
5. **Permissões sem rota**: `patrimonio.excluir`, `movimentacao.editar`,
   `movimentacao.cancelar`, `manutencao.editar` existem no catálogo, mas nenhuma rota as exige.
6. **Datas mistas**: `datetime.now()` (hora local) em `asset_service`/`movement_service` vs.
   `datetime.utcnow()` em auth/sessões/modelos.

---

## Checklist antes de alterar código (resumo das regras do projeto)

1. Rodar `pytest` antes e depois — a suíte cobre RBAC, auth, AD e negócio (110 testes).
2. Toda rota nova: `require_permission(...)` desde o início (deny by default).
3. Ações de escrita relevantes: registrar auditoria (`write_audit`/`write_change_audit`),
   nunca incluindo senhas/segredos.
4. Mudanças de custódia/local/status de bem: sempre via `MovementService.create_movement`.
5. Integração AD: manter "autenticação ≠ autorização" e provisionamento só pós-mapeamento
   (testes `tests/test_ad.py` protegem isso).
6. Colaborador: nunca criado automaticamente (importação/telas explícitas apenas).
7. Coluna nova em tabela existente: modelo **+** `_ensure_schema_migrations`.
8. Senhas: só PBKDF2 via `auth_service.hash_password`; sessões invalidadas em
   troca/reset de senha e bloqueio.
