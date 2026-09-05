# SisPatrimônio Pro 📦🏢

**SisPatrimônio Pro** é um sistema completo e moderno de **Gestão Patrimonial (Controle de Ativo Fixo e Equipamentos)** desenvolvido em **Python** com **FastAPI**, **SQLAlchemy** e **Bootstrap 5**, focado no **rastreamento auditável e gravação detalhada do fluxo de movimentação de cada equipamento**.

---

## ✨ Principais Funcionalidades

### 1. 🔄 Motor de Fluxo de Movimentação & Auditoria (Audit Trail)
- **Gravação Imutável de Histórico**: Cada alteração de localização, colaborador ou estado gera um snapshot histórico indelével com data/hora, origem $\to$ destino, motivo e operador.
- **Tipos de Fluxo Suportados**:
  - `ENTRADA_AQUISICAO`: Cadastro inicial e incorporação ao acervo.
  - `ALOCACAO_CAUTELA`: Entrega de equipamento a um colaborador específico.
  - `TRANSFERENCIA_LOCAL`: Mudança de filial, prédio, sala ou departamento.
  - `ENVIO_MANUTENCAO`: Saída para reparo ou assistência técnica externa/interna.
  - `RETORNO_MANUTENCAO`: Reintegração do bem após conserto.
  - `DEVOLUCAO_ESTOQUE`: Recolhimento do bem (demissão ou substituição).
  - `BAIXA_DESCARTE`: Descarte por obsolescência, perda, quebra ou leilão.
  - `ATUALIZACAO_ESTADO`: Vistoria e alteração do estado de conservação.
- **Linha do Tempo Visual (Interactive Timeline)**: Visualização gráfica no estilo GitHub/Jira da vida útil e de todas as transferências de cada bem.
- **Termo de Responsabilidade & Cautela**: Emissão e formatação automática de termo formal com dados da empresa, colaborador, especificações do bem e validação via QR Code, pronto para impressão e assinatura.

### 2. 💻 Gestão de Bens & Equipamentos
- Tombamento / Tag única com geração dinâmica de etiquetas QR Code.
- Ficha técnica completa (marca, modelo, número de série, especificações).
- Gestão fiscal e financeira (Nota Fiscal, fornecedor, garantia, data e valor de compra).
- **Cálculo de Depreciação Linear Contábil** automática.
- Busca e filtros multifacetados por status, categoria, setor e custodiante.

### 3. 👥 Gestão de Colaboradores & Departamentos
- Cadastro de colaboradores com visão instantânea de todos os equipamentos sob a custódia de cada um.
- Cadastro de unidades físicas, prédios, andares, salas e departamentos.

### 4. 🔧 Gestão de Manutenções
- Abertura de Ordens de Serviço (Preventiva, Corretiva, Upgrade).
- Controle de custos acumulados de reparo e prestadores de serviço.
- Envio e retorno de manutenção com atualização automática do fluxo.

### 5. 📊 Dashboard, Relatórios & Exportações
- Dashboard com KPIs operacionais, gráficos de pizza e barras (Chart.js).
- Exportação de inventário patrimonial completo em **CSV/Excel**.
- Exportação da trilha de movimentações em **CSV/Excel**.
- Documentação interativa da **API REST via Swagger UI** (`/docs`).

---

## 🚀 Como Executar o Sistema

### Pré-requisitos
- Python 3.10 ou superior instalado.

### 1. Instalar as dependências
```bash
pip install -r requirements.txt
```

### 2. (Opcional) Popular o banco de dados com dados de teste
Para iniciar o sistema já com equipamentos, colaboradores e histórico de movimentações pré-carregados:
```bash
python seed_demo.py
```

### 3. Iniciar o servidor
```bash
python run.py
```

Acesse no seu navegador:
- **Interface Web**: [http://localhost:8000](http://localhost:8000)
- **API REST (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🔐 Autenticação

O sistema exige **login** para a interface web, para a API REST e para as exportações de dados.

### Primeiro usuário (administrador)

**Opção A — variáveis de ambiente** (criado automaticamente no primeiro start):

```bash
AUTH_ADMIN_USERNAME=admin AUTH_ADMIN_PASSWORD='SenhaForte@123' python run.py
```

**Opção B — linha de comando:**

```bash
python -m app.cli create-user --username admin --password 'SenhaForte@123' --name "Administrador" --admin
```

> ⚠️ A senha deve ter **no mínimo 8 caracteres**. Nunca é armazenada em texto puro:
> o sistema grava apenas o hash **PBKDF2-HMAC-SHA256** (salt aleatório por usuário,
> 600.000 iterações por padrão) usando apenas a biblioteca padrão do Python.

### Login e logout

- Acesse [http://localhost:8000/login](http://localhost:8000/login) e entre com usuário/senha.
- O menu do usuário (canto superior direito) exibe o nome logado e o botão **Sair** (`POST /logout`).
- A sessão fica em **cookie HttpOnly + SameSite=Lax**, com token aleatório seguro;
  o banco armazena **apenas o hash** do token. A sessão expira no servidor
  (padrão 8h) e é **revogada no logout** — mesmo que o cookie ainda exista,
  ele deixa de valer.

### O que exige autenticação

| Área | Comportamento sem login |
|---|---|
| Páginas web (`/`, `/assets`, `/custodians`, `/reports/...`, etc.) | Redirecionamento para `/login` (o caminho original é preservado via `?next=`) |
| API REST `/api/v1/*` (mutações, consultas e relatórios) | `401 Unauthorized` |
| Exportações CSV (`/api/v1/reports/*/csv`) | `401 Unauthorized` |
| `/health` | Público (monitoramento) |
| `/docs` (Swagger) | Público; as chamadas "Try it out" exigem sessão |
| `/api/v1/auth/login` e `/api/v1/auth/logout` | Públicos (são o ponto de autenticação) |
| `/api/v1/auth/me` | `401` sem sessão |

**Decisão:** toda a API `/api/v1` (inclusive consultas GET) foi protegida porque os
retornos contêm dados sensíveis (CPF, números de série, valores, nomes). Não há
consumidor público da API — ela é o backend administrativo do sistema.

### API via script (curl)

```bash
# 1. Login: guarda o cookie de sessão
curl -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=admin&password=SenhaForte@123"

# 2. Usar a API com a sessão
curl -b cookies.txt http://localhost:8000/api/v1/assets
curl -b cookies.txt -o colaboradores.csv http://localhost:8000/api/v1/reports/custodians/csv

# 3. Logout (revoga a sessão no servidor)
curl -b cookies.txt -c cookies.txt -X POST http://localhost:8000/api/v1/auth/logout
```

### Variáveis de ambiente de autenticação

| Variável | Padrão | Descrição |
|---|---|---|
| `AUTH_PROVIDER` | `local` | Provedor ativo (`local`; `ad`/`ldap` reservado) |
| `AUTH_ADMIN_USERNAME` | `admin` | Usuário admin inicial (criado se `AUTH_ADMIN_PASSWORD` definida) |
| `AUTH_ADMIN_PASSWORD` | *(vazio)* | Senha do admin inicial (mín. 8 caracteres) |
| `AUTH_ADMIN_NAME` | `Administrador` | Nome exibido do admin inicial |
| `AUTH_SESSION_TTL` | `28800` (8h) | Duração da sessão em segundos |
| `AUTH_COOKIE_NAME` | `session` | Nome do cookie de sessão |
| `AUTH_COOKIE_SECURE` | `false` | `true` envia o cookie apenas via HTTPS |
| `AUTH_PBKDF2_ITERATIONS` | `600000` | Iterações do PBKDF2 para hash de senha |
| `AUTH_MAX_FAILED_ATTEMPTS` | `5` | Tentativas de login falhas antes do bloqueio temporário |
| `AUTH_LOCKOUT_SECONDS` | `900` | Duração (s) do bloqueio por excesso de tentativas |

### Proteção contra força bruta (lockout)

Após **5 tentativas de login com senha errada** (configurável), a conta fica
bloqueada por **15 minutos** no servidor (`423 Locked` na API; mensagem na web).
O bloqueio é por conta, registrado na trilha de auditoria (`LOGIN_BLOQUEADO`),
e não revela a existência da conta (o tempo de resposta é equalizado para
usuários inexistentes).

### Preparação para Active Directory / LDAP

A arquitetura está **preparada** para a integração futura com AD/LDAP/LDAPS,
mas **ainda não implementada**:

- `app/services/auth_provider.py` define o contrato `AuthProvider` com o provedor
  `LocalAuthProvider` ativo; um `ADAuthProvider` foi esboçado e recusa login até
  ser implementado (sem falha silenciosa).
- `app/config.py` já expõe `AD_SERVER`, `AD_PORT`, `AD_USE_SSL`, `AD_BASE_DN`,
  `AD_USER_DN` e `AD_GROUP_BASE_DN` (vazios/desativados por padrão).
- A sessão é desacoplada da autenticação: o provedor futuro só precisa devolver
  o usuário (`User`) autenticado; sessão, cookies e proteção de rotas não mudam.

Para ativar AD no futuro: implementar o `ADAuthProvider`, apontar
`AUTH_PROVIDER=ad` e definir as variáveis `AD_*`.

---

## 🔐 Controle de Acesso e Permissões (RBAC)

O sistema implementa **RBAC (Role-Based Access Control)** com o princípio
**deny by default**: um usuário só executa uma operação se possuir
explicitamente a permissão necessária. Nenhuma permissão é concedida por
padrão — usuários novos começam **sem perfil** até um administrador atribuir.

```text
Usuário ──> Perfis (roles) ──> Permissões (modulo.acao)
   N:N                        N:N
```

### Superusuário (`is_admin`)

O flag legado `users.is_admin` é tratado como **superusuário**: ignora todas as
verificações de permissão (bypass total). Ele preserva o comportamento do
usuário administrador inicial. Na prática, recomendamos usar o **perfil
Administrador** para novos administradores (o flag permanece imutável pela
interface — só pode ser concedido via CLI/env).

### Perfis padrão (seed automático e idempotente)

| Perfil | Acesso |
|---|---|
| **Administrador** | Total: usuários, perfis, permissões, auditoria e todos os módulos |
| **Gestor de TI** | Visualiza e cadastra/edita patrimônio, movimenta, registra manutenção, gera relatórios. Sem permissões de sistema |
| **Técnico de TI** | Consulta equipamentos, registra manutenção/diagnóstico/peças, consulta histórico. Não exclui nem administra |
| **Patrimônio** | Cadastra, edita e movimenta bens, inventário, termos e relatórios patrimoniais |
| **Almoxarifado** | Estoque: entradas/saídas e consulta de equipamentos |
| **Auditor** | Somente leitura (patrimônio, movimentações, histórico, auditoria, relatórios) |
| **Consulta** | Somente leitura dos módulos autorizados (acesso mínimo) |

Perfis padrão (`is_system=True`) **não podem ser excluídos**; podem ser
editados (nome/descrição/permissões) pela interface.

### Catálogo de permissões

Todas as permissões seguem o padrão `modulo.acao`:

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

### Endpoints protegidos (API)

| Método | Endpoint | Permissão |
|---|---|---|
| `GET` | `/api/v1/assets`, `/api/v1/assets/{id}`, `/tag/{tag}`, `/timeline`, `/depreciation` | `patrimonio.visualizar` |
| `POST` | `/api/v1/assets`, `/api/v1/assets/import/csv` | `patrimonio.criar` |
| `PUT` | `/api/v1/assets/{id}` | `patrimonio.editar` |
| `GET` | `/api/v1/movements`, `/api/v1/movements/{id}`, `/term` | `movimentacao.visualizar` |
| `POST` | `/api/v1/movements` | `movimentacao.criar` |
| `GET` | `/api/v1/custodians*` | `colaboradores.visualizar` |
| `POST` | `/api/v1/custodians`, `/import/csv` | `colaboradores.criar` |
| `PUT` | `/api/v1/custodians/{id}` | `colaboradores.editar` |
| `GET` | `/api/v1/locations*` | `locais.visualizar` |
| `POST` | `/api/v1/locations` | `locais.criar` |
| `PUT` | `/api/v1/locations/{id}` | `locais.editar` |
| `GET` | `/api/v1/reports/dashboard-stats` | `relatorios.visualizar` |
| `GET` | `/api/v1/reports/*/csv` | `relatorios.exportar` |
| `GET` | `/api/v1/auth/me`, login/logout | Autenticado (público) |

**Status HTTP:** `401` não autenticado · `403` autenticado sem permissão ·
`404` recurso não encontrado · `423` conta temporariamente bloqueada.

### Páginas web protegidas

Toda página exige autenticação + a permissão do módulo (ex: `/assets` →
`patrimonio.visualizar`, `/assets/new` → `patrimonio.criar`, `/admin/users` →
`usuarios.visualizar`). O menu lateral e os botões são renderizados conforme
as permissões do usuário (`can('patrimonio.criar')` nos templates), mas a
**segurança nunca depende da interface** — o backend valida em todas as rotas.

### Administração

| Rota | Permissão |
|---|---|
| `/admin/users` (listar/pesquisar) | `usuarios.visualizar` |
| `/admin/users/new` | `usuarios.criar` |
| `/admin/users/{id}/edit` (dados + perfis) | `usuarios.editar` |
| `/admin/users/{id}/toggle-active` (bloquear/desbloquear) | `usuarios.bloquear` |
| `/admin/users/{id}/reset-password` | `usuarios.editar` |
| `/admin/roles*` | `perfis.*` |
| `/admin/audit` | `auditoria.visualizar` |
| `/profile/password` (troca de senha própria) | autenticado |

**Proteções:** o usuário não pode bloquear a si mesmo; o **último
administrador ativo** não pode ser removido/desativado; a troca de senha
própria exige a senha atual e invalida as sessões existentes; o reset
administrativo também invalida sessões.

### Auditoria (`audit_logs`)

Registra: login, falha de login, login bloqueado, logout, criação, alteração,
bloqueio, desbloqueio, reset/troca de senha, alteração de perfil e
permissões, movimentação patrimonial, importação CSV e **acessos negados
(403)**. Cada registro contém data/hora, usuário (snapshot), ação, módulo,
recurso, ID, IP, resultado e dados anteriores/posteriores (JSON).

A auditoria é **somente-leitura**: não existe rota de escrita/exclusão e a
consulta exige `auditoria.visualizar`.

### Banco de dados (migração segura)

Tabelas novas: `roles`, `permissions`, `user_roles`, `role_permissions`,
`audit_logs`. Colunas novas em `users`: `failed_login_attempts`,
`locked_until`. A migração é automática e idempotente (`init_db` +
`_ensure_schema_migrations` com `ALTER TABLE ADD COLUMN` condicional) —
**nenhum dado existente é alterado ou removido**.

### Como criar uma nova permissão

1. Adicione ao catálogo em `app/services/permission_service.py`
   (`PERMISSION_CATALOG`), no padrão `modulo.acao`.
2. Associe-a aos perfis desejados na interface `Perfis & Permissões` (ou no
   seed `DEFAULT_ROLES` para perfis padrão).
3. O catálogo é sincronizado automaticamente no startup (`ensure_default_roles`).

### Como criar um novo perfil

Use a tela **Administração → Perfis & Permissões → Novo Perfil** (marque as
permissões desejadas). Por código: `permission_service.create_role(...)` +
`update_role(..., permission_names=[...])`.

### Como proteger uma nova rota/endpoint

**API:**
```python
from app.api.deps import require_permission

@router.post("/algo", dependencies=[Depends(require_permission("modulo.acao"))])
def criar_algo(request: Request, db: Session = Depends(get_db)):
    ...
```

**Web:**
```python
@web_router.get("/algo", dependencies=[Depends(require_permission("modulo.acao"))])
def ver_algo(request: Request, db: Session = Depends(get_db)):
    ...
```

**Frontend:** use `{% if can('modulo.acao') %}` no template para exibir/ocultar
botões e itens de menu (apenas apresentação — a validação é no backend).

### Escopo por unidade/setor (evolução futura)

A arquitetura atual não possui conceito de unidade/setor no usuário, então o
controle por escopo (`escopo_global`, `escopo_unidade`, `escopo_setor`,
`escopo_proprio`) foi **avaliado e adiado**. Caminho sugerido: adicionar
`users.department`/`users.unit`, tabelas `user_scopes`/`role_scopes`, e filtrar
os services de patrimônio (ex: `AssetService.get_all`) pelo escopo do usuário
logado, mantendo os testes de RBAC como base.

---

## 💻 Interface de Linha de Comando (CLI)

O SisPatrimônio Pro também inclui uma ferramenta de terminal (`app/cli.py`):

```bash
# Ver resumo e KPIs
python -m app.cli stats

# Listar equipamentos
python -m app.cli list

# Buscar equipamentos
python -m app.cli list --search "MacBook"

# Ver detalhes e linha do tempo de um equipamento
python -m app.cli show PAT-00101

# Registrar uma movimentação pelo terminal
python -m app.cli move PAT-00101 --type ALOCACAO_CAUTELA --custodian-id 1 --reason "Alocação pelo terminal"

# Criar um usuário (login do sistema)
python -m app.cli create-user --username admin --password 'SenhaForte@123' --name "Administrador" --admin

# Criar um usuário com perfil específico (menor privilégio)
python -m app.cli create-user --username maria --password 'SenhaForte@123' --name "Maria" --role "Técnico de TI"
python -m app.cli create-user --username joao --password 'SenhaForte@123' --name "João" --role "Consulta" --role "Auditor"
```

> `create-user` solicita a senha interativamente se `--password` for omitido.
> `--role` pode ser repetido para múltiplos perfis. Sem `--role` nem `--admin`,
> o usuário é criado sem permissões (deny by default) até um administrador
> atribuir perfis pela interface.

### CLI: atribuição de perfis

O catálogo de permissões e os perfis padrão são garantidos automaticamente a
cada execução do CLI (`ensure_default_roles`).

---

## ❓ Central de Ajuda e Manual

O sistema possui uma **central de ajuda integrada** (`/ajuda`), acessível pelo
botão ❓ no cabeçalho ou pelo item "Ajuda e Manual" no menu:

- **Pesquisa** no manual (artigos e FAQ por texto completo).
- **Artigos** por módulo (primeiros passos, patrimônio, movimentação, manutenção,
  colaboradores/locais, relatórios, administração) com passos a passo.
- **FAQ** (perguntas frequentes) em acordeão.
- **Ajuda contextual**: tooltips em campos de formulários e botões
  "Como faço isso?" em telas-chave.

O conteúdo fica centralizado em `app/services/help_service.py` (listas
`ARTICLES`, `FAQ` e `CATEGORIES`) — para adicionar um artigo basta criar um
item na lista. Artigos de administração (`audience="admin"`) só são exibidos
para usuários com permissão administrativa.

---

## 🧪 Executando os Testes Automatizados

Para rodar a suite de testes unitários e de integração:

```bash
pytest -v
```

A suite inclui testes de **controle de acesso** (`tests/test_rbac.py`):
autorização por perfil em APIs e páginas, deny by default, menu dinâmico,
bloqueio/desbloqueio de usuário, lockout por tentativas, auditoria,
proteção do último administrador e tentativas de escalação de privilégios.

---

## 📂 Estrutura do Projeto

```
sistema_patrimonio/
├── app/
│   ├── api/                  # Endpoints REST (FastAPI) + dependências de auth/RBAC
│   ├── models/               # Modelos SQLAlchemy: User, Session, Role, Permission, AuditLog...
│   ├── schemas/              # Schemas de validação (Pydantic)
│   ├── services/             # Regras de negócio + auth/sessão + RBAC (permission_service) + auditoria
│   ├── web/                  # Interface Web e Templates Jinja2
│   │   ├── routes.py         # Páginas do sistema (com permissões)
│   │   ├── admin_routes.py   # Administração: usuários, perfis, auditoria, troca de senha
│   │   ├── static/           # CSS e JS customizados
│   │   └── templates/        # HTML (Dashboard, CRUD, admin/*, 403/404)
│   ├── cli.py                # Interface de linha de comando (create-user --role)
│   ├── config.py             # Configurações gerais (incl. lockout AUTH_MAX_FAILED_ATTEMPTS)
│   ├── database.py           # Conexão, sessão SQLAlchemy e migração leve (_ensure_schema_migrations)
│   └── main.py               # Aplicação principal FastAPI (handlers 403/404, seed RBAC)
├── tests/                    # Suite com pytest (incl. test_rbac.py)
├── seed_demo.py              # Carga de dados de teste realistas
├── run.py                    # Script de inicialização do servidor
└── requirements.txt          # Dependências do projeto
```
