# SisPatrimônio Pro — Inventário Técnico

> Inventário objetivo de arquivos, módulos, classes, funções, rotas, modelos, schemas,
> serviços, integrações, configurações e scripts. Baseado exclusivamente no código do
> repositório. Objetivo: **localização rápida**.

---

## 1. Arquivos de raiz

| Arquivo | Função |
|---|---|
| `run.py` | Inicia Uvicorn com `app.main:app` (`APP_HOST`/`APP_PORT`); chama `init_db()` antes |
| `requirements.txt` | Dependências (mínimos): fastapi, uvicorn[standard], sqlalchemy, pydantic, jinja2, python-multipart, pytest, requests, ldap3 |
| `seed_demo.py` | Demo: `Base.metadata.drop_all` + `init_db` + carga de 4 locais, 4 colaboradores, 7 bens, movimentações e 1 manutenção |
| `data/logs/` | Logs técnicos (`app.log`, `app.error.log`) criados por `app/logging_config.py` |
| `README.md` | Documentação geral do projeto (execução, auth, AD, RBAC, CLI, testes) |
| `data/patrimonio.db` | Banco SQLite da aplicação |

---

## 2. App — núcleo

| Arquivo | Conteúdo principal |
|---|---|
| `app/main.py` | `app` (FastAPI), `lifespan` (`init_db`, `ensure_admin_user`, `ensure_default_roles`), montagem `/static`, inclusão dos roteadores, `http_exception_handler` (403/404 HTML), rota `/health` |
| `app/config.py` | Constantes: `BASE_DIR`, `DATA_DIR`, `DATABASE_URL`, `APP_*`, `COMPANY_*`, `AUTH_*` (10 variáveis), `AD_*` (8 variáveis) |
| `app/database.py` | `engine`, `SessionLocal`, `Base`, `get_db()`, `init_db()`, `_ensure_schema_migrations()` |
| `app/logging_config.py` | `configure_logging()`: logs técnicos em `data/logs/app.log` (INFO) e `app.error.log` (WARNING+), rotação 5 MB × 5 backups; chamado por `run.py` |
| `app/cli.py` | `main()` com subcomandos: `stats`, `list`, `show`, `move`, `create-user` (`--username --password --name --email --admin --role` repetível) |

---

## 3. Modelos (`app/models/`) — 16 arquivos

| Modelo | Tabela | Destaques |
|---|---|---|
| `user.py::User` | `users` | `username` unique; `password_hash`; `is_admin`; `auth_provider` (local/ad); `failed_login_attempts`, `locked_until`; `ad_object_guid` (índice), `ad_dn`, `ad_last_sync`; rel: `sessions`, `user_roles` |
| `session.py::UserSession` | `user_sessions` | `token_hash` unique (SHA-256), `expires_at`, FK `users.id` CASCADE |
| `role.py::Role` | `roles` | `name` unique; `is_system` |
| `permission.py::Permission` | `permissions` | `name` unique (`modulo.acao`), `module`, `label` |
| `user_role.py::UserRole` | `user_roles` | unique (user,role); `assigned_by` (`local`/`ad`) |
| `role_permission.py::RolePermission` | `role_permissions` | unique (role,permission) |
| `audit_log.py::AuditLog` | `audit_logs` | timestamp, user_id (SET NULL), username snapshot, action, module, resource(_id/ref), ip, result, description, previous_data/new_data (JSON em TEXT) |
| `ad_settings.py::ADSettings` | `ad_settings` | singleton id=1: enabled, server, port, use_ldaps, verify_tls, base_dn, search_dn, bind_user (legado), timeout_seconds, auto_create_user, link_by_email, group_role_priority, disabled_behavior |
| `ad_group_role.py::ADGroupRole` | `ad_group_roles` | group_name unique, role_id FK→roles, priority (menor vence), is_active |
| `asset.py::Asset` | `assets` | tag unique, serial_number unique (nullable), category/condition/status (Enum), purchase_value, FKs location/custodian; rel: movements, maintenances |
| `movement.py::Movement` | `movements` | movement_uuid unique, movement_type (Enum), snapshots origem/destino (FK+nome), previous/new status/condition, reason, operator_name, term_code, term_signed |
| `custodian.py::Custodian` | `custodians` | registration_code unique (matrícula), email unique, role (cargo), department (setor) |
| `location.py::Location` | `locations` | name unique, branch, building, floor, room, department, manager_name |
| `maintenance.py::Maintenance` | `maintenances` | maintenance_type/status (Enum), provider_name, description, solution, cost, start/end_date |
| `enums.py` | — | `AssetStatus` (5), `AssetCondition` (6), `AssetCategory` (11), `MovementType` (8), `MaintenanceType` (3), `MaintenanceStatus` (4) |
| `__init__.py` | — | registra todos os modelos no `Base.metadata` |

---

## 4. Schemas Pydantic (`app/schemas/`)

| Arquivo | Classes |
|---|---|
| `asset.py` | `AssetBase`, `AssetCreate` (+ `initial_location_id`, `initial_custodian_id`, `initial_operator`), `AssetUpdate`, `AssetRead` |
| `movement.py` | `MovementCreate` (`reason` min 3; `generate_term=True`), `MovementRead`, `MovementFilter` |
| `custodian.py` | `CustodianBase`, `CustodianCreate`, `CustodianUpdate`, `CustodianRead` (+ `active_assets_count`) |
| `location.py` | `LocationBase`, `LocationCreate`, `LocationUpdate`, `LocationRead` (+ `assets_count`) |
| `maintenance.py` | `MaintenanceCreate`, `MaintenanceUpdate`, `MaintenanceRead` |
| `user.py` | `UserRead`, `UserWithPermissions` (+ `permissions: List[str]`) |

---

## 5. Serviços (`app/services/`) — 17 módulos

### 5.1 Autenticação e acesso

| Módulo | Funções/classes-chave |
|---|---|
| `auth_service.py` | `hash_password`, `verify_password`, `create_user`, `authenticate` (lockout, timing dummy), `change_password`, `reset_password`, `ensure_admin_user`, `AccountLockedError` |
| `session_service.py` | `create_session`, `get_session_user`, `revoke_session`, `purge_expired_sessions`, `set_session_cookie`, `clear_session_cookie` |
| `auth_provider.py` | `AuthProvider` (ABC), `LocalAuthProvider`, `ADAuthProvider`, `get_auth_provider` (**sem chamadores**), `resolve_authentication` (usado pelos logins) |

### 5.2 RBAC e auditoria

| Módulo | Funções/chaves |
|---|---|
| `permission_service.py` | `PERMISSION_CATALOG` (29 permissões), `DEFAULT_ROLES` (7 perfis), `ensure_default_roles`, `get_user_permission_names`, `user_has_permission`, `get_user_role_names`, `get_user_roles`, `assign_role`, `remove_role`, `get_all_roles`, `get_role_by_name/id`, `get_role_permission_names`, `create_role`, `update_role`, `delete_role` |
| `audit_service.py` | `write_audit`, `write_change_audit`, `changed_fields`, `get_audit_logs`, `get_distinct_modules`, `get_distinct_actions`; constantes `ACTION_*` (17 gerais + 13 AD) e `RESULT_SUCCESS/FAILURE/DENIED/LOCKED` |

### 5.3 Negócio

| Módulo | Funções-chave |
|---|---|
| `asset_service.py` | `AssetService.get_all/get_by_id/get_by_tag/create/update/calculate_depreciation` |
| `movement_service.py` | `MovementService.create_movement` (motor do fluxo), `get_by_id`, `get_by_uuid`, `get_timeline_for_asset` (dicts: movimentações + auditoria, com dedup de `CRIACAO`), `get_all_movements`, `get_term_details` |
| `maintenance_service.py` | `MaintenanceService.get_all/get_by_id/create/complete_maintenance` |
| `custodian_service.py` | `CustodianService.get_all/get_by_id/get_by_registration_code/create/update/get_assigned_assets/count_assigned_assets` |
| `location_service.py` | `LocationService.get_all/get_by_id/get_by_name/create/update/count_assets` |
| `location_import_service.py` | `parse_locations_csv`, `preview_locations_import`, `execute_locations_import` (importação CSV de locais) |
| `dashboard_service.py` | `DashboardService.get_stats` (KPIs + recent_movements/recent_assets) |
| `report_service.py` | `ReportService.generate_inventory_csv`, `generate_custodians_csv`, `generate_movements_csv` |
| `import_service.py` | `parse_csv`, `preview_import`, `execute_import`; `CATEGORY_MAP`, `CONDITION_MAP`, `COLUMN_ALIASES`, helpers de normalização |
| `custodian_import_service.py` | `parse_custodian_csv`, `preview_custodian_import`, `execute_custodian_import`; `COLUMN_ALIASES` |

### 5.4 Ajuda e AD

| Módulo | Conteúdo |
|---|---|
| `help_service.py` | `ARTICLES` (21 artigos), `FAQ` (12 perguntas), `CATEGORIES` (7), `get_articles`, `get_article`, `get_faq`, `get_categories`, `serialize_search_index` |
| `ad_ldap.py` | `ADUser` (dataclass), `ADError`, `authenticate_ad`, `test_connection`, `get_user_groups`, `_build_server`, `_connect`, `_search_service_account`, `_canonical_guid`, `_normalize_username`, `_extract_common_name`, `UAC_DISABLED_BIT` |
| `ad_service.py` | `ADNotConfiguredError`, `ADAuthenticationError`, `ADUnavailableError`, `ADNoProfileError`; `get_ad_settings`, `_effective_settings`, `ad_enabled`, `get_group_mappings`, `upsert_group_mapping`, `delete_group_mapping`, `resolve_role_for_groups`, `_find_user_by_identity`, `find_linked_custodian`, `_assign_ad_role`, `_upsert_ad_user`, `_link_custodian`, `authenticate_and_sync`; constantes `PROVIDER_LOCAL/PROVIDER_AD` |

---

## 6. API REST (`app/api/`)

| Arquivo | Rotas |
|---|---|
| `v1_router.py` | prefixo `/api/v1`; negócio protegido por `require_api_auth` |
| `auth_api.py` | POST `/auth/login`, POST `/auth/logout`, GET `/auth/me` |
| `assets_api.py` | GET/POST `/assets`; GET/PUT `/assets/{id}`; GET `/assets/tag/{tag}`; GET `/assets/{id}/timeline`; GET `/assets/{id}/depreciation`; POST `/assets/import/csv` |
| `movements_api.py` | GET/POST `/movements`; GET `/movements/{id}`; GET `/movements/{id}/term` |
| `custodians_api.py` | GET/POST `/custodians`; GET/PUT `/custodians/{id}`; GET `/custodians/{id}/assets`; POST `/custodians/import/csv` |
| `locations_api.py` | GET/POST `/locations`; GET/PUT `/locations/{id}` |
| `reports_api.py` | GET `/reports/dashboard-stats`; GET `/reports/{inventory,movements,custodians}/csv` |
| `deps.py` | `get_current_user`, `require_api_auth`, `require_web_auth`, `require_permission`, `stash_access`, `get_request_permissions`, `_client_ip`, `PUBLIC_WEB_PATHS` |

Inventário completo (método, permissão, handler) → ver `ARQUITETURA_E_MANUTENCAO.md` §14.

---

## 7. Interface web (`app/web/`)

| Arquivo | Rotas |
|---|---|
| `routes.py` | `/login` (GET/POST), `/logout`, `/`, `/setup` (GET/POST, primeiro acesso), `/assets*` (list, labels, new, import+confirm, {id}), `/movements*` (list, new, {id}/term), `/custodians*` (list, new, {id}/edit, import+confirm, {id}), `/locations*` (list, new, import+confirm), `/maintenances*` (list, new, {id}/complete), `/reports/{inventory,movements,custodians}`; configura `templates` com context processor `_inject_current_user` (fornece `can()`) |
| `admin_routes.py` | `/admin`, `/admin/users*` (list/new/edit/toggle-active/reset-password), `/admin/roles*` (list/new/{id}/edit/delete), `/admin/audit`, `/profile/password` (GET/POST), `/admin/ad` (page/settings/test/mappings/mappings/{id}/delete); helpers `_user_has_admin_access`, `_count_active_admins`, `_guard_remove_admin_access`, `_ad_admin_guard` |
| `help_routes.py` | GET `/ajuda`, GET `/ajuda/{article_id}` |

### Templates (37) — `app/web/templates/`

`base.html`, `login.html`, `dashboard.html`, `setup.html`, `403.html`, `404.html`,
`assets/{list,form,detail,import,labels}.html`, `movements/{list,new,term}.html`,
`custodians/{list,form,detail,import}.html`, `locations/{list,form,import}.html`,
`maintenances/{list,new}.html`, `reports/{inventory,movements_report,custodians_report}.html`,
`admin/users/{list,new,edit}.html`, `admin/roles/{list,form}.html`, `admin/audit/list.html`,
`admin/ad/settings.html`, `ajuda/{index,article}.html`, `profile/password.html`.

### Estáticos — `app/web/static/`

`css/style.css` (tema + layout; inclui o bloco de CSS de impressão das Etiquetas), `js/main.js`
(dark mode, tooltips, alertas, contadores, sidebar).
Bibliotecas externas via CDN em `base.html`: Bootstrap 5.3.3, Bootstrap Icons 1.11.3, Chart.js,
QRCode.js, Google Fonts (Plus Jakarta Sans).

---

## 8. Testes (`tests/`) — 12 arquivos, 156 testes — **156/156 passando**

| Arquivo | Qtde | Escopo |
|---|---|---|
| `conftest.py` | — | SQLite em memória (StaticPool), fixtures `db_session`, `client` (admin autenticado), `unauth_client`; `AUTH_PBKDF2_ITERATIONS=1000` |
| `test_rbac.py` | 30 | Autorização por perfil (API/web), deny by default, menu, bloqueio, lockout, último admin, auditoria |
| `test_ad.py` | 32 | Login híbrido, provisionamento, sem-mapeamento, prioridade, conta desabilitada, 503, vínculo, tela AD, auditoria AD, regressões ldap3 |
| `test_auth.py` | 17 | Redirects 303/401, login válido/inválido, open redirect, me/logout, sessão expirada, `create_user` |
| `test_custodians_edit.py` | 14 | Edição de colaborador (web + API) |
| `test_custodian_import.py` | 13 | CSV de colaboradores (parse/exec/preview/export/web) |
| `test_assets_labels.py` | 12 | Página de etiquetas: permissão, seleção em lote, folha, CSS de impressão, menu ativo |
| `test_import_asset_location.py` | 12 | Importação CSV de bens com localização |
| `test_help.py` | 9 | Central de ajuda (acesso, artigos, filtro admin, links) |
| `test_api.py` | 7 | Health, fluxo asset+movement, duplicatas |
| `test_navbar.py` | 4 | Estrutura da navbar e guard de menu |
| `test_movements.py` | 5 | Alocação, devolução, baixa, movimento inicial, QR do termo |
| `test_assets.py` | 1 | CRUD + depreciação |

Execução: `pytest -v` (ou `python -m pytest tests/`). LDAP é mockado nos testes de AD.

---

## 9. Integrações

| Integração | Biblioteca | Onde |
|---|---|---|
| Active Directory / Samba AD (LDAP/LDAPS) | `ldap3` 2.9.1 | `app/services/ad_ldap.py`, `ad_service.py` |
| Frontend CDN | Bootstrap, Bootstrap Icons, Chart.js, QRCode.js, Google Fonts | `app/web/templates/base.html` |
| Swagger/OpenAPI | nativo FastAPI | `/docs` |

Nenhuma outra integração externa (e-mail, storage, filas) existe no código.

---

## 10. Configurações (resumo)

Detalhamento completo em `ARQUITETURA_E_MANUTENCAO.md` §17. Nomes: `DATABASE_URL`,
`APP_HOST`, `APP_PORT`, `AUTH_PROVIDER`, `AUTH_SESSION_TTL`, `AUTH_COOKIE_NAME`,
`AUTH_COOKIE_SECURE`, `AUTH_PBKDF2_ITERATIONS`, `AUTH_MAX_FAILED_ATTEMPTS`,
`AUTH_LOCKOUT_SECONDS`, `AUTH_ADMIN_USERNAME`, `AUTH_ADMIN_PASSWORD`, `AUTH_ADMIN_NAME`,
`AD_SERVER`, `AD_PORT`, `AD_USE_SSL`, `AD_BASE_DN`, `AD_USER_DN`, `AD_GROUP_BASE_DN`,
`AD_BIND_USER` (legado), `AD_BIND_PASSWORD` (legado).

Sem `.env` versionado; sem segredos no repositório (senhas existem apenas em runtime/env).
