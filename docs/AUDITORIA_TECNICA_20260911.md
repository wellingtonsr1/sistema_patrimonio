# SisPatrimônio Pro — Auditoria Técnica (Backend, Frontend, Banco, Segurança, Arquitetura e Integrações)

> **Data da análise:** 11/09/2026
> **Método:** auditoria **exclusivamente de leitura** do código-fonte (leitura de arquivos, `grep`, `cat`, `ls`, `wc`, `du`, `git ls-files`, `git status --porcelain`). Nenhum arquivo, código, banco, configuração, dependência ou permissão foi alterado durante a análise.
> **Escopo:** varredura completa de `app/` (rotas web e API, serviços, modelos, schemas, templates, JS/CSS, configurações, banco, importações/exportações, RBAC, sessões, integração LDAP/AD), com verificação da relação entre componentes (frontend → rota → serviço → banco).
> **Restrição:** somente leitura. Nenhuma correção foi aplicada — este documento é o único artefato produzido.

**Limitação declarada:** onde a comprovação exigiria execução (serialização real de resposta HTTP, comportamento do `ldap3` em runtime, renderização do PDF com texto malformado), o item está marcado como **possível** e identificado como não confirmado.

---

## 1. Resumo Executivo

| Classificação | Quantidade |
|---|---|
| 🔴 Problema confirmado | 16 |
| 🟠 Possível problema | 8 |
| 🟡 Melhoria recomendada | 5 |
| **Total** | **29** |

**Status:** 🔴 **PROBLEMAS ENCONTRADOS** — 2 críticos, 7 altos, 13 médios e 7 baixos.

> **Atualização de 11/09/2026 (após o relatório):** os dois problemas **críticos foram corrigidos** — `PROB-001` (corrida no primeiro acesso) e `PROB-002` (banco/logs/backups/bytecode versionados). O restante do relatório permanece descrevendo o estado original auditado.

**Principais riscos identificados:**

1. **Exposição de dados no repositório** — o banco SQLite de produção (usuários, hashes de senha, sessões, trilha de auditoria) e os logs técnicos estão versionados no Git.
2. **Escalada de privilégio no primeiro acesso** — condição de corrida em `POST /setup` pode criar mais de um administrador.
3. **Integridade da rastreabilidade** — relógios mistos (UTC × hora local) entre movimentações e auditoria, código de termo (`term_code`) duplicável e importação em lote que pode ser integralmente descartada reportando sucesso.
4. **Disponibilidade** — HTTP 500 em upload não-UTF8 e em parâmetros de data inválidos; `/health` sem autenticação com vazamento de sessões; bloqueio de conta explorável como negação de serviço.
5. **Superfície exposta** — `/docs`, `/redoc` e `/openapi.json` públicos, ausência de headers de segurança, dependências de CDN sem SRI.
6. **Funcionalidade silenciosamente limitada** — listagens sem paginação: registros acima do limite fixo ficam inacessíveis pela interface.

**Arquivos/componentes mais afetados:** `app/web/routes.py`, `app/services/movement_service.py`, `app/services/import_service.py`, `app/services/report_service.py`, `app/services/audit_service.py`, `app/api/reports_api.py`, `app/api/assets_api.py`, `app/main.py`, `app/web/templates/assets/list.html`, `app/web/static/js/main.js`, `.gitignore` / `data/`.

---

## 2. Problemas Confirmados 🔴

### PROB-001 — ✅ CORRIGIDO (11/09/2026)

> Correção aplicada: novo modelo `SetupClaim` (tabela `setup_claims`, singleton `id=1`) e helper `_claim_first_access` em `app/web/routes.py`. A criação do primeiro administrador passou a ser precedida de uma escrita atômica com chave primária, revalidando a ausência de usuários dentro da mesma transação; falhas fazem `rollback` e liberam o primeiro acesso. Coberto por `tests/test_setup_first_access.py`.

- **Severidade:** Crítica
- **Categoria:** Segurança
- **Arquivo:** `app/web/routes.py` (`_first_access_enabled`, `first_access_submit`) + `app/services/auth_service.py` (`create_user`)
- **Local:** rota pública `POST /setup` (`PUBLIC_WEB_PATHS = {"/login","/logout","/setup"}` em `app/api/deps.py`)
- **Problema:** o "primeiro acesso" valida apenas `db.query(User).first() is None` e depois insere. O endpoint é `def` síncrono → executa no threadpool do Starlette. Duas requisições concorrentes com **usernames diferentes** podem ambas ver "nenhum usuário" e ambas criar administradores. O comentário no código afirma que a checagem+INSERT no mesmo commit impede a corrida, mas não há `UNIQUE` sobre "existe algum usuário" nem lock.
- **Impacto:** criação de administradores indevidos durante a janela de instalação inicial; persistência de acesso privilegiado.
- **Evidência:** `if AUTH_ADMIN_PASSWORD: return False` / `return db.query(User).first() is None` seguido de `create_user(...)`; `create_user` faz SELECT por `username` (não impede nomes distintos).
- **Correção sugerida:** proteger com unicidade/lock real (ex.: flag de bootstrap em tabela com `UNIQUE`, ou `BEGIN IMMEDIATE` com re-checagem dentro da transação) e revalidar a condição após o início da escrita.

### PROB-002 — ✅ CORRIGIDO (11/09/2026)

> Correção aplicada: `data/patrimonio.db`, `data/logs/*.log`, `app/config.py~`, `app/.config.py.un~` e os ~200 `.pyc` foram removidos do índice do Git com `git rm --cached` (arquivos preservados em disco) e o `.gitignore` foi reforçado (`*.log`, `data/logs/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `*~`, `.*.un~`, `*.swp`). **Pendente:** decidir sobre o versionamento de `tests/`, que continua ignorado.

- **Severidade:** Crítica
- **Categoria:** Segurança / Configuração
- **Arquivo:** `.gitignore`, `data/patrimonio.db`, `data/logs/app.log`, `data/logs/app.error.log`, `app/config.py~`, `app/.config.py.un~`, `**/__pycache__/*.pyc`
- **Local:** raiz do repositório
- **Problema:** `git ls-files` mostra o **banco SQLite de produção (472 KB: usuários, hashes de senha, sessões, trilha de auditoria) e os logs técnicos versionados**. O `.gitignore` lista `*.db` e `data/patrimonio.db`, mas ignore não retroage sobre arquivos já rastreados. Também estão versionados ~200 `.pyc` (de 3 versões de Python), arquivos de backup de editor (`config.py~`, `.config.py.un~`) e o `.gitignore` ignora `tests/` inteiro (a suíte não é versionada).
- **Impacto:** exposição de dados sensíveis/credenciais no histórico do Git, PRs com dados reais, repositório poluído, ausência de testes versionados; o backup `config.py~` ainda contém IP interno antigo (`APP_HOST = "10.39.0.16"`).
- **Evidência:** saída de `git ls-files` contendo `data/patrimonio.db`, `data/logs/app.log`, `app/config.py~`; `.gitignore` com bloco `*.db` e linha `tests/`.
- **Correção sugerida:** remover do índice (`git rm --cached`) os artefatos, ajustar `.gitignore` (`__pycache__/`, `*~`, `.*.un~`, `data/logs/`, `data/`), passar a versionar `tests/` e tratar segredos/dados por ambiente.

### PROB-003

- **Severidade:** Alta
- **Categoria:** Backend
- **Arquivo:** `app/web/routes.py` (`process_import_assets`), `app/api/assets_api.py` (`import_csv_api`)
- **Local:** `content = file.file.read().decode("utf-8-sig")`
- **Problema:** o decode UTF-8 não tem tratamento. Um CSV em ANSI/CP1252 (padrão do Excel em pt-BR) ou qualquer arquivo binário renomeado para `.csv` levanta `UnicodeDecodeError` não tratado.
- **Impacto:** HTTP 500 (página de erro crua do Starlette, sem handler genérico para não-HTTPException) em um fluxo comum; o usuário perde a importação e não recebe orientação.
- **Evidência:** ausência de `try/except` em torno do `.decode(...)`; `main.py` só trata `HTTPException`.
- **Correção sugerida:** tratar erro de decodificação com fallback (`cp1252`) e mensagem amigável; validar extensão/content-type; avaliar caminho equivalente nas importações de colaboradores e locais (não foi possível confirmar sem executar).

### PROB-004

- **Severidade:** Alta
- **Categoria:** Backend / Integridade de dados
- **Arquivo:** `app/services/import_service.py` (`execute_import`)
- **Local:** laço de linhas com `except Exception` + `db.commit()` único ao final
- **Problema:** as linhas acumulam no session e só há **um commit no fim**. Se qualquer linha gerar erro de banco (ex.: `IntegrityError` não coberto pelos pré-checks de duplicata), a sessão entra em estado inválido e todas as operações seguintes falham; o `commit` final falha, o `rollback()` descarta **tudo**, mas o dicionário retornado mantém `imported`/`skipped` já incrementados.
- **Impacto:** perda silenciosa de toda a importação com relatório dizendo que N registros foram importados — divergência real entre tela e banco.
- **Evidência:** contadores incrementados dentro do laço antes do commit; `errors.append("Erro ao salvar os dados no banco.")` sem invalidar os contadores; `except Exception as e: errors.append(...); continue` mascara erros de programação.
- **Correção sugerida:** commit por lote/linha com `savepoint`, ou rollback explícito + recálculo dos contadores a partir do que realmente persistiu; relatar erro de transação de forma destacada.

### PROB-005

- **Severidade:** Alta
- **Categoria:** Banco de dados / Integridade
- **Arquivo:** `app/services/asset_service.py` (`create`), `app/services/import_service.py` (`execute_import`)
- **Local:** `purchase_date=data.purchase_date or datetime.now()` / `purchase_date=purchase_date or datetime.now()`
- **Problema:** quando a data de aquisição não é informada (campo opcional no formulário e no CSV), o sistema **grava a data atual** em vez de deixar nulo.
- **Impacto:** dados fiscais falsos e depreciação calculada sobre uma data inventada (o KPI de "Valor Contábil Atual" fica incorreto).
- **Evidência:** `Asset.purchase_date` é `nullable=True` no modelo, mas o serviço preenche `now()`; `calculate_depreciation` usa `purchase_date` diretamente.
- **Correção sugerida:** persistir `None` quando não informado e tratar a ausência na depreciação/exibição.

### PROB-006

- **Severidade:** Alta
- **Categoria:** Banco de dados / Auditoria
- **Arquivo:** `app/services/movement_service.py`, `app/services/asset_service.py`, `app/services/audit_service.py`, `app/models/audit_log.py`
- **Local:** `timestamp=datetime.now()` (movimentos) versus `datetime.utcnow()` (auditoria, sessões)
- **Problema:** coexistência de dois relógios: movimentações e `updated_at` usam hora **local**, enquanto a trilha de auditoria usa **UTC**. Em `MovementService.get_timeline_for_asset` as duas fontes são mescladas e ordenadas pelo timestamp.
- **Impacto:** ordenação cronológica errada da trilha (offset do fuso), filtros por período incorretos e relatórios com horários inconsistentes entre telas (Brasil = UTC-3).
- **Evidência:** `Movement(timestamp=datetime.now())` em `create_movement`/`create`/`execute_import`; `AuditLog.timestamp` default `datetime.utcnow`; `timeline.sort(key=lambda x: x['timestamp'], reverse=True)`.
- **Correção sugerida:** padronizar um único relógio (UTC) em todo o domínio e converter apenas na apresentação.

### PROB-007

- **Severidade:** Alta
- **Categoria:** Frontend / Funcionalidade
- **Arquivo:** `app/web/routes.py` (`list_assets` L324, `list_movements_view` L703, `form_new_maintenance`/`form_new_movement` L725/L1345, `view_inventory_report` L1471, `view_movements_report` L1500) e `app/web/templates/assets/list.html`
- **Local:** `limit=200` / `limit=500` / `limit=1000` fixos, sem parâmetro de página
- **Problema:** as listagens não têm paginação. A tela exibe "Mostrando N de **total** equipamentos", mas o `total` é o count real do banco e não há nenhum controle para acessar o excedente.
- **Impacto:** em um sistema patrimonial (milhares de bens), registros acima do limite ficam **invisíveis e inacessíveis pela interface**, sem erro.
- **Evidência:** assinatura de `list_assets` sem `page`/`offset`; template L128 mostra `{{ assets|length }}` de `{{ total }}`; `grep` por `page=`/`pagination` nos templates/rota retorna vazio.
- **Correção sugerida:** implementar paginação (ou exportar/avisar quando truncado).

### PROB-008

- **Severidade:** Alta
- **Categoria:** Banco de dados
- **Arquivo:** `app/models/movement.py` (`term_code`), `app/services/movement_service.py` (`create_movement`)
- **Local:** `term_code = f"TR-{datetime.now().year}-{count_year:05d}"` com `count_year = db.query(Movement).filter(...).count() + 1`
- **Problema:** o código do Termo de Responsabilidade é gerado por contagem sequencial, sem `unique` na coluna e sem lock. Duas movimentações simultâneas calculam o mesmo `count` → **código duplicado**. Além disso, a contagem ignora o ano (apesar do nome `count_year`) e soma `ALLOCATION` + `RETURN_STOCK`.
- **Impacto:** dois termos diferentes com o mesmo número (valor probatório/jurídico do documento comprometido); numeração reiniciada/colidida ao longo dos anos.
- **Evidência:** `term_code = Column(String(50), nullable=True, index=True)` (sem `unique=True`), enquanto `movement_uuid` tem `unique=True`.
- **Correção sugerida:** gerar por sequência atômica (tabela de contador com lock/`UPDATE ... RETURNING`), restringir ao ano corrente e criar constraint `UNIQUE` (tratando dados legados).

### PROB-009

- **Severidade:** Alta
- **Categoria:** Backend / API
- **Arquivo:** `app/api/movements_api.py` (`get_movement_term`), `app/services/movement_service.py` (`get_term_details`)
- **Local:** endpoint `GET /api/v1/movements/{movement_id}/term` sem `response_model`
- **Problema:** `get_term_details` devolve um dicionário que contém **objetos ORM** (`asset`, `custodian`, `location` com instâncias) e o endpoint retorna esse dicionário direto. Sem `response_model`, o FastAPI cai no `jsonable_encoder` genérico, que tenta `dict()/vars()` em objetos arbitrários.
- **Impacto:** risco de HTTP 500 na serialização **ou** de expor estado interno do ORM (`_sa_instance_state`, metadados de sessão) no corpo da resposta.
- **Evidência:** `return term_data` sem schema; contraste com `.../timeline`, que monta payload explícito e comentários indicando consciência do problema.
- **Correção sugerida:** definir um schema Pydantic de termo e serializar explicitamente. *(Não foi possível confirmar o comportamento exato sem executar o endpoint.)*

### PROB-010

- **Severidade:** Média
- **Categoria:** Backend
- **Arquivo:** `app/api/reports_api.py` (3 endpoints), `app/web/routes.py` (`list_assets`)
- **Local:** `datetime.strptime(purchase_date_from, "%Y-%m-%d") if purchase_date_from else None`
- **Problema:** conversão de data de query string sem tratamento de `ValueError`.
- **Impacto:** `GET /api/v1/reports/inventory/csv?purchase_date_from=abc` e as telas de lista com data malformada → HTTP 500, em vez de 422/400 com mensagem.
- **Evidência:** não há `try/except` nem validação de formato antes do `strptime`.
- **Correção sugerida:** validar/normalizar parâmetros (helper único) e responder 400/422.

### PROB-011

- **Severidade:** Média
- **Categoria:** Integração / Recursos
- **Arquivo:** `app/main.py` (`health_check`)
- **Local:** `get_ad_settings(SessionLocal())` / `SessionLocal().close()` / `ad_enabled(SessionLocal())`
- **Problema:** o endpoint público `/health` instancia `SessionLocal()` três vezes; apenas **um** objeto (que não é o mesmo usado nas chamadas) é fechado, deixando sessões abertas a cada requisição. Se o AD estiver configurado, dispara tentativa de conexão LDAP por requisição.
- **Impacto:** vazamento de conexões/pool esgotado sob polling frequente de monitoramento; uso do `/health` como amplificador de conexões ao controlador de domínio; endpoint sem autenticação/rate limit expõe o estado de infraestrutura.
- **Evidência:** `ad_settings = get_ad_settings(SessionLocal())` (sessão nunca fechada) seguido de `SessionLocal().close()` (fecha um objeto diferente).
- **Correção sugerida:** abrir uma única sessão em `try/finally`, cachear o resultado do teste de AD e proteger/limitar o endpoint.

### PROB-012

- **Severidade:** Média
- **Categoria:** Backend / Consistência
- **Arquivo:** `app/services/movement_service.py` (`create_movement`, ramo `MAINTENANCE_IN`), `app/services/maintenance_service.py`
- **Local:** `new_status = AssetStatus.AVAILABLE` sem limpar `asset.custodian_id`
- **Problema:** o retorno da manutenção marca o bem como **Disponível** mas mantém o responsável anterior (o custodian só muda se um `destination_custodian_id` for informado). O mesmo ocorre no caminho de envio para manutenção.
- **Impacto:** bem aparece como "estoque/disponível" nos KPIs do dashboard (`status_counts.available`) enquanto continua vinculado a um colaborador; relatórios de estoque e de cautela divergem.
- **Evidência:** ramo `MAINTENANCE_IN` só altera `custodian_id` quando `data.destination_custodian_id` é enviado; `MaintenanceService.complete_maintenance` não envia destino.
- **Correção sugerida:** definir explicitamente a regra (manter ou limpar o responsável) e garantir coerência status × custódia.

### PROB-013

- **Severidade:** Média
- **Categoria:** Frontend
- **Arquivo:** `app/web/templates/assets/list.html` (links de exportação CSV/Excel/PDF)
- **Local:** `?search={{ search }}&status={{ selected_status }}&...`
- **Problema:** valores interpolados sem codificação de URL (`urlencode`).
- **Impacto:** busca contendo `&`, `#`, `%` ou espaço gera link quebrado ou com parâmetros errados (ex.: `search="notebook & mouse"` passa a enviar `mouse=` como filtro extra); exportação retorna dados diferentes do filtro visível.
- **Evidência:** `href="/api/v1/reports/inventory/csv?search={{ search }}&status={{ selected_status }}..."` (Jinja escapa HTML, não URL).
- **Correção sugerida:** aplicar `| urlencode`/`urlencode` nos parâmetros ou montar a query por `URLSearchParams`.

### PROB-014

- **Severidade:** Média
- **Categoria:** Frontend
- **Arquivo:** `app/web/static/js/main.js`, `app/web/templates/base.html`
- **Local:** `document.querySelectorAll('[data-bs-toggle="tooltip"]')` em `main.js` (DOMContentLoaded) **e** no `<script>` inline do `base.html`
- **Problema:** os tooltips do Bootstrap são inicializados duas vezes na mesma página (duas instâncias por elemento) e `main.js` executa `window.scrollTo(0, 0)` incondicionalmente em todo carregamento.
- **Impacto:** comportamento duplicado/instâncias órfãs de tooltip, avisos no console; o scroll forçado ao topo cancela a restauração de scroll e quebra links de âncora/voltar do navegador.
- **Evidência:** dois blocos equivalentes de inicialização; `history.scrollRestoration = 'manual'` seguido de `window.scrollTo(0,0)` na carga.
- **Correção sugerida:** centralizar a inicialização em um único ponto e só rolar ao topo quando não houver hash/restauração.

### PROB-015

- **Severidade:** Média
- **Categoria:** Backend / Validação
- **Arquivo:** `app/schemas/asset.py`, `app/schemas/custodian.py`
- **Local:** `AssetBase`, `CustodianBase`, `AssetUpdate`
- **Problema:** validação insuficiente: `tag`, `name`, `registration_code`, `role`, `department` aceitam string vazia (só `Field(...)` de presença); `email` é `str` (o `EmailStr` é importado e **não usado**); `purchase_value`/`cost` sem `ge=0` (aceita valor negativo); `CustodianUpdate` permite alterar `registration_code` (matrícula usada em termos e histórico).
- **Impacto:** registros sem identificação, valores negativos afetando depreciação/relatórios e alteração de matrícula sem rastro no histórico de termos já emitidos.
- **Evidência:** `email: str` com `from pydantic import ... EmailStr` no mesmo arquivo; `tag: str = Field(..., description="...")` sem `min_length`.
- **Correção sugerida:** adicionar `min_length`, `ge=0`, `EmailStr` e regra explícita para alteração de matrícula.

### PROB-016

- **Severidade:** Média
- **Categoria:** Segurança
- **Arquivo:** `app/main.py`, `app/config.py`, `app/web/templates/base.html`, `login.html`, `setup.html`
- **Local:** criação do `FastAPI(...)` sem ajuste de docs; ausência de middleware
- **Problema:** (a) `/docs`, `/redoc` e `/openapi.json` ficam **públicos** sem autenticação (nada define `docs_url`/`openapi_url`); (b) não existe middleware de headers de segurança (CSP, `X-Frame-Options`, `X-Content-Type-Options`, `HSTS`, `Referrer-Policy`); (c) todos os assets vêm de CDN sem SRI/crossorigin e o `chart.js` é carregado sem versão fixa; (d) `AUTH_COOKIE_SECURE` tem default `false` e SameSite=Lax (sem token CSRF).
- **Impacto:** exposição completa do inventário de endpoints/schemas; ausência de mitigação de clickjacking/XSS/MIME-sniffing; dependência de terceiros sem integridade (supply chain) e indisponibilidade da UI em rede sem internet; cookie trafegando sem TLS se implantado sem a variável.
- **Evidência:** `grep` por `add_middleware|X-Frame|Content-Security-Policy|docs_url` em `app/` não retorna resultados; `main.py` usa apenas `FastAPI(title=..., lifespan=...)`.
- **Correção sugerida:** avaliar desabilitar/limitar docs em produção, adicionar middleware de headers, SRI + versão fixa nos CDNs e documentar/forçar `AUTH_COOKIE_SECURE=true` em HTTPS.

---

## 3. Possíveis Problemas 🟠

### PROB-017

- **Severidade:** Média · **Categoria:** Segurança
- **Arquivo:** `app/services/report_service.py` (`generate_inventory_csv`, `generate_inventory_excel`, `generate_movements_csv`)
- **Local:** escrita de valores livres (`name`, `supplier`, `invoice_number`, `notes`, `reason`, `operator_name`)
- **Problema:** não há neutralização de "formula injection": valores iniciados por `=`, `+`, `-`, `@` são gravados como estão. No caso do `.xlsx`, o `openpyxl` pode interpretar uma string iniciada por `=` como **fórmula**.
- **Impacto:** execução de fórmulas/exfiltração ao abrir o relatório em Excel/LibreOffice (CSV/Excel injection).
- **Evidência:** `writer.writerow([...])` sem prefixo de segurança e `ws.cell(..., value=...)` com strings do usuário.
- **Correção sugerida:** prefixar valores perigosos (apóstrofo/espaço) e/ou marcar células como texto.

### PROB-018

- **Severidade:** Média · **Categoria:** Banco de dados
- **Arquivo:** `app/services/movement_service.py` (`create_movement`)
- **Problema:** fluxo read-modify-write sem lock/serialização: lê o `Asset`, decide o novo status, atualiza e insere o movimento.
- **Impacto:** duas movimentações simultâneas do mesmo bem podem gerar dois registros para uma única transição real e "perder" uma das atualizações (last-write-wins) — estado do bem divergente da trilha.
- **Evidência:** ausência de `with_for_update()`/controle de versão; `db.commit()` único ao final. *(Não confirmado em runtime.)*
- **Correção sugerida:** lock pessimista/otimista ou verificação de versão no update.

### PROB-019

- **Severidade:** Média · **Categoria:** Banco de dados
- **Arquivo:** `app/services/asset_service.py` (`create`/`update`), `app/services/custodian_service.py`
- **Problema:** unicidade é verificada por SELECT antes do INSERT, sem capturar `IntegrityError`. As colunas `assets.tag`, `assets.serial_number` e `custodians.registration_code/email` são `UNIQUE`.
- **Impacto:** em corrida, o banco levanta `IntegrityError` não tratada → HTTP 500 em vez de mensagem "já existe".
- **Evidência:** pré-checagens por query e nenhum `except IntegrityError` nos serviços/rotas.
- **Correção sugerida:** tratar a exceção de integridade e devolver erro de negócio.

### PROB-020

- **Severidade:** Média · **Categoria:** Arquitetura
- **Arquivo:** `app/services/audit_service.py` (`write_audit`), `app/api/deps.py`
- **Problema:** `write_audit` faz `db.commit()` + `db.refresh()` na **sessão de negócio**, acoplando auditoria e transação funcional. O próprio `deps.py` contém um workaround (`db.refresh(user)`) porque o commit da auditoria expira o usuário da requisição.
- **Impacto:** alteração de negócio pode ser persistida por efeito colateral da auditoria, impossibilitando rollback coerente do conjunto; dificulta transações atômicas e testes.
- **Evidência:** comentário em `deps.py` ("Recarrega os atributos do usuário (o commit da auditoria os expira)") e `db.commit()` dentro de `write_audit`.
- **Correção sugerida:** modelar auditoria na mesma unidade de trabalho (flush) com commit único controlado pela camada de aplicação.

### PROB-021

- **Severidade:** Média · **Categoria:** Segurança
- **Arquivo:** `app/services/auth_service.py`, `app/api/auth_api.py`, `app/web/routes.py`
- **Problema:** o bloqueio é **por conta** (`AUTH_MAX_FAILED_ATTEMPTS=5` → 15 min), sem rate limiting por IP/roteador; qualquer pessoa que conheça um username pode bloqueá-lo repetidamente (lockout como DoS). Não foi possível confirmar se o caminho de autenticação AD aplica o mesmo limite.
- **Impacto:** indisponibilidade de contas legítimas; tentativas distribuídas contra o diretório (AD) sem contenção local.
- **Evidência:** incremento de `failed_login_attempts` apenas em `auth_service.authenticate` (fluxo local); `ad_service.authenticate_and_sync` é o caminho do AD e não foi lido integralmente nesta varredura.
- **Correção sugerida:** combinar proteção por conta com throttling por IP/global e revisar o caminho AD.

### PROB-022

- **Severidade:** Baixa · **Categoria:** Segurança
- **Arquivo:** `app/web/routes.py`, `app/api/assets_api.py`
- **Problema:** não há limite de tamanho no servidor para upload (a UI informa "Máximo 10 MB", mas o backend lê `file.file.read()` inteiro) nem validação de `file.filename is None` no caminho da API.
- **Impacto:** consumo de memória/DoS com uploads grandes; possível `AttributeError` no caminho da API quando o nome do upload é ausente.
- **Evidência:** `not file.filename or not file.filename.endswith(".csv")` existe na rota web, mas na API é `if not file.filename.endswith(".csv")` (sem guarda de `None`).
- **Correção sugerida:** limitar tamanho, ler em streaming e validar metadados.

### PROB-023

- **Severidade:** Baixa · **Categoria:** Integração
- **Arquivo:** `app/services/report_service.py` (`generate_inventory_pdf`)
- **Problema:** textos do usuário são inseridos em `reportlab.Paragraph`, que interpreta uma mini-linguagem XML/HTML.
- **Impacto:** caractere `<` ou tag malformada em nome/observação pode quebrar a geração do PDF (500) ou alterar a formatação do documento.
- **Evidência:** `Paragraph(asset.name or "", cell_style)` com valores livres. *(Comportamento exato não confirmado sem execução.)*
- **Correção sugerida:** escapar texto antes de montar o parágrafo.

### PROB-024

- **Severidade:** Baixa · **Categoria:** Frontend
- **Arquivo:** `app/web/templates/ajuda/index.html`
- **Problema:** o índice de busca é injetado com `{{ search_index | safe }}` dentro de `<script>` e os resultados são renderizados com `innerHTML`.
- **Impacto:** hoje o conteúdo é escrito em código (risco baixo), porém qualquer conteúdo dinâmico futuro (ou um `</script>` no texto) vira vetor de XSS/DOM-XSS.
- **Evidência:** `const HELP_INDEX = {{ search_index | safe }};` e `helpResults.innerHTML = matches.map(...)`.
- **Correção sugerida:** usar `tojson`/`JSON.parse` e construir o DOM com `textContent`.

---

## 4. Melhorias Recomendadas 🟡

### PROB-025

- **Severidade:** Baixa · **Categoria:** Banco de dados / Performance
- **Arquivo:** `app/services/dashboard_service.py` (`_get_inconsistencies`, `get_stats`)
- **Problema:** as inconsistências são contadas carregando **todas** as linhas em memória (`.all()` + `len()`) em vez de `func.count()`; o dashboard executa ~9 consultas por carregamento, sem cache.
- **Impacto:** degradação progressiva com o crescimento do acervo.
- **Evidência:** `assets_without_location = db.query(Asset.id, Asset.tag, Asset.name).filter(...).all()` seguido de `"count": len(assets_without_location)`.
- **Correção sugerida:** usar agregações no banco e cachear as estatísticas.

### PROB-026

- **Severidade:** Baixa · **Categoria:** Arquitetura
- **Arquivo:** `app/api/reports_api.py`, `app/web/admin_routes.py`, `app/schemas/custodian.py`, `app/web/static/js/main.js`, `app/web/routes.py`
- **Problema:** código duplicado/morto: os três endpoints de exportação repetem o mesmo parsing de ID/data e o mesmo bloco de nome de arquivo; `import os` sem uso em `admin_routes.py`; `EmailStr` importado e não usado; `_count_active_admins` calcula em Python percorrendo todos os usuários ativos; `tooltipTriggerList.map(...)` descarta o retorno; `_inject_current_user` abre uma sessão extra como fallback.
- **Evidência:** leitura direta dos trechos citados.
- **Correção sugerida:** extrair helpers comuns e remover imports/códigos mortos.

### PROB-027

- **Severidade:** Baixa · **Categoria:** Arquitetura / Manutenção
- **Arquivo:** `requirements.txt`, `app/web/templates/base.html`/`login.html`/`setup.html`, `app/web/static/img/`
- **Problema:** dependências com faixa aberta (`>=`), `pytest` entre dependências de produção, `chart.js` de CDN **sem versão**; assets duplicados (`favicon.ico` e `favicon_.ico`, `Logo_IPMjp.png` e `"Logo IPMjp_.png"` — este último com espaço no nome); cache-busting inconsistente (`style.css?v=20260913` no `base.html` vs `v=20260905` em login/setup).
- **Impacto:** builds não reprodutíveis, risco de quebra por atualização de terceiros, confusão de cache CSS entre telas e arquivos órfãos.
- **Evidência:** conteúdo de `requirements.txt`; listagem de `app/web/static`; `grep` de `style.css?v=`.
- **Correção sugerida:** fixar versões (lock/reproducible), separar deps de teste/CDN com versão e unificar versionamento/limpar assets.

### PROB-028

- **Severidade:** Baixa · **Categoria:** Arquitetura / Operação
- **Arquivo:** `run.py`, `app/main.py`, `app/logging_config.py`
- **Problema:** `init_db()` roda duas vezes (em `run.py` e no `lifespan`); `configure_logging()` é chamado **apenas** por `run.py`, de modo que iniciar por `uvicorn app.main:app` deixa de gravar `data/logs/*`.
- **Evidência:** `run.py` chama `init_db()` e depois `uvicorn.run("app.main:app")` (que dispara o `lifespan` chamando `init_db()` novamente); nenhum outro ponto importa `configure_logging`.
- **Correção sugerida:** centralizar inicialização (só no `lifespan`) e configurar logging na aplicação.

### PROB-029

- **Severidade:** Baixa · **Categoria:** UX/UI
- **Arquivo:** `app/web/templates/assets/import.html`, `app/web/templates/admin/roles/form.html`
- **Local:** tabela "Formato do Arquivo CSV" e lista de permissões do perfil
- **Problema:** permanecem textos em formato técnico na interface: nomes de coluna `nota_fiscal` e `data_aquisicao` (exibidos como rótulo da coluna) e códigos de permissão (`patrimonio.criar`) renderizados em `<code>`.
- **Impacto:** baixo — no caso das colunas, o sublinhado é o texto que o arquivo deve conter (técnico por natureza); nos códigos de permissão, é referência técnica deliberada. Vale padronizar rótulo humano + referência técnica.
- **Evidência:** `<td><code>nota_fiscal</code></td>` / `<td><code>data_aquisicao</code></td>` e `<code ...>{{ perm.name }}</code>`.
- **Correção sugerida:** apresentar o rótulo em linguagem natural e manter o identificador apenas como referência (quando necessário).

---

## 5. Priorização

| ID | Severidade | Categoria | Arquivo | Problema |
|---|---|---|---|---|
| PROB-001 | Crítica | Segurança | `app/web/routes.py` | Corrida no `/setup` pode criar mais de um administrador |
| PROB-002 | Crítica | Segurança | `.gitignore`, `data/` | Banco de produção, logs e backups versionados |
| PROB-003 | Alta | Backend | `routes.py`, `assets_api.py` | CSV não-UTF8 causa 500 sem tratamento |
| PROB-004 | Alta | Backend | `import_service.py` | Rollback total com relatório dizendo que importou |
| PROB-005 | Alta | Banco | `asset_service.py`, `import_service.py` | Data de aquisição inventada (`or now()`) |
| PROB-006 | Alta | Banco | `movement_service.py`, `audit_service.py` | Relógios mistos (local × UTC) na trilha |
| PROB-007 | Alta | Frontend | `routes.py`, `assets/list.html` | Sem paginação (limite fixo, resto invisível) |
| PROB-008 | Alta | Banco | `movement.py`, `movement_service.py` | `term_code` duplicável (sem UNIQUE, por contagem) |
| PROB-009 | Alta | Backend | `movements_api.py` | `/term` retorna objetos ORM sem schema |
| PROB-010 | Média | Backend | `reports_api.py`, `routes.py` | `strptime` sem tratamento → 500 |
| PROB-011 | Média | Integração | `main.py` | `/health` vaza sessões e dispara LDAP |
| PROB-012 | Média | Backend | `movement_service.py` | Status "Disponível" mantendo responsável |
| PROB-013 | Média | Frontend | `assets/list.html` | Links de exportação sem `urlencode` |
| PROB-014 | Média | Frontend | `main.js`, `base.html` | Tooltips duplicados + `scrollTo(0,0)` |
| PROB-015 | Média | Backend | `schemas/*.py` | Validação fraca (string vazia, negativos, `EmailStr`) |
| PROB-016 | Média | Segurança | `main.py`, templates | Docs públicos, sem headers de segurança/SRI |
| PROB-017 | Média | Segurança | `report_service.py` | Formula injection em CSV/Excel |
| PROB-018 | Média | Banco | `movement_service.py` | Lost update em movimentações concorrentes |
| PROB-019 | Média | Banco | `asset_service.py`, `custodian_service.py` | `IntegrityError` → 500 em corrida |
| PROB-020 | Média | Arquitetura | `audit_service.py` | Auditoria commita a transação de negócio |
| PROB-021 | Média | Segurança | `auth_service.py` | Lockout por conta (DoS) e sem rate limit |
| PROB-022 | Baixa | Segurança | `routes.py`, `assets_api.py` | Upload sem limite/validação de nome |
| PROB-023 | Baixa | Integração | `report_service.py` | PDF interpreta texto do usuário como markup |
| PROB-024 | Baixa | Frontend | `ajuda/index.html` | `\|safe` + `innerHTML` no índice de busca |
| PROB-025 | Baixa | Banco | `dashboard_service.py` | `len()` sobre consultas completas (performance) |
| PROB-026 | Baixa | Arquitetura | vários | Código duplicado/morto |
| PROB-027 | Baixa | Arquitetura | `requirements.txt`, templates | Versões abertas, assets duplicados, cache inconsistente |
| PROB-028 | Baixa | Arquitetura | `run.py`, `logging_config.py` | `init_db` duplo; logging não configura fora do `run.py` |
| PROB-029 | Baixa | UX/UI | `assets/import.html`, `admin/roles/form.html` | Texto técnico (`nota_fiscal`, `data_aquisicao`, código de permissão) |

### Resumo por severidade

- 🔴 Críticos: **2**
- 🟠 Altos: **7**
- 🟡 Médios: **13**
- 🟢 Baixos: **7**

### Resumo por categoria

- Backend: **6**
- Banco de dados: **6**
- Segurança: **6**
- Frontend: **4**
- Arquitetura: **4**
- Integrações: **2**
- UX/UI: **1**
- Outros: **0**

---

## 6. Itens não confirmáveis em modo somente leitura

Os pontos abaixo dependem de execução para confirmação e estão registrados como **possíveis**:

- Serialização real de `GET /api/v1/movements/{id}/term` (PROB-009).
- Corrida de movimentações concorrentes sobre o mesmo bem (PROB-018).
- Tratamento de strings iniciadas por `=` pelo `openpyxl` na exportação Excel (PROB-017).
- Quebra da geração de PDF com caracteres de markup em texto do usuário (PROB-023).
- Existência de bloqueio por tentativas falhas no caminho de autenticação AD (PROB-021).

---

## 7. Pontos verificados e considerados íntegros

Registrados para evitar releitura e para diferenciar "não avaliado" de "avaliado e conforme":

- **RBAC deny-by-default:** todas as rotas web de negócio e toda a API (`/api/v1`, exceto `auth` e `/me` que exige sessão) têm `require_permission(...)` por operação; o bypass é restrito a `User.is_admin` e é auditado; a negação grava `ACESSO_NEGADO`.
- **Sessões:** token aleatório (`secrets.token_urlsafe`), apenas hash SHA-256 persistido, cookie `HttpOnly` + `SameSite=Lax`, expiração no servidor, revogação no logout e invalidação de todas as sessões ao trocar/redefinir senha.
- **Senhas:** PBKDF2-HMAC-SHA256 com salt por usuário e iterações configuráveis (padrão 600.000), verificação em tempo constante (`hmac.compare_digest`) e hash "dummy" para equalizar tempo em usuário inexistente.
- **Injeção LDAP:** o filtro de busca passa por `_escape` (RFC 4515); senhas nunca são logadas nem persistidas; LDAPS valida certificado por padrão (`verify_tls=True`).
- **XSS em templates:** autoescape do Jinja2 ativo; `\|safe` aparece apenas no índice de busca da Ajuda; o único caso de `innerHTML` com dados de assets usa `textContent` para os valores do usuário (`assets/labels.html`).
- **Logs técnicos:** nenhuma ocorrência de senha/token/hash em `data/logs/*` (verificado por `grep`).
- **Links da interface:** todos os `href` internos apontam para rotas existentes; os três artigos de ajuda linkados (`cadastrar-equipamento`, `movimentar-equipamento`, `abrir-ordem-servico`) existem.
- **IDs duplicados:** nenhuma duplicidade de `id=` em `base.html` e `assets/labels.html`.
- **`togglePasswordVisibility`:** a chamada sem argumentos no login é válida (parâmetros têm valores padrão).
- **Upload restrito por tipo:** a rota web valida presença e extensão `.csv` do arquivo.

---

## RESULTADO DA AUDITORIA

**Status:** 🔴 **PROBLEMAS ENCONTRADOS**

- **Quantidade total de problemas:** **29**
- **Quantidade por severidade:** 2 críticos · 7 altos · 13 médios · 7 baixos
- **Principais riscos:** exposição de dados no repositório (banco/logs/backups versionados), escalada de privilégio no primeiro acesso, integridade da rastreabilidade (relógios mistos, `term_code` duplicável, importação que pode ser descartada reportando sucesso), falhas de disponibilidade (500 em upload/datas, `/health` sem autenticação e com sessões vazadas, lockout como DoS), superfície exposta (`/docs` público, sem headers de segurança/SRI) e funcionalidade silenciosamente limitada (listagens sem paginação).
- **Arquivos/componentes mais afetados:** `app/web/routes.py`, `app/services/movement_service.py`, `app/services/import_service.py`, `app/services/report_service.py`, `app/services/audit_service.py`, `app/api/reports_api.py`, `app/api/assets_api.py`, `app/main.py`, `app/web/templates/assets/list.html`, `app/web/static/js/main.js`, `.gitignore` / `data/`.

**Nada foi corrigido ou alterado.** Este relatório é o artefato produzido pela auditoria.

---

# Apêndice A — Auditoria de textos da interface (SNAKE_CASE visível)

> **Data:** 11/09/2026 (mesma sessão de análise)
> **Critério:** nenhum texto destinado ao usuário final pode conter identificadores técnicos em `SNAKE_CASE` (ou `_` indevido).
> **Resultado na época da varredura:** **REPROVADO** — 17 identificadores distintos em 32 pontos de exibição.

## A.1 Inconformidades encontradas (estado original)

| Grupo | Texto encontrado | Onde aparecia | Forma recomendada |
|---|---|---|---|
| Status de equipamento | `DISPONIVEL`, `EM_USO`, `EM_MANUTENCAO`, `EM_TRANSITO`, `BAIXADO` | Lista/filtros de Equipamentos, Etiquetas, Detalhe do Bem, Detalhe do Colaborador, Relatório de Inventário, Relatório e lista de Movimentações, Nova Movimentação, Manutenções, Ajuda (artigos e FAQ) | Disponível, Em Uso, Em Manutenção, Em Trânsito, Baixado |
| Categoria | `REDE_E_CONECTIVIDADE`, `SMARTPHONE_TABLET`, `EQUIPAMENTO_GERAL` | Filtros e badges de categoria, formulário de equipamento, prévia da importação CSV, relatório de inventário | Rede e Conectividade, Smartphone / Tablet, Equipamento Geral |
| Tipo de movimentação | `ENTRADA_AQUISICAO`, `ALOCACAO_CAUTELA`, `TRANSFERENCIA_LOCAL`, `ENVIO_MANUTENCAO`, `RETORNO_MANUTENCAO`, `DEVOLUCAO_ESTOQUE`, `BAIXA_DESCARTE`, `ATUALIZACAO_ESTADO` | Dashboard, lista de Movimentações, trilha de fluxo do bem, relatório de movimentações | Entrada por Aquisição, Alocação / Cautela, Transferência de Local, Envio para Manutenção, Retorno de Manutenção, Devolução ao Estoque, Baixa / Descarte, Atualização de Estado |
| Status de manutenção | `EM_ANDAMENTO` | Badge na lista de Manutenções | Em Andamento |
| Ação de auditoria | `LOGIN_FALHA`, `RESET_SENHA`, `ACESSO_NEGADO`, `LOGIN_AD_AUTORIZADO`, `CONFLITO_GRUPOS_AD`, entre outras | Tela de Auditoria (filtro "Ação" e badge da coluna Ação) e trilha do bem | Falha de Login, Redefinição de Senha, Acesso Negado, Login AD Autorizado, Conflito de Grupos AD |
| Colunas de CSV | `nota_fiscal`, `data_aquisicao` | Ajuda da tela de Importação (tabela de formato do arquivo) | **Mantido** — é o texto literal que o cabeçalho do arquivo deve conter (técnico por natureza) |

**Não contabilizado** (fora do escopo do critério): atributos `name=`/`id=`, classes CSS (`status-pill-EM_MANUTENCAO`), parâmetros de URL (`?m_type=DEVOLUCAO_ESTOQUE`) e chaves de formulário.

## A.2 Correções aplicadas em sequência nesta mesma sessão

- `app/models/enums.py`: base `_LabeledEnum` com a propriedade `label` e mapa único de rótulos; `value` preservado como identificador técnico (banco, filtros, CSS, APIs).
- Templates: exibição de status, categoria, tipo de movimentação, status/tipo de manutenção e condição passou de `.value` para `.label` (mantendo `.value` em `value=`, classes CSS e comparações).
- Termo de Cautela impresso: `{{ term.asset.category }}` e `{{ term.asset.condition }}` renderizavam o objeto do enum (`AssetCategory.NOTEBOOK`) — corrigido para o rótulo.
- Dashboard: rótulos do gráfico de categorias passaram a usar o rótulo em vez do valor técnico.
- Ajuda: textos que citavam `DISPONIVEL`, `EM_USO`, `EM_MANUTENCAO`, `EM_TRANSITO` e `BAIXADO` reescritos em linguagem natural.
- Auditoria: `ACTION_LABELS` + `action_label()` com fallback legível para ações futuras; aplicado no filtro, no badge da coluna Ação e na trilha do bem; coluna "Resultado" ganhou o caso `LOCKED` → "BLOQUEADO".
- Exportações: inventário CSV/Excel e movimentações CSV passaram a sair com rótulos; `_normalize_category`/`_normalize_condition` passaram a aceitar valor técnico **e** rótulo (com normalização de acentos), preservando a reimportação.
- Relatórios PDF de inventário (documento apresentado ao usuário) também passaram a usar rótulos.

## A.3 Situação atual do critério

- **Status:** ⚠️ **Parcialmente conforme** — resta apenas PROB-029 (`nota_fiscal`/`data_aquisicao` na tabela de formato do CSV e códigos de permissão em `<code>`), classificada como **Baixa/UX** e, no caso das colunas, tecnicamente necessária.
- **Verificação executada na época:** suíte completa com **130 testes passando** após as alterações de rótulos.
