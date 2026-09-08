# PLANO DE MIGRAÇÃO DO BANCO DE DADOS — SISPATRIMÔNIO PRO

> **Documento gerado por análise técnica estática do código-fonte.**  
> **Regra absoluta observada:** Não foram realizadas alterações no sistema, nem no banco de dados, nem no repositório Git durante esta análise.

---

## 1. RESUMO EXECUTIVO

**Sistema analisado:** SisPatrimônio Pro v1.0.0  
**Banco atual:** SQLite (arquivo `data/patrimonio.db`, 1.47 MB)  
**ORM:** SQLAlchemy 2.0.52  
**Framework:** FastAPI + Uvicorn  
**Linguagem:** Python 3.10+

**Recomendação:** PostgreSQL é **recomendado** para este sistema. A migração apresenta **risco MÉDIO**, pois:
- O sistema não usa SQL bruto específico do SQLite no dia a dia (toda consulta é via ORM)
- Apenas o mecanismo de migração leve (`_ensure_schema_migrations`) depende de `PRAGMA`
- Há ~2.277 movimentações e ~193 ativos que precisarão de transferência
- O schema é bem estruturado com FKs, índices e constraints

---

## 2. ARQUITETURA ATUAL

```
Browser/Cliente HTTP
    ↓
FastAPI (app/main.py) — Uvicorn
    ├── Rotas Web (Jinja2)  →  app/web/routes.py, admin_routes.py, help_routes.py
    └── API REST (/api/v1)  →  app/api/*_api.py
    ↓ (dependências de auth: app/api/deps.py)
Services (17 módulos)  →  app/services/*
    ↓
Models (16 modelos SQLAlchemy + enums)  →  app/models/*
    ↓
SQLAlchemy (create_engine + sessionmaker + declarative_base)
    ↓
SQLite → arquivo data/patrimonio.db (1.47 MB, 12 tabelas)
```

**Nilorização:**
- **Framework web:** FastAPI 0.141.1
- **Servidor:** Uvicorn 0.30.6
- **ORM:** SQLAlchemy 2.0.52
- **Driver:** sqlite3 (padrão Python, sem driver PostgreSQL instalado)
- **Template:** Jinja2 3.1.6
- **Autenticação:** Local (PBKDF2-HMAC-SHA256) + AD/LDAP (ldap3)
- **Migrações:** NENHUM sistema formal (Alembic ausente). Apenas `Base.metadata.create_all` + `_ensure_schema_migrations()` com PRAGMA

---

## 3. BANCO DE DADOS ATUAL

| Item | Valor |
|------|-------|
| **Tipo** | SQLite 3.x |
| **Arquivo** | `data/patrimonio.db` |
| **Tamanho** | 1.474.560 bytes (~1.4 MB) |
| **Tabelas** | 12 (confirmado via `.tables`) |
| **Dados** | 2 usuários, 193 ativos, 2.277 movimentações, 55 colaboradores, 20 locais |

**Tabelas encontradas:**
1. `users` — 2 registros
2. `assets` — 193 registros
3. `movements` — 2.277 registros
4. `custodians` — 55 registros
5. `locations` — 20 registros
6. `maintenances` — não contado (presumivelmente poucos)
7. `audit_logs` — não contado
8. `user_sessions` — não contado
9. `roles` — não contado (7 perfis padrão seed)
10. `permissions` — não contado (29 permissões)
11. `user_roles` — não contado
12. `role_permissions` — não contado
13. `ad_group_roles` — não contado
14. `ad_settings` — singleton (id=1)

---

## 4. CONFIGURAÇÃO DA CONEXÃO

**Arquivo:** `app/config.py` (linha 10)

```python
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'patrimonio.db'}")
```

**Configuração do engine:** `app/database.py` (linhas 4-12)

```python
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False
)
```

**Ponto crítico:** A lógica condicional `if DATABASE_URL.startswith("sqlite")` em `connect_args` precisa ser removida/generalizada para o PostgreSQL.

**Variáveis de ambiente relevantes:**
- `DATABASE_URL` — controlling toda a conexão
- `APP_HOST` / `APP_PORT` — servidor (não afetado pela migração)
- `AUTH_*` — autenticação (não afetado)
- `AD_*` — integração AD (não afetada)

---

## 5. ANÁLISE DO SQLALCHEMY

### Engine e Sessão

```python
# app/database.py
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Dependência do SQLite no código

| Localização | Dependência SQLite | Necessidade de alteração |
|-------------|-------------------|------------------------|
| `app/database.py:6` | `connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}` | **Sim** — remover condicional ou tornar genérico |
| `app/database.py:39` | `PRAGMA table_info(users)` em `_ensure_schema_migrations()` | **Sim** — substituir por consulta information_schema ou refatorar |
| `app/database.py:59` | `PRAGMA table_info(user_roles)` | **Sim** — mesma situação |
| `tests/conftest.py:18` | `SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"` | Sim — parametrizar para testes com PostgreSQL |

### Sessões e Transações

- `autocommit=False, autoflush=False` — padrão recomendado, funciona no PostgreSQL
- `get_db()` é uma generator dependency do FastAPI — funciona igual
- `db.commit()` / `db.refresh()` — padrão SQLAlchemy, compatível
- `db.query(Model).filter(...).first()` — ORM, compatível

### Observação importante

O sistema **não usa SQL bruto** em consultas de negócio. Toda a lógica usa:
- `db.query(Model).filter(...)`
- `db.query(Model).options(joinedload(...))`
- `db.query(func.count(...))`
- `db.query(Model).filter(...).all()`

As únicas exceções de SQL bruto são:
1. `PRAGMA table_info(...)` no `_ensure_schema_migrations()` — SQLite-specific
2. `text("ALTER TABLE ... ADD COLUMN")` no `_ensure_schema_migrations()` — deve ser adaptado

---

## 6. ANÁLISE DOS MODELOS

### Tabela: `users`

| Campo | Tipo atual | PK | FK | NULL | Default | Observação |
|-------|-----------|-----|-----|------|---------|------------|
| id | Integer | ✓ | — | NO | — | Auto-increment (SQLite) |
| username | String(100) | — | — | NO | — | UNIQUE + INDEX |
| password_hash | String(255) | — | — | NO | — | — |
| full_name | String(150) | — | — | YES | — | — |
| email | String(150) | — | — | YES | — | — |
| is_active | Boolean | — | — | YES | — | — |
| is_admin | Boolean | — | — | YES | — | — |
| auth_provider | String(20) | — | — | NO | 'local' | — |
| last_login | DateTime | — | — | YES | — | — |
| created_at | DateTime | — | — | YES | datetime.utcnow | — |
| failed_login_attempts | Integer | — | — | NO | 0 | Adicionado via migração |
| locked_until | DateTime | — | — | YES | — | Adicionado via migração |
| ad_object_guid | String(64) | — | — | YES | — | INDEX |
| ad_dn | String(400) | — | — | YES | — | — |
| ad_last_sync | DateTime | — | — | YES | — | — |

**Incompatibilidade PostgreSQL:**
- `Boolean` do SQLAlchemy mapeia para `BOOLEAN` no PostgreSQL — OK
- `DateTime` mapeia para `TIMESTAMP` — OK
- `String` mapeia para `VARCHAR` — OK

### Tabela: `assets`

| Campo | Tipo atual | PK | FK | NULL | Default | Observação |
|-------|-----------|-----|-----|------|---------|------------|
| id | Integer | ✓ | — | NO | — | Auto-increment |
| tag | String(50) | — | — | NO | — | UNIQUE + INDEX |
| name | String(150) | — | — | NO | — | INDEX |
| category | Enum(AssetCategory) | — | — | NO | AssetCategory.OTHER | SQLite armazena como VARCHAR(10) |
| brand | String(100) | — | — | YES | — | — |
| model | String(100) | — | — | YES | — | — |
| serial_number | String(100) | — | — | YES | — | UNIQUE + INDEX |
| specifications | Text | — | — | YES | — | — |
| purchase_date | DateTime | — | — | YES | — | — |
| purchase_value | Float | — | — | NO | 0.0 | — |
| invoice_number | String(100) | — | — | YES | — | — |
| supplier | String(150) | — | — | YES | — | — |
| warranty_expiry | DateTime | — | — | YES | — | — |
| status | Enum(AssetStatus) | — | — | NO | AssetStatus.AVAILABLE | VARCHAR(14) |
| condition | Enum(AssetCondition) | — | — | NO | AssetCondition.NEW | VARCHAR(13) |
| location_id | Integer | — | ✓→locations.id | YES | — | — |
| custodian_id | Integer | — | ✓→custodians.id | YES | — | — |
| notes | Text | — | — | YES | — | — |
| created_at | DateTime | — | — | YES | datetime.utcnow | — |
| updated_at | DateTime | — | — | YES | datetime.utcnow | onupdate |

**Ponto de atenção — ENUMS:**
No SQLite, os enums `AssetStatus`, `AssetCondition`, `AssetCategory` são armazenados como VARCHAR (ex: `VARCHAR(10)` para category, `VARCHAR(14)` para status, `VARCHAR(13)` para condition). No PostgreSQL, o SQLAlchemy pode usar o tipo nativo `ENUM` ou manter como VARCHAR. Como os valores são strings fixas definidos em `app/models/enums.py`, **recomenda-se manter como VARCHAR no PostgreSQL** para evitar complicações com criação de tipo ENUM e migração de dados existentes.

### Tabela: `movements`

| Campo | Tipo atual | PK | FK | NULL | Default | Observação |
|-------|-----------|-----|-----|------|---------|------------|
| id | Integer | ✓ | — | NO | — | — |
| movement_uuid | String(36) | — | — | YES | uuid4() | UNIQUE + INDEX |
| asset_id | Integer | — | ✓→assets.id CASCADE | NO | — | INDEX |
| movement_type | Enum(MovementType) | — | — | NO | — | VARCHAR(15) + INDEX |
| timestamp | DateTime | — | — | NO | datetime.utcnow | INDEX |
| origin_location_id | Integer | — | ✓→locations.id | YES | — | — |
| origin_location_name | String(150) | — | — | YES | — | Snapshot textual |
| origin_custodian_id | Integer | — | ✓→custodians.id | YES | — | — |
| origin_custodian_name | String(150) | — | — | YES | — | Snapshot textual |
| destination_location_id | Integer | — | ✓→locations.id | YES | — | — |
| destination_location_name | String(150) | — | — | YES | — | Snapshot textual |
| destination_custodian_id | Integer | — | ✓→custodians.id | YES | — | — |
| destination_custodian_name | String(150) | — | — | YES | — | Snapshot textual |
| previous_status | Enum(AssetStatus) | — | — | YES | — | VARCHAR(14) |
| new_status | Enum(AssetStatus) | — | — | NO | — | VARCHAR(14) |
| previous_condition | Enum(AssetCondition) | — | — | YES | — | VARCHAR(13) |
| new_condition | Enum(AssetCondition) | — | — | YES | — | VARCHAR(13) |
| reason | String(255) | — | — | NO | — | — |
| operator_name | String(100) | — | — | NO | 'Sistema' | — |
| term_code | String(50) | — | — | YES | — | INDEX |
| term_signed | Boolean | — | — | YES | False | — |
| notes | Text | — | — | YES | — | — |
| created_at | DateTime | — | — | YES | datetime.utcnow | — |

**FKs com múltiplas referências:** `origin_location_id` e `destination_location_id` ambas referenciam `locations.id`, igual para custodiantes. Isso é suportado pelo PostgreSQL.

### Tabela: `custodians`

| Campo | Tipo | PK | FK | NULL | Default |
|-------|------|-----|-----|------|---------|
| id | Integer | ✓ | — | NO | — |
| registration_code | String(50) | — | — | NO | — | UNIQUE + INDEX |
| name | String(150) | — | — | NO | — | INDEX |
| email | String(150) | — | — | NO | — | UNIQUE + INDEX |
| cpf | String(20) | — | — | YES | — | — |
| role | String(100) | — | — | NO | — | — |
| department | String(100) | — | — | NO | — | — |
| is_active | Boolean | — | — | YES | True | — |
| created_at | DateTime | — | — | YES | datetime.utcnow | — |

### Tabela: `locations`

| Campo | Tipo | PK | NULL | Default |
|-------|------|-----|-----|---------|
| id | Integer | ✓ | NO | — |
| name | String(100) | — | NO | — | UNIQUE + INDEX |
| branch | String(100) | — | NO | — |
| building | String(100) | — | YES | — |
| floor | String(50) | — | YES | — |
| room | String(50) | — | YES | — |
| department | String(100) | — | NO | — |
| manager_name | String(100) | — | YES | — |
| description | Text | — | YES | — |
| created_at | DateTime | — | YES | datetime.utcnow |

### Tabela: `maintenances`

| Campo | Tipo | PK | FK | NULL |
|-------|------|-----|-----|------|
| id | Integer | ✓ | — | NO |
| asset_id | Integer | — | ✓→assets.id CASCADE | NO |
| maintenance_type | Enum(MaintenanceType) | — | — | NO | VARCHAR(10) |
| status | Enum(MaintenanceStatus) | — | — | NO | VARCHAR(11) |
| provider_name | String(150) | — | — | YES |
| description | Text | — | — | NO |
| solution | Text | — | — | YES |
| cost | Float | — | — | YES | 0.0 |
| start_date | DateTime | — | — | NO |
| end_date | DateTime | — | — | YES |
| created_at | DateTime | — | — | YES |

### Tabela: `audit_logs`

| Campo | Tipo | PK | FK | NULL |
|-------|------|-----|-----|------|
| id | Integer | ✓ | — | NO |
| timestamp | DateTime | — | — | NO | INDEX |
| user_id | Integer | — | ✓→users.id SET NULL | YES | INDEX |
| username | String(100) | — | — | YES |
| action | String(50) | — | — | NO | INDEX |
| module | String(50) | — | — | YES | INDEX |
| resource | String(100) | — | — | YES |
| resource_id | Integer | — | — | YES |
| resource_ref | String(150) | — | — | YES |
| ip_address | String(45) | — | — | YES |
| result | String(20) | — | — | NO | DEFAULT 'SUCCESS' |
| description | Text | — | — | YES |
| previous_data | Text | — | — | YES | JSON em texto |
| new_data | Text | — | — | YES | JSON em texto |

**Observação:** `previous_data` e `new_data` são JSON serializado em TEXT. No PostgreSQL, seria ideal usar `JSONB` para consultas eficientes, mas isso seria uma melhoria futura, não obrigatória na migração.

### Demais tabelas (RBAC e AD)

- `roles` — `name` UNIQUE, `is_system` BOOLEAN
- `permissions` — `name` UNIQUE, `module` INDEX
- `user_roles` — UniqueConstraint (user_id, role_id), FK CASCADE
- `role_permissions` — UniqueConstraint (role_id, permission_id), FK CASCADE
- `user_sessions` — `token_hash` UNIQUE
- `ad_settings` — singleton id=1
- `ad_group_roles` — `group_name` UNIQUE

Todas estas usam tipos básicos (Integer, String, Boolean, DateTime) — **plena compatibilidade com PostgreSQL**.

---

## 7. ANÁLISE DAS MIGRAÇÕES

### Situação Atual

O sistema **não utiliza Alembic** ou qualquer sistema de migrações versionadas.

**Mecanismo atual** (`app/database.py::init_db` e `_ensure_schema_migrations`):

1. `Base.metadata.create_all(bind=engine)` — cria TODAS as tabelas que ainda não existem
2. `_ensure_schema_migrations()` — ADICIONA colunas em tabelas EXISTENTES via:
   - `PRAGMA table_info(tabela)` — para verificar quais colunas existem
   - `ALTER TABLE ... ADD COLUMN ...` — adiciona colunas faltantes

**Colunas adicionadas dinamicamente:**
- `users`: `failed_login_attempts`, `locked_until`, `ad_object_guid`, `ad_dn`, `ad_last_sync`
- `user_roles`: `assigned_by`

### Problemas para PostgreSQL

1. **`PRAGMA table_info()` é exclusivo do SQLite** — não funciona no PostgreSQL
2. **`ALTER TABLE ... ADD COLUMN` com condição `IF NOT EXISTS`** — o PostgreSQL suporta `ADD COLUMN IF NOT EXISTS` desde a versão 9.6, mas a verificação via PRAGMA precisa ser substituída
3. **`Base.metadata.create_all`** — funciona no PostgreSQL, mas não é ideal para produção (não gerencia versões)

### Recomendação

**Alembic** é a escolha recomendada para o PostgreSQL porque:
- É o padrão-ouro para migrações SQLAlchemy
- Gera scripts de upgrade/downgrade versionados
- Permite revisão humana das mudanças
- Integra-se com o workflow existente (basta `alembic init` e configurar o env.py)
- Permite rollback de migrações via `alembic downgrade`

**Alternativa:** Se Alembic for considerado pesado, as migrations manuais poderiam ser mantidas com consultas ao `information_schema` do PostgreSQL no lugar de `PRAGMA`, mas isso é menos robusto.

---

## 8. DEPENDÊNCIAS SQLITE ENCONTRADAS

### Código que depende diretamente do SQLite

| Arquivo | Linha | Depência | Impacto |
|---------|-------|----------|---------|
| `app/database.py` | 6 | `DATABASE_URL.startswith("sqlite")` — define `check_same_thread` | **Crítico** — remover ou adaptar |
| `app/database.py` | 39 | `PRAGMA table_info(users)` | **Crítico** — substituir |
| `app/database.py` | 59 | `PRAGMA table_info(user_roles)` | **Crítico** — substituir |
| `app/database.py` | 41-42, 61-62 | `ALTER TABLE ... ADD COLUMN` via `text()` | **Moderado** — syntax compatível, mas condição de verificação muda |
| `tests/conftest.py` | 18 | `sqlite:///:memory:` URL de teste | **Baixo** — parametrizar para testes com PostgreSQL |
| `seed_demo.py` | 25 | `Base.metadata.drop_all(bind=engine)` | **Baixo** — `drop_all` funciona no PostgreSQL |

### SQL bruto encontrado

- `PRAGMA table_info(...)` — SQLite exclusivo (em `_ensure_schema_migrations`)
- `ALTER TABLE users ADD COLUMN ...` — syntax padrão SQL, funciona no PostgreSQL
- `ALTER TABLE user_roles ADD COLUMN ...` — idem

**Nenhum SQL SELECT/INSERT/UPDATE/DELETE manual encontrado** — toda operação usa ORM.

---

## 9. COMPATIBILIDADE SQLITE → POSTGRESQL

### Enums (CRITICAL — atenção)

**SQLite:**
```sql
CREATE TABLE assets (
    category VARCHAR(10) NOT NULL,  -- armazena 'NOTEBOOK', 'DESKTOP', etc.
    status VARCHAR(14) NOT NULL,    -- armazena 'DISPONIVEL', 'EM_USO', etc.
    ...
)
```

**PostgreSQL com SQLAlchemy Enum:**
Se mantido como `Enum(AssetStatus)` no modelo, o PostgreSQL criará tipos ENUM dedicados. Isso **pode complicar a migração de dados existentes** se os valores não couberem exatamente.

**Solução recomendada:** Manter os campos como `String`/`VARCHAR` no PostgreSQL (mesmo com os_enums em Python para validação), já que os dados existentes são strings textuais. Isso evita necessidade de converter tipos ENUM durante a migração.

### Booleanos

**SQLite:** BOOLEAN mapeia para INTEGER (0/1)  
**PostgreSQL:** BOOLEAN é tipo nativo (true/false)  
**Impacto:** Nenhum — SQLAlchemy abstrai a diferença. Os dados migrados devem ser 0/1 ou true/false, ambos aceitos.

### Datas e Horas

**SQLite:** DATETIME é TEXT (formato flexível)  
**PostgreSQL:** TIMESTAMP é tipo nativo  
**Impacto:** Os dados devem estar em formato ISO 8601 (`YYYY-MM-DD HH:MM:SS`). Se houver inconsistências de formato no SQLite, a migração pode falhar. **Verificar os dados existentes antes.**

### AUTOINCREMENT vs SERIAL/IDENTITY

**SQLite:** `INTEGER PRIMARY KEY` é alias para ROWID (auto-incremento implícito)  
**PostgreSQL:** Precisa de `SERIAL` ou `IDENTITY` para auto-incremento  
**Impacto:** SQLAlchemy `Integer(primary_key=True)` gera `SERIAL` no PostgreSQL automaticamente. Os IDs existentes (1, 2, 3...) serão preservados se a migração inserir explicitamente os valores.

### CHECK SAME THREAD

**SQLite:** Necessário `check_same_thread=False` para uso com FastAPI multithread  
**PostgreSQL:** Não aplicável — cada conexão é thread-safe  
**Impacto:** Remover a lógica condicional em `app/database.py:6`.

### PRAGMA

**SQLite:** `PRAGMA table_info()` para introspecção  
**PostgreSQL:** Usar `information_schema.columns` ou `\d` no psql  
**Impacto:** `_ensure_schema_migrations()` precisa ser refatorado completamente.

### Transações e CONCORRÊNCIA

**SQLite:**
- Escrita serializada (WAL não está ativado conforme análise)
- Leitura concorrente permitida
- Arquivo único — bloqueio no nível do arquivo
- `check_same_thread=False` necessário porque multiple threads acessam a mesma conexão

**PostgreSQL:**
- MVCC — múltiplas transações concorrentes
- Leitura não bloqueia escrita e vice-versa
- Locking em nível de linha (não arquivo)
- Pool de conexões gerenciado pelo driver (psycopg2/pgbouncer)

**Impacto positivo:** O PostgreSQL lida muito melhor com múltiplos usuários simultâneos, especialmente para:
- Múltiplas movimentações simultâneas
- Consultas de relatórios enquanto usuários editem
- Importação CSV concorrente

### Funções SQL

Nenhuma função SQL específica do SQLite foi encontrada no código. Toda lógica é em Python via ORM.

---

## 10. RISCOS

| # | Risco | Gravidade | Mitigação |
|---|-------|-----------|-----------|
| 1 | **ENUMs no PostgreSQL** — criação de tipos ENUM novos podem conflitar com dados existentes | MÉDIO | Manter como VARCHAR no PostgreSQL; validar no modelo Python |
| 2 | **Datas inconsistentes** — SQLite aceita formatos flexíveis, PostgreSQL exige TIMESTAMP válido | MÉDIO | Validar formato das datas antes da migração; limpiar se necessário |
| 3 | **Migration de `_ensure_schema_migrations`** — PRAGMA não existe no PostgreSQL | ALTO | Refatorar para usar information_schema ou abandonar migrações dinâmicas a favor de Alembic |
| 4 | **Perda de dados durante transferência** — conversão entre formatos | ALTO | Usar ferramentas de migração testadas (pgloader, script Python com SQLAlchemy) |
| 5 | **IDs e sequências** — ao inserir dados no PostgreSQL, as sequências precisam ser sincronizadas | MÉDIO | `setval()` após migração para cada tabela |
| 6 | **Tamanho do banco** — 1.4 MB é pequeno, mas 2.277 movimentações precisam de importação ordenada | BAIXO | Importar em ordem de dependência (referências primeiro) |
| 7 | **Testes existentes** — usam SQLite em memória (`sqlite:///:memory:`) | MÉDIO | Parametrizar URL de teste ou manter SQLite para testes |
| 8 | **JSON em TEXT** — `audit_logs.previous_data`/`new_data` são JSON em texto | BAIXO | PostgreSQL tem JSONB, mas TEXT funciona; migração direta OK |
| 9 | **Cascade DELETE** — SQLite e PostgreSQL handle CASCADE similarmente, mas necessita teste | BAIXO | Testar exclusão de ativo e verificar movimentações/maintenances removidas |
| 10 | **Integração AD** — `ad_settings` é singleton, não afetado pelo banco | BAIXO | Sem impacto |

---

## 11. ESTRATÉGIA DE BACKUP

### Antes da migração

1. **Backup do SQLite atual:**
   ```bash
   cp data/patrimonio.db data/patrimonio.db.backup-$(date +%Y%m%d-%H%M%S)
   ```
   Ou dump SQL:
   ```bash
   sqlite3 data/patrimonio.db ".dump" > dados_backup_$(date +%Y%m%d).sql
   ```

2. **Verificar integridade do SQLite:**
   ```bash
   sqlite3 data/patrimonio.db "PRAGMA integrity_check;"
   ```
   *(Apenas leitura — não modifica nada)*

3. **Backup do código:**
   ```bash
   git tag antes-migracao-pg-$(date +%Y%m%d)
   ```

### Após a migração

1. Manter o arquivo SQLite original **imutável** por pelo menos 30 dias
2. Fazer dump do PostgreSQL após migração para verificação cruzada:
   ```bash
   pg_dump -Fc sispatrimonio_pro > pg_backup_$(date +%Y%m%d).dump
   ```

### Durante a migração

- Não deletar o SQLite até validação completa
- Ter o dump SQL do SQLite disponível como fallback

---

## 12. PLANO DE MIGRAÇÃO

### Fase 0 — Preparação (Antes de qualquer mudança)

- [ ] Documentar versão atual do sistema: `APP_VERSION=1.0.0`
- [ ] Identificar ambiente de homologação (separado da produção)
- [ ] Agendar janela de manutenção (se produção)
- [ ] Comunicar stakeholders

### Fase 1 — Instalação do PostgreSQL

**Servidor PostgreSQL (documentação para execução futura):**

```bash
# Ubuntu/Debian (exemplo)
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Criar usuário e banco
sudo -u postgres createuser --interactive sispatrimonio
sudo -u postgres createdb -O sispatrimonio sispatrimonio_pro

# Senha (alterar para valor seguro)
sudo -u postgres psql -c "ALTER USER sispatrimonio WITH PASSWORD 'SENHA_SEGURA_AQUI';"

# Permissões
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE sispatrimonio_pro TO sispatrimonio;"
```

**Network/Segurança:**
- Restringir acesso à porta 5432 apenas para IPs autorizados
- Configurar `pg_hba.conf` para autenticação password
- Considerar SSL/TLS se acesso remoto

### Fase 2 — Schema no PostgreSQL

**Opção A — Alembic (Recomendado):**

```bash
pip install alembic psycopg2-binary
alembic init alembic
```

Configurar `alembic.ini`:
```ini
sqlalchemy.url = postgresql://sispatrimonio:SENHA@localhost/sispatrimonio_pro
```

Configurar `alembic/env.py` para usar os models do `app.models`.

Gerar primeira migration:
```bash
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

**Opção B — SQLAlchemy create_all (menos recomendado):**
```python
# Em um script de setup
from app.database import engine, Base
from app import models  # noqa
Base.metadata.create_all(bind=engine)
```
*(Nota: create_all não suporta ALTER — só cria tabelas novas. Para colunas adicionais, seria necessário migração manual como no SQLite.)*

### Fase 3 — Migração dos dados

**Ferramentas possíveis:**

1. **pgloader** (recomendado para conversão SQLite → PostgreSQL):
   ```bash
   pgloader sqlite:///data/patrimonio.db pgsql://sispatrimonio:SENHA@localhost/sispatrimonio_pro
   ```
   Vantagens: conversão automática de tipos, índices, FKs

2. **Script Python com SQLAlchemy** (mais controle):
   ```python
   # Pseudocódigo — executar em ambiente de homologação primeiro
   from sqlalchemy import create_engine
   from sqlalchemy.orm import sessionmaker, Session
   
   sqlite_engine = create_engine("sqlite:///data/patrimonio.db")
   pg_engine = create_engine("postgresql://sispatrimonio:SENHA@localhost/sispatrimonio_pro")
   
   with Session(sqlite_engine) as src, Session(pg_engine) as dest:
       # Iterar por cada tabela em ordem de dependência
       for table in dependency_order:
           rows = src.query(table).all()
           for row in rows:
               dest.add(row)
           dest.commit()
       # Sincronizar sequências
       for table in tables_with_auto_increment:
           max_id = dest.query(func.max(table.id)).scalar()
           dest.execute(text(f"SELECT setval('{table.__tablename__}_id_seq', {max_id})"))
   ```

**Ordem de importação recomendada:**
1. `permissions` — referência por `role_permissions`
2. `roles` — referência por `user_roles`, `role_permissions`, `ad_group_roles`
3. `users` — referência por `user_roles`, `user_sessions`, `audit_logs`
4. `locations` — referência por `assets`, `movements`
5. `custodians` — referência por `assets`, `movements`
6. `assets` — referência por `movements`, `maintenances`
7. `user_roles` — referência por usuário/perfil
8. `role_permissions` — referência por perfil/permissão
9. `ad_group_roles` — referência por grupo/perfil
10. `ad_settings` — singleton
11. `user_sessions` — sessões ativas
12. `audit_logs` — logs
13. `movements` — movimentações (FK para assets)
14. `maintenances` — manutenções (FK para assets)

**Pontos de atenção na migração:**
- **Booleanos:** Converter 0/1 para true/false se necessário (SQLAlchemy deve fazer automaticamente)
- **ENUMs:** Manter como VARCHAR — não transformar em tipo ENUM PostgreSQL
- **IDs:** Preservar IDs existentes (não recriar sequências)
- **Sequências:** Após inserção, sincronizar `setval()` para cada sequence
- **JSON em TEXT:** Manter como TEXT no PostgreSQL (JSONB é opcional)
- **NULLs:** Verificar colunas com NOT NULL que possam ter NULL no SQLite (ex: `purchase_value` tem default 0.0 no modelo, mas verificar dados reais)

### Fase 4 — Configuração da aplicação

**Alterar `app/config.py`:**

```python
# ANTES (SQLite):
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'patrimonio.db'}")

# DEPOIS (PostgreSQL):
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sispatrimonio:SENHA@localhost/sispatrimonio_pro")
```

**Alterar `app/database.py`:**

```python
# REMOVER a lógica condicional de check_same_thread:
# ANTES:
# connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# DEPOIS:
connect_args = {}  # PostgreSQL não precisa deste argumento
```

Ou manter a verificação, mas garantir que para SQLite não SQLite o dict é vazio.

**Refatorar `_ensure_schema_migrations`:**

Substituir `PRAGMA table_info()` por consulta ao `information_schema`:

```python
# Exemplo de substituição (documentação):
def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(text(
        f"SELECT 1 FROM information_schema.columns "
        f"WHERE table_name = '{table_name}' AND column_name = '{column_name}'"
    )).scalar()
    return result is not None
```

### Fase 5 — Testes

Ver **Seção 13 — Plano de Testes** abaixo.

### Fase 6 — Homologação

1. Instalar PostgreSQL em ambiente de teste
2. Executar migração de dados
3. Configurar `DATABASE_URL` para apontar para o PostgreSQL de homologação
4. Executar TODO o sistema normalmente (login, CRUD, relatórios)
5. Validar dados (ver Fase 7)
6. Executar suite de testes (adaptada para PostgreSQL)
7. Tempo de observação: pelo menos 1 semana com uso normal

### Fase 7 — Produção

1. **Janela de manutenção:** comunicar indisponibilidade temporária
2. **Backup final do SQLite:** cópia e dump
3. **Parar o serviço:** `Ctrl+C` no run.py ou systemctl stop
4. **Migração final:** executar migração de dados para PostgreSQL de produção
5. **Validar dados:** ver Fase 7 (seção de validação)
6. **Atualizar DATABASE_URL:** apontar para PostgreSQL de produção
7. **Iniciar serviço:** `python run.py` ou systemctl start
8. **Monitorar:** logs, erros, performance
9. **Manter rollback:** SQLite intacto por 30 dias

---

## 13. PLANO DE TESTES

### Testes de funcionalidade (adaptar suite existente)

| # | Teste | Rota/Service | Critério de sucesso |
|---|-------|-------------|---------------------|
| 1 | Login com conta local | `/api/v1/auth/login` | 200 + cookie válido |
| 2 | Login com conta bloqueada | `/api/v1/auth/login` | 423 Locked |
| 3 | Logout | `/api/v1/auth/logout` | Sessão removida |
| 4 | Criar usuário administrador | CLI `create-user` | Usuário criado com hash PBKDF2 |
| 5 | CRUD de ativos | `/api/v1/assets` | Criar, ler, atualizar funcionam |
| 6 | Tag único e serial único | `AssetService.create` | ValueError se duplicado |
| 7 | Movimentação de alocação | `MovementService.create_movement` | Movimento criado, termo gerado |
| 8 | Movimentação de devolução | `MovementService.create_movement` | Status → AVAILABLE |
| 9 | Movimentação de baixa | `MovementService.create_movement` | Status → WRITTEN_OFF |
| 10 | Não movimentar ativo baixado | `MovementService.create_movement` | ValueError |
| 11 | Timeline de movimentações | `MovementService.get_timeline_for_asset` | Histórico completo retornado |
| 12 | Depreciação linear | `AssetService.calculate_depreciation` | Cálculo correto (20%/ano) |
| 13 | Importação CSV de ativos | `/api/v1/assets/import/csv` | Ativos importados corretamente |
| 14 | Importação CSV de colaboradores | `/api/v1/custodians/import/csv` | Colaboradores importados |
| 15 | CRUD de colaboradores | `/api/v1/custodians` | Criar, editar funcionam |
| 16 | CRUD de locais | `/api/v1/locations` | Criar, editar funcionam |
| 17 | Manutenção — criar OS | `MaintenanceService.create` | OS criada, movimentação de envio gerada |
| 18 | Manutenção — finalizar | `MaintenanceService.complete_maintenance` | Status → CONCLUIDA, retorno gerado |
| 19 | Dashboard stats | `/api/v1/reports/dashboard-stats` | KPIs corretos |
| 20 | Exportação CSV de inventário | `/api/v1/reports/inventory/csv` | CSV válido |
| 21 | Exportação CSV de movimentações | `/api/v1/reports/movements/csv` | CSV válido |
| 22 | Exportação CSV de colaboradores | `/api/v1/reports/custodians/csv` | CSV válido |
| 23 | Permissões RBAC — deny by default | `require_permission` | Sem perfil → 403 |
| 24 | Permissões RBAC — perfil atribuído | `require_permission` | Com perfil → acesso liberado |
| 25 | Último administrador protegido | `admin_routes.py` | Não pode remover último admin |
| 26 | Auditoria — login | `audit_service.write_audit` | LOGIN registrado |
| 27 | Auditoria — movimentação | `audit_service.write_audit` | MOVIMENTACAO registrado |
| 28 | Auditoria — acesso negado | `require_permission` | ACESSO_NEGADO auditado |
| 29 | Integração AD — conexão | `ad_ldap.test_connection` | True/False conforme config |
| 30 | Teste de sessão expirada | `session_service` | Sessão expirada → 401 |

### Testes de migração específicos

| # | Teste | Critério |
|---|-------|----------|
| M1 | Contagem de registros por tabela | Igual SQLite vs PostgreSQL |
| M2 | IDs preservados | IDs iguais em ambas as bases |
| M3 | Dados de ativos | Mesmo tag, name, purchase_value, status |
| M4 | Dados de movimentações | Mesmo movement_uuid, asset_id, timestamp |
| M5 | Integridade referencial | Nenhuma FK órfã |
| M6 | Sequências sincronizadas | `setval()` correto para cada tabela |
| M7 | Relatório de inventário | Mesmo número de ativos, mesmo total de valor |
| M8 | Dashboard stats | Mesmos KPIs calculados |
| M9 | Login de todos os usuários | Todos os usuários conseguem logar |
| M10 | Histórico de um ativo específico | Timeline completa e igual |

---

## 14. PLANO DE ROLLBACK

### Cenário: Problema detectado no PostgreSQL

**Passo a passo de rollback:**

1. **Não apagar o SQLite** — manter `data/patrimonio.db` intacto
2. **Parar a aplicação** que está apontando para PostgreSQL
3. **Reverter DATABASE_URL** para SQLite:
   ```bash
   # Em app/config.py ou variável de ambiente:
   DATABASE_URL=sqlite:///data/patrimonio.db
   ```
4. **Reiniciar a aplicação:**
   ```bash
   python run.py
   ```
5. **Validar:** executar testes rápidos de login e CRUD

### Tempo estimado de rollback
- Reverter configuração: 5 minutos
- Reiniciar serviço: 1 minuto
- Validar operação: 10 minutos

### Condição para rollback
- Qualquer erro de dados (perda, corrupção, inconsistência)
- Erro de configuração que impeça operação
- Performance inaceitável
- Problema com migração de dados não resolvido em 24h

### O que NÃO fazer no rollback
- Não deletar o PostgreSQL (mantê-lo para análise do problema)
- Não alterar o SQLite (ele é a versão "boa conhecida")
- Não fazer commit de código com a configuração PostgreSQL até validação OK

---

## 15. ARQUIVOS QUE DEVEM SER ALTERADOS

| Arquivo | Motivo | Alteração prevista | Risco |
|---------|--------|-------------------|-------|
| `app/config.py` | DATABASE_URL default SQLite | Alterar default ou depender apenas de variável de ambiente | BAIXO — apenas string de conexão |
| `app/database.py` | `check_same_thread` condicional | Remover lógica condicional ou tornar genérica | BAIXO — apenas connect_args |
| `app/database.py` | `_ensure_schema_migrations` com PRAGMA | Refatorar para usar information_schema ou eliminar | MÉDIO — altera comportamento de migrations |
| `tests/conftest.py` | URL de teste `sqlite:///:memory:` | Parametrizar ou manter para testes SQLite | BAIXO — testes podem continuar com SQLite |
| `requirements.txt` | Faltam drivers PostgreSQL | Adicionar `psycopg2-binary` ou `psycopg2` | BAIXO — dependência nova |
| `docs/ARQUITETURA_E_MANUTENCAO.md` | Documentação do banco atual | Atualizar com informações do PostgreSQL | BAIXO — documentação |
| `docs/INVENTARIO_TECNICO.md` | Documentação técnica | Atualizar stack com PostgreSQL | BAIXO — documentação |
| `docs/GUIA_DE_MANUTENCAO.md` | Guia de manutenção | Atualizar procedimentos de backup/migração | BAIXO — documentação |
| `README.md` | Documentação geral | Atualizar seção de banco de dados | BAIXO — documentação |

**Nota:** `seed_demo.py` usa `drop_all` + `create_all` — funciona no PostgreSQL, mas `drop_all` apaga todos os dados. Cuidado se usado em produção.

---

## 16. DEPENDÊNCIAS QUE DEVEM SER ADICIONADAS

### Obrigatórias

| Dependência | Para que serves | Onde será utilizada | Comando de instalação futuro |
|-------------|-----------------|---------------------|------------------------------|
| `psycopg2-binary` (ou `psycopg2`) | Driver PostgreSQL para SQLAlchemy | SQLAlchemy create_engine | `pip install psycopg2-binary` |
| `alembic` (recomendado) | Sistema de migrations versionadas | Migrações de schema | `pip install alembic` |
| `pgloader` (opcional) | Ferramenta de migração de dados | Transferência SQLite → PostgreSQL | Instalação via sistema operacional (`apt/brew`) |

### Opcionais

| Dependência | Para que serve |
|-------------|---------------|
| `psycopg2` (compilado) | Performance melhor que psycopg2-binary em produção |
| `pgbouncer` | Pool de conexões se necessário (para muitos concorrentes) |
| `pg_stat_statements` | Extensão de monitoramento de queries |

**Não instalar agora** — apenas documentar para instalação futura no momento da migração.

---

## 17. COMANDOS QUE DEVEM SER EXECUTADOS FUTURAMENTE

### Instalação do PostgreSQL (futuro)

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib

# Fedora/RHEL
sudo dnf install -y postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl enable postgresql
sudo systemctl start postgresql

# macOS (Homebrew)
brew install postgresql
brew services start postgresql
```

### Criar banco e usuário (futuro)

```bash
sudo -u postgres createuser --interactive sispatrimonio
sudo -u postgres createdb -O sispatrimonio sispatrimonio_pro
sudo -u postgres psql -c "ALTER USER sispatrimonio WITH PASSWORD 'SENHA_SEGURA';"
```

### Configurar pg_hba.conf (futuro)

```bash
# Editar /etc/postgresql/*/main/pg_hba.conf ou equivalente
# Exemplo: acesso password para usuario sispatrimonio
host    sispatrimonio_pro    sispatrimonio    127.0.0.1/32            md5
host    sispatrimonio_pro    sispatrimonio    ::1/128                 md5
```

### Instalar dependências Python (futuro)

```bash
pip install psycopg2-binary alembic
```

### Gerar migration Alembic (futuro)

```bash
alembic init alembic
# Configurar alembic.ini e env.py
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

### Migração de dados com pgloader (futuro)

```bash
pgloader \
  --with "data only" \
  --with "workers = 4" \
  sqlite:///data/patrimonio.db \
  pgsql://sispatrimonio:SENHA@localhost/sispatrimonio_pro
```

### Migração de dados com script Python (futuro — alternativa)

```bash
python migrate_sqlite_to_postgresql.py
# Script para ser desenvolvido: lê SQLite, insere no PostgreSQL preservando IDs
```

### Sincronizar sequências (futuro — após migração)

```sql
-- Para cada tabela com SERIAL/IDENTITY:
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));
SELECT setval('assets_id_seq', (SELECT MAX(id) FROM assets));
SELECT setval('movements_id_seq', (SELECT MAX(id) FROM movements));
-- ... e assim por diante para todas as tabelas com ID auto-increment
```

### Validar integridade (futuro)

```sql
-- Verificar FKs órfãs no PostgreSQL
SELECT COUNT(*) FROM movements m
LEFT JOIN assets a ON m.asset_id = a.id
WHERE a.id IS NULL;

SELECT COUNT(*) FROM audit_logs al
LEFT JOIN users u ON al.user_id = u.id
WHERE u.id IS NULL AND al.user_id IS NOT NULL;
-- Esperado: 0 (ou apenas registros com user_id=NULL que são válidos por SET NULL)
```

### Dump de backup do PostgreSQL (futuro)

```bash
pg_dump -Fc sispatrimonio_pro -f backup_$(date +%Y%m%d).dump
```

### Restore do PostgreSQL (futuro)

```bash
pg_restore -d sispatrimonio_pro backup_20260907.dump
```

---

## 18. CHECKLIST PRÉ-MIGRAÇÃO

### Documentação e Planejamento
- [ ] Revisar este plano com a equipe
- [ ] Agendar janela de manutenção (se produção)
- [ ] Identificar ambiente de homologação
- [ ] Documentar versão do sistema: `APP_VERSION=1.0.0`

### Banco SQLite Atual
- [ ] Executar `PRAGMA integrity_check;` no SQLite — verificar sem erros
- [ ] Backup do arquivo: `cp data/patrimonio.db data/patrimonio.db.backup-YYYYMMDD`
- [ ] Dump SQL: `sqlite3 data/patrimonio.db ".dump" > dump_YYYYMMDD.sql`
- [ ] Registrar contagem de registros por tabela
- [ ] Verificar formato das datas (possíveis inconsistências)

### Código
- [ ] Verificar se há branches não commitadas
- [ ] Criar tag no git: `git tag antes-migracao-pg-YYYYMMDD`
- [ ] Verificar se `DATABASE_URL` está hardcoded em algum lugar além de `config.py`

### PostgreSQL de Homologação
- [ ] Instalar PostgreSQL em ambiente de teste
- [ ] Criar banco e usuário
- [ ] Configurar `pg_hba.conf` para acesso
- [ ] Testar conexão: `psql -h localhost -U sispatrimonio -d sispatrimonio_pro`

### Script de Migração
- [ ] Escrever/validar script de migração (pgloader ou Python)
- [ ] Testar migração no ambiente de homologação
- [ ] Validar contagem de registros após migração
- [ ] Validar integridade referencial
- [ ] Validar sequências sincronizadas

### Testes
- [ ] Executar suite de testes contra PostgreSQL de homologação
- [ ] Testar fluxos críticos manualmente (login, CRUD, movimentações)
- [ ] Validar relatórios e exportações

---

## 19. CHECKLIST PÓS-MIGRAÇÃO

### Validação de Dados
- [ ] Contagem de registros por tabela igual ao SQLite
- [ ] IDs preservados (amostra de 10-20 registros por tabela)
- [ ] Dados de ativos: tag, name, purchase_value, status válidos
- [ ] Dados de movimentações: movement_uuid, asset_id, timestamp válidos
- [ ] Nenhuma FK órfã (verificar queries de validação)
- [ ] Sequências atualizadas: `SELECT last_value FROM cada_sequence`
- [ ] Datas válidas em todas as colunas DateTime
- [ ] Valores booleanos consistentes (0/1 ou true/false)

### Funcionalidade
- [ ] Login funciona para todos os usuários
- [ ] CRUD de ativos funciona (criar, ler, atualizar, importar CSV)
- [ ] Movimentações funcionam (alocação, devolução, transferência, baixa)
- [ ] Manutenções funcionam (criar OS, finalizar)
- [ ] CRUD de colaboradores e locais funciona
- [ ] RBAC funciona (permissões aplicadas corretamente)
- [ ] Auditoria registra corretamente
- [ ] Dashboard mostra KPIs corretos
- [ ] Exportações CSV funcionam

### Performance
- [ ] Tempo de resposta aceitável (login < 1s, consultas < 2s)
- [ ] Múltiplos usuários simultâneos testados
- [ ] Importação CSV grande testada (se houver dados grandes)

### Segurança
- [ ] Credenciais do PostgreSQL armazenadas em variável de ambiente (não em código)
- [ ] Acesso restrito à porta 5432
- [ ] AUTH_ADMIN_PASSWORD não versionada no git

### Monitoramento
- [ ] Habilitar logs do PostgreSQL se necessário
- [ ] Monitorar taxa de erros nos primeiros dias
- [ ] Manter backup do SQLite por 30 dias

---

## 20. RECOMENDAÇÃO FINAL

### 1. PostgreSQL é realmente recomendado para este sistema?

**SIM.** O sistema transforma-se bem para PostgreSQL porque:
- Uso puramente ORM (SQLAlchemy) — pouca dependência de SQL específico
- Schemas bem estruturados com FKs, índices e constraints
- Necessidade de concorrência melhor (múltiplos usuários simultaneous)
- Volume moderado de dados (1.4 MB, 2.277 movimentações)
- Alembic é naturalmente compatível com o SQLAlchemy já usado

### 2. MariaDB seria melhor ou pior?

**Pior para este caso.** MariaDB/MySQL tem algumas diferenças que adicionam complexidade:
- Tipos ENUM são diferentes (MySQL tem ENUM nativo, MariaDB também)
- Sintaxe de algumas funções pode diferir
- Fluxo de migração similar, mas PostgreSQL tem melhor aderência ao padrão SQL e melhor integração com SQLAlchemy/Alembic
- PostgreSQL é mais robusto para aplicações que podem crescer

### 3. Vale a pena permanecer no SQLite?

**Depende do cenário de uso:**
- **Vale a pena se:** sistema single-user, protótipo, menos de 100 usuários simultaneous, pouco escrita concorrente
- **Não vale a pena se:** múltiplos usuários simultaneous (escrita concorrente), sistema de produção com vários acessos, necessidade de backup mais robusto, escalabilidade

**Análise do sistema atual:** O sistema tem 2.277 movimentações, múltiplos colaboradores, RBAC, auditoria — características de um sistema de produção que pode se beneficiar do PostgreSQL.

### 4. A migração é de baixo, médio ou alto risco?

**Risco MÉDIO.**

Justificativa:
- Baixo fator de risco: uso quase totalmente ORM, sem SQL bruto de negócio, schema bem definido
- Médio fator de risco: migração de dados (2.277 movimentações, FKs, IDs), PRAGMA no código de migrations, ENUMs, possíveis inconsistências de data
- Alto fator de risco: se houver dados corrompidos ou inconsistências não detectadas

### 5. Qual é a estratégia mais segura?

**Estratégia recomendada (ordem de prioridade):**

1. **Usar pgloader** para migração de dados (ferramenta madura, testada)
2. **Manter ENUMs como VARCHAR** no PostgreSQL (evita conversão de tipos)
3. **Adotar Alembic** para gestão de schema futuro
4. **Testar em homologação** antes de produção
5. **Manter SQLite intacto** como fallback por 30 dias
6. **Validar dados** com queries de integridade antes de trocar a aplicação

### 6. É possível manter o SQLite como fallback?

**SIM, e é recomendado.**

Estratégia de fallback:
- Manter `data/patrimonio.db` intacto após migração
- Ter `DATABASE_URL` configurável via variável de ambiente
- Em caso de problema, reverter para SQLite em minutos
- Após 30 dias de operação estável no PostgreSQL, SQLite pode ser arquivado

### 7. Qual seria o tempo/esforço aproximado?

| Fase | Estimativa |
|------|------------|
| Análise (já feita) | — |
| Preparação do PostgreSQL (instalação, configuração) | 2-4 horas |
| Escrita/validação do script de migração | 4-8 horas |
| Testes de migração em homologação | 1-2 dias |
| Testes funcionais completos | 1 dia |
| Migração de produção + validação | 2-4 horas |
| **Total estimado** | **3-5 dias úteis** |

### 8. Quais arquivos precisam ser alterados?

Ver **Seção 15 — Arquivos que deverão ser alterados**.

Resumo:
- `app/config.py` — DATABASE_URL
- `app/database.py` — connect_args e `_ensure_schema_migrations`
- `tests/conftest.py` — URL de teste (opcional, pode manter SQLite)
- `requirements.txt` — adicionar psycopg2-binary
- Documentos: atualizar docs com informações do PostgreSQL

### 9. Quais testes são obrigatórios antes da migração definitiva?

**Testes obrigatórios:**

1. **Integridade dos dados migrados:**
   - Contagem de registros por tabela (SQLite vs PostgreSQL — deve ser igual)
   - IDs preservados (amostra representativa)
   - FKs válidas (não existem registros órfãos)
   - Sequências atualizadas

2. **Funcionalidade básica:**
   - Login de todos os usuários
   - CRUD completo de ativos (com tag e serial únicos)
   - Movimentações completas (alocação, devolução, transferência, baixa)
   - Manutenções (criar e finalizar)
   - Importação CSV
   - RBAC (verificar permissões aplicadas)
   - Auditoria (registra eventos)
   - Dashboard e relatórios

3. **Regressão:**
   - Executar suite de testes existente (adaptada para PostgreSQL)
   - Ou executar os testes manuais listados na Seção 13

4. **Performance:**
   - Resposta aceitável para operações comuns
   - Múltiplos usuários simultâneos (se possível testar)

---

## ANEXO: ESTRUTURA DE DIRETÓRIOS DO PROJETO

```
.
├── app/
│   ├── main.py              # FastAPI app, lifespan
│   ├── config.py            # Configurações (DATABASE_URL, AUTH_*, AD_*)
│   ├── database.py          # SQLAlchemy engine, Session, Base, get_db, init_db
│   ├── cli.py               # CLI tools
│   ├── api/                 # API REST
│   │   ├── v1_router.py
│   │   ├── deps.py
│   │   ├── auth_api.py
│   │   ├── assets_api.py
│   │   ├── movements_api.py
│   │   ├── custodians_api.py
│   │   ├── locations_api.py
│   │   └── reports_api.py
│   ├── models/              # 16 modelos SQLAlchemy + enums
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── asset.py
│   │   ├── movement.py
│   │   ├── location.py
│   │   ├── custodian.py
│   │   ├── role.py
│   │   ├── permission.py
│   │   ├── user_role.py
│   │   ├── role_permission.py
│   │   ├── session.py
│   │   ├── audit_log.py
│   │   ├── maintenance.py
│   │   ├── ad_group_role.py
│   │   ├── ad_settings.py
│   │   └── enums.py
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # 17 módulos de serviço
│   └── web/                 # Jinja2 templates, rotas web
├── data/
│   └── patrimonio.db        # SQLite (1.47 MB, 12 tabelas)
├── tests/                   # 9 arquivos, 110 testes
├── docs/                    # Documentação
├── seed_demo.py             # Demo data (drop_all + create_all)
├── run.py                   # Ponto de entrada
└── requirements.txt         # Dependências mínimas
```

---

## ANEXO 2: ESTRATÉGIA PARA MIGRAÇÃO DE ENUMS

Como os enums são armazenados como VARCHAR no SQLite, há duas abordagens para PostgreSQL:

### Abordagem A — Manter como VARCHAR (recomendada)

No modelo SQLAlchemy, usar `String` no lugar de `Enum` para as colunas que atualmente usam Enum. Os valores são validados em Python via `enum` mesmo, mas no banco são VARCHAR.

```python
# Exemplo de alteração no modelo (futuro):
class Asset(Base):
    status = Column(String(14), nullable=False, default=AssetStatus.AVAILABLE.value)
    # Em vez de:
    # status = Column(Enum(AssetStatus), nullable=False, default=AssetStatus.AVAILABLE)
```

Vantagem: migração de dados direta, sem conversão de tipos.

### Abordagem B — Usar ENUM nativo do PostgreSQL

Criar tipos ENUM no PostgreSQL e usar `Enum` no SQLAlchemy. Requer:
- Criar os tipos ENUM antes de inserir dados
- Converter os dados VARCHAR existentes para o tipo ENUM

```sql
-- No PostgreSQL, antes da migração:
CREATE TYPE asset_status AS ENUM ('DISPONIVEL', 'EM_USO', 'EM_MANUTENCAO', 'EM_TRANSITO', 'BAIXADO');
CREATE TYPE asset_condition AS ENUM ('NOVO', 'EXCELENTE', 'BOM', 'REGULAR', 'RUIM', 'INSERVIVEL');
-- etc.
```

Vantagem: validação no banco.
Desvantagem: complexidade na migração.

**Recomendação:** Usar Abordagem A para a migração inicial. Avaliar Abordagem B como melhoria futura, se houver benefício claro.

---

## CONCLUSÃO

O **SisPatrimônio Pro** está bem preparado para migração para PostgreSQL. O principal trabalho está em:

1. **Remover dependências SQLite específicas** (`check_same_thread`, `PRAGMA`)
2. **Escolher e configurar o método de migração de dados** (pgloader recomendado)
3. **Decidir sobre ENUMs** (manter como VARCHAR recomendado)
4. **Testar exaustivamente em homologação**
5. **Executar com rollback seguro**

O plano acima fornece todos os passos necessários para execução segura da migração, sem alterar o sistema atual.
