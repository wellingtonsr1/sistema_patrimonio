# SisPatrimônio Pro — Diagnóstico Técnico do Estado Atual × Lista de Melhorias

> **Data da análise:** 10/09/2026
> **Documento de referência:** `docs/Melhorias_SisPatrimonio_Pro.md`
> **Método:** auditoria exclusivamente de leitura do código-fonte (grep, leitura de arquivos, `git status`/`git log`). Nenhum arquivo, código, banco, configuração ou dependência foi alterado durante a análise.
> **Escopo:** comparar cada melhoria planejada com o estado REAL do código, classificando o que já existe, o que está parcialmente pronto e o que realmente falta.

---

## 1. Resumo Executivo

O SisPatrimônio Pro é um sistema **maduro** para o ciclo patrimonial básico: cadastro de bens com tombamento único, motor de movimentação com trilha imutável, colaboradores/custódia, locais, manutenções, termos de responsabilidade com QR Code, autenticação local + Active Directory, RBAC completo (deny-by-default), auditoria abrangente, importação CSV com prévia e 144 testes automatizados passando.

**Resultado da comparação com a lista de melhorias (24 sub-itens analisados):**

| Classificação | Quantidade | Itens |
|---|---|---|
| Já implementado | **8** | 1.5, 1.6, 2.1, 2.2, 2.3, 3.1, 4.2, 6.1 |
| Implementado, c/ aprimoramento | **1** | 1.4 |
| Parcialmente implementado | **9** | 1.1, 1.2, 1.3, 3.2, 4.1, 4.4, 5.1, 6.3, 6.4 |
| Não implementado | **6** | 3.3, 3.4, 4.3, 5.2, 6.2 |

**Conclusão central:** os pilares de segurança, integridade e rastreabilidade — que o próprio documento declara como prioridade — **já estão implementados**. O que falta é sobretudo **gestão/visibilidade gerencial** (inconsistências, relatórios por dimensão, exportação filtrada) e **produtividade em volume** (etiquetas, lote). Nenhuma lacuna encontrada compromete segurança ou integridade patrimonial hoje.

---

## 2. Arquitetura Atual

- **Linguagem/Framework:** Python + FastAPI (`app/main.py`), Jinja2 server-side templates, Bootstrap 5 + Bootstrap Icons via CDN (`base.html`), Chart.js (dashboard), QRCode.js.
- **ORM/Banco:** SQLAlchemy 2.x sobre SQLite (`data/patrimonio.db`), com migrações leves idempotentes via `ALTER TABLE` (`app/database.py:_ensure_schema_migrations`, linha ~28).
- **Camadas:** `models/` (12 modelos), `schemas/` (Pydantic), `services/` (17 serviços — lógica de negócio centralizada), `api/` (REST `/api/v1`), `web/` (rotas server-rendered + admin), `cli.py` (subcomandos stats/list/show/move/create-user).
- **Autenticação:** PBKDF2-HMAC-SHA256 (600k iterações, OWASP), sessão server-side com token hasheado SHA-256 no banco, cookie HttpOnly/SameSite=Lax, lockout por tentativas (`auth_service.py`, `session_service.py`).
- **Autorização:** RBAC com catálogo canônico de 31 permissões (`permission_service.py:PERMISSION_CATALOG`), 7 perfis padrão, `require_permission()` (deny by default, admin bypass auditado) em `app/api/deps.py`.
- **AD:** integração completa — bind direto por usuário (sem conta de serviço), mapeamento Grupo AD→Perfil existente, provisionamento somente após grupo autorizado, vínculo a colaborador por e-mail/matrícula sem duplicar (`ad_service.py`, `ad_ldap.py`), tela admin própria.
- **Auditoria:** `audit_service.py` com ~30 constantes de ação (login, AD, CRUD, movimentação, importação, configuração AD, acesso negado), snapshots before/after, trilha somente-leitura consultável em `/admin/audit`.
- **Testes:** 3.167 linhas / 144 testes (auth 237, RBAC 635, AD 663, movimentações 172, imports 597, edição de colaboradores 366, navbar, ajuda).

---

## 3. Funcionalidades Já Implementadas

| Funcionalidade | Localização |
|---|---|
| CRUD de bens com validação de unicidade (tag/serial) | `asset_service.py:create/update` (linhas ~72–100); `Asset.tag/serial_number unique=True` (`asset.py:12,17`) |
| Motor de movimentação atômico com 8 tipos e guardas | `movement_service.py:create_movement` (~15–160): bloqueia bem baixado, exige custodiante em alocação, exige local em transferência |
| Timeline imutável por bem | `movement_service.py:get_timeline_for_asset` + `assets/detail.html:138–156` ("Trilha de Fluxo & Movimentações") |
| Termo de Responsabilidade com QR | `movement_service.py:get_term_details` + `movements/term.html:140–154` |
| QR Code da ficha → `/assets/{id}` | `assets/detail.html:220–231` |
| Depreciação linear contábil | `asset_service.py:calculate_depreciation` |
| AD + RBAC + provisionamento seguro | `ad_service.py:authenticate_and_sync` (~linha 280+), `permission_service.py` |
| Auditoria completa com before/after | `audit_service.py` + `write_change_audit` usado em todos os módulos |
| Importação CSV com prévia→erros→confirmar→resumo (bens, colaboradores, locais) | `import_service.py`, `custodian_import_service.py`, `location_import_service.py` + templates `*/import.html` (`show_preview`, `show_result`) |
| Exportação CSV (inventário, movimentações, colaboradores) | `report_service.py` + `reports_api.py` + botões web |
| Edição de colaboradores preservando custódia | `app/web/routes.py:776–846`, `custodian_service.py:update` |
| Estados vazios orientados | componentes `.empty-state` em 10+ templates |
| Health check da aplicação | `app/main.py:90–92` (`/health`) |
| Testes automatizados abrangentes | `tests/` (144 passando) |

---

## 4. Comparação com a Lista de Melhorias

| Melhoria | Situação Atual | Classificação | Evidência no Código | O que Falta | Prioridade |
|---|---|---|---|---|---|
| **1.1 Dashboard mais útil** | Total, valor, status, categorias (chart), últimas 8 movimentações, últimos bens | Parcial | `dashboard_service.py:get_stats`; `dashboard.html` (KPIs + `statusChart`/`categoryChart`) | Distribuição por localização/setor; alertas de inconsistência | Alta (inconsistências), Média (por local/setor) |
| **1.2 Busca global** | Busca por texto só na listagem de bens (tag, nome, marca, modelo, série, NF); busca em usuários e auditoria isoladas | Parcial | `asset_service.py:get_all` (search `or_` ~26–36); `admin_routes.py:admin_list_users` | Busca unificada incluindo colaborador, setor e local | Média |
| **1.3 Filtros avançados** | Bens: status, categoria, local, custodiante ✓. Movimentações web: só tipo. API de movimentações já aceita mais filtros | Parcial | `assets/list.html:30–60`; `MovementFilter` (`schemas/movement.py:51–57`: custodian_id, location_id, start_date, end_date) | Expor filtros de período/colaborador/local na web; marca/modelo; setor | Alta |
| **1.4 Histórico completo** | Timeline de movimentações completa (inclui entrada, manutenções via MAINTENANCE_OUT/IN, responsáveis, motivo, operador) | Implementado c/ aprimoramento | `get_timeline_for_asset`; `maintenance_service.py:49,88` gera movimentos | Vincular eventos de auditoria do bem à mesma visão | Média |
| **1.5 QR Code por equipamento** | Completo (ficha + termo) | **Já implementado** | `assets/detail.html:220`; `movements/term.html:148` | — | — |
| **1.6 Controle rigoroso** | Tag única, serial único, histórico, status controlado, movimentos inconsistentes bloqueados, campos obrigatórios | **Já implementado** | `asset.py:12,17`; `movement_service.py:23–24,69–71,76–78`; `Form(...)` obrigatórios | — | — |
| **2.1 AD + RBAC** | Fluxo exatamente como proposto (AD autentica; grupo mapeado → perfil existente; sem mapeamento → negado, nada criado) | **Já implementado** | `ad_service.py:authenticate_and_sync` (~280–380); `resolve_role_for_groups`; 7 perfis em `DEFAULT_ROLES` | — | — |
| **2.2 Auditoria robusta** | Todos os eventos listados no documento existem (login/logout, AD, falhas, CRUD, movimentações, perfis, importações, config AD, IP, resultado) | **Já implementado** | `audit_service.py` (~30 ACTION_*); uso difuso em todos os routers | — | — |
| **2.3 Proteção contra exclusões** | **Não existe nenhuma rota DELETE no sistema** (grep `@router.delete` = vazio). Colaborador tem `is_active`; descarte de bem é movimento `BAIXA_DESCARTE` controlado | **Já atendido por outra funcionalidade** | grep negativo em `app/api/*.py` e `web/routes.py`; `enums.py:WRITE_OFF` | Nada essencial | — |
| **3.1 Importação CSV** | Fluxo prévia→erros→confirmar→resumo idêntico ao proposto (válidos/duplicados/erros) | **Já implementado** | `import.html:92–191` (`show_preview`, `preview.duplicates`); `import_service.py:332–364` | — | — |
| **3.2 Exportação** | CSV completo para 3 conjuntos; sem Excel/PDF server-side; export não aplica filtros da tela | Parcial | `report_service.py`; `reports_api.py` (sem params de filtro) | Export filtrado; Excel/PDF (PDF parcial via impressão do navegador no termo) | Média |
| **3.3 Etiquetas** | Não existe (QR existe apenas na ficha e no termo) | Não implementado | grep "etiqueta" só em textos de ajuda (`help_service.py:257`) | Página de etiquetas em lote com QR+tag | Média |
| **3.4 Ações em lote** | Não existe | Não implementado | grep "lote/batch/bulk" = vazio | Seleção múltipla + operações autorizadas | Não implementar agora |
| **4.1 Feedback visual** | Mensagens de sucesso/erro nos fluxos de edição (query `?success=`/`?error=`) e importação; mas `?created=true`/`?moved=true` da criação de bens/movimentos não são consumidos pelos templates | Parcial | `admin_routes.py` (redirects com success); grep `alert-success` em assets/movements = vazio | Banner pós-criação/movimentação | Baixa |
| **4.2 Estados vazios** | Implementado com orientação útil | **Já implementado** | `.empty-state` em assets, custodians, users, audit, AD, locations | — | — |
| **4.3 Preservação de filtros** | "Voltar" da ficha vai para `/assets` sem params | Não implementado | `assets/detail.html:33–35` | Repassar querystring ao voltar | Baixa |
| **4.4 Atalhos de teclado** | Esc fecha sidebar; não há Ctrl+K (não há busca global) | Parcial | `main.js:108–111` | Ctrl+K dependente da busca global | Baixa |
| **5.1 Relatórios gerenciais** | Web: inventário geral, movimentações, por responsável. CSV: inventário completo. Sem: por setor, por localização, sem responsável, sem localização, manutenções | Parcial | `routes.py:1308–1344`; `templates/reports/` (3 arquivos) | 6 visões dimensionais faltantes | Média |
| **5.2 Indicadores de inconsistência** | Não existe painel de inconsistências (duplicidade já é prevenida por constraints, então o indicador real seria "sem localização/sem responsável") | Não implementado | grep "inconsist" = vazio em `dashboard_service.py` | Queries de nulos + card de alertas | Alta |
| **6.1 Testes** | 144 testes cobrindo exatamente as áreas priorizadas (auth, RBAC, AD, movimentações, importação, localização, equipamentos, auditoria via RBAC/403) | **Já implementado** | `tests/` 3.167 linhas | — | — |
| **6.2 Backup/restauração** | Nada no código | Não implementado | grep "backup" = vazio | É procedimento operacional (SQLite = copiar arquivo), não funcionalidade | Não implementar agora |
| **6.3 Auditoria x logs** | Separação conceitual existe; logs técnicos pontuais via `logging.getLogger` (ad_service, ad_ldap, web) sem configuração central/arquivo/rotação | Parcial | `ad_ldap.py:36`, `ad_service.py:41`, `routes.py:109` | Configuração de logging estruturado | Média |
| **6.4 Health check** | `/health` verifica apenas aplicação | Parcial | `main.py:90–92` | Verificação de banco e AD | Média |

---

## 5. Melhorias que NÃO precisam ser implementadas

1. **1.5 QR Code** — completo (ficha + termo), já usa a rota proposta `/assets/{id}`.
2. **1.6 Controle patrimonial rigoroso** — todos os 6 requisitos já estão no modelo e no serviço de movimentação.
3. **2.1 AD + RBAC** — implementação coincide ponto a ponto com o fluxo proposto no documento, inclusive a regra "autenticação AD não concede acesso".
4. **2.2 Auditoria robusta** — todos os eventos e campos solicitados já são registrados.
5. **2.3 Proteção contra exclusões** — atendida por design: não há exclusão física exposta em nenhuma camada; desligamento de bem é movimento auditado (`BAIXA_DESCARTE`) e colaborador só é inativado (`is_active`).
6. **3.1 Importação CSV** — o fluxo de 7 etapas proposto já é o comportamento atual, incluindo o resumo com válidos/duplicados/erros.
7. **4.2 Estados vazios** — já há componentes orientados em todas as listagens.
8. **6.1 Testes automatizados** — 144 testes cobrem todas as 8 áreas priorizadas pelo documento.

---

## 6. Melhorias que precisam de aprimoramento

- **1.4 Histórico completo** — existe (timeline imutável); vale agregar a auditoria cadastral do bem na mesma visão. Impacto: somente leitura, sem risco; consultas a `audit_log` por `resource_id`.
- **1.3 Filtros avançados** — backend de movimentações **já suporta** os filtros (`MovementFilter`); falta apenas expor na UI. Impacto: frontend-only, risco mínimo.
- **3.2 Exportação** — CSV já existe; aplicar os filtros da tela à exportação é baixo impacto (passar params a `ReportService`). Excel/PDF exigiriam dependências novas (openpyxl/reportlab) — avaliar custo/benefício.
- **4.1 Feedback visual** — padronizar consumo de `?created=true`/`?moved=true` já emitidos pelos redirects. Impacto: templates apenas.
- **1.1 Dashboard** — adicionar distribuição por local/setor (queries simples de agrupamento já existentes como padrão em `get_stats`).
- **6.4 Health check** — acrescentar check de banco (SELECT 1) e AD (quando habilitado) ao `/health` existente.
- **6.3 Logs técnicos** — configurar handlers/rotação centralizados; o código já usa `logging` corretamente, falta a configuração.

---

## 7. Melhorias realmente não implementadas

1. **3.3 Impressão de etiquetas** (QR + tombamento + descrição + setor/local, em lote).
2. **3.4 Ações em lote**.
3. **4.3 Preservação de filtros** ao voltar da ficha.
4. **5.2 Indicadores de inconsistência** (painel de "sem localização / sem responsável").
5. **6.2 Backup e restauração** (procedimento operacional, não funcionalidade).
6. Partes de **1.1/1.2/5.1** detalhadas na tabela da seção 4 (busca global unificada; relatórios por setor/localização).

---

## 8. Problemas Técnicos Encontrados *(registrados — não corrigidos)*

1. **CSRF ausente nos formulários web** — POSTs dependem apenas de cookie de sessão (`SameSite=Lax` mitiga, mas não substitui token CSRF).
2. **`term_code` gerado por COUNT+1** (`movement_service.py:~128`) — risco de colisão sob concorrência (SQLite mitiga parcialmente).
3. **3.333 DeprecationWarnings** de `datetime.utcnow()` na suíte (Python 3.14) — dívida técnica.
4. **`term_signed`** existe no modelo/schema mas não há fluxo que o altere — campo morto.
5. **README desatualizado** — afirma "106 testes"; são 144.
6. **`.gitignore` ignora `tests/`** — a suíte de testes não é versionada.
7. **`__pycache__/*.pyc` e `app/.config.py.un~` versionados no git** (331 arquivos rastreados incluem binários).
8. **`APP_HOST` com IP fixo hardcoded** (`config.py:16`, default `10.39.0.16`) — específico de ambiente no código.
9. **`seed_demo.py` faz `drop_all`** — destrutivo se executado apontando para o banco real.
10. **Operator_name padrões fixos** ("Operador"/"Sistema") em alguns fluxos web em vez do usuário autenticado.
11. **`/health` não valida banco/AD** — falha de dependência não é detectada.

---

## 9. Riscos de Alteração

- **`movement_service.create_movement`** — coração da integridade patrimonial; qualquer alteração exige testes de todos os 8 tipos de movimento.
- **`permission_service.py`** — catálogo/perfis alimentam seed idempotente e telas de admin; mudanças afetam RBAC inteiro.
- **`ad_service.py`** — fluxo de provisionamento cuidadosamente desenhado para não criar nada sem mapeamento; regressões aqui criariam usuários/fábricas de duplicados.
- **Migrações leves em `database.py`** — padrão correto para SQLite, mas ALTERs novos devem seguir o mesmo padrão idempotente.
- **Templates base/`main.js`** — compartilhados por todas as páginas; navbar/tema têm testes de regressão que devem acompanhar mudanças.

---

## 10. Roadmap Recomendado *(apenas recomendação)*

1. **Segurança:** CSRF nos formulários web (registro nº 1 do diagnóstico).
2. **Integridade:** gerar `term_code` de forma concorrência-segura; (opcional) índice em `audit_log.resource_id` para suportar histórico por bem.
3. **Auditoria:** logging técnico configurado (rotação/arquivo).
4. **Controle patrimonial:** painel de inconsistências (5.2) + indicadores no dashboard (1.1).
5. **Produtividade:** exportação CSV filtrada (3.2); expor filtros já suportados pela API na UI (1.3); preservação de filtros (4.3); feedback pós-operação (4.1).
6. **Usabilidade:** busca global (1.2) + Ctrl+K (4.4) em sequência.
7. **Relatórios:** visões por setor, localização, sem responsável/localização, manutenções (5.1).
8. **Visual:** etiquetas com QR (3.3) por último — depende das anteriores e de definição de layout de impressão.

---

## 11. Melhorias que NÃO devem ser feitas agora

- **3.4 Ações em lote** — maior complexidade do sistema (seleção, RBAC por operação, auditoria em lote) sem dor demonstrada ainda.
- **3.2 Excel/PDF server-side** — exigiria novas dependências; impressão via navegador já cobre o termo; só investir se houver demanda real.
- **6.2 Backup/restauração** — é procedimento operacional (copiar/validar o arquivo SQLite), não código de aplicação; documentar externamente.
- **Refazer interface / trocar framework / refatoração ampla / migrar banco** — o próprio documento lista como não-prioridade, e a análise confirma: a base é coesa e não justifica.

---

## 12. Conclusão

- **Pronto:** núcleo patrimonial completo (bens, movimentações, custódia, manutenções, termos, QR), segurança de ponta a ponta (AD+RBAC+sessões+lockout), auditoria robusta, importação com prévia, testes (144), estados vazios.
- **Parcialmente pronto:** dashboard (falta por local/setor e alertas), busca (só em bens), filtros (web abaixo do que a API já suporta), exportação (sem filtro/Excel/PDF), relatórios (3 de ~9 visões), health check e logs técnicos.
- **Falta de fato:** etiquetas, lote, preservação de filtros, painel de inconsistências, backup (operacional).
- **Priorizar:** painel de inconsistências → exportação filtrada → filtros de período na UI → CSRF → logging → busca global.
- **Descartar/adiar:** lote, Excel/PDF, refatorações amplas.
- **Próxima etapa recomendada:** implementar o **painel de indicadores de inconsistência (5.2)** — é o item de maior valor patrimonial pendente, de risco baixo (somente leitura) e que aproveita os constraints de unicidade já existentes.

---

## Validação de Integridade da Análise

A análise foi conduzida exclusivamente por leitura. Durante sua execução:

- nenhum arquivo foi alterado, criado, excluído ou renomeado;
- nenhum código Python/HTML/CSS/JS foi modificado;
- nenhum banco de dados, tabela ou registro foi alterado;
- nenhuma migração foi executada;
- nenhuma configuração ou variável de ambiente foi alterada;
- nenhuma dependência foi instalada ou removida;
- nenhum commit ou operação de escrita no Git foi realizada (`git status` limpo ao final).

**Nota:** este documento é o único arquivo criado nesta etapa, a pedido do usuário; nenhuma outra parte do sistema foi tocada.
