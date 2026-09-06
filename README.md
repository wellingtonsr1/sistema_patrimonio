# SisPatrimônio Pro 📦🏢

**SisPatrimônio Pro** é um sistema completo e moderno de **Gestão Patrimonial (Controle de Ativo Fixo e Equipamentos)** desenvolvido em **Python** com **FastAPI**, **SQLAlchemy** e **Bootstrap 5**, focado no **rastreamento auditável e gravação detalhada do fluxo de movimentação de cada equipamento**.

**Status:** Em desenvolvimento ativo · Suite com **106 testes automatizados** (`pytest`, todos passando).

---

## ✨ Principais Funcionalidades

### 1. 🔄 Motor de Fluxo de Movimentação & Auditoria (Audit Trail)
- **Gravação Imutável de Histórico**: Cada alteração de localização, colaborador ou estado gera um snapshot histórico indelével com data/hora, origem → destino, motivo e operador.
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
- **Cálculo de Depreciação Linear Contábil** automática (20% ao ano sobre o valor de aquisição).
- Busca e filtros multifacetados por status, categoria, setor e custodiante.
- **Importação em massa via CSV** (equipamentos e colaboradores) com pré-visualização e confirmação.

### 3. 👥 Gestão de Colaboradores & Departamentos
- Cadastro de colaboradores com visão instantânea de todos os equipamentos sob a custódia de cada um.
- Cadastro de unidades físicas, prédios, andares, salas e departamentos.

### 4. 🔧 Gestão de Manutenções
- Abertura de Ordens de Serviço (Preventiva, Corretiva, Upgrade).
- Controle de custos acumulados de reparo e prestadores de serviço.
- Envio e retorno de manutenção com atualização automática do fluxo do bem.

### 5. 📊 Dashboard, Relatórios & Exportações
- Dashboard com KPIs operacionais, gráficos de pizza e barras (Chart.js).
- Exportação de inventário, movimentações e colaboradores em **CSV** (UTF-8 com BOM, abre direto no Excel).
- Documentação interativa da **API REST via Swagger UI** (`/docs`).

### 6. 🧭 Central de Ajuda Integrada
- Manual embutido (`/ajuda`) com pesquisa em texto completo, artigos por módulo, FAQ e tooltips contextuais nos formulários.

### 7. 🔐 Autenticação Local + Active Directory / Samba AD (LDAP)
- Login híbrido: contas locais (PBKDF2) e contas do diretório (`ldap3`), com provisionamento automático no 1º login.
- RBAC completo (perfis e permissões) permanece 100% interno — o AD nunca define permissões.

---

## 🛠️ Tecnologias

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.10+ |
| Framework web | FastAPI |
| Servidor ASGI | Uvicorn |
| ORM / Banco | SQLAlchemy 2 + SQLite (arquivo local, sem serviço externo) |
| Validação | Pydantic v2 |
| Templates | Jinja2 + Bootstrap 5 + Bootstrap Icons |
| Frontend | Chart.js, QRCode.js, tema claro/escuro |
| Diretório | LDAP/LDAPS padrão via `ldap3` (Microsoft AD ou Samba AD DC) |
| Testes | pytest (+ TestClient do FastAPI) |

---

## 🏗️ Arquitetura

O sistema é organizado em **camadas desacopladas**:

```text
Interface Web (Jinja2)          API REST (/api/v1)
        └────────────┬──────────────┘
                     ↓
        Autenticação (provedores)
        local (PBKDF2 no banco) · AD (LDAP bind)
                     ↓
                Services (regras de negócio)
        assets · movements · custodians · locations ·
        maintenance · reports · help · import · RBAC · auditoria
                     ↓
        Models (SQLAlchemy) → Banco de dados
```

- **Autenticação** (quem você é): via `app/services/auth_provider.py`, que resolve entre o provedor **local** e o provedor **Active Directory**. Contas locais existentes sempre autenticam localmente; contas `auth_provider='ad'` autenticam sempre no diretório.
- **Autorização** (o que você pode fazer): **RBAC interno** — o AD apenas indica um *perfil* existente do sistema via mapeamento Grupo AD → Perfil. Permissões nunca vêm do AD.
- **Sessões**: token aleatório (`secrets.token_urlsafe`) gravado em cookie **HttpOnly + SameSite=Lax** (Secure opcional); o banco armazena apenas o **hash SHA-256** do token. Expiração no servidor (padrão 8h) e revogação no logout.
- **Auditoria**: trilha somente-leitura (`audit_logs`) com eventos de autenticação, alterações, movimentações e acessos negados.

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
> ⚠️ O seed **recria as tabelas** (`drop_all` + `create_all`): use apenas em banco dedicado a testes/demo.

### 3. Iniciar o servidor
```bash
python run.py
```

Acesse no seu navegador:
- **Interface Web**: [http://localhost:8000](http://localhost:8000)
- **API REST (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health check**: [http://localhost:8000/health](http://localhost:8000/health)

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
| `AUTH_PROVIDER` | `local` | Provedor ativo (`local` ou `ad`) |
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

---

## 🏢 Integração Active Directory / Samba AD

O sistema autentica via **Active Directory** (Microsoft AD ou **Samba AD DC**)
usando apenas LDAP/LDAPS padrão (biblioteca `ldap3`), **sem substituir** a
autenticação local nem o RBAC existente. Integração **implementada e testada
contra AD real** (bind, busca por `sAMAccountName`, validação de senha por bind
do usuário, leitura de grupos e provisionamento).

### Fluxo de autenticação (implementação real)

```text
Usuário (login com sAMAccountName + senha)
   ↓
SisPatrimônio (resolve_authentication)
   ↓
Conta local existente (auth_provider='local')? → autenticação local (PBKDF2)
   ↓ (não)
AD habilitado?
   ↓
Bind LDAP com a CONTA DE SERVIÇO (AD_BIND_USER / AD_BIND_PASSWORD)
   ↓
Busca do usuário por sAMAccountName (Base DN / DN de busca)
   ↓
Bind LDAP com o DN ENCONTRADO + senha digitada  ← valida a senha
   ↓
Rebind de serviço → leitura de atributos e memberOf (grupos)
   ↓
Conta desabilitada no AD (userAccountControl)? → ACESSO NEGADO
   ↓
Provisionamento/atualização do usuário local (guid, DN, e-mail, nome)
   ↓
Mapeamento Grupo AD → Perfil (prioridade determinística)
   ↓
Perfil atribuído (assigned_by='ad'; perfis manuais preservados)
   ↓
Sessão criada → acesso ao sistema (RBAC interno)
```

> **Dois binds distintos**: o bind da conta de serviço só **pesquisa** o
> usuário; a senha é validada sempre por um **segundo bind** usando o DN
> encontrado + a senha digitada no login.

### Comportamentos garantidos pelo código

- **Login híbrido**: contas locais (ex: `admin`) continuam autenticando como antes; contas `auth_provider='ad'` autenticam sempre no diretório (nunca por senha local).
- **Provisionamento no 1º login**: cria o usuário do sistema e o vincula ao **colaborador existente** por e-mail/matrícula (nunca duplica cadastro). Usuários do AD não sobrescrevem dados patrimoniais do colaborador (matrícula, CPF, cargo, setor).
- **Sem perfil mapeado**: o usuário é autenticado no AD, porém **não recebe acesso** — mensagem específica ("autenticado, mas não possui um perfil autorizado"), distinta de credencial inválida.
- **Conta desabilitada no AD**: login negado (`userAccountControl`, bit ACCOUNTDISABLE), com histórico/colaborador preservados.
- **Erros diferenciados**: AD indisponível (503), credencial inválida (401), conta desabilitada (401) e falta de perfil (401) têm mensagens e tratamentos próprios.
- **Segurança**: senha do usuário AD nunca é armazenada/logada; a senha da conta de serviço existe somente em variáveis de ambiente (`AD_BIND_PASSWORD`); timeout obrigatório em todas as operações; nenhuma credencial vai para logs ou auditoria.
- **Auditoria**: eventos próprios na trilha existente (`LOGIN_AD`, `LOGIN_AD_FALHA`, `CONTA_AD_DESABILITADA`, `USUARIO_AD_PROVISIONADO`, `USUARIO_AD_VINCULADO_COLABORADOR`, `GRUPOS_AD_IDENTIFICADOS`, `GRUPO_AD_SEM_MAPEAMENTO`, `CONFLITO_GRUPOS_AD`, `PERFIL_SINCRONIZADO_AD`, `FALHA_COMUNICACAO_AD`, `ALTERACAO_CONFIG_AD`, `TESTE_CONEXAO_AD`) — sem credenciais.

### Como ativar

1. Tela **Administração → Integração AD**: marque *Habilitar*, informe **Servidor** e **Base DN**, teste a conexão e salve.
2. Cadastre os mapeamentos **Grupo AD → Perfil** na mesma tela (o nome do grupo é o `CN`/`sAMAccountName` do grupo, ex.: `GRP-SISPAT-TECNICOS-TI` ou `Administrators`).
3. Defina as variáveis de ambiente da conta de serviço no processo do servidor:

```env
# Exemplos — NÃO use credenciais reais em repositórios
AD_SERVER=192.168.0.10
AD_BIND_USER=usuario_de_servico@empresa.local
AD_BIND_PASSWORD=senha_da_conta_de_servico
```

Variáveis de ambiente suportadas (fallback/valor inicial dos campos da tela):

| Variável | Função |
|---|---|
| `AD_SERVER` | Host/IP do controlador de domínio |
| `AD_PORT` | Porta (`389` LDAP · `636` LDAPS) |
| `AD_USE_SSL` | `true` para LDAPS |
| `AD_BASE_DN` | Base DN da busca (ex.: `DC=empresa,DC=local`) |
| `AD_USER_DN` | DN de busca de usuários (escopo; vazio = usa a Base DN) |
| `AD_GROUP_BASE_DN` | Base DN de grupos (reservado) |
| `AD_BIND_USER` | Conta de serviço para consultas |
| `AD_BIND_PASSWORD` | Senha da conta de serviço — **somente ambiente, nunca no banco** |

> **Dica operacional**: se o "DN de busca de usuários" estiver vazio, a busca
> usa a Base DN inteira (funciona independentemente da OU onde os usuários
> estão). Um DN de busca apontando para uma OU que não contém os usuários faz
> o login falhar como "credencial inválida" — verifique o log, que registra a
> base usada quando a busca não encontra o usuário.

### Mapeamento Grupo AD → Perfil

- Armazenado na tabela `ad_group_roles` (grupo único → perfil existente + prioridade).
- **Usuário em vários grupos mapeados**: vence a **menor prioridade numérica** (1 = maior). Opcionalmente, o campo `group_role_priority` da tela (CSV de nomes de grupos, em ordem) sobrepõe a prioridade numérica.
- **Sincronização**: perfis atribuídos via AD são marcados `assigned_by='ad'` e substituídos a cada login conforme os grupos atuais; perfis atribuídos **manualmente** (`assigned_by='local'`) **nunca são removidos** pela sincronização.
- **Sem mapeamento**: autentica no AD, mas não recebe acesso (auditoria `GRUPO_AD_SEM_MAPEAMENTO`).

### LDAPS

O uso de **LDAPS (636) com validação de certificado** é o recomendado em
produção (`Usar LDAPS` + `Validar certificado TLS` na tela). Ambientes sem CA
publicada podem desativar a validação explicitamente (`Validar certificado
TLS` desmarcado) — o sistema nunca silencia TLS sem escolha do administrador.
LDAP simples (389) funciona igualmente, incluindo Samba AD DC.

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
| `GET` | `/api/v1/assets`, `/api/v1/assets/{id}`, `/api/v1/assets/tag/{tag}`, `/api/v1/assets/{id}/timeline`, `/api/v1/assets/{id}/depreciation` | `patrimonio.visualizar` |
| `POST` | `/api/v1/assets`, `/api/v1/assets/import/csv` | `patrimonio.criar` |
| `PUT` | `/api/v1/assets/{id}` | `patrimonio.editar` |
| `GET` | `/api/v1/movements`, `/api/v1/movements/{id}`, `/api/v1/movements/{id}/term` | `movimentacao.visualizar` |
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
`404` recurso não encontrado · `423` conta temporariamente bloqueada ·
`503` Active Directory indisponível.

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
| `/admin/ad` (Integração AD) | superusuário **ou** `usuarios.editar` + `perfis.editar` |
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
A integração AD adiciona os eventos listados na seção de AD — sempre sem
credenciais.

A auditoria é **somente-leitura**: não existe rota de escrita/exclusão e a
consulta exige `auditoria.visualizar`.

### Banco de dados (migração segura)

Tabelas novas: `roles`, `permissions`, `user_roles`, `role_permissions`,
`audit_logs`, `ad_settings`, `ad_group_roles`. Colunas novas em `users`:
`failed_login_attempts`, `locked_until`, `ad_object_guid`, `ad_dn`,
`ad_last_sync`, `auth_provider`. A migração é automática e idempotente
(`init_db` + `_ensure_schema_migrations` com `ALTER TABLE ADD COLUMN`
condicional) — **nenhum dado existente é alterado ou removido**.

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

## 🗄️ Banco de Dados e Backup

- **Tecnologia**: SQLite em arquivo local (`data/patrimonio.db` por padrão; ajustável via `DATABASE_URL`), acessado pelo SQLAlchemy — **nenhum serviço de banco externo é necessário**.
- **Criação**: automática no primeiro start (`init_db`), incluindo a migração leve e idempotente de colunas novas (seção RBAC acima).
- **Backup**: por ser um arquivo único, basta copiar `data/patrimonio.db` com a aplicação parada (ou usar a API de backup do SQLite). O diretório `data/` **não deve ser versionado** com dados reais.

---

## 🧪 Executando os Testes Automatizados

Para rodar a suite de testes unitários e de integração:

```bash
pytest -v
```

A suite (106 testes) cobre: **controle de acesso** (`tests/test_rbac.py`):
autorização por perfil em APIs e páginas, deny by default, menu dinâmico,
bloqueio/desbloqueio de usuário, lockout por tentativas, auditoria,
proteção do último administrador e tentativas de escalação de privilégios;
**autenticação** (`tests/test_auth.py`); **integração AD** (`tests/test_ad.py`,
com a camada LDAP mockada — inclui regressões do retorno `bool` de
`Connection.search()` e do `raw_values` do `objectGUID`); movimentações, bens,
importações e central de ajuda.

---

## 📂 Estrutura do Projeto

```
sistema_patrimonio/
├── app/
│   ├── api/                  # Endpoints REST (FastAPI) + dependências de auth/RBAC
│   │   └── v1_router.py      # Agrega: auth, assets, movements, custodians, locations, reports
│   ├── models/               # Modelos SQLAlchemy: User, Session, Role, Permission,
│   │                         #   AuditLog, Asset, Movement, Custodian, Location,
│   │                         #   Maintenance, ADSettings, ADGroupRole
│   ├── schemas/              # Schemas de validação (Pydantic)
│   ├── services/             # Regras de negócio: auth/sessão/RBAC, auditoria,
│   │                         #   asset/movement/custodian/location/maintenance,
│   │                         #   reports/dashboard/help/import,
│   │                         #   ad_ldap (protocolo LDAP) + ad_service (integração AD)
│   ├── web/                  # Interface Web e Templates Jinja2
│   │   ├── routes.py         # Páginas do sistema (com permissões)
│   │   ├── admin_routes.py   # Administração: usuários, perfis, auditoria, Integração AD
│   │   ├── help_routes.py    # Central de ajuda (/ajuda)
│   │   ├── static/           # CSS e JS customizados
│   │   └── templates/        # HTML (Dashboard, CRUD, admin/*, 403/404)
│   ├── cli.py                # Interface de linha de comando (create-user --role)
│   ├── config.py             # Configurações gerais (app, auth, AD via env)
│   ├── database.py           # Conexão, sessão SQLAlchemy e migração leve
│   └── main.py               # Aplicação principal FastAPI (lifespan, handlers 403/404)
├── data/                     # Banco SQLite (data/patrimonio.db) — não versionar dados reais
├── tests/                    # Suite pytest (auth, rbac, ad, api, assets, movements, imports, help)
├── seed_demo.py              # Carga de dados de teste realistas (recria as tabelas)
├── run.py                    # Script de inicialização do servidor
└── requirements.txt          # Dependências do projeto
```

---

## 🔒 Segurança

Práticas implementadas (verificáveis no código):

- **Senhas locais**: PBKDF2-HMAC-SHA256 com salt por usuário (600.000 iterações), apenas biblioteca padrão.
- **Sessões**: token de 32 bytes (`secrets.token_urlsafe`) em cookie HttpOnly/SameSite=Lax (Secure configurável); banco guarda apenas o hash SHA-256; expiração e revogação no servidor.
- **Lockout**: bloqueio temporário por conta após N falhas, com timing equalizado para usuários inexistentes.
- **RBAC deny by default** validado no backend em todas as rotas; menu/botões são apenas apresentação.
- **AD/LDAP**: senha do usuário nunca persistida/logada; senha da conta de serviço somente em variáveis de ambiente; timeout em todas as operações; LDAPS com validação de certificado recomendado; dois binds distintos (busca vs. autenticação).
- **Auditoria** imutável e somente-leitura, incluindo acessos negados, com dados before/after em JSON — nunca credenciais.
- **Open redirect**: o parâmetro `next` do login aceita apenas caminhos internos.

Recomendações para produção: defina `AUTH_COOKIE_SECURE=true` atrás de HTTPS, use LDAPS com certificado válido, forneça `AUTH_ADMIN_PASSWORD` apenas no primeiro start e mantenha `AD_BIND_PASSWORD` fora de arquivos versionados.

---

## 📄 Licença

Não identificada na implementação atual (nenhum arquivo `LICENSE` no repositório).
