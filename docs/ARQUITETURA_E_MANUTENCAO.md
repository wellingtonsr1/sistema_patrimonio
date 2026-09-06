# SisPatrimônio Pro — Arquitetura e Manutenção

> **Documento gerado a partir da análise do código-fonte real do projeto.** Todas as
> afirmações abaixo foram verificadas nos arquivos indicados. Onde uma informação não
> pôde ser confirmada no código, está marcada como `não identificado no código analisado`.

---

## 1. Visão geral do sistema

| Item | Descrição |
|---|---|
| **Nome** | SisPatrimônio Pro (`APP_NAME` em `app/config.py`) |
| **Versão** | `1.0.0` (`APP_VERSION` em `app/config.py`) |
| **Finalidade** | Gestão Patrimonial: controle de ativo fixo/equipamentos, com foco no rastreamento auditável do fluxo de movimentação de cada bem |
| **Problema que resolve** | Tombamento de equipamentos, controle de custódia (quem está com o bem), localização física, manutenções, depreciação contábil e histórico completo (audit trail) de cada movimentação |
| **Usuários típicos** | Administrador, Gestor de TI, Técnico de TI, Patrimônio, Almoxarifado, Auditor, Consulta (perfis padrão em `app/services/permission_service.py`) |

### Módulos funcionais existentes

1. **Dashboard** — KPIs do acervo (`app/services/dashboard_service.py`, template `dashboard.html`).
2. **Patrimônio / Equipamentos** — CRUD de bens, ficha técnica, QR Code, depreciação linear, importação CSV (`app/services/asset_service.py`, `app/services/import_service.py`).
3. **Fluxo & Movimentação** — motor de movimentações com trilha imutável e Termo de Responsabilidade (`app/services/movement_service.py`).
4. **Manutenções** — ordens de serviço preventiva/corretiva/upgrade, integradas ao fluxo (`app/services/maintenance_service.py`).
5. **Colaboradores (custodiantes) & Locais** — cadastro e importação CSV (`custodian_service.py`, `location_service.py`, `custodian_import_service.py`).
6. **Relatórios & Exportações** — dashboard-stats e 3 exportações CSV (`report_service.py`).
7. **Administração** — usuários, perfis & permissões (RBAC), auditoria, Integração AD (`app/web/admin_routes.py`).
8. **Central de Ajuda** — manual embutido em `/ajuda` (`app/services/help_service.py`).
9. **Autenticação & Sessões** — local (PBKDF2) + Active Directory (LDAP/LDAPS) com sessão server-side (`auth_service.py`, `auth_provider.py`, `session_service.py`).
10. **Auditoria** — trilha somente-leitura (`audit_service.py`, modelo `AuditLog`).
11. **CLI** — interface de linha de comando (`app/cli.py`).

### Fluxo geral da aplicação

```text
Browser / cliente HTTP
   ↓
FastAPI (app/main.py)
   ├── Rotas web (Jinja2)  app/web/routes.py, admin_routes.py, help_routes.py
   └── API REST (/api/v1)  app/api/*
   ↓ (dependências de auth: app/api/deps.py)
Services (regras de negócio)  app/services/*
   ↓
Models (SQLAlchemy)  app/models/*
   ↓
SQLite (data/patrimonio.db)
```

---

## 2. Stack tecnológica

Baseado em `requirements.txt` e nas versões efetivamente instaladas no ambiente de análise
(as versões abaixo **foram confirmadas** executando os imports no ambiente; o `requirements.txt`
define apenas mínimos):

| Camada | Tecnologia | Versão mínima (requirements.txt) | Versão instalada |
|---|---|---|---|
| Linguagem | Python | 3.10+ (README; ambiente de análise: 3.10.12) | 3.10.12 |
| Framework web | FastAPI | `>=0.110.0` | 0.141.1 |
| Servidor ASGI | Uvicorn (`uvicorn[standard]`) | `>=0.28.0` | 0.30.6 |
| ORM | SQLAlchemy | `>=2.0.0` | 2.0.52 |
| Banco de dados | SQLite (arquivo local) | — | — |
| Validação | Pydantic v2 | `>=2.6.0` | 2.13.5 |
| Templates | Jinja2 | `>=3.1.3` | 3.1.6 |
| Multipart (upload) | python-multipart | `>=0.0.9` | instalada |
| LDAP/LDAPS | ldap3 | `>=2.9.1` | 2.9.1 |
| Testes | pytest | `>=8.0.0` | instalada |
| HTTP client (testes/uso) | requests | `>=2.31.0` | instalada |
| Frontend (CDN) | Bootstrap 5.3.3, Bootstrap Icons 1.11.3, Chart.js, QRCode.js, Plus Jakarta Sans | — | servidos via CDN (`app/web/templates/base.html`) |

**Servidor:** Uvicorn iniciado por `run.py` (`uvicorn.run("app.main:app", host, port, reload=False)`).
**Porta padrão:** `8000` (`APP_PORT` em `app/config.py`); host padrão `127.0.0.1` (`APP_HOST`).

---

## 3. Estrutura de diretórios

```text
sistema_patrimonio/
├── app/
│   ├── main.py                # Aplicação FastAPI: lifespan (init_db, admin, seed RBAC), montagem de /static e dos roteadores, handler central de HTTPException (403/404 amigáveis)
│   ├── config.py              # Único ponto de configuração: app, banco, autenticação (AUTH_*), AD (AD_*) via variáveis de ambiente
│   ├── database.py            # engine/SessionLocal/Base; get_db(); init_db(); _ensure_schema_migrations() (migração leve idempotente)
│   ├── cli.py                 # CLI: stats, list, show, move, create-user
│   ├── api/                   # API REST /api/v1
│   │   ├── v1_router.py       # Agrega auth + demais roteadores (estes com require_api_auth)
│   │   ├── deps.py            # require_api_auth, require_web_auth, require_permission (RBAC deny-by-default), stash_access
│   │   ├── auth_api.py        # /auth/login, /auth/logout, /auth/me
│   │   ├── assets_api.py      # Bens (CRUD, tag, timeline, depreciação, import CSV)
│   │   ├── movements_api.py   # Movimentações (list, get, term, create)
│   │   ├── custodians_api.py  # Colaboradores (CRUD, bens sob custódia, import CSV)
│   │   ├── locations_api.py   # Locais (CRUD)
│   │   └── reports_api.py     # dashboard-stats + 3 exportações CSV
│   ├── models/                # 16 modelos SQLAlchemy + enums.py (fonte de verdade das tabelas)
│   ├── schemas/               # Schemas Pydantic v2 (Create/Update/Read por entidade; user.py para /auth/me)
│   ├── services/              # 17 módulos de regra de negócio (ver §8 e INVENTARIO_TECNICO.md)
│   └── web/
│       ├── routes.py          # Páginas de negócio + login/logout + configuração Jinja2Templates (context processor _inject_current_user, função can())
│       ├── admin_routes.py    # /admin/users*, /admin/roles*, /admin/audit, /profile/password, /admin/ad*
│       ├── help_routes.py     # /ajuda e /ajuda/{article_id}
│       ├── templates/         # 33 templates Jinja2 (base.html, dashboard, assets/, movements/, custodians/, locations/, maintenances/, reports/, admin/, ajuda/, profile/, 403/404, login)
│       └── static/
│           ├── css/style.css  # CSS customizado (tema claro/escuro)
│           └── js/main.js     # Dark mode, tooltips, alertas, contadores animados, sidebar mobile
├── data/
│   └── patrimonio.db          # Banco SQLite (criado no primeiro start; NÃO versionar dados reais)
├── tests/                     # Suite pytest: 9 arquivos, 110 testes
├── docs/                      # Esta documentação
├── seed_demo.py               # Carga de demonstração (recria as tabelas: drop_all + create_all)
├── run.py                     # Ponto de entrada do servidor (uvicorn)
└── requirements.txt           # Dependências (mínimos)
```

**Por que a estrutura existe:** a separação `api/` × `web/` × `services/` × `models/` é real e
usada em toda a aplicação — as rotas **não** falam com o banco diretamente (exceto consultas
simples em `admin_routes.py`, que usam `db.query(User)`/`db.query(ADGroupRole)` inline), elas
chamam serviços ou fazem operações curtas de ORM na própria rota.

---

## 4. Ponto de entrada e inicialização

### Comandos

```bash
python run.py        # servidor web + API (fluxo principal)
python -m app.cli    # CLI (stats, list, show, move, create-user)
python seed_demo.py  # DEMO: apaga e recria todas as tabelas + dados de exemplo
pytest               # suíte de testes
```

### Fluxo de inicialização (real, `run.py` → `app/main.py`)

```text
python run.py
  ↓
init_db()  (app/database.py)
  ├── Base.metadata.create_all() — cria tabelas novas (importa app.models para registrá-las)
  └── _ensure_schema_migrations() — ALTER TABLE ADD COLUMN condicionais (idempotente, só SQLite)
  ↓
uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=False)
  ↓ (startup — lifespan em app/main.py)
init_db() (novamente, idempotente)
  ↓
ensure_admin_user(db)  — cria o admin inicial SOMENTE se AUTH_ADMIN_PASSWORD estiver definida
  ↓
ensure_default_roles(db) — seed idempotente do catálogo de permissões (PERMISSION_CATALOG)
                           e dos 7 perfis padrão (DEFAULT_ROLES)
  ↓
App pronta: /static montado, roteadores incluídos, handler 403/404 registrado
  ↓
Servidor em http://APP_HOST:APP_PORT  ·  Swagger em /docs  ·  health em /health
```

### Migração de esquema (`app/database.py::_ensure_schema_migrations`)

Mecanismo **leve e idempotente** baseado em `PRAGMA table_info(...)` + `ALTER TABLE ... ADD COLUMN`:

- `users`: `failed_login_attempts`, `locked_until`, `ad_object_guid`, `ad_dn`, `ad_last_sync`
- `user_roles`: `assigned_by` (default `'local'`)

`Base.metadata.create_all` cria as tabelas quando não existem. **Não há** sistema de migrations
com versionamento (nenhum Alembic ou equivalente no código).

---

## 5. Arquitetura da aplicação

Arquitetura real: **camadas por responsabilidade** (rotas → serviços → modelos), com duas
interfaces de entrada (web e API) compartilhando os mesmos serviços.

```text
┌─────────────────────────────┐   ┌──────────────────────────────┐
│  Interface Web (Jinja2)     │   │  API REST (/api/v1, FastAPI) │
│  app/web/routes.py          │   │  app/api/*_api.py            │
│  app/web/admin_routes.py    │   │                              │
│  app/web/help_routes.py     │   │                              │
└──────────────┬──────────────┘   └───────────────┬──────────────┘
               │   deps: require_web_auth         │  deps: require_api_auth
               │   + require_permission(...)      │  + require_permission(...)
               └──────────────┬───────────────────┘
                              ↓
        Autenticação (app/services/auth_provider.py::resolve_authentication)
             LocalAuthProvider (PBKDF2)  ·  ADAuthProvider (LDAP)
                              ↓
        Sessão server-side (session_service.py; hash SHA-256 do token no banco)
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Services (regras de negócio)                                        │
│ asset_service · movement_service · maintenance_service ·            │
│ custodian_service · location_service · dashboard_service ·          │
│ report_service · import_service · custodian_import_service ·        │
│ permission_service (RBAC) · audit_service · help_service ·          │
│ auth_service · session_service · auth_provider · ad_service/ad_ldap │
└──────────────────────────────┬──────────────────────────────────────┘
                               ↓
        Models (SQLAlchemy, app/models/*) → SQLite (data/patrimonio.db)
```

Observações factuais sobre a arquitetura:

- **Autorização** acontece sempre nas dependências das rotas (`require_permission`, `app/api/deps.py`).
- **Auditoria** é chamada dentro das rotas (não nos services) para as ações de negócio;
  no fluxo AD a auditoria é feita dentro do próprio serviço (`ad_service.py`).
- Não existe camada de "repositories" separada nem injeção de dependência além das
  dependências nativas do FastAPI.

---

## 6. Banco de dados

| Item | Valor |
|---|---|
| Banco | SQLite em arquivo: `data/patrimonio.db` (default de `DATABASE_URL` em `app/config.py`) |
| Acesso | SQLAlchemy 2 (`create_engine` + `sessionmaker`); `check_same_thread=False` para SQLite |
| Sessão por request | `app.database.get_db` (dependency FastAPI) |
| Migrações | `Base.metadata.create_all` + `_ensure_schema_migrations()` (ALTER TABLE condicional; sem Alembic) |
| Inicialização | Automática no start (`run.py` e lifespan de `main.py`) |
| Dados padrão | Catálogo de permissões + 7 perfis padrão (`ensure_default_roles`); admin inicial via env (opcional) |

### Modelo de dados (16 tabelas)

Relacionamentos conforme definidos nos modelos (`app/models/`):

```text
RBAC / acesso
  User ──< UserRole >── Role ──< RolePermission >── Permission
  User ──< UserSession                     (1:N, CASCADE)
  User ──< AuditLog                        (FK user_id com ondelete SET NULL)

Integração AD
  ADSettings (singleton id=1)              — configuração da integração
  ADGroupRole >── Role                     — Grupo AD → Perfil EXISTENTE

Patrimônio
  Asset >── Location                       (location_id, opcional)
  Asset >── Custodian                      (custodian_id, opcional)
  Asset ──< Movement                       (CASCADE; trilha imutável do fluxo)
  Asset ──< Maintenance                    (CASCADE; ordens de serviço)
  Movement >── Location (origem/destino)   (FKs + snapshots de nome em texto)
  Movement >── Custodian (origem/destino)  (FKs + snapshots de nome em texto)
```

### Tabelas e chaves (resumo)

| Tabela | Modelo | Chaves/índices relevantes |
|---|---|---|
| `users` | `User` | `username` unique+índice; `ad_object_guid` índice; colunas de lockout e AD |
| `user_sessions` | `UserSession` | `token_hash` unique+índice (SHA-256 do token; nunca o token puro); `expires_at` índice |
| `roles` | `Role` | `name` unique; `is_system` protege perfis padrão |
| `permissions` | `Permission` | `name` unique (`modulo.acao`), `module` índice |
| `user_roles` | `UserRole` | unique (`user_id`,`role_id`) `uq_user_role`; `assigned_by` (`local`/`ad`) |
| `role_permissions` | `RolePermission` | unique (`role_id`,`permission_id`) `uq_role_permission` |
| `audit_logs` | `AuditLog` | índices em `timestamp`, `user_id`, `action`, `module`; `previous_data`/`new_data` JSON em TEXT |
| `ad_settings` | `ADSettings` | singleton `id=1` |
| `ad_group_roles` | `ADGroupRole` | `group_name` unique `uq_ad_group_role_group`; `priority` (menor vence); `is_active` |
| `assets` | `Asset` | `tag` unique+índice; `serial_number` unique (nullable); FKs `locations.id`, `custodians.id` |
| `movements` | `Movement` | `movement_uuid` unique; FK `assets.id` CASCADE; snapshots origem/destino; `term_code` índice |
| `custodians` | `Custodian` | `registration_code` unique (matrícula); `email` unique |
| `locations` | `Location` | `name` unique |
| `maintenances` | `Maintenance` | FK `assets.id` CASCADE |
| `enums` | `app/models/enums.py` | `AssetStatus`, `AssetCondition`, `AssetCategory`, `MovementType`, `MaintenanceType`, `MaintenanceStatus` (colunas `Enum(...)` no banco) |

---

## 7. Usuários × Colaboradores (não confundir)

São **duas entidades diferentes com propósitos diferentes**:

| Aspecto | **Usuário** (`users` / `User`) | **Colaborador** (`custodians` / `Custodian`) |
|---|---|---|
| Finalidade | Login no sistema (autenticação + RBAC) | Custódia de bens patrimoniais |
| Criado por | Admin (tela), CLI (`create-user`), seed env, provisionamento AD (somente autorizado) | Admin (tela), API, importação CSV |
| Campos chave | `username`, `password_hash`, `is_admin`, `auth_provider`, `ad_object_guid` | `registration_code` (matrícula, unique), `email` (unique), `role` (cargo), `department` (setor) |
| Relacionamento | `user_roles`, `user_sessions`, `audit_logs` | `assets` (bens sob custódia) |
| Usa o sistema? | Sim — é quem acessa | Não necessariamente — pode existir só para custódia física |
| Vínculo entre si | **Não há FK direta** entre `users` e `custodians` | O vínculo AD→Colaborador é lógico (por e-mail/matrícula), registrado apenas em auditoria (`USUARIO_AD_VINCULADO_COLABORADOR`) |

**Impacto prático:**

- Bloquear (`is_active=False`) um **usuário** derruba as sessões válidas dele (a consulta
  `get_session_user` exige `User.is_active == True`) — não afeta a custódia de bens.
- Desativar um **colaborador** (`is_active=False`) não o remove das movimentações passadas
  (os snapshots de nome em `movements` preservam o histórico).
- Um colaborador pode ter bens e **nunca** logar no sistema; um usuário pode logar e não ter
  bens sob custódia.

---

## 8. Autenticação

### 8.1 Provedores (`app/services/auth_provider.py`)

```text
resolve_authentication(db, username, password)   ← usado pelas rotas de login
  1. username existe e auth_provider == 'local'  → LocalAuthProvider (senha nunca migra p/ AD)
  2. integração AD habilitada                    → ADAuthProvider (ad_service.authenticate_and_sync)
  3. AD habilitado? não e user é 'ad'            → None (sem senha local utilizável)
  4. caso contrário                              → LocalAuthProvider (compatibilidade)
```

> **Ponto de atenção:** a função `get_auth_provider()` existe em `auth_provider.py` e retorna o
> provedor conforme `AUTH_PROVIDER` (env), porém **nenhum ponto de login a utiliza** — os pontos
> de login chamam `resolve_authentication()`, que decide pelas regras acima. A variável
> `AUTH_PROVIDER` (default `local`) é lida em `app/config.py` mas o fluxo real de decisão é o
> de `resolve_authentication` (usuário local existente → local; caso contrário, se AD habilitado → AD).

### 8.2 Autenticação local (`app/services/auth_service.py`)

- Hash: `PBKDF2-HMAC-SHA256` (hashlib padrão), salt de 16 bytes, formato
  `pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>`; iterações default **600.000** (`AUTH_PBKDF2_ITERATIONS`).
- Verificação com `hmac.compare_digest` (resistente a timing).
- **Timing equalizado**: usuário inexistente verifica um hash "dummy" (`_DUMMY_HASH`).
- **Lockout**: após `AUTH_MAX_FAILED_ATTEMPTS` (5) falhas consecutivas, bloqueia a conta por
  `AUTH_LOCKOUT_SECONDS` (900 s); levanta `AccountLockedError` (HTTP 423 na API).
- Troca de senha própria (`change_password`) exige a senha atual e **invalida todas as sessões**;
  reset administrativo (`reset_password`) faz o mesmo.

### 8.3 Sessões (`app/services/session_service.py`, modelo `UserSession`)

- Token aleatório: `secrets.token_urlsafe(32)`, gravado no cookie.
- Banco guarda **apenas o hash SHA-256** do token (`token_hash`, unique).
- Cookie: nome `AUTH_COOKIE_NAME` (default `session`), `HttpOnly`, `SameSite=Lax`,
  `Secure` conforme `AUTH_COOKIE_SECURE`, `max_age = AUTH_SESSION_TTL` (28800 s = 8 h).
- Sessão expira no servidor (`expires_at`); `purge_expired_sessions` roda a cada `create_session`.
- Logout (`POST /logout`) revoga a sessão no servidor e limpa o cookie.

### 8.4 Middleware/dependências de proteção (`app/api/deps.py`)

- `require_web_auth` — aplicado aos roteadores web/admin/help no `main.py`; sem sessão →
  `HTTPException(303, Location: /login?next=...)` (paths públicos: `/login`, `/logout`).
- `require_api_auth` — aplicado a todos os roteadores de negócio do `/api/v1`; sem sessão → 401.
- `get_current_user` — resolve o usuário a partir do cookie + `user_sessions`.
- `stash_access` — pré-computa permissões/perfis em `request.state` (usada pelo menu dinâmico).
- `require_permission(perm)` — **fábrica de autorização** (ver §9).

### 8.5 Endpoints/páginas de login

| Entrada | Arquivo | Comportamento |
|---|---|---|
| `POST /api/v1/auth/login` | `app/api/auth_api.py` | 200 + cookie; 401 (credencial/perfil AD/conta desabilitada), 423 (lockout), 503 (AD indisponível). Audita `LOGIN`/`LOGIN_FALHA`/`LOGIN_BLOQUEADO`; falhas específicas do AD são auditadas dentro de `ad_service` |
| `POST /login` (web) | `app/web/routes.py::login_submit` | Redireciona 303 para `_safe_next_url(next)` (só caminhos internos — anti open redirect); erros AD exibem mensagem na tela |
| `POST /api/v1/auth/logout` e `POST /logout` | `auth_api.py` / `routes.py` | Revogam a sessão no servidor |
| `GET /api/v1/auth/me` | `auth_api.py` | `UserWithPermissions` (usuário + lista de permissões efetivas) |

---

## 9. RBAC — Perfis e Permissões

Implementação em `app/services/permission_service.py`. Regra: **deny by default**.

### Modelo

```text
User ──< UserRole >── Role ──< RolePermission >── Permission
                                    (N:N)            (N:N)
```

- `UserRole.assigned_by`: `'local'` (interface/CLI) ou `'ad'` (sincronização AD).
- **Superusuário**: flag legado `users.is_admin` ignora TODAS as verificações
  (`user_has_permission` retorna `True` direto; `get_user_permission_names` retorna o
  catálogo inteiro). `ensure_default_roles` atribui o perfil Administrador a quem tem `is_admin=True`.

### Catálogo de permissões (29, em `PERMISSION_CATALOG` — fonte única)

| Módulo | Permissões |
|---|---|
| Patrimônio | `patrimonio.visualizar`, `patrimonio.criar`, `patrimonio.editar`, `patrimonio.excluir` |
| Movimentação | `movimentacao.visualizar`, `movimentacao.criar`, `movimentacao.editar`, `movimentacao.cancelar` |
| Manutenção | `manutencao.visualizar`, `manutencao.criar`, `manutencao.editar`, `manutencao.finalizar` |
| Colaboradores | `colaboradores.visualizar`, `colaboradores.criar`, `colaboradores.editar` |
| Locais | `locais.visualizar`, `locais.criar`, `locais.editar` |
| Usuários | `usuarios.visualizar`, `usuarios.criar`, `usuarios.editar`, `usuarios.bloquear` |
| Perfis | `perfis.visualizar`, `perfis.criar`, `perfis.editar`, `perfis.excluir` |
| Relatórios | `relatorios.visualizar`, `relatorios.exportar` |
| Auditoria | `auditoria.visualizar` |

> Nota factual: `patrimonio.excluir`, `movimentacao.editar` e `movimentacao.cancelar` existem no
> catálogo (e no seed do Administrador), mas **não há endpoint/rota que os exija** no código atual —
> não existe rota de exclusão de bem nem de edição/cancelamento de movimentação.

### Perfis padrão (seed idempotente, `DEFAULT_ROLES`)

`Administrador` (todas), `Gestor de TI`, `Técnico de TI`, `Patrimônio`, `Almoxarifado`,
`Auditor`, `Consulta` — todos `is_system=True` (não podem ser excluídos; `delete_role` levanta
`ValueError`). O seed só popula permissões se o perfil estiver **vazio** (preserva ajustes do admin).

### Verificações de autorização — onde acontecem

1. **Backend (fonte da verdade):** `require_permission("modulo.acao")` nas rotas
   (factory em `app/api/deps.py`):
   - não autenticado → 401 (API) ou 303 → `/login` (web);
   - sem permissão → **403** + auditoria `ACESSO_NEGADO` (com módulo, permissão e path);
   - `is_admin` → bypass.
2. **Apresentação (apenas visual):** templates usam `can('modulo.acao')` (context processor
   `_inject_current_user` em `app/web/routes.py`) para esconder menus/botões.

### Regras administrativas codificadas (`app/web/admin_routes.py`)

- Usuário **não pode bloquear a si mesmo** (`toggle-active`).
- **Último administrador ativo** não pode perder acesso (`_guard_remove_admin_access`,
  `_count_active_admins`) — nem por remoção do perfil, nem por desativação.
- A tela `/admin/ad` exige `is_admin` **ou** (`usuarios.editar` **e** `perfis.editar`)
  (`_ad_admin_guard`).

---

## 10. Integração Active Directory (LDAP/LDAPS)

Implementação dividida em duas camadas:

- **`app/services/ad_ldap.py`** — protocolo puro (ldap3): conexão, bind, busca, parsing de atributos.
- **`app/services/ad_service.py`** — regras de negócio da integração: mapeamento grupo→perfil,
  provisionamento, sincronização de perfil, auditoria.

### 10.1 Configuração

- Persistida na tabela `ad_settings` (singleton `id=1`), editada na tela **Administração →
  Integração AD** (`/admin/ad`).
- Variáveis de ambiente (`app/config.py`) funcionam como **fallback** dos campos vazios:
  `AD_SERVER`, `AD_PORT` (636), `AD_USE_SSL`, `AD_BASE_DN`, `AD_USER_DN` (`search_dn`),
  `AD_GROUP_BASE_DN` (reservado, sem uso no fluxo), `AD_BIND_USER` e `AD_BIND_PASSWORD`
  (legado: a autenticação atual **não** usa conta de serviço — ver 10.2).
- Campos da tela: `enabled`, `server`, `port`, `use_ldaps`, `verify_tls`, `base_dn`, `search_dn`,
  `bind_user` (legado, sem função), `timeout_seconds`, `auto_create_user`, `link_by_email`,
  `group_role_priority`, `disabled_behavior`.
- Integração ativa = `enabled AND server AND base_dn` (`ad_service.ad_enabled`).

### 10.2 Autenticação no AD (bind direto do usuário)

`ad_ldap.authenticate_ad(settings, username, password)`:

```text
usuario  →  UPN derivado da Base DN (_normalize_username): usuario@dominio
             (UPN digitado ou DOMÍNIO\sam passam intocados)
   ↓
Bind SIMPLE direto com a CONTA DO USUÁRIO (sem conta de serviço)
   ├── LDAPBindError → credencial inválida → retorna None
   └── OK → busca na MESMA conexão autenticada
        (filtro (&(objectClass=person)(sAMAccountName=...)), escopo SUBTREE,
         base = search_dn ou base_dn)
   ↓
Atributos lidos: sAMAccountName, mail, displayName/cn, objectGUID (binário→
string canônica _canonical_guid), userAccountControl (bit 0x2 = ACCOUNTDISABLE),
memberOf (grupos), distinguishedName
   ↓
ADUser(username, display_name, email, dn, guid, enabled, groups[DNs])
```

Erros: `ADError` (comunicação/configuração). Timeout obrigatório
(`connect_timeout`/`receive_timeout` = `timeout_seconds`, default 10).
LDAPS valida o certificado quando `verify_tls=True` (`Tls(validate=1)`); a desativação é
explícita na tela, nunca silenciosa.

`test_connection(settings)` (tela `/admin/ad/test`) valida TCP/TLS + RootDSE/naming contexts,
sem bind e sem credenciais.

### 10.3 Fluxo completo do login AD (`ad_service.authenticate_and_sync`)

```text
resolve_authentication → ADAuthProvider → authenticate_and_sync(db, username, password, ip)
   ↓
ad_ldap.authenticate_ad
   ├── None          → auditoria LOGIN_AD_FALHA → ADAuthenticationError (401)
   ├── ADError       → auditoria FALHA_COMUNICACAO_AD → ADUnavailableError (503)
   └── ADUser
        ↓
Conta desabilitada (enabled=False)? → auditoria CONTA_AD_DESABILITADA (DENIED) → 401
        ↓
resolve_role_for_groups(db, ad_user.groups)   ← ANTES de qualquer provisionamento
  CN dos DNs de memberOf → compara com ad_group_roles (is_active)
  Vencedor: CSV group_role_priority (ordem do admin) OU menor priority (empate: menor id)
  Sem match → (None, None, [])
        ↓
role_id is None (SEM grupo autorizado/mapeado)?
  → auditoria GRUPO_AD_SEM_MAPEAMENTO (DENIED, user=None) com:
    nome, identificador_ad (objectGUID), grupos identificados,
    grupos_autorizados=NENHUM, perfil=NENHUM, motivo=NENHUM_GRUPO_AD_MAPEADO
  → ADNoProfileError (401)
  → NÃO cria usuário, NÃO cria colaborador, NÃO atribui perfil/permissões, NÃO cria sessão
        ↓
Autorizado:
  _upsert_ad_user  — localiza por objectGUID → username → email;
                     cria SOMENTE se settings.auto_create_user (se falso: audita
                     GRUPO_AD_SEM_MAPEAMENTO motivo PROVISIONAMENTO_DESABILITADO e nega);
                     atualiza full_name/email/guid/dn/ad_last_sync; auth_provider='ad';
                     password_hash='!ad-external' (bloqueia login local);
                     auditoria USUARIO_AD_PROVISIONADO (se criado)
  _link_custodian  — vincula ao COLABORADOR EXISTENTE por e-mail, senão matrícula==username;
                     nunca cria colaborador; auditoria USUARIO_AD_VINCULADO_COLABORADOR
  auditoria GRUPOS_AD_IDENTIFICADOS (todos os grupos)
  _assign_ad_role  — aplica o perfil do mapeamento com assigned_by='ad';
                     remove perfis anteriores atribuídos via AD; NUNCA remove perfis
                     manuais ('local'); auditoria PERFIL_SINCRONIZADO_AD
  auditoria LOGIN_AD_AUTORIZADO (SUCCESS: grupos, grupo vencedor, perfil)
        ↓
retorna User → rota cria a sessão normalmente (RBAC interno passa a valer)
```

**Regra central implementada:** autenticação AD **não** concede acesso. Acesso somente com
grupo AD explicitamente mapeado para um perfil **existente**; usuário do domínio sem grupo
mapeado permanece fora do banco (apenas auditoria).

### 10.4 Mapeamento Grupo AD → Perfil (`ad_group_roles`)

- `group_name` = CN do grupo (ex.: `GRP-SISPAT-TECNICOS-TI`); unique.
- `role_id` referencia um perfil **existente** (nunca cria perfil).
- `priority`: menor vence; `ADSettings.group_role_priority` (CSV de nomes) sobrepõe a prioridade numérica.
- `is_active=False` desativa o mapeamento sem apagá-lo.

### 10.5 Auditoria da integração (eventos AD, definidos em `audit_service.py`)

`LOGIN_AD`, `LOGIN_AD_AUTORIZADO`, `LOGIN_AD_FALHA`, `CONTA_AD_DESABILITADA`,
`USUARIO_AD_PROVISIONADO`, `USUARIO_AD_VINCULADO_COLABORADOR`, `GRUPOS_AD_IDENTIFICADOS`,
`GRUPO_AD_SEM_MAPEAMENTO`, `PERFIL_SINCRONIZADO_AD`, `CONFLITO_GRUPOS_AD` (constante definida;
sem uso no fluxo atual), `FALHA_COMUNICACAO_AD`, `ALTERACAO_CONFIG_AD`, `TESTE_CONEXAO_AD`.

**Nenhuma senha/credencial é persistida, logada ou auditada** (a senha existe apenas no bind;
os testes `test_ad_failed_login_audited` verificam a ausência da senha na trilha).

---

## 11. Auditoria

### Implementação (`app/services/audit_service.py`, modelo `AuditLog`, tabela `audit_logs`)

- Função central: `write_audit(...)` — grava e faz commit imediato (cada evento é uma transação).
- `write_change_audit(...)` — compara `before`/`after` e gera descrição automática dos campos alterados
  (`changed_fields` → `{"campo": {"de": ..., "para": ...}}`).
- Somente-leitura: **não existe rota de escrita/exclusão**; consulta exige `auditoria.visualizar`
  (`/admin/audit`, filtros via `get_audit_logs`: search, module, action, result, user_id, datas).

### Estrutura do registro

`timestamp` (UTC), `user_id` (FK, `SET NULL` na exclusão do usuário) + `username` (snapshot
que sobrevive à exclusão), `action`, `module`, `resource`, `resource_id`, `resource_ref`,
`ip_address`, `result` (`SUCCESS | FAILURE | DENIED | LOCKED`), `description`,
`previous_data`/`new_data` (JSON em TEXT).

### Eventos registrados (constantes de `audit_service.py`)

| Categoria | Ações |
|---|---|
| Autenticação | `LOGIN`, `LOGIN_FALHA`, `LOGIN_BLOQUEADO`, `LOGOUT` |
| CRUD genérico | `CRIACAO`, `ALTERACAO`, `EXCLUSAO` |
| Administração | `BLOQUEIO`, `DESBLOQUEIO`, `RESET_SENHA`, `TROCA_SENHA`, `ALTERACAO_PERFIL` |
| Perfis | `CRIACAO_PERFIL`, `ALTERACAO_PERFIL_PERMISSOES`, `EXCLUSAO_PERFIL` |
| Negócio | `MOVIMENTACAO`, `MANUTENCAO`, `IMPORTACAO` |
| Segurança | `ACESSO_NEGADO` (403 de `require_permission`) |
| Integração AD | ver §10.5 (13 eventos) |

### O que NÃO deve ser registrado (regra do código)

Senhas, tokens, segredos, bind password. A auditoria registra o **resultado** da operação,
nunca a credencial utilizada. Testes cobrem a ausência de senha na trilha (`tests/test_ad.py`).

### Retenção

Não existe rotina de expurgos/retenção de logs no código — `não identificado no código analisado`
(nenhum mecanismo implementado).

---

## 12. Módulos funcionais — detalhamento

### 12.1 Patrimônio (Assets)

- **Arquivos:** `app/api/assets_api.py`, `app/web/routes.py` (seção ASSETS),
  `app/services/asset_service.py`, `app/services/import_service.py`, `app/models/asset.py`,
  templates `assets/*.html`.
- **Permissões:** `patrimonio.visualizar` / `patrimonio.criar` / `patrimonio.editar`.
- **Regras reais do código:**
  - `tag` única (normalizada para maiúsculas); `serial_number` único quando informado.
  - Todo cadastro gera automaticamente a movimentação `ENTRADA_AQUISICAO` com termo
    `TR-INIC-<ano>-<id>` e status inicial `EM_USO` (se custodiante) ou `DISPONIVEL`.
  - Alteração de `condition` via `AssetService.update` gera movimentação `ATUALIZACAO_ESTADO`.
  - **Depreciação linear**: `calculate_depreciation(asset, annual_rate=0.20)` — 20%/ano (5 anos),
    cálculo por meses, valor mínimo zero.
  - **Importação CSV** (`import_service.py`): delimitador detectado (`;` ou `,`), aliases de
    colunas extensivos (`COLUMN_ALIASES`), categorias/condições normalizadas de texto livre,
    valores BR (`1.234,56`), datas `DD/MM/AAAA` ou `AAAA-MM-DD`; fluxo web em duas etapas
    (preview → confirm) e endpoint direto `/api/v1/assets/import/csv`; opção
    `skip_duplicates` (ignora ou **atualiza** o existente).

### 12.2 Fluxo & Movimentação

- **Arquivos:** `app/services/movement_service.py`, `app/api/movements_api.py`,
  `app/web/routes.py` (seção MOVEMENTS), `app/models/movement.py`.
- **Permissões:** `movimentacao.visualizar` / `movimentacao.criar`.
- **Motor (`create_movement`):** transação única que (1) valida o bem (não movimenta `BAIXADO`),
  (2) tira snapshots de origem, (3) aplica a regra do tipo:

| Tipo | Regra aplicada |
|---|---|
| `ALOCACAO_CAUTELA` | exige `destination_custodian_id`; status → `EM_USO` |
| `TRANSFERENCIA_LOCAL` | exige `destination_location_id`; status `EM_USO` se tiver custodiante, senão `DISPONIVEL` |
| `DEVOLUCAO_ESTOQUE` | limpa custodiante; status → `DISPONIVEL` |
| `ENVIO_MANUTENCAO` | status → `EM_MANUTENCAO` |
| `RETORNO_MANUTENCAO` | status → `DISPONIVEL` (ou `EM_USO` se custodiante informado) |
| `BAIXA_DESCARTE` | status → `BAIXADO`; limpa custodiante; condição default `INSERVIVEL` |
| `ATUALIZACAO_ESTADO` | mantém status/origem; registra troca de condição |

  (4) grava o registro imutável com `previous_*`/`new_*`; (5) gera `term_code`
  (`TR-<ano>-<seq>`) quando `generate_term` **ou** tipo ∈ {ALOCACAO_CAUTELA, DEVOLUCAO_ESTOQUE}.
  O formulário web envia `generate_term=True` sempre; a API usa o default `True` do schema.
- **Termo de Responsabilidade:** `get_term_details` monta o documento com dados da empresa
  (constantes `COMPANY_NAME/CNPJ/ADDRESS` de `config.py`), bem, custodiante e local;
  páginas web `/movements/{id}/term` e API `/api/v1/movements/{id}/term`.

### 12.3 Manutenções

- **Arquivos:** `app/services/maintenance_service.py`, `app/web/routes.py` (seção MAINTENANCES),
  `app/models/maintenance.py`.
- **Permissões:** `manutencao.visualizar` / `manutencao.criar` / `manutencao.finalizar`
  (não há rota para `manutencao.editar` — a permissão existe apenas no catálogo).
- **Fluxo real:** `create` abre a OS (status `EM_ANDAMENTO`) **e** registra `ENVIO_MANUTENCAO`
  no fluxo do bem; `complete_maintenance` conclui (status `CONCLUIDA`, `end_date`, solução, custo)
  **e** registra `RETORNO_MANUTENCAO`.

### 12.4 Colaboradores & Locais

- **Arquivos:** `custodian_service.py`, `location_service.py`, `custodian_import_service.py`,
  `app/api/custodians_api.py`, `app/api/locations_api.py`, templates `custodians/`, `locations/`.
- **Permissões:** `colaboradores.*`, `locais.*`.
- **Regras reais:** matrícula e e-mail únicos (matrícula normalizada para maiúsculas, e-mail
  para minúsculas na importação); `count_assigned_assets` exclui bens `BAIXADO`; importação CSV
  de colaboradores valida e-mail por regex, converte `ativo` (sim/não/true/false/1/0/ativo/inativo)
  e aceita atualização por matrícula (protegendo colisões de e-mail).

### 12.5 Dashboard & Relatórios

- **Arquivos:** `dashboard_service.py`, `report_service.py`, `app/api/reports_api.py`,
  templates `dashboard.html`, `reports/*.html`.
- **Permissões:** `relatorios.visualizar` (dashboard-stats e páginas) e `relatorios.exportar` (CSV).
- **CSVs:** inventário (com depreciação), movimentações e colaboradores — separador `;`,
  `utf-8-sig` (abre direto no Excel).

### 12.6 Administração

- **Arquivos:** `app/web/admin_routes.py` + templates `admin/**`.
- **Páginas:** usuários (`/admin/users*`), perfis (`/admin/roles*`), auditoria (`/admin/audit`),
  troca de senha própria (`/profile/password`), integração AD (`/admin/ad*`).
- Permissões: ver tabela em §9 e regras administrativas (último admin, auto-bloqueio).

### 12.7 Central de Ajuda

- **Arquivos:** `app/services/help_service.py` (conteúdo: `ARTICLES`, `FAQ`, `CATEGORIES`),
  `app/web/help_routes.py`, templates `ajuda/`.
- `/ajuda` e `/ajuda/{article_id}`; artigos `audience="admin"` exigem uma das permissões
  `usuarios.visualizar`, `perfis.visualizar`, `auditoria.visualizar`. Busca client-side via
  `serialize_search_index()`.

---

## 13. Frontend

- **Motor:** Jinja2 (`Jinja2Templates` do FastAPI) com **context processor**
  `_inject_current_user` — todo template recebe `current_user`, `user_permissions`, `user_roles`
  e a função `can(perm)`.
- **Layout:** `templates/base.html` — Bootstrap 5.3.3 + Bootstrap Icons 1.11.3 + Chart.js +
  QRCode.js via CDN, Google Fonts (Plus Jakarta Sans), `/static/css/style.css` e `/static/js/main.js`.
- **JS (`main.js`):** tema claro/escuro (localStorage `sispatrim-theme`, sincronizado com
  `data-bs-theme`), tooltips Bootstrap, auto-dismiss de alertas, contadores animados, sidebar mobile.
- **Gráficos:** `dashboard.html` usa `Chart(...)` (pizza de categorias; barras conforme o template).
- **QR Code:** `assets/detail.html` renderiza QRCode apontando para a rota do termo
  (testado por `test_term_page_qr_code_points_to_term_route`).
- **Onde mexer em cada tela:** templates em `app/web/templates/<módulo>/` + handler em
  `app/web/routes.py` (ou `admin_routes.py`). Menu/botões condicionais usam
  `{% if can('modulo.acao') %}` — **a segurança real está no backend** (`require_permission`).

---

## 14. Rotas e endpoints (inventário real)

### API REST `/api/v1` (Swagger em `/docs`)

Autenticação por cookie de sessão. `login`/`logout` são públicos; **todo o restante** exige
`require_api_auth` + a permissão indicada.

| Método | URL | Função (arquivo) | Permissão |
|---|---|---|---|
| POST | `/api/v1/auth/login` | `api_login` (`auth_api.py`) | pública |
| POST | `/api/v1/auth/logout` | `api_logout` | pública |
| GET | `/api/v1/auth/me` | `api_me` | autenticado |
| GET | `/api/v1/assets` | `list_assets` | `patrimonio.visualizar` |
| POST | `/api/v1/assets` | `create_asset` (201) | `patrimonio.criar` |
| GET | `/api/v1/assets/{id}` | `get_asset` | `patrimonio.visualizar` |
| PUT | `/api/v1/assets/{id}` | `update_asset` | `patrimonio.editar` |
| GET | `/api/v1/assets/tag/{tag}` | `get_asset_by_tag` | `patrimonio.visualizar` |
| GET | `/api/v1/assets/{id}/timeline` | `get_asset_timeline` | `patrimonio.visualizar` |
| GET | `/api/v1/assets/{id}/depreciation` | `get_asset_depreciation` | `patrimonio.visualizar` |
| POST | `/api/v1/assets/import/csv` | `import_csv_api` | `patrimonio.criar` |
| GET | `/api/v1/movements` | `list_movements` | `movimentacao.visualizar` |
| POST | `/api/v1/movements` | `record_movement` (201) | `movimentacao.criar` |
| GET | `/api/v1/movements/{id}` | `get_movement` | `movimentacao.visualizar` |
| GET | `/api/v1/movements/{id}/term` | `get_movement_term` | `movimentacao.visualizar` |
| GET | `/api/v1/custodians` | `list_custodians` | `colaboradores.visualizar` |
| POST | `/api/v1/custodians` | `create_custodian` (201) | `colaboradores.criar` |
| GET | `/api/v1/custodians/{id}` | `get_custodian` | `colaboradores.visualizar` |
| PUT | `/api/v1/custodians/{id}` | `update_custodian` | `colaboradores.editar` |
| GET | `/api/v1/custodians/{id}/assets` | `get_custodian_assets` | `colaboradores.visualizar` |
| POST | `/api/v1/custodians/import/csv` | `import_custodians_csv` | `colaboradores.criar` |
| GET | `/api/v1/locations` | `list_locations` | `locais.visualizar` |
| POST | `/api/v1/locations` | `create_location` (201) | `locais.criar` |
| GET | `/api/v1/locations/{id}` | `get_location` | `locais.visualizar` |
| PUT | `/api/v1/locations/{id}` | `update_location` | `locais.editar` |
| GET | `/api/v1/reports/dashboard-stats` | `get_dashboard_stats` | `relatorios.visualizar` |
| GET | `/api/v1/reports/inventory/csv` | `export_inventory_csv` | `relatorios.exportar` |
| GET | `/api/v1/reports/movements/csv` | `export_movements_csv` | `relatorios.exportar` |
| GET | `/api/v1/reports/custodians/csv` | `export_custodians_csv` | `relatorios.exportar` |

Códigos de erro padronizados: `400` (regra de negócio via `ValueError`), `401`, `403`,
`404`, `422` (validação Pydantic/CSV), `423` (lockout), `503` (AD indisponível).

### Interface web

| Método | URL | Handler | Permissão |
|---|---|---|---|
| GET | `/` | `view_dashboard` | autenticado |
| GET/POST | `/login` | `login_page` / `login_submit` | pública |
| POST | `/logout` | `logout` | autenticada |
| GET | `/assets` | `list_assets` | `patrimonio.visualizar` |
| GET | `/assets/new` | `form_new_asset` | `patrimonio.criar` |
| POST | `/assets/new` | `create_asset_form` | `patrimonio.criar` |
| GET/POST | `/assets/import` | importação (preview) | `patrimonio.criar` |
| POST | `/assets/import/confirm` | `confirm_import_assets` | `patrimonio.criar` |
| GET | `/assets/{id}` | `view_asset_detail` | `patrimonio.visualizar` |
| GET | `/movements` | `list_movements_view` | `movimentacao.visualizar` |
| GET/POST | `/movements/new` | nova movimentação | `movimentacao.criar` |
| GET | `/movements/{id}/term` | `view_movement_term` | `movimentacao.visualizar` |
| GET | `/custodians` | `list_custodians_view` | `colaboradores.visualizar` |
| GET/POST | `/custodians/new` | novo colaborador | `colaboradores.criar` |
| GET/POST | `/custodians/import` (+`/confirm`) | importação | `colaboradores.criar` |
| GET | `/custodians/{id}` | `view_custodian_detail` | `colaboradores.visualizar` |
| GET | `/locations` | `list_locations_view` | `locais.visualizar` |
| GET/POST | `/locations/new` | novo local | `locais.criar` |
| GET | `/maintenances` | `list_maintenances_view` | `manutencao.visualizar` |
| GET/POST | `/maintenances/new` | `create_maintenance_form` | `manutencao.criar` |
| POST | `/maintenances/{id}/complete` | `complete_maintenance_form` | `manutencao.finalizar` |
| GET | `/reports/inventory` · `/reports/movements` · `/reports/custodians` | páginas de relatório | `relatorios.visualizar` |
| GET | `/ajuda`, `/ajuda/{article_id}` | central de ajuda | autenticada (admin-artigos filtrados) |
| GET | `/admin` | `admin_index` (redireciona conforme permissão) | autenticada |
| GET | `/admin/users` | lista/pesquisa | `usuarios.visualizar` |
| GET/POST | `/admin/users/new` | criação | `usuarios.criar` |
| GET/POST | `/admin/users/{id}/edit` | edição (dados+perfis) | `usuarios.editar` |
| POST | `/admin/users/{id}/toggle-active` | bloquear/desbloquear | `usuarios.bloquear` |
| POST | `/admin/users/{id}/reset-password` | reset | `usuarios.editar` |
| GET | `/admin/roles` | perfis | `perfis.visualizar` |
| GET/POST | `/admin/roles/new` · `/admin/roles/{id}/edit` | perfis | `perfis.criar` / `perfis.editar` |
| POST | `/admin/roles/{id}/delete` | exclusão | `perfis.excluir` |
| GET | `/admin/audit` | trilha com filtros | `auditoria.visualizar` |
| GET | `/profile/password` | troca de senha própria | autenticada |
| GET | `/admin/ad` | tela Integração AD | `is_admin` ou (`usuarios.editar`+`perfis.editar`) |
| POST | `/admin/ad/settings` | salva configuração | idem |
| POST | `/admin/ad/test` | testa conexão | idem |
| POST | `/admin/ad/mappings` | cria/atualiza mapeamento | idem |
| POST | `/admin/ad/mappings/{id}/delete` | remove mapeamento | idem |
| GET | `/health` | health check (`main.py`) | pública |

---

## 15. Fluxos importantes (implementados)

### Login (local)

```text
Formulário/API → resolve_authentication → usuário local existente?
  → LocalAuthProvider.authenticate (PBKDF2; lockout após 5 falhas)
  → sessão criada (token_urlsafe; hash no banco) + cookie HttpOnly
  → auditoria LOGIN / LOGIN_FALHA / LOGIN_BLOQUEADO
  → redireciona para next (web) ou 200 (API)
```

### Login AD

```text
resolve_authentication (usuário não-local ou sem conta local)
  → ad_enabled? → ad_service.authenticate_and_sync
      bind direto do usuário → desabilitado? nega → grupos → mapeamento
      → sem mapeamento: nega (só auditoria, nada é criado)
      → com mapeamento: provisiona/vincula → aplica perfil existente → sessão
```

### Cadastro de equipamento

```text
Formulário/API → validação Pydantic (AssetCreate) → AssetService.create
  (tag/série únicas; status inicial; ENTRADA_AQUISICAO no fluxo)
  → auditoria CRIACAO (snapshot after)
```

### Movimentação

```text
Formulário/API → MovementCreate → MovementService.create_movement
  (valida bem; snapshots; aplica regra do tipo; termo TR-AAAA-NNNNN)
  → auditoria MOVIMENTACAO (before/after de status/condição)
  → redireciona para o termo (alocação/devolução pela web)
```

### Manutenção

```text
Abrir OS: MaintenanceService.create → OS EM_ANDAMENTO + ENVIO_MANUTENCAO no fluxo
Finalizar: complete_maintenance → CONCLUIDA + RETORNO_MANUTENCAO (bem volta a DISPONIVEL)
```

---

## 16. Regras de negócio identificadas no código

1. **Movimentação é a única forma de mudar custódia/local/status** — edição de bem (`AssetUpdate`)
   não altera `status`/`location_id`/`custodian_id` (o schema nem expõe esses campos).
2. **Bem baixado não pode ser movimentado** (`create_movement` levanta `ValueError`), exceto
   re-aquisição (guarda `!= ACQUISITION` no código).
3. **Alocação exige colaborador; transferência exige local** (`ValueError`).
4. **Tag e número de série são únicos**; tag é normalizada em maiúsculas.
5. **Depreciação linear fixa em 20% ao ano**, floor em zero.
6. **Termo gerado** para alocação/devolução (e sempre que `generate_term`), numeração
   `TR-<ano>-<sequencial>` (sequencial conta alocações+devoluções; aquisição usa prefixo `TR-INIC`).
7. **Deny by default**: usuário recém-criado sem perfil não acessa nada
   (testado por `test_login_user_without_profile_is_denied_by_default`).
8. **Último administrador ativo não pode perder acesso**; usuário não bloqueia a si mesmo.
9. **Troca/reset de senha invalida todas as sessões** do usuário.
10. **Login AD não concede acesso por si só** — só grupo mapeado para perfil existente;
    sem mapeamento: nada é criado no banco (nem usuário "pendente"), apenas auditoria.
11. **Sincronização AD nunca remove perfis manuais** (`assigned_by='local'`); perfis `'ad'`
    são substituídos conforme os grupos atuais.
12. **Perfis de sistema (`is_system`) não são excluíveis**; perfis atribuídos a usuários também não.
13. **Colaborador nunca é criado pela integração AD** — apenas vinculado se já existir.

---

## 17. Configuração e variáveis de ambiente (`app/config.py`)

> **Nunca documentar/copiar valores reais de segredos.** Abaixo apenas nome, finalidade e exemplo seguro.

| Variável | Padrão | Finalidade |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/patrimonio.db` | Conexão do SQLAlchemy |
| `APP_HOST` / `APP_PORT` | `127.0.0.1` / `8000` | Bind do servidor (`run.py`) |
| `AUTH_PROVIDER` | `local` | Lida em `config.py` e em `get_auth_provider()`; **o fluxo real de login usa `resolve_authentication()`** (ver §8.1) |
| `AUTH_SESSION_TTL` | `28800` | TTL da sessão (segundos) |
| `AUTH_COOKIE_NAME` | `session` | Nome do cookie |
| `AUTH_COOKIE_SECURE` | `false` | Cookie só em HTTPS quando `true` |
| `AUTH_PBKDF2_ITERATIONS` | `600000` | Iterações do hash de senha |
| `AUTH_MAX_FAILED_ATTEMPTS` | `5` | Falhas antes do lockout |
| `AUTH_LOCKOUT_SECONDS` | `900` | Duração do lockout |
| `AUTH_ADMIN_USERNAME` / `AUTH_ADMIN_NAME` | `admin` / `Administrador` | Admin inicial |
| `AUTH_ADMIN_PASSWORD` | *(vazio)* | Se definida, cria o admin no primeiro start (não versionar) |
| `AD_SERVER` | *(vazio)* | Host/IP do controlador de domínio (ex.: `dc01.empresa.local`) |
| `AD_PORT` | `636` | Porta LDAP/LDAPS |
| `AD_USE_SSL` | `false` | `true` = LDAPS |
| `AD_BASE_DN` | *(vazio)* | Base DN (ex.: `DC=empresa,DC=local`) |
| `AD_USER_DN` | *(vazio)* | DN de busca de usuários (escopo) |
| `AD_GROUP_BASE_DN` | *(vazio)* | Reservado — sem uso no fluxo atual |
| `AD_BIND_USER` / `AD_BIND_PASSWORD` | *(vazio)* | Legado — a autenticação atual usa bind direto do usuário; campos mantidos por compatibilidade |

Constantes não-env: `APP_NAME`, `APP_VERSION`, `APP_DESCRIPTION`, `COMPANY_NAME`,
`COMPANY_CNPJ`, `COMPANY_ADDRESS` (usadas no Termo de Responsabilidade).

---

## 18. Segurança — mecanismos existentes

| Mecanismo | Implementação |
|---|---|
| Senhas locais | PBKDF2-HMAC-SHA256, salt por usuário, 600k iterações, só stdlib |
| Timing attack / enumeração | hash dummy + `hmac.compare_digest`; lockout com timing equalizado |
| Sessões | token aleatório 32 bytes; só hash SHA-256 no banco; expiração no servidor; revogação no logout; bloqueio de usuário invalida sessão |
| Cookies | HttpOnly, SameSite=Lax, Secure opcional |
| Força bruta | lockout por conta (5 falhas / 15 min), `423` na API, evento `LOGIN_BLOQUEADO` |
| RBAC | deny by default, validado no backend em toda rota; 403 auditado (`ACESSO_NEGADO`) |
| AD/LDAP | bind direto com a conta do usuário; senha nunca persistida/logada; timeout obrigatório; LDAPS com validação TLS (desativação explícita); conta desabilitada (`userAccountControl` bit 0x2) nega acesso |
| Open redirect | `next` do login aceita apenas caminhos internos (`_safe_next_url`) |
| SQL Injection | SQLAlchemy com parâmetros vinculados (queries via ORM/filtros) |
| XSS | Jinja2 com autoescape padrão (Jinja2Templates); valores dinâmicos escapados |
| Auditoria | imutável na prática (sem rotas de escrita/exclusão), antes/depois em JSON |

### Pontos de atenção identificados (somente registro — NÃO corrigir nesta documentação)

1. **Sem proteção CSRF explícita** nos formulários web (não há token CSRF no código); o cookie
   `SameSite=Lax` mitiga parte do risco, mas o mecanismo não está implementado.
2. **`AUTH_PROVIDER` não governa o fluxo real de login** — `get_auth_provider()` não é chamado
   pelos pontos de login (ver §8.1). Configurável apenas no papel.
3. **Variáveis `AD_BIND_USER`/`AD_BIND_PASSWORD` e campos `bind_user` são legados** — lidos em
   `config.py`/model, mas sem função no fluxo de autenticação atual (bind direto).
4. `README.md` mantém um trecho antigo na seção Segurança mencionando "dois binds distintos
   (busca vs. autenticação)", que descreve a implementação anterior de conta de serviço.
5. **Inconsistência de datas**: `asset_service.py` e `movement_service.py` usam `datetime.now()`
   (hora local) enquanto `auth_service.py`, `session_service.py` e os modelos usam `datetime.utcnow()`.
6. **`help_service.py` (FAQ)** informa que a integração AD "ainda não está disponível", o que
   contradiz a implementação atual em `ad_ldap.py`/`ad_service.py`.
7. Permissões `patrimonio.excluir`, `movimentacao.editar`, `movimentacao.cancelar` e
   `manutencao.editar` existem no catálogo mas não são exigidas por nenhuma rota (não há
   exclusão de bem nem edição/cancelamento de movimentação implementados).
8. **`seed_demo.py` executa `drop_all`** — apaga todas as tabelas/dados antes de recriar; usar
   apenas em banco de teste/demo.
9. Sem `LICENSE` no repositório.
10. `data/patrimonio.db` é versionado no repositório atual (arquivo binário alterado a cada
    execução local) — o README recomenda não versionar dados reais.

---

## 19. Testes

A suite de testes (9 arquivos, 110 testes) cobre autenticação, RBAC, integração AD (com LDAP mockado), API, movimentações, bens, importações e central de ajuda.

Execução: `pytest -v` (ou `python3 -m pytest tests/`).

### Execução

```bash
pytest -v
```

A suíte cobre: **controle de acesso** (`tests/test_rbac.py`): autorização por perfil em APIs e páginas, deny by default, menu dinâmico, bloqueio/desbloqueio de usuário, lockout por tentativas, auditoria, proteção do último administrador e tentativas de escalação de privilégios; **autenticação** (`tests/test_auth.py`); **integração AD** (`tests/test_ad.py`, com a camada LDAP mockada); movimentações, bens, importações e central de ajuda.

---

## 20. Segurança adicional

### Primeiro acesso protegido

O endpoint `/setup` é protegido por verificação de existência de usuários: só está disponível quando **não existem usuários** no banco e **não há** `AUTH_ADMIN_PASSWORD` configurada. Após a criação do primeiro administrador, o acesso a `/setup` é redirecionado para `/login`.

### Impasse de acesso resolvido

Antes da implementação do primeiro acesso web, uma instalação nova sem `AUTH_ADMIN_PASSWORD` ficava inacessível (impossível criar o primeiro usuário). Agora o fluxo web resolve esse impasse, mantendo as outras opções (variável de ambiente e CLI) como alternativas.

---

## 21. Primeiro Acesso (Setup Inicial)

### Quando o sistema considera que está em estado de primeira configuração

O sistema entra em estado de primeiro acesso quando **ambas** as condições são verdadeiras:
1. **Não existem usuários** no banco de dados (`users` vazio)
2. **`AUTH_ADMIN_PASSWORD` não está definida** (variável de ambiente vazia)

Nesse estado, o sistema oferece a tela de configuração inicial.

### Como o usuário acessa o fluxo

1. **Via link na tela de login**: na página `/login`, existe um link "Primeiro acesso" que redireciona para `/setup`
2. **Acesso direto**: acessando `/setup` diretamente no navegador

### Comportamento em instalações já configuradas

- Se **existirem usuários** no banco: o acesso a `/setup` é redirecionado para `/login`
- Se **`AUTH_ADMIN_PASSWORD` estiver definida**: o fluxo de primeiro acesso não está disponível (o admin foi criado automaticamente no start)

### Botão/link "Primeiro acesso"

O template `login.html` contém um link visível apenas em estado de primeiro acesso:
```html
<a href="/setup" class="text-decoration-none text-primary small fw-semibold">
    <i class="bi bi-person-plus me-1"></i> Primeiro acesso
</a>
```

### Criação do primeiro administrador

A tela `/setup` permite criar o primeiro administrador com:
- **Nome completo** (obrigatório)
- **Nome de usuário** (obrigatório)
- **E-mail** (opcional)
- **Senha** (obrigatória, mínimo 8 caracteres)
- **Confirmação de senha** (deve coincidir)

### Ausência de senha padrão ou temporária

**Não existe senha padrão ou temporária.** O administrador cria sua própria senha durante o primeiro acesso. A senha é hasheada com PBKDF2-HMAC-SHA256 antes de ser armazenada.

### Ausência de obrigatoriedade de troca de senha posteriormente

**Não há obrigatoriedade de troca de senha** após o primeiro login. O administrador pode usar a senha criada indefinidamente, até que opte por alterá-la voluntarymente em `/profile/password`.

### Proteção do endpoint de bootstrap

O endpoint `/setup` possui proteções:
- Verificação de estado de primeiro acesso em **cada requisição** (GET e POST)
- Se outro processo criar o usuário entre a verificação e o commit, a segunda requisição é redirecionada para `/login`
- A criação é atômica dentro de uma transação

### Impossibilidade de repetir a criação inicial

**Não é possível repetir a criação inicial** depois que o sistema já foi inicializado (primeiro administrador criado). O link "Primeiro acesso" desaparece e o acesso a `/setup` é redirecionado.

### Comportamento em situações concorrentes

O código utiliza verificação dentro da mesma requisição/commit:
```python
def _first_access_enabled(db: Session) -> bool:
    if AUTH_ADMIN_PASSWORD:
        return False
    return db.query(User).first() is None
```

A verificação é feita no início de cada requisição GET e POST para `/setup`. Como o SQLite serializa escritas e a checagem + INSERT acontecem no mesmo commit, duas requisições concorrentes não criam dois administradores — a segunda verá o usuário já existente e será redirecionada.

### Auditoria do primeiro acesso

A criação do primeiro administrador é registrada na auditoria com:
- Ação: `CRIACAO`
- Módulo: `Usuários`
- Recurso: `User`
- Dados novos: username, full_name, email, is_admin
- **Nunca** registra senha, hash ou credencial

---

## 19. Testes- **Framework:** pytest + `TestClient` (FastAPI/starlette). **110 testes coletados**, todos passando
  no momento da análise (`python3 -m pytest tests/`).
- **Infra (`tests/conftest.py`):** SQLite **em memória** (`StaticPool`, banco compartilhado entre
  sessões), tabelas recriadas por teste (`Base.metadata.create_all`/`drop_all`),
  `AUTH_PBKDF2_ITERATIONS=1000` (hash rápido), fixtures `client` (autenticado como `testuser`,
  admin) e `unauth_client`.
- **Camada LDAP mockada** nos testes de AD (`patch.object(ad_ldap, "authenticate_ad", ...)`),
  sem servidor AD real; inclui regressões específicas do ldap3 2.9.1
  (`Connection.search()` retorna `bool`; `objectGUID` via `raw_values`).

| Arquivo | Testes | Cobre |
|---|---|---|
| `tests/test_rbac.py` | 30 | perfis/permissões em API e web, deny by default, menu dinâmico, lockout, bloqueio, último admin, auditoria, escalação |
| `tests/test_ad.py` | 29 | login híbrido, provisionamento pós-mapeamento, sem-mapeamento (nada criado, auditado), prioridade de grupos, perfil manual preservado, conta desabilitada, 503, vínculo colaborador, tela admin, auditoria AD, regressões ldap3 |
| `tests/test_auth.py` | 16 | redirect/401 sem login, login válido/inválido, usuário sem perfil, open redirect, me/logout, sessão expirada, validações de `create_user` |
| `tests/test_custodian_import.py` | 13 | parse/normalização/validação CSV, execução (criar/skip/atualizar), preview, export/round-trip, páginas web |
| `tests/test_help.py` | 9 | ajuda autenticada, artigos, filtro admin, links de ajuda |
| `tests/test_api.py` | 7 | health, fluxo asset+movement, duplicatas (e-mail, matrícula, série, local) |
| `tests/test_movements.py` | 5 | CRUD/depreciação, movimento inicial, alocação, devolução, baixa, QR do termo |
| `tests/test_assets.py` | 1 | `test_asset_crud_and_depreciation` |
| `tests/test_help.py`/`conftest.py` | — | infraestrutura |

---

## 20. Execução e desenvolvimento

```bash
# 1. Ambiente (Python 3.10+)
python -m venv .venv && source .venv/bin/activate   # exemplo Linux

# 2. Dependências
pip install -r requirements.txt

# 3. Variáveis de ambiente (opcionais — ver §17)
export AUTH_ADMIN_PASSWORD='<senha-forte-aqui>'   # cria o admin no 1º start (mín. 8 caracteres)

# 4. Banco
# Criado automaticamente no start (init_db). Dados de DEMO (apaga o banco!):
python seed_demo.py

# 5. Iniciar
python run.py            # http://127.0.0.1:8000 · Swagger /docs · health /health

# 6. CLI
python -m app.cli stats|list|show|move|create-user

# 7. Testes
pytest -v
```

Documentação interativa da API: `/docs` (Swagger UI nativo do FastAPI; chamadas "Try it out"
exigem sessão válida via cookie).

---

## 21. Deployment

`não identificado no código analisado` — não existem no repositório: Dockerfile, arquivos de
serviço (systemd/supervisor), configuração de proxy reverso, pipeline de CI/CD ou scripts de
deploy. O que o código possibilita:

- Servidor: Uvicorn (processo único; `reload=False` em `run.py`).
- Porta/host por env (`APP_HOST`/`APP_PORT`).
- Persistência em arquivo único SQLite — backup = cópia do arquivo com a aplicação parada.
- Produção segura (recomendações do README, reproduzíveis via env): `AUTH_COOKIE_SECURE=true`
  atrás de HTTPS, LDAPS com certificado válido, credenciais apenas via ambiente.

---

## 22. Decisões técnicas existentes (com evidência)

| Decisão | Motivo identificado no código/documentação | Impacto |
|---|---|---|
| Sessão server-side com hash do token (`session_service.py`) | "o banco armazena apenas o hash SHA-256 do token, nunca o token" | Logout/bloqueio revogam de fato |
| Bind LDAP direto do usuário (sem conta de serviço) | docstrings de `ad_ldap.py`/`ad_service.py`; commit `d9bb1d4` ("Sem o AD_BIND_USER, AD_BIND_PASSWORD") | Credenciais de serviço não são mais necessárias; envs legadas mantidas |
| Mapeamento Grupo AD → Perfil (nunca → permissão) | `ad_group_roles` + `resolve_role_for_groups`; README | RBAC interno preservado; AD não concede privilégios |
| Provisionamento só após grupo mapeado | `authenticate_and_sync` (resolução antes do upsert); testes `test_ad_unmapped_group_denied` | Domínio ≠ acesso; nada é criado sem autorização |
| Perfis AD marcados `assigned_by='ad'` | `UserRole.assigned_by`; `_assign_ad_role` | Coexistência com perfis manuais, que nunca são removidos |
| `is_admin` como bypass total | `permission_service.py` ("compatibilidade com o flag legado") | Compatibilidade do admin inicial; recomendação é usar o perfil Administrador |
| Toda a `/api/v1` protegida (inclusive GET) | README ("retornos contêm dados sensíveis") | Sem API pública |
| Migração leve própria (sem Alembic) | `_ensure_schema_migrations` | Simples e idempotente; cobre apenas ADD COLUMN |

---

## 23. Mapa de dependências entre módulos

```text
run.py ──► app.main ──► app.config · app.database
   │            │
   │            ├──► app.api.v1_router ──► api/auth_api · assets_api · movements_api
   │            │                          custodians_api · locations_api · reports_api
   │            │        └──(todos)──► api/deps ──► services/session_service
   │            │                                      services/permission_service
   │            │                                      services/audit_service
   │            ├──► app.web.routes ──► services/* (negócio) · api/deps
   │            ├──► app.web.admin_routes ──► services/permission_service · audit_service
   │            │                             auth_service · ad_service · ad_ldap
   │            └──► app.web.help_routes ──► services/help_service
   │
   └── services/ad_service ──► services/ad_ldap ──► ldap3 · models/ad_settings
            │                    │
            └──► models/ad_group_role · models/user(_role) · services/audit_service
                                       └──► services/permission_service (resolução de perfis)

services/maintenance_service ──► services/movement_service (reaproveita o motor de fluxo)
services/import_service · custodian_import_service ──► schemas/* · models/*
app.cli ──► services/* (mesma camada de negócio das rotas)
```

---

## 24. Guia "Onde mexer"

| Se eu precisar alterar... | Procurar primeiro em... |
|---|---|
| Login/sessão | `app/services/auth_provider.py`, `auth_service.py`, `session_service.py`; rotas em `app/api/auth_api.py` e `app/web/routes.py` |
| Integração AD | `app/services/ad_ldap.py` (protocolo), `app/services/ad_service.py` (regras), `app/web/admin_routes.py` (tela `/admin/ad`), `app/models/ad_settings.py`/`ad_group_role.py` |
| Usuários | `app/web/admin_routes.py` (seção USUÁRIOS), `app/services/auth_service.py` |
| Perfis/permissões | `app/services/permission_service.py` (catálogo + seed), `app/web/admin_routes.py` (seção PERFIS) |
| Proteger nova rota | `app/api/deps.py::require_permission` (+ `can()` no template) |
| Equipamentos | `app/services/asset_service.py`, `app/api/assets_api.py`, `app/web/routes.py`, templates `assets/` |
| Importação CSV | `app/services/import_service.py` (bens) e `custodian_import_service.py` (colaboradores) |
| Movimentações/Termo | `app/services/movement_service.py`, templates `movements/term.html` |
| Colaboradores | `app/services/custodian_service.py`; Locais: `location_service.py` |
| Manutenção | `app/services/maintenance_service.py` |
| Dashboard/Relatórios | `dashboard_service.py`, `report_service.py`, `app/api/reports_api.py` |
| Auditoria | `app/services/audit_service.py`, `app/web/admin_routes.py` (seção AUDITORIA) |
| Ajuda/Manual | `app/services/help_service.py` (conteúdo) |
| Layout/CSS/JS | `app/web/templates/base.html`, `app/web/static/css/style.css`, `app/web/static/js/main.js` |
| Configuração/env | `app/config.py` |
| Banco/migração | `app/models/*` + `app/database.py::_ensure_schema_migrations` |
| CLI | `app/cli.py` |

---

## 25. Regras para manutenção futura

1. **Não quebrar o deny by default**: qualquer rota nova deve nascer com
   `require_permission("modulo.acao")`; permissões novas entram no `PERMISSION_CATALOG`
   (o seed as cria no startup) e são atribuídas aos perfis pela tela de perfis.
2. **Auditoria**: ações relevantes de escrita devem registrar `CRIACAO`/`ALTERACAO`/
   `MOVIMENTACAO` etc. com snapshot before/after (`write_change_audit`). Nunca registrar
   senhas/credenciais.
3. **Fluxo do bem é imutável**: alterações de custódia/local/status passam por
   `MovementService.create_movement` — nunca por `UPDATE` direto no `Asset`.
4. **RBAC ≠ AD**: nunca conceder permissão direta a partir de grupos AD; qualquer mudança na
   integração deve manter a regra "autenticação ≠ autorização" e o provisionamento pós-mapeamento.
5. **Usuários locais**: não migrar contas `'local'` para AD automaticamente
   (`resolve_authentication` garante o caminho local).
6. **Sessões**: ao tocar em senha/bloqueio, invalidar sessões (padrão atual: deletar
   `UserSession` do usuário ou confiar em `User.is_active`).
7. **Migração de banco**: colunas novas → adicionar no modelo **e** em
   `_ensure_schema_migrations` (ALTER condicional) para bancos existentes.
8. **Colaborador**: nunca criar colaborador automaticamente (importação e telas explícitas
   são os únicos caminhos; a integração AD apenas vincula).
9. **Testes**: `pytest` deve continuar passando; comportamentos de segurança (403/401,
   lockout, último admin, sem-mapeamento-AD) têm testes dedicados que precisam ser preservados.
10. **Atenção aos pontos de atenção listados em §18** (CSRF, `AUTH_PROVIDER` inerte, envs
    legadas de AD, datas `now` × `utcnow`, FAQ da ajuda desatualizado sobre AD, catálogo com
    permissões sem rota) antes de qualquer mudança nessas áreas.

---

## 26. Limitações da documentação

- **Versões de runtime** confirmadas no ambiente de análise (Python 3.10.12, FastAPI 0.141.1,
  SQLAlchemy 2.0.52, Pydantic 2.13.5, Jinja2 3.1.6, uvicorn 0.30.6, ldap3 2.9.1); `requirements.txt`
  define apenas mínimos — outro ambiente pode ter versões diferentes.
- **Deploy/infra** (proxy, serviço, CI/CD, HTTPS) não está no repositório — não documentado.
- **Conteúdo do banco atual** (`data/patrimonio.db`) não foi inspecionado em profundidade; o
  modelo de dados documentado vem do código (`app/models/`), não de dump do banco.
- Motivos históricos de decisões antigas (ex.: escolha do SQLite) não constam no código —
  registrados como `motivo histórico não identificado`.
- Testes executados uma única vez no ambiente de análise; nenhum comportamento foi modificado
  para esta documentação.
