# Investigação do Primeiro Login — SisPatrimônio Pro

> **Aviso:** Esta é uma análise somente-leitura do código-fonte. Nenhum arquivo, banco de dados, configuração, senha, dependência ou funcionalidade foi alterado durante esta investigação.

---

## 1. Resumo Executivo

O SisPatrimônio Pro possui **três formas** de criação do primeiro administrador:

- **Variável de ambiente `AUTH_ADMIN_PASSWORD` definida** → o sistema cria automaticamente um usuário administrador (padrão: `admin`) no primeiro início.
- **Interface web de Primeiro Acesso (`/setup`)** → quando não existem usuários no banco e `AUTH_ADMIN_PASSWORD` não está definida, a tela de login exibe um link "Primeiro acesso" que leva a uma página de configuração onde o administrador cria sua conta diretamente pelo navegador.
- **CLI `create-user` executada** → permite criar um usuário manualmente antes do primeiro login.

O fluxo de Primeiro Acesso resolve o impasse anterior onde uma instalação nova sem `AUTH_ADMIN_PASSWORD` ficava inacessível.

---

## 2. Fluxo da Primeira Execução

```
python run.py
  ↓
init_db()          # app/database.py — cria tabelas se não existirem
  ├── Base.metadata.create_all()
  └── _ensure_schema_migrations()
  ↓
uvicorn.run("app.main:app", ...)
  ↓ (lifespan do FastAPI, app/main.py)
init_db()          # chamado novamente (idempotente)
  ↓
ensure_admin_user(db)     # SO SOMENTE SE AUTH_ADMIN_PASSWORD estiver definida
  ↓
ensure_default_roles(db)  # seed idempotente: permissões + 7 perfis padrão
  ↓
Aplicação pronta → servidor ouvindo
```

**Arquivos envolvidos:**
- `app/main.py` — `lifespan`, chama `init_db()`, `ensure_admin_user()`, `ensure_default_roles()`
- `app/database.py` — `init_db()`, `Base.metadata.create_all()`, `_ensure_schema_migrations()`
- `app/services/auth_service.py` — `ensure_admin_user()`
- `app/services/permission_service.py` — `ensure_default_roles()`

---

## 3. Criação do Banco de Dados

- **Banco:** SQLite, arquivo `data/patrimonio.db` (padrão em `app/config.py`).
- **Como é criado:** `Base.metadata.create_all(bind=engine)` dentro de `init_db()` (`app/database.py`).
- **Quando:** na primeira execução do servidor (`run.py`) e novamente no `lifespan` do FastAPI.
- **Migrações:** Não existe Alembic. Existe apenas `_ensure_schema_migrations()` que adiciona colunas condicionalmente em tabelas existentes (somente SQLite).

**Evidência:** `app/database.py`.

---

## 4. Criação do Primeiro Usuário

Três formas:

### 4.1 Variável de Ambiente (automático, opcional)

| Variável | Padrão | Descrição |
|---|---|---|
| `AUTH_ADMIN_USERNAME` | `"admin"` | Nome de usuário do administrador inicial |
| `AUTH_ADMIN_PASSWORD` | `""` (vazio) | Senha (mínimo 8 caracteres). Se vazia, **nenhum usuário é criado** |
| `AUTH_ADMIN_NAME` | `"Administrador"` | Nome completo |

Se `AUTH_ADMIN_PASSWORD` estiver definida, `ensure_admin_user(db)` cria o usuário automaticamente no início do sistema.

**Evidência:** `app/config.py`, `app/services/auth_service.py` (linhas 193-216), `app/main.py` (lifespan).

### 4.2 CLI `create-user` (manual)

```
python -m app.cli create-user \
  --username <nome> \
  --password <senha> \
  [--admin] \
  [--role <perfil>] \
  [--name <nome completo>] \
  [--email <e-mail>]
```

- Senha mínima de 8 caracteres.
- Se a senha não for informada no comando, o CLI solicita interativamente.
- Pode criar como administrador (`--admin`).

**Evidência:** `app/cli.py`.

### 4.3 Interface de Primeiro Acesso (web — NOVA)

**Implementada em:** `app/web/routes.py` (seção "PRIMEIRO ACESSO / CONFIGURAÇÃO INICIAL").

**Rotas:**
- `GET /setup` — exibe a tela de configuração inicial (`app/web/templates/setup.html`)
- `POST /setup` — processa a criação do primeiro administrador

**Quando está disponível:**
- Só quando **não existem usuários** no banco (`db.query(User).first() is None`)
- E **`AUTH_ADMIN_PASSWORD` não está definida** (variável de ambiente vazia)

**Função de verificação:**
```python
def _first_access_enabled(db: Session) -> bool:
    if AUTH_ADMIN_PASSWORD:
        return False
    return db.query(User).first() is None
```

**Proteções:**
- Verificação em cada requisição GET e POST para `/setup`
- Se outro processo criar o usuário entre a verificação e o commit, a segunda requisição é redirecionada para `/login`
- Após a criação, o link "Primeiro acesso" na tela de login deixa de aparecer

**Template:** `app/web/templates/setup.html` — formulário com:
- Nome completo (obrigatório)
- Nome de usuário (obrigatório)
- E-mail (opcional)
- Senha (obrigatória, mínimo 8 caracteres)
- Confirmação de senha (deve coincidir)

**Link na tela de login:** `app/web/templates/login.html` contém:
```html
<a href="/setup" class="text-decoration-none text-primary small fw-semibold">
    <i class="bi bi-person-plus me-1"></i> Primeiro acesso
</a>
```

**Auditoria:** A criação é registrada com ação `CRIACAO`, módulo `Usuários`, sem registrar senha ou credencial.

**Fluxo após criação:**
1. O administrador é criado com `is_admin=True`
2. `ensure_default_roles(db)` é chamado para garantir os perfis padrão
3. O perfil "Administrador" é atribuído ao novo usuário (se ainda não estiver)
4. Redireciona para `/login` onde o administrador pode fazer login

**Evidência:** `app/web/routes.py` (seção "PRIMEIRO ACESSO / CONFIGURAÇÃO INICIAL"), `app/web/templates/setup.html`, `app/web/templates/login.html`.

### 4.4 Interface Administrativa (após login)

- Rota: `POST /admin/users/new` (`app/web/admin_routes.py`, função `admin_create_user`).
- Exige permissão `usuarios.criar`.
- **Disponível somente após** um login válido.

**Evidência:** `app/web/admin_routes.py`.

---

## 5. Administrador Inicial

| Pergunta | Resposta |
|---|---|
| Existe? | Pode existir, mas não é obrigatório. |
| É automático? | Sim, **somente se `AUTH_ADMIN_PASSWORD` estiver definida**. |
| Username padrão? | `"admin"` (configurável via `AUTH_ADMIN_USERNAME`). |
| Senha padrão? | **Não existe senha fixa no código.** A senha é definida pela variável `AUTH_ADMIN_PASSWORD`. Se vazia, nenhum usuário é criado. |
| Como é definida? | Pelo administrador, exportando a variável de ambiente antes de iniciar: `export AUTH_ADMIN_PASSWORD='senha-forte'`. |
| Onde é configurada? | `app/config.py` (variáveis de ambiente), usada por `ensure_admin_user()` em `app/services/auth_service.py`. |

**Sobre credenciais:** O código lê `AUTH_ADMIN_PASSWORD` como variável de ambiente. O valor padrão é **vazio** — não há senha hardcoded. Se definida, o valor é usado para criar o usuário, mas o código nunca expõe o valor (apenas o mecanismo).

---

## 6. Primeiro Login

Não existe fluxo especial. A tela de login (`GET /login`, template `login.html`) é sempre a mesma, independente de existirem ou não usuários.

**Fluxo real (local):**

```
Tela de login (GET /login)   → template login.html
  ↓
Formulário POST /login       → app/web/routes.py::login_submit
  ↓
resolve_authentication(db, username, password)
  ↓ (usuário local existente)
LocalAuthProvider.authenticate  → app/services/auth_service.py::authenticate
  ├── busca usuário por username
  ├── se não existe: executa verificação dummy (timing equalizado) → None
  ├── se conta bloqueada: AccountLockedError (HTTP 423)
  ├── se senha incorreta: incrementa failed_login_attempts → lockout após 5 falhas
  ├── se inativo: None
  └── se sucesso: zera falhas, atualiza last_login, retorna User
  ↓
create_session(db, user.id)  → app/services/session_service.py
  ├── token = secrets.token_urlsafe(32)
  ├── hash SHA-256 do token salvo no banco (UserSession.token_hash)
  └── cookie HttpOnly, SameSite=Lax, Secure (opcional), max_age = AUTH_SESSION_TTL (8h)
  ↓
Redireciona para next (página original) ou / (dashboard)
  ↓
dashboard.html
```

**Evidência:** `app/web/routes.py`, `app/services/auth_provider.py`, `app/services/auth_service.py`, `app/services/session_service.py`.

---

## 7. Sessão

- **Como é criada:** `create_session(db, user_id)` gera um token aleatório de 32 bytes (`secrets.token_urlsafe(32)`) e salva **apenas seu hash SHA-256** no banco (`UserSession.token_hash`). O token em texto puro vai para o cookie.
- **Onde é armazenada:** tabela `user_sessions` (`app/models/session.py`), com `token_hash` (unique, indexed), `user_id` (FK), `created_at`, `expires_at`.
- **Como o usuário é identificado:** a cada requisição, `get_current_user` lê o cookie `AUTH_COOKIE_NAME` (padrão `"session"`), computa o hash SHA-256 do token e consulta `UserSession` pelo `token_hash`, unindo com `users` e verificando `expires_at` e `is_active`.
- **Validade:** expira em `AUTH_SESSION_TTL` segundos (28800 = 8 horas). Sessões expiradas são purgadas a cada criação de nova sessão.
- **Revogação:** logout (`POST /logout`) deleta a sessão no banco e remove o cookie. Troca/reset de senha também invalida todas as sessões do usuário.

**Evidência:** `app/api/deps.py`, `app/services/session_service.py`, `app/models/session.py`.

---

## 8. Perfil e Permissões do Primeiro Usuário

- **RBAC com Deny By Default:** um usuário só tem acesso se possuir explicitamente a permissão necessária.
- **Catálogo de 29 permissões** (`PERMISSION_CATALOG` em `app/services/permission_service.py`).
- **7 perfis padrão** (`DEFAULT_ROLES`), criados automaticamente por `ensure_default_roles()`:
  - `Administrador` (todas as 29 permissões)
  - `Gestor de TI`
  - `Técnico de TI`
  - `Patrimônio`
  - `Almoxarifado`
  - `Auditor`
  - `Consulta` (acesso mínimo)

**Como o primeiro usuário recebe permissões:**
- Se criado como administrador (`is_admin=True`, variável `AUTH_ADMIN_PASSWORD` ou CLI `--admin`), recebe automaticamente o perfil `Administrador` (via `ensure_default_roles` que atribui o perfil a todos os `is_admin=True`, e o flag `is_admin` atua como bypass total).
- Se criado **sem** o flag de administrador e **sem** perfis atribuídos, o usuário **não tem acesso a nada** (deny by default) até que um administrador atribua perfis.
- Um usuário sem perfil pode fazer login, mas receberá 403 em qualquer ação.

**Evidência:** `app/services/permission_service.py`, `app/api/deps.py`, `app/models/user.py`, `app/models/user_role.py`.

---

## 9. Active Directory / LDAP

- **Implementação:** `app/services/ad_ldap.py` (protocolo LDAP/LDAPS com ldap3) + `app/services/ad_service.py` (regras).
- **Configuração:** `ADSettings` (singleton `id=1`), editável em `/admin/ad`. Variáveis `AD_*` funcionam como fallback.
- **Autenticação AD:** cada usuário autentica **com a própria conta e senha** (bind direto), sem conta de serviço.
- **Mapeamento:** grupos AD → Perfil **existente** (`ad_group_roles`). AD nunca define permissões diretamente.
- **Provisionamento no primeiro login AD:** se `auto_create_user=True` (padrão) e o usuário tem grupo mapeado para um perfil existente, o sistema cria o usuário (`auth_provider='ad'`, `password_hash='!ad-external'`). Se `auto_create_user=False`, o acesso é negado sem criar usuário.
- **Sem grupo mapeado:** usuário AD autenticado mas sem grupo mapeado **não recebe acesso, não é criado no banco, apenas auditado**.
- **Auditoria:** todo o fluxo AD é auditado. Senha nunca é logada.

**Importante:** `AUTH_PROVIDER` (variável de ambiente) não governa o fluxo real de login — o fluxo usa `resolve_authentication()` que decide internamente.

**Evidência:** `app/services/ad_ldap.py`, `app/services/ad_service.py`, `app/services/auth_provider.py`, `app/models/ad_settings.py`, `app/models/ad_group_role.py`, `app/web/admin_routes.py` (/admin/ad).

---

## 10. Primeiro Login Local × AD

| Item | Local | AD |
|---|---|---|
| Autenticação | LocalAuthProvider (PBKDF2, lockout 5 falhas) | ADAuthProvider → `authenticate_and_sync` (bind direto LDAP) |
| Criação de usuário | Manual (variável de ambiente, CLI, ou interface após login) | Automático se `auto_create_user=True` e grupo mapeado para perfil existente; senão, negado sem criação |
| Perfil | Atribuído manualmente (CLI `--role`, interface `/admin/users/{id}/edit`) ou automaticamente se `is_admin=True` | Determinado pelo mapeamento Grupo AD → Perfil existente (`assigned_by='ad'`); perfis manuais `'local'` nunca são removidos |
| Permissões | Via perfis atribuídos (RBAC) ou bypass total se `is_admin` | Via perfis atribuídos pelo mapeamento AD (RBAC); `is_admin` local não se aplica |
| Sessão | Sessão server-side (token_urlsafe, hash SHA-256 no banco, cookie) | Mesma sessão server-side, criada após autenticação e atribuição de perfil |
| Primeiro acesso | Sem usuário criado, **não há como acessar**. Exige variável de ambiente, CLI ou criação manual prévia | Se AD habilitado, usuário com grupo mapeado e `auto_create_user=True`, o primeiro acesso AD **cria o usuário automaticamente** |
| Funciona sem AD? | Sim — funciona normalmente sem AD | O sistema funciona inicialmente sem AD (modo local); AD é totalmente opcional |

---

## 11. Arquivos Envolvidos (relevantes)

| Arquivo | Finalidade | Função/classe relevante | Relação com o primeiro login |
|---|---|---|---|
| `app/main.py` | FastAPI app, lifespan | `lifespan`, `app` | Chama `init_db()`, `ensure_admin_user()`, `ensure_default_roles()` na inicialização |
| `app/config.py` | Configuração central (env) | Variáveis `AUTH_ADMIN_*`, `AUTH_PBKDF2_ITERATIONS`, `AD_*` | Define padrões e leitura das variáveis de ambiente para admin inicial e AD |
| `app/database.py` | Banco de dados, inicialização | `init_db()`, `Base.metadata`, `SessionLocal` | Cria as tabelas no primeiro start |
| `app/services/auth_service.py` | Autenticação local, criação de usuário | `ensure_admin_user()`, `authenticate()`, `create_user()`, `hash_password()`, `verify_password()` | Cria o admin inicial se `AUTH_ADMIN_PASSWORD` definida; autentica localmente |
| `app/services/permission_service.py` | RBAC, seed de perfis | `ensure_default_roles()`, `PERMISSION_CATALOG`, `DEFAULT_ROLES`, `get_user_permission_names()` | Cria o catálogo de permissões e 7 perfis padrão (idempotente, toda inicialização) |
| `app/services/auth_provider.py` | Camada de provedores | `resolve_authentication()`, `LocalAuthProvider`, `ADAuthProvider` | Decide se o login é local ou AD; usado pela rota de login |
| `app/services/session_service.py` | Sessão server-side | `create_session()`, `get_session_user()`, `set_session_cookie()` | Cria a sessão após login |
| `app/services/ad_service.py` | Integração AD (regras) | `authenticate_and_sync()`, `_upsert_ad_user()`, `resolve_role_for_groups()` | Fluxo completo de login AD, provisionamento, mapeamento |
| `app/services/ad_ldap.py` | Protocolo LDAP/LDAPS | `authenticate_ad()`, `get_user_groups()`, `ADUser` | Autenticação no AD com bind direto |
| `app/api/deps.py` | Dependências de auth | `get_current_user()`, `require_web_auth()`, `require_permission()`, `stash_access()` | Protege as rotas, resolve o usuário da sessão, verifica permissões |
| `app/web/routes.py` | Rotas web (incluindo login) | `login_page()`, `login_submit()`, `logout()` | Tela e processamento do login, criação da sessão |
| `app/web/admin_routes.py` | Rotas administrativas | `admin_create_user()`, `admin_edit_user()`, `/admin/ad*` | Criação de usuários via interface, tela de configuração AD |
| `app/models/user.py` | Modelo de usuário | `User` (users) | Tabela de usuários; campos de hash, is_admin, auth_provider, failed_login_attempts, locked_until |
| `app/models/session.py` | Modelo de sessão | `UserSession` (user_sessions) | Tabela de sessões; token_hash (SHA-256), expires_at |
| `app/models/role.py`, `app/models/permission.py`, `app/models/user_role.py`, `app/models/role_permission.py` | Modelos RBAC | `Role`, `Permission`, `UserRole`, `RolePermission` | Perfis, permissões e associações |
| `app/models/ad_settings.py`, `app/models/ad_group_role.py` | Modelos AD | `ADSettings`, `ADGroupRole` | Configuração AD e mapeamento grupo→perfil |
| `app/web/templates/login.html` | Template de login | — | Tela de login (sem botão de primeiro acesso, sem setup) |
| `app/web/templates/admin/ad/settings.html` | Tela de configuração AD | — | Interface para habilitar AD, mapeamento de grupos |
| `app/database.py::_ensure_schema_migrations` | Migrações leves | — | Adiciona colunas em tabelas existentes (idempotente, somente SQLite) |

---

## 12. Fluxograma

```
INSTALLAÇÃO / PRIMEIRA EXECUÇÃO
  ↓
python run.py                    ← ponto de entrada
  ↓
init_db()                        ← app/database.py
  ├── Base.metadata.create_all() ← cria todas as tabelas (users, sessions, roles, ...)
  └── _ensure_schema_migrations() ← ALTER TABLE ADD COLUMN condicional (idempotente)
  ↓
uvicorn.run("app.main:app")      ← inicia servidor
  ↓ (lifespan do FastAPI)
init_db()                        ← novamente (idempotente)
  ↓
ensure_admin_user(db)            ← SOMENTE SE AUTH_ADMIN_PASSWORD estiver definida
  ├── se AUTH_ADMIN_PASSWORD vazio → retorna None (não cria nada)
  └── senão → create_user(username=AUTH_ADMIN_USERNAME, password=AUTH_ADMIN_PASSWORD,
                           full_name=AUTH_ADMIN_NAME, is_admin=True)
  ↓
ensure_default_roles(db)         ← cria permissões (29) + 7 perfis padrão (idempotente)
  ↓
Aplicação pronta                 ← servidor ouvindo em http://APP_HOST:APP_PORT
  ↓
                                                       ┌──────────────────┐
                                                       │  Decisão do      │
                                                       │  administrador   │
                                                       └──────────────────┘
                                                        │
                    ┌─────────────────────────────────┼─────────────────────┐
                    │ AUTH_ADMIN_PASSWORD definida?  │                     │
                    ▼                                 ▼                     ▼
               SIM                                  NÃO                  NÃO
                    │                                 │                     │
  ┌───────────────┴───────────────┐         ┌────────┴────────┐   ┌─────────┴─────────┐
  │ admin (ex: "admin") criado    │         │ Banco SEM usuários│   │ Usuário criado     │
  │ automaticamente no start      │         │ (vazio de login)  │   │ via CLI create-user│
  └───────────────┬───────────────┘         └────────┬────────┘   │ ou via /admin      │
                  │                                   │            │ (após outro login!) │
                  ▼                                   ▼            └─────────┬─────────┘
          ┌───────────────┐                    ┌──────────────────────────┐
          │ Primeiro login│                    │  NENHUM USUÁRIO NO BANCO │
          │ com admin:    │                    │  → login sempre falha    │
          │ username="admin"                 │  → "Usuário ou senha     │
          │ password=<AUTH_ADMIN_PASSWORD>  │    inválidos"             │
          │                                 └────────────────────────────┘
          ▼
  ┌─────────────────────────────────────────────┐
  │ resolve_authentication                     │
  │ → LocalAuthProvider.authenticate          │
  │   → busca usuário por username             │
  │   → verifica password_hash (PBKDF2)       │
  │   → zera falhas, atualiza last_login       │
  │   → retorna User                           │
  └─────────────────────────────────────────────┘
                  ▼
  ┌─────────────────────────────────────────────┐
  │ create_session(db, user.id)               │
  │ → token = secrets.token_urlsafe(32)       │
  │ → UserSession(token_hash=sha256(token))   │
  │ → cookie HttpOnly, SameSite=Lax, max_age   │
  │   = AUTH_SESSION_TTL (8h)                 │
  └─────────────────────────────────────────────┘
                  ▼
  ┌─────────────────────────────────────────────┐
  │ Redireciona para / (dashboard)             │
  │ → dashboard.html                           │
  │ → menu dinâmico com permissões do usuário  │
  └─────────────────────────────────────────────┘
```

**Sobre AD como primeiro acesso:**

```
Login AD → resolve_authentication → ADAuthProvider
  → ad_service.authenticate_and_sync
    → autentica no AD (bind direto)
    → resolve_role_for_groups (antes de qualquer criação!)
    → se grupo mapeado para perfil existente:
      → _upsert_ad_user (cria se auto_create_user=True, senão nega)
      → _link_custodian (vincula colaborador existente por e-mail)
      → _assign_ad_role (atribui perfil com assigned_by='ad')
      → cria sessão normal
    → se SEM grupo mapeado:
      → NÃO cria usuário, NÃO cria colaborador, NÃO atribui perfil
      → apenas auditoria GRUPO_AD_SEM_MAPEAMENTO
      → nega acesso (ADNoProfileError)
```

---

## 13. Pontos de Atenção (apenas relatório — sem correção)

1. **`AUTH_PROVIDER` não governa o fluxo:** a variável existe e é lida em `get_auth_provider()`, mas os pontos de login não usam essa função — usam `resolve_authentication()` que decide internamente.

2. **AD opcional:** o sistema funciona totalmente sem AD. Até o primeiro login pode ser feito com o admin local sem qualquer configuração de AD.

3. **Configuração do AD via interface exige login prévio:** para configurar o AD pela interface (`/admin/ad`), é necessário já existir um usuário local administrador — o AD não resolve o problema do primeiro acesso.

> **Nota:** Os pontos 1-3 do relatório anterior (impasse de acesso, sem tela de primeiro acesso, CLI como única saída) foram **resolvidos** com a implementação da interface web de Primeiro Acesso (`/setup`). Agora existe uma terceira forma de criar o primeiro administrador sem variável de ambiente nem CLI.

---

## 14. Conclusão

> **"Em uma instalação nova, o que o administrador precisa fazer para conseguir realizar o primeiro login?"**

Resposta baseada no código existente:

**Opção A — Usando variável de ambiente (mais simples):**
1. Antes de iniciar o sistema, definir as variáveis de ambiente:
   - `AUTH_ADMIN_USERNAME` (opcional, padrão `"admin"`)
   - `AUTH_ADMIN_PASSWORD` (obrigatória, senha com no mínimo 8 caracteres)
   - `AUTH_ADMIN_NAME` (opcional, padrão `"Administrador"`)
2. Executar `python run.py`.
3. Na tela de login, usar o username e a senha definidos.
4. O sistema já criou automaticamente o usuário administrador e os perfis padrão.

**Opção B — Usando CLI (sem variável de ambiente):**
1. Executar `python run.py` (o sistema inicia, cria tabelas e perfis, mas **não cria nenhum usuário**).
2. Em outro terminal, executar:
   ```
   python -m app.cli create-user --username admin --password <senha> --admin
   ```
   (senha mínima de 8 caracteres; pode usar `--name` e `--email`; pode adicionar `--role` para atribuir outros perfis).
3. Na tela de login, usar as credenciais criadas.

**Opção C — Usando interface web de Primeiro Acesso (NOVA — resolve o impasse):**
1. Executar `python run.py` (o sistema inicia, cria tabelas e perfis, mas **não cria nenhum usuário** se `AUTH_ADMIN_PASSWORD` não estiver definida).
2. Acessar [http://localhost:8000/login](http://localhost:8000/login) no navegador.
3. Clicar no link **"Primeiro acesso"** (ou acessar diretamente `/setup`).
4. Preencher o formulário de configuração inicial:
   - Nome completo
   - Nome de usuário
   - E-mail (opcional)
   - Senha (mínimo 8 caracteres)
   - Confirmação da senha
5. Clicar em "Criar administrador".
6. O sistema:
   - Valida os dados (senha mínimo 8 caracteres, confirmação iguais)
   - Cria o usuário administrador (`is_admin=True`)
   - Garante os perfis padrão (`ensure_default_roles`)
   - Vincula o perfil "Administrador" ao novo usuário
   - Registra a criação na auditoria (sem senha/credencial)
7. Redireciona para `/login` onde o administrador já pode fazer login com as credenciais criadas.

** Quando o Primeiro Acesso NÃO está disponível:**
- Se **`AUTH_ADMIN_PASSWORD` estiver definida** (admin já criado automaticamente)
- Se **existirem usuários** no banco (sistema já configurado)
- Nesses casos, o acesso a `/setup` é redirecionado para `/login`

**Impedimentos resolvidos pela interface web de Primeiro Acesso:**
- Antes: sem `AUTH_ADMIN_PASSWORD` e sem CLI, a instalação ficava inacessível
- Agora: a tela de login oferece o link "Primeiro acesso" que permite criar o primeiro administrador diretamente pelo navegador
- O link só aparece quando o sistema está em estado de primeira configuração (banco vazio sem usuários)

**Opção D — Usando AD (se integrado):**
1. O administrador configura a integração AD via `/admin/ad` — **mas isso só é acessível após um login**...
2. ...o que requer que o primeiro usuário já exista (via Opção A, B ou C).
3. Ou seja, **para configurar o AD pela interface, é necessário já existir um usuário local administrador** — o AD não resolve o problema do primeiro acesso.

**Resumo definitivo:** O SisPatrimônio Pro oferece **quatro formas** de criar o primeiro administrador:
1. **Variável de ambiente** (`AUTH_ADMIN_PASSWORD`) — automático no start
2. **Interface web de Primeiro Acesso** (`/setup`) — via navegador, resolve o impasse de instalações sem var de ambiente
3. **CLI** (`python -m app.cli create-user`) — criação manual
4. **AD** — só funciona se já existir um usuário local para acessar a configuração

Sem nenhuma dessas formas, uma instalação nova não permite login. Agora, com a interface web de Primeiro Acesso, o impasse é resolvido para instalações sem `AUTH_ADMIN_PASSWORD`.

---

## 15. Verificação Final

```
[x] Nenhum arquivo foi alterado.
[x] Nenhum arquivo foi criado.
[x] Nenhum arquivo foi excluído.
[x] Nenhum dado foi alterado (somente leitura de código).
[x] Nenhuma migration foi executada (apenas análise do código).
[x] Nenhuma configuração foi alterada (somente leitura de config.py).
[x] Nenhuma senha/credencial foi alterada (somente documentação do mecanismo).
[x] Nenhuma dependência foi modificada (somente leitura de requirements.txt).
[x] Nenhuma funcionalidade foi modificada (somente documentação do fluxo).
```

---

## 16. Evidências

Todas as conclusões deste relatório são baseadas exclusivamente na leitura do código-fonte existente. As evidências (arquivos, funções, linhas) estão indicadas em cada seção. Onde não foi possível determinar, está marcado explicitamente.

**Arquivos consultados:**
- `run.py`
- `app/__init__.py`
- `app/main.py`
- `app/config.py`
- `app/database.py`
- `app/cli.py`
- `app/services/auth_service.py`
- `app/services/permission_service.py`
- `app/services/auth_provider.py`
- `app/services/session_service.py`
- `app/services/ad_service.py`
- `app/services/ad_ldap.py`
- `app/api/deps.py`
- `app/api/auth_api.py`
- `app/api/v1_router.py`
- `app/web/routes.py`
- `app/web/admin_routes.py`
- `app/web/help_routes.py`
- `app/web/templates/login.html`
- `app/web/templates/setup.html`
- `app/web/templates/admin/ad/settings.html`
- `app/models/user.py`
- `app/models/session.py`
- `app/models/role.py`
- `app/models/permission.py`
- `app/models/user_role.py`
- `app/models/role_permission.py`
- `app/models/ad_settings.py`
- `app/models/ad_group_role.py`
- `app/models/enums.py`
- `app/services/audit_service.py`
- `seed_demo.py`
- `requirements.txt`
- `docs/ARQUITETURA_E_MANUTENCAO.md`

---

**Relatório gerado a partir da análise do código-fonte do SisPatrimônio Pro (versão 1.0.0).**
**Nenhuma alteração foi realizada no sistema.**
