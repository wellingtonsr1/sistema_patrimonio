"""
Central de Ajuda / Manual do SisPatrimônio Pro.

Este módulo concentra TODO o conteúdo da documentação (artigos, categorias
e perguntas frequentes) em um único lugar, facilitando a manutenção: para
adicionar um novo artigo basta criar um item na lista ARTICLES e, se
desejado, referenciá-lo em uma categoria.

Regras de conteúdo:
- Documenta SOMENTE funcionalidades realmente existentes no sistema.
- Terminologia consistente com a interface (Equipamentos/Patrimônio,
  Fluxo & Movimentação, Manutenções, Colaboradores, Locais, Relatórios...).
- `audience`: "user" (qualquer usuário autenticado) ou "admin" (exige
  permissão administrativa para visualizar).

Seções de um artigo (campo `sections`):
- {"heading": ..., "body": ...}   → parágrafos (separados por linha em branco)
- {"heading": ..., "steps": [...]} → lista numerada (passo a passo)
- {"heading": ..., "note": ...}    → destaque/aviso
"""

from typing import Dict, List, Optional

# ============================================================================
# ARTIGOS
# ============================================================================

ARTICLES: List[Dict] = [
    # ------------------------------------------------------------------ #
    # PRIMEIROS PASSOS
    # ------------------------------------------------------------------ #
    {
        "id": "o-que-e-o-sistema",
        "title": "O que é o SisPatrimônio Pro",
        "module": "Primeiros Passos",
        "icon": "bi-box-seam",
        "audience": "user",
        "summary": "Visão geral do sistema de gestão patrimonial e dos módulos disponíveis.",
        "keywords": ["sistema", "visão geral", "módulos", "patrimônio", "introdução", "sobre"],
        "sections": [
            {
                "heading": "O que o sistema faz",
                "body": (
                    "O SisPatrimônio Pro é o sistema de gestão patrimonial do órgão. Ele controla o "
                    "cadastro de equipamentos (computadores, notebooks, monitores, impressoras, servidores "
                    "e demais bens), a movimentação entre setores e responsáveis, as manutenções e os "
                    "relatórios do acervo.\n\n"
                    "Tudo o que acontece com um bem — entrada, entrega, transferência, manutenção, "
                    "devolução ou baixa — fica registrado no histórico (linha do tempo) do equipamento, "
                    "garantindo rastreabilidade total."
                ),
            },
            {
                "heading": "Módulos do sistema",
                "steps": [
                    "Dashboard — visão geral com indicadores do acervo.",
                    "Equipamentos — cadastro, consulta, detalhes e importação em massa.",
                    "Fluxo & Movimentação — transferências, entregas, devoluções e baixas.",
                    "Manutenções — ordens de serviço e reparos.",
                    "Colaboradores — cadastro dos responsáveis/custodiantes dos bens.",
                    "Locais — prédios, salas e departamentos.",
                    "Relatórios — inventário, trilha de auditoria e relação de colaboradores.",
                ],
            },
            {
                "heading": "Quem pode acessar o quê",
                "body": (
                    "O acesso é controlado por perfis. Cada perfil possui um conjunto de permissões, "
                    "por exemplo visualizar, cadastrar ou editar. Um usuário só enxerga os menus e "
                    "executa as ações para as quais possui permissão. Se você não vê um menu ou botão, "
                    "procure o administrador do sistema para verificar seu perfil de acesso."
                ),
            },
        ],
    },
    {
        "id": "entrar-e-sair",
        "title": "Como entrar e sair do sistema",
        "module": "Primeiros Passos",
        "icon": "bi-box-arrow-in-right",
        "audience": "user",
        "summary": "Login, logout, sessão e troca de senha.",
        "keywords": ["login", "logar", "entrar", "sair", "logout", "senha", "acesso"],
        "sections": [
            {
                "heading": "Entrar no sistema",
                "steps": [
                    "Acesse o endereço do sistema no navegador (ex.: http://localhost:8000).",
                    "Informe seu usuário (login) e sua senha.",
                    "Clique em Entrar.",
                ],
                "body": (
                    "Se você ainda não tem usuário, o administrador do sistema deve criá-lo e atribuir "
                    "seu perfil de acesso."
                ),
            },
            {
                "heading": "Sair do sistema",
                "body": (
                    "Clique no seu usuário (canto superior direito) e depois em Sair. A sessão é "
                    "encerrada no servidor e o acesso é revogado imediatamente."
                ),
            },
            {
                "heading": "Trocar minha senha",
                "steps": [
                    "Clique no seu usuário (canto superior direito).",
                    "Escolha Alterar senha.",
                    "Informe a senha atual e a nova senha (mínimo de 8 caracteres).",
                    "Confirme e clique em Alterar Senha.",
                ],
                "note": (
                    "Após a troca, você precisará fazer login novamente. Se esquecer a senha, o "
                    "administrador pode redefini-la."
                ),
            },
            {
                "heading": "Proteção contra tentativas de acesso",
                "body": (
                    "Após várias tentativas de login com senha incorreta, a conta é bloqueada "
                    "temporariamente. Aguarde alguns minutos ou procure o administrador."
                ),
            },
        ],
    },
    {
        "id": "conhecendo-a-interface",
        "title": "Conhecendo a interface",
        "module": "Primeiros Passos",
        "icon": "bi-layout-sidebar",
        "audience": "user",
        "summary": "Menu lateral, cabeçalho, dashboard e tema claro/escuro.",
        "keywords": ["interface", "menu", "navegação", "dashboard", "tema", "escuro", "claro"],
        "sections": [
            {
                "heading": "Como navegar",
                "body": (
                    "O menu no topo (e o menu lateral no celular) dá acesso aos módulos. Cada item do "
                    "menu aparece de acordo com o seu perfil de permissões — itens sem permissão não "
                    "são exibidos.\n\n"
                    "Na maioria das listas (equipamentos, movimentações) há uma caixa de pesquisa e "
                    "filtros para localizar rapidamente o que você procura."
                ),
            },
            {
                "heading": "Dashboard",
                "body": (
                    "O Dashboard é a primeira tela após o login. Ele mostra indicadores do acervo: "
                    "total de equipamentos, valor total, bens em uso, disponíveis em estoque, em "
                    "manutenção e as movimentações mais recentes."
                ),
            },
            {
                "heading": "Tema claro e escuro",
                "body": (
                    "Use o botão de lua/sol no canto superior direito para alternar entre os temas. "
                    "A preferência fica salva no seu navegador."
                ),
            },
        ],
    },

    # ------------------------------------------------------------------ #
    # PATRIMÔNIO / EQUIPAMENTOS
    # ------------------------------------------------------------------ #
    {
        "id": "cadastrar-equipamento",
        "title": "Como cadastrar um equipamento",
        "module": "Patrimônio & Equipamentos",
        "icon": "bi-laptop",
        "audience": "user",
        "summary": "Passo a passo para tombar um novo bem no patrimônio.",
        "keywords": ["cadastrar", "novo", "tombamento", "equipamento", "patrimônio", "bem", "tag"],
        "sections": [
            {
                "heading": "Antes de começar",
                "body": (
                    "Você precisa da permissão de cadastro de patrimônio. Tenha em mãos os dados do "
                    "bem: número de tombamento (tag), descrição, categoria, marca/modelo, número de "
                    "série e, se houver, nota fiscal e valor."
                ),
            },
            {
                "heading": "Passo a passo",
                "steps": [
                    "No menu, acesse Equipamentos.",
                    "Clique em Novo Equipamento.",
                    "Preencha o Nº de Tombamento (código único, ex.: PAT-00125).",
                    "Informe o nome/descrição e a categoria do bem.",
                    "Preencha marca, modelo, número de série e especificações.",
                    "Informe os dados fiscais (data de compra, valor, nota fiscal, fornecedor, garantia).",
                    "Defina a localização inicial e, se for o caso, o colaborador responsável (cautela).",
                    "Revise as informações e clique em Concluir Tombamento.",
                ],
            },
            {
                "heading": "O que acontece ao salvar",
                "body": (
                    "O bem é registrado com status Disponível (em estoque) ou Em uso (se informado um "
                    "responsável), e a entrada é gravada automaticamente no histórico do equipamento."
                ),
            },
        ],
    },
    {
        "id": "consultar-equipamentos",
        "title": "Como consultar e filtrar equipamentos",
        "module": "Patrimônio & Equipamentos",
        "icon": "bi-search",
        "audience": "user",
        "summary": "Busca por texto e filtros por status, categoria, local e responsável.",
        "keywords": ["consultar", "pesquisar", "buscar", "filtrar", "lista", "equipamentos", "status", "categoria"],
        "sections": [
            {
                "heading": "Como funciona",
                "body": (
                    "Na tela Equipamentos, digite na caixa de busca qualquer termo — tombamento, nome, "
                    "marca, modelo ou número de série — e pressione Filtrar.\n\n"
                    "Use os filtros ao lado para refinar por status (Disponível, Em uso, Em manutenção, "
                    "Baixado), categoria, local ou responsável."
                ),
            },
            {
                "heading": "Significado dos status",
                "steps": [
                    "DISPONIVEL — o bem está no estoque/almoxarifado, sem responsável.",
                    "EM_USO — o bem está alocado a um colaborador ou setor.",
                    "EM_MANUTENCAO — o bem está em reparo técnico.",
                    "EM_TRANSITO — o bem está em transporte/transferência.",
                    "BAIXADO — o bem foi descartado, leiloado ou perdido (baixa definitiva).",
                ],
            },
        ],
    },
    {
        "id": "detalhes-do-bem",
        "title": "Como visualizar os detalhes de um bem",
        "module": "Patrimônio & Equipamentos",
        "icon": "bi-eye",
        "audience": "user",
        "summary": "Ficha técnica, custódia, localização, depreciação, QR Code e linha do tempo.",
        "keywords": ["detalhes", "ficha", "histórico", "linha do tempo", "timeline", "depreciação", "qr", "código"],
        "sections": [
            {
                "heading": "Abrindo o detalhe",
                "body": (
                    "Clique sobre o tombamento ou o nome do equipamento na lista para abrir a página de "
                    "detalhes do bem."
                ),
            },
            {
                "heading": "O que a tela mostra",
                "steps": [
                    "Custódia e localização atual — quem é o responsável e onde o bem está.",
                    "Ficha técnica e dados fiscais — marca, modelo, série, nota fiscal, garantia.",
                    "Contabilidade e depreciação — valor de aquisição e valor contábil atual.",
                    "Etiqueta QR Code — código para identificação/impressão do bem.",
                    "Trilha de fluxo — todo o histórico de movimentações do bem, do mais recente ao mais antigo.",
                ],
            },
            {
                "heading": "Imprimir o termo",
                "body": (
                    "Quando uma movimentação gera termo (alocação ou devolução), o link Imprimir Termo "
                    "abre o documento pronto para impressão e assinatura."
                ),
            },
        ],
    },
    {
        "id": "importar-equipamentos",
        "title": "Como importar equipamentos em massa (CSV)",
        "module": "Patrimônio & Equipamentos",
        "icon": "bi-filetype-csv",
        "audience": "user",
        "summary": "Importação de vários bens de uma vez a partir de um arquivo CSV.",
        "keywords": ["importar", "csv", "planilha", "massa", "vários", "equipamentos"],
        "sections": [
            {
                "heading": "Passo a passo",
                "steps": [
                    "Na tela Equipamentos, clique em Importar CSV.",
                    "Selecione um arquivo .csv com os dados dos bens.",
                    "O sistema exibe uma pré-visualização antes de gravar.",
                    "Confirme a importação. Bens duplicados (mesmo tombamento) podem ser ignorados.",
                ],
            },
            {
                "heading": "Importante",
                "note": (
                    "A importação exige permissão de cadastro de patrimônio. A pré-visualização permite "
                    "conferir os dados antes de confirmar; erros de leitura do arquivo são exibidos "
                    "para correção."
                ),
            },
        ],
    },
    {
        "id": "corrigir-informacoes",
        "title": "Como corrigir informações cadastrais de um bem",
        "module": "Patrimônio & Equipamentos",
        "icon": "bi-pencil",
        "audience": "user",
        "summary": "Correção de dados de cadastro (técnica, fiscal e observações).",
        "keywords": ["corrigir", "editar", "alterar", "dados", "cadastro", "erro"],
        "sections": [
            {
                "heading": "Correção de dados cadastrais",
                "body": (
                    "A alteração de dados cadastrais (marca, modelo, nota fiscal, observações, estado "
                    "de conservação) é feita pela API do sistema, para usuários com permissão de edição "
                    "de patrimônio (ex.: perfil Gestor de TI ou Patrimônio).\n\n"
                    "Para correções em massa, utilize a reimportação CSV. Mudanças de responsável, "
                    "localização ou situação devem ser feitas por uma movimentação (ver Fluxo & "
                    "Movimentação), nunca por edição direta."
                ),
            },
            {
                "heading": "O que NÃO deve ser editado",
                "note": (
                    "Responsável, localização e status não se alteram por edição: eles mudam por "
                    "movimentação, para que tudo fique registrado no histórico do bem."
                ),
            },
        ],
    },

    # ------------------------------------------------------------------ #
    # FLUXO & MOVIMENTAÇÃO
    # ------------------------------------------------------------------ #
    {
        "id": "movimentar-equipamento",
        "title": "Como movimentar um equipamento",
        "module": "Fluxo & Movimentação",
        "icon": "bi-arrow-left-right",
        "audience": "user",
        "summary": "Entregar, transferir, devolver ou dar baixa em um bem, com registro no histórico.",
        "keywords": ["movimentar", "transferir", "alocar", "entregar", "devolver", "baixa", "responsável", "setor"],
        "sections": [
            {
                "heading": "Quando usar",
                "body": (
                    "Utilize uma movimentação sempre que um equipamento mudar de setor, localização ou "
                    "responsável, for enviado para manutenção, devolvido ao estoque ou der baixa. O "
                    "sistema registra tudo no histórico para manter a rastreabilidade do patrimônio."
                ),
            },
            {
                "heading": "Passo a passo",
                "steps": [
                    "Acesse Fluxo & Movimentação e clique em Nova Movimentação (ou, nos detalhes do bem, em Movimentar).",
                    "Selecione o equipamento.",
                    "Escolha o tipo de movimentação (ver artigo Tipos de movimentação).",
                    "Informe o destino: novo colaborador (cautela) e/ou novo local.",
                    "Descreva o motivo/justificativa.",
                    "Confirme e Grave.",
                ],
            },
            {
                "heading": "Termo de responsabilidade",
                "body": (
                    "Em alocações e devoluções, o sistema gera automaticamente um termo de "
                    "responsabilidade/cautela com os dados do bem e do colaborador, pronto para "
                    "impressão e assinatura."
                ),
            },
        ],
    },
    {
        "id": "tipos-de-movimentacao",
        "title": "Entendendo os tipos de movimentação",
        "module": "Fluxo & Movimentação",
        "icon": "bi-diagram-3",
        "audience": "user",
        "summary": "Explicação amigável de cada tipo de movimentação disponível.",
        "keywords": ["tipos", "alocação", "cautela", "transferência", "devolução", "baixa", "descarte", "manutenção"],
        "sections": [
            {
                "heading": "Tipos disponíveis",
                "steps": [
                    "Alocação a Colaborador — entrega do equipamento a um funcionário (cautela).",
                    "Transferência de Setor/Filial — mudança de sala, prédio, filial ou departamento.",
                    "Devolução ao Estoque — recolhimento do bem (ex.: desligamento ou troca).",
                    "Baixa / Descarte Definitivo — obsolescência, perda, quebra ou leilão.",
                    "Envio/Retorno de Manutenção — saída e reintegração do bem após reparo.",
                    "Atualização de Estado — vistoria que altera a condição de conservação.",
                ],
            },
            {
                "heading": "Qual tipo escolher",
                "body": (
                    "Regra prática: mudou o responsável? Alocação. Mudou o local/setor? Transferência. "
                    "O bem voltou para o almoxarifado? Devolução ao estoque. O bem não será mais usado? "
                    "Baixa/descarte."
                ),
            },
        ],
    },
    {
        "id": "historico-do-bem",
        "title": "Como consultar o histórico de um bem",
        "module": "Fluxo & Movimentação",
        "icon": "bi-clock-history",
        "audience": "user",
        "summary": "Linha do tempo do bem e relatório de trilha de auditoria.",
        "keywords": ["histórico", "linha do tempo", "timeline", "trilha", "auditoria", "movimentações"],
        "sections": [
            {
                "heading": "Histórico individual",
                "body": (
                    "Abra os detalhes do bem e role até a Trilha de Fluxo & Movimentações. Cada evento "
                    "mostra data/hora, tipo, origem, destino, motivo e quem registrou."
                ),
            },
            {
                "heading": "Histórico geral",
                "body": (
                    "O relatório Trilha de Auditoria (menu Relatórios) consolida todas as movimentações "
                    "do sistema, com filtros por tipo, período, local e colaborador, e pode ser "
                    "exportado em CSV."
                ),
            },
        ],
    },

    # ------------------------------------------------------------------ #
    # MANUTENÇÕES
    # ------------------------------------------------------------------ #
    {
        "id": "abrir-ordem-servico",
        "title": "Como abrir uma ordem de serviço (manutenção)",
        "module": "Manutenções",
        "icon": "bi-wrench",
        "audience": "user",
        "summary": "Registrar o envio de um equipamento para reparo.",
        "keywords": ["manutenção", "ordem de serviço", "os", "reparo", "defeito", "preventiva", "corretiva"],
        "sections": [
            {
                "heading": "Passo a passo",
                "steps": [
                    "Acesse Manutenções e clique em Abrir Nova OS.",
                    "Selecione o equipamento.",
                    "Escolha o tipo: Preventiva, Corretiva ou Upgrade.",
                    "Informe a assistência/técnico responsável.",
                    "Descreva o defeito ou escopo do serviço.",
                    "Informe o custo estimado (se houver).",
                    "Clique em Abrir OS.",
                ],
            },
            {
                "heading": "O que acontece",
                "body": (
                    "O equipamento passa automaticamente para o status EM MANUTENÇÃO e a saída é "
                    "registrada no histórico do bem."
                ),
            },
        ],
    },
    {
        "id": "finalizar-manutencao",
        "title": "Como finalizar uma manutenção",
        "module": "Manutenções",
        "icon": "bi-check2-circle",
        "audience": "user",
        "summary": "Registrar a solução aplicada e concluir a ordem de serviço.",
        "keywords": ["finalizar", "concluir", "solução", "peças", "custo", "manutenção"],
        "sections": [
            {
                "heading": "Passo a passo",
                "steps": [
                    "Na lista de Manutenções, localize a OS em andamento.",
                    "Clique em Concluir.",
                    "Descreva a solução aplicada e os custos finais.",
                    "Confirme a finalização.",
                ],
            },
            {
                "heading": "O que acontece",
                "body": (
                    "A OS é marcada como concluída, o status do equipamento retorna para DISPONIVEL e o "
                    "retorno da manutenção é registrado no histórico do bem."
                ),
            },
        ],
    },

    # ------------------------------------------------------------------ #
    # COLABORADORES & LOCAIS
    # ------------------------------------------------------------------ #
    {
        "id": "cadastrar-colaboradores",
        "title": "Como cadastrar colaboradores (custodiantes)",
        "module": "Colaboradores & Locais",
        "icon": "bi-people",
        "audience": "user",
        "summary": "Cadastro de colaboradores, importação em massa e consulta de bens sob custódia.",
        "keywords": ["colaborador", "funcionário", "custodiante", "responsável", "matrícula", "cadastrar"],
        "sections": [
            {
                "heading": "Passo a passo",
                "steps": [
                    "Acesse Colaboradores e clique em Cadastrar Colaborador.",
                    "Informe matrícula, nome, e-mail e CPF.",
                    "Informe o cargo e o departamento/setor.",
                    "Clique em Salvar.",
                ],
            },
            {
                "heading": "Importação em massa",
                "body": (
                    "Também é possível importar colaboradores via arquivo CSV, com pré-visualização "
                    "antes de confirmar (exige permissão de cadastro de colaboradores)."
                ),
            },
            {
                "heading": "Bens sob custódia",
                "body": (
                    "Na página de detalhes do colaborador, a seção Equipamentos sob Custódia lista "
                    "todos os bens atualmente alocados àquela pessoa."
                ),
            },
        ],
    },
    {
        "id": "cadastrar-locais",
        "title": "Como cadastrar locais e departamentos",
        "module": "Colaboradores & Locais",
        "icon": "bi-geo-alt",
        "audience": "user",
        "summary": "Cadastro de unidades, prédios, andares, salas e departamentos.",
        "keywords": ["local", "departamento", "setor", "prédio", "andar", "sala", "filial"],
        "sections": [
            {
                "heading": "Passo a passo",
                "steps": [
                    "Acesse Locais e clique em Cadastrar Novo Local.",
                    "Informe o nome do local, a filial e o departamento.",
                    "Preencha prédio, andar e sala quando aplicável.",
                    "Informe o gestor responsável e uma descrição, se desejar.",
                    "Clique em Salvar.",
                ],
            },
            {
                "heading": "Ver bens por local",
                "body": (
                    "Na lista de locais, o botão Ver Bens abre a listagem de equipamentos filtrada "
                    "pelaquele local."
                ),
            },
        ],
    },

    # ------------------------------------------------------------------ #
    # RELATÓRIOS & EXPORTAÇÕES
    # ------------------------------------------------------------------ #
    {
        "id": "relatorios",
        "title": "Relatórios disponíveis",
        "module": "Relatórios & Exportações",
        "icon": "bi-file-earmark-text",
        "audience": "user",
        "summary": "Inventário geral, trilha de auditoria e relação de colaboradores.",
        "keywords": ["relatórios", "inventário", "trilha", "auditoria", "colaboradores", "imprimir"],
        "sections": [
            {
                "heading": "Quais relatórios existem",
                "steps": [
                    "Inventário Geral — listagem analítica de todos os bens com depreciação e valor contábil.",
                    "Trilha de Auditoria — todas as movimentações do acervo, com origem, destino e operador.",
                    "Relação de Colaboradores — colaboradores e a quantidade de bens sob custódia de cada um.",
                ],
            },
            {
                "heading": "Como gerar",
                "body": (
                    "Acesse o menu Relatórios e escolha o relatório desejado. Todos podem ser impressos "
                    "pelo botão Imprimir do navegador."
                ),
            },
            {
                "heading": "Acesso",
                "note": (
                    "A visualização de relatórios exige permissão relatorios.visualizar; a exportação "
                    "em CSV exige permissão adicional de exportação."
                ),
            },
        ],
    },
    {
        "id": "exportar-csv",
        "title": "Como exportar os dados em CSV",
        "module": "Relatórios & Exportações",
        "icon": "bi-download",
        "audience": "user",
        "summary": "Baixar inventário, movimentações e colaboradores em arquivo CSV.",
        "keywords": ["exportar", "csv", "baixar", "download", "planilha", "dados"],
        "sections": [
            {
                "heading": "Onde exportar",
                "body": (
                    "Os relatórios Inventário Geral, Trilha de Auditoria e Relação de Colaboradores "
                    "possuem o botão Baixar CSV. Os arquivos são compatíveis com planilhas eletrônicas."
                ),
            },
            {
                "heading": "Permissão",
                "note": (
                    "A exportação exige permissão específica (relatorios.exportar). Se o botão não "
                    "aparecer, seu perfil não possui essa permissão."
                ),
            },
        ],
    },

    # ------------------------------------------------------------------ #
    # ADMINISTRAÇÃO
    # ------------------------------------------------------------------ #
    {
        "id": "gerenciar-usuarios",
        "title": "Como criar e gerenciar usuários (administração)",
        "module": "Administração",
        "icon": "bi-person-gear",
        "audience": "admin",
        "summary": "Criar usuários, atribuir perfis, bloquear e redefinir senhas.",
        "keywords": ["usuários", "criar", "perfis", "bloquear", "desbloquear", "senha", "admin"],
        "sections": [
            {
                "heading": "Acessando a administração",
                "body": (
                    "No menu Administração, a tela Usuários lista todos os usuários com busca, status, "
                    "perfis e último acesso."
                ),
            },
            {
                "heading": "Criar um usuário",
                "steps": [
                    "Clique em Novo Usuário.",
                    "Informe usuário (login), senha (mínimo 8 caracteres), nome e e-mail.",
                    "Marque os perfis de acesso — comece com o mínimo necessário (menor privilégio).",
                    "Clique em Criar Usuário.",
                ],
            },
            {
                "heading": "Editar, bloquear e redefinir senha",
                "steps": [
                    "Editar — altera nome, e-mail, situação da conta e os perfis atribuídos.",
                    "Bloquear/Desbloquear — o acesso é revogado imediatamente; sessões ativas são invalidadas.",
                    "Redefinir Senha — define nova senha e exige novo login do usuário.",
                ],
            },
            {
                "heading": "Regras de segurança",
                "note": (
                    "Um usuário não pode bloquear a si mesmo, e o sistema não permite remover ou "
                    "desativar o último administrador ativo — isso evita deixar o sistema sem "
                    "administração."
                ),
            },
        ],
    },
    {
        "id": "perfis-e-permissoes",
        "title": "Como criar e editar perfis e permissões (administração)",
        "module": "Administração",
        "icon": "bi-shield-lock",
        "audience": "admin",
        "summary": "Entender e ajustar os perfis de acesso e suas permissões granulares.",
        "keywords": ["perfis", "permissões", "papéis", "acesso", "rbac", "admin"],
        "sections": [
            {
                "heading": "O que são perfis",
                "body": (
                    "Um perfil agrupa permissões. Os perfis padrão do sistema são Administrador, "
                    "Gestor de TI, Técnico de TI, Patrimônio, Almoxarifado, Auditor e Consulta. Perfis "
                    "padrão podem ser editados, mas não excluídos."
                ),
            },
            {
                "heading": "Criar ou editar um perfil",
                "steps": [
                    "Acesse Administração → Perfis & Permissões.",
                    "Clique em Novo Perfil (ou Editar em um perfil existente).",
                    "Informe o nome e a descrição.",
                    "Marque as permissões desejadas, agrupadas por módulo.",
                    "Clique em Salvar Perfil.",
                ],
            },
            {
                "heading": "Como as permissões funcionam",
                "body": (
                    "Cada permissão segue o padrão módulo.ação, como patrimonio.visualizar ou "
                    "patrimonio.criar. O usuário só executa uma ação se possuir a permissão "
                    "correspondente — por isso, atribua sempre o menor conjunto de permissões "
                    "necessário para a função."
                ),
            },
        ],
    },
    {
        "id": "auditoria",
        "title": "Como consultar a trilha de auditoria (administração)",
        "module": "Administração",
        "icon": "bi-journal-check",
        "audience": "admin",
        "summary": "Consultar o registro de logins, ações e acessos negados do sistema.",
        "keywords": ["auditoria", "trilha", "log", "registro", "ip", "ações", "admin"],
        "sections": [
            {
                "heading": "O que a auditoria registra",
                "body": (
                    "O sistema registra automaticamente logins, falhas de login, logout, criações e "
                    "alterações, bloqueios, redefinições de senha, mudanças de perfis, movimentações "
                    "patrimoniais e tentativas de acesso sem permissão."
                ),
            },
            {
                "heading": "Como consultar",
                "steps": [
                    "Acesse Administração → Auditoria.",
                    "Use os filtros por módulo, ação, resultado ou texto de busca.",
                    "Nos registros com alteração de dados, abra Detalhes para ver os dados anteriores e posteriores.",
                ],
            },
            {
                "heading": "Importante",
                "note": (
                    "A trilha de auditoria é somente leitura: não há como editar ou apagar registros "
                    "pela interface. A consulta exige permissão auditoria.visualizar."
                ),
            },
        ],
    },
]

# ============================================================================
# PERGUNTAS FREQUENTES (FAQ)
# ============================================================================

FAQ: List[Dict] = [
    {
        "question": "Como localizar um equipamento?",
        "answer": (
            "Acesse Equipamentos e use a caixa de busca (tombamento, nome, marca, modelo ou número de "
            "série) ou os filtros de status, categoria, local e responsável. Nos detalhes do bem você "
            "vê a localização e o responsável atuais."
        ),
    },
    {
        "question": "Como alterar o responsável de um equipamento?",
        "answer": (
            "Use uma movimentação: abra o bem e clique em Movimentar, escolha Alocação a Colaborador "
            "(ou Transferência de Setor/Filial), informe o novo responsável e o motivo. O histórico "
            "registra a mudança automaticamente."
        ),
    },
    {
        "question": "Como consultar o histórico de um bem?",
        "answer": (
            "Abra os detalhes do equipamento e veja a Trilha de Fluxo & Movimentações. Para uma visão "
            "geral de tudo, use o relatório Trilha de Auditoria no menu Relatórios."
        ),
    },
    {
        "question": "Como registrar uma manutenção?",
        "answer": (
            "Acesse Manutenções e clique em Abrir Nova OS. Selecione o equipamento, o tipo de "
            "manutenção, descreva o defeito e salve. O bem passa automaticamente para EM MANUTENÇÃO. "
            "Ao finalizar o reparo, use Concluir na lista de manutenções."
        ),
    },
    {
        "question": "Como gerar um relatório?",
        "answer": (
            "No menu Relatórios escolha Inventário Geral, Trilha de Auditoria ou Relação de "
            "Colaboradores. Todos podem ser impressos pelo botão Imprimir."
        ),
    },
    {
        "question": "Como exportar os dados?",
        "answer": (
            "Os relatórios possuem o botão Baixar CSV, que gera um arquivo compatível com planilhas. "
            "A exportação exige permissão específica no seu perfil."
        ),
    },
    {
        "question": "O que fazer quando um equipamento não é encontrado na busca?",
        "answer": (
            "Confira a grafia do tombamento e limpe os filtros aplicados. Verifique se o bem não está "
            "com status Baixado (filtro Status). Se ainda assim não aparecer, o seu perfil pode não "
            "ter acesso de visualização ao módulo — procure o administrador."
        ),
    },
    {
        "question": "Como corrigir uma informação cadastrada incorretamente?",
        "answer": (
            "Correções de dados cadastrais são feitas pela API do sistema (para perfis com permissão "
            "de edição) ou pela reimportação CSV. Responsável, localização e status não devem ser "
            "editados diretamente: use uma movimentação para manter o histórico correto."
        ),
    },
    {
        "question": "Esqueci minha senha. O que faço?",
        "answer": (
            "Procure o administrador do sistema, que pode redefinir sua senha pela tela "
            "Administração → Usuários. Você poderá trocá-la depois em Alterar senha, no menu do seu "
            "usuário."
        ),
    },
    {
        "question": "Por que não vejo alguns menus ou botões?",
        "answer": (
            "O menu e os botões são exibidos conforme o seu perfil de permissões. Se uma ação não "
            "aparece, seu perfil não possui a permissão correspondente. Solicite a atribuição do "
            "perfil adequado ao administrador."
        ),
    },
    {
        "question": "Como devolver um equipamento ao estoque?",
        "answer": (
            "Abra o bem e clique em Movimentar, escolha Devolução ao Estoque e informe o motivo. O "
            "status volta para DISPONIVEL e o termo de devolução é gerado."
        ),
    },
    {
        "question": "A integração com Active Directory/LDAP está disponível?",
        "answer": (
            "Ainda não. O sistema está preparado para a futura integração com Active Directory/LDAP, "
            "mas hoje a autenticação é feita com usuário e senha locais cadastrados no próprio sistema."
        ),
    },
]

# ============================================================================
# CATEGORIAS (cards da página central)
# ============================================================================

CATEGORIES: List[Dict] = [
    {
        "key": "primeiros-passos",
        "title": "Primeiros Passos",
        "icon": "bi-rocket-takeoff",
        "description": "Entrar no sistema, navegar e entender a interface.",
        "audience": "user",
        "article_ids": ["o-que-e-o-sistema", "entrar-e-sair", "conhecendo-a-interface"],
    },
    {
        "key": "patrimonio",
        "title": "Patrimônio & Equipamentos",
        "icon": "bi-laptop",
        "description": "Cadastrar, consultar e importar os bens do acervo.",
        "audience": "user",
        "article_ids": ["cadastrar-equipamento", "consultar-equipamentos", "detalhes-do-bem",
                        "importar-equipamentos", "corrigir-informacoes"],
    },
    {
        "key": "movimentacao",
        "title": "Fluxo & Movimentação",
        "icon": "bi-arrow-left-right",
        "description": "Entregas, transferências, devoluções e baixas.",
        "audience": "user",
        "article_ids": ["movimentar-equipamento", "tipos-de-movimentacao", "historico-do-bem"],
    },
    {
        "key": "manutencao",
        "title": "Manutenções",
        "icon": "bi-wrench",
        "description": "Ordens de serviço e reparos de equipamentos.",
        "audience": "user",
        "article_ids": ["abrir-ordem-servico", "finalizar-manutencao"],
    },
    {
        "key": "colaboradores",
        "title": "Colaboradores & Locais",
        "icon": "bi-people",
        "description": "Custodiantes, departamentos e localizações físicas.",
        "audience": "user",
        "article_ids": ["cadastrar-colaboradores", "cadastrar-locais"],
    },
    {
        "key": "relatorios",
        "title": "Relatórios & Exportações",
        "icon": "bi-file-earmark-text",
        "description": "Inventário, trilha de auditoria e exportação em CSV.",
        "audience": "user",
        "article_ids": ["relatorios", "exportar-csv"],
    },
    {
        "key": "administracao",
        "title": "Administração",
        "icon": "bi-shield-lock",
        "description": "Usuários, perfis, permissões e auditoria.",
        "audience": "admin",
        "article_ids": ["gerenciar-usuarios", "perfis-e-permissoes", "auditoria"],
    },
]

# ============================================================================
# HELPERS
# ============================================================================

def get_articles() -> List[Dict]:
    """Todos os artigos, na ordem de exibição."""
    return ARTICLES


def get_article(article_id: str) -> Optional[Dict]:
    """Retorna um artigo pelo id, ou None."""
    for article in ARTICLES:
        if article["id"] == article_id:
            return article
    return None


def get_faq() -> List[Dict]:
    return FAQ


def get_categories() -> List[Dict]:
    """Categorias com os artigos correspondentes embutidos."""
    categories = []
    by_id = {a["id"]: a for a in ARTICLES}
    for cat in CATEGORIES:
        item = dict(cat)
        item["articles"] = [by_id[a_id] for a_id in cat.get("article_ids", []) if a_id in by_id]
        categories.append(item)
    return categories


def serialize_search_index() -> List[Dict]:
    """
    Índice leve para a busca no manual (client-side): id, título, módulo,
    resumo e o texto completo (títulos, corpos, passos e palavras-chave)
    de cada artigo, além das perguntas/respostas do FAQ.
    """
    def _full_text(article: Dict) -> str:
        parts = [article.get("title", ""), article.get("summary", "")]
        parts.extend(article.get("keywords", []))
        for section in article.get("sections", []):
            parts.append(section.get("heading", ""))
            parts.append(section.get("body", ""))
            parts.append(section.get("note", ""))
            parts.extend(section.get("steps", []))
        return " ".join(parts).lower()

    index = [
        {
            "id": a["id"],
            "title": a["title"],
            "module": a["module"],
            "summary": a["summary"],
            "text": _full_text(a),
            "type": "article",
        }
        for a in ARTICLES
    ]
    index.extend(
        {
            "id": f"faq-{i}",
            "title": f["question"],
            "module": "Perguntas Frequentes",
            "summary": f["answer"],
            "text": (f["question"] + " " + f["answer"]).lower(),
            "type": "faq",
        }
        for i, f in enumerate(FAQ)
    )
    return index