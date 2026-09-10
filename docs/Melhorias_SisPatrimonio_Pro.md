# Sugestões de Melhorias — SisPatrimônio Pro

## Objetivo

Reunir sugestões para evoluir o SisPatrimônio Pro com foco em segurança, confiabilidade, rastreabilidade, produtividade e facilidade de uso, sempre preservando as funcionalidades existentes.

## 1. Prioridade Alta

### 1.1 Dashboard mais útil
- Total de equipamentos.
- Equipamentos em uso, estoque e manutenção.
- Equipamentos por localização e setor/departamento.
- Últimas movimentações.
- Alertas e inconsistências.

### 1.2 Busca global
Permitir busca por número de patrimônio, número de série, modelo, marca, colaborador, setor e localização.

### 1.3 Filtros avançados
Adicionar filtros por localização, status, categoria, marca/modelo, colaborador, período, situação de manutenção e setor/departamento.

### 1.4 Histórico completo do patrimônio

```text
Cadastro
   ↓
Movimentações
   ↓
Responsáveis anteriores
   ↓
Manutenções
   ↓
Alterações cadastrais
   ↓
Auditoria
```

Permitir rastrear a trajetória do bem ao longo de sua vida útil.

### 1.5 QR Code por equipamento
Gerar QR Code individual para cada equipamento, direcionando para sua ficha no sistema, por exemplo `/assets/123`.

### 1.6 Controle patrimonial mais rigoroso
- Número de patrimônio único.
- Número de série único quando aplicável.
- Histórico de localização e responsável.
- Status controlado.
- Bloqueio de movimentações inconsistentes.
- Validação de dados obrigatórios.

## 2. Segurança e Controle de Acesso

### 2.1 Integração AD + RBAC

```text
AD = autenticação e grupos
SisPatrimônio = autorização e regras de negócio
```

Fluxo:

```text
Usuário AD
    ↓
Autenticação
    ↓
Grupo AD autorizado
    ↓
Perfil existente
    ↓
Permissões
```

A autenticação no domínio, por si só, não deve conceder acesso ao SisPatrimônio.

### 2.2 Auditoria robusta
Registrar:
- Login e logout.
- Login via AD.
- Falhas de autenticação.
- Criação, alteração e exclusão.
- Movimentações.
- Alterações de perfil e permissões.
- Importações.
- Alterações da configuração do AD.

Informações úteis:

```text
Usuário
Data/hora
Ação
Registro afetado
IP
Resultado
```

### 2.3 Proteção contra exclusões acidentais
Avaliar inativação/arquivamento em vez de exclusão física para registros importantes. Exigir confirmação e verificar dependências.

## 3. Produtividade

### 3.1 Importação CSV aprimorada

```text
Selecionar arquivo
       ↓
Validar
       ↓
Mostrar prévia
       ↓
Mostrar erros
       ↓
Confirmar
       ↓
Importar
       ↓
Resumo
```

Exemplo:

```text
250 registros analisados

✓ 242 válidos
⚠ 5 duplicados
✕ 3 com erro

[Cancelar] [Importar 242 registros]
```

### 3.2 Exportação de dados
Permitir exportação dos resultados filtrados em:
- CSV.
- Excel.
- PDF.

### 3.3 Impressão de etiquetas
Etiquetas podem conter QR Code, número de patrimônio, descrição, setor e localização. Avaliar impressão em lote.

### 3.4 Ações em lote
Permitir operações autorizadas sobre vários registros, como alterar localização, gerar etiquetas e exportar.

## 4. Usabilidade

### 4.1 Feedback visual
Exibir mensagens claras após operações:

> ✓ Equipamento movimentado com sucesso.

### 4.2 Estados vazios
Substituir mensagens genéricas por orientações úteis:

> Nenhum equipamento encontrado.  
> Tente remover alguns filtros ou cadastre um novo equipamento.

### 4.3 Preservação de filtros
Avaliar manter filtros ativos ao retornar de uma ficha para a listagem.

### 4.4 Atalhos de teclado
Exemplos:
- `Ctrl + K` → Busca global.
- `Esc` → Fechar modal.

Devem ser documentados e não conflitar com recursos de acessibilidade.

## 5. Gestão e Relatórios

### 5.1 Relatórios gerenciais
- Patrimônio por setor.
- Patrimônio por localização.
- Patrimônio por responsável.
- Equipamentos em manutenção.
- Equipamentos sem responsável.
- Equipamentos sem localização.
- Histórico de movimentações.
- Inventário geral.
- Patrimônio por categoria.
- Patrimônio por situação.

### 5.2 Indicadores de inconsistência

```text
⚠ 7 equipamentos sem localização
⚠ 3 equipamentos sem responsável
⚠ 4 patrimônios duplicados
⚠ 2 números de série duplicados
```

## 6. Arquitetura, Qualidade e Operação

### 6.1 Testes automatizados
Priorizar:
- Autenticação.
- RBAC.
- Integração AD.
- Movimentações.
- Importação.
- Localização.
- Equipamentos.
- Auditoria.

### 6.2 Backup e restauração

```text
Backup
   ↓
Validação
   ↓
Restauração
```

Definir frequência, armazenamento, retenção, restauração e verificação periódica.

### 6.3 Auditoria x logs técnicos

```text
Auditoria
→ ações dos usuários e eventos de negócio.

Logs técnicos
→ erros, exceções, falhas de infraestrutura e diagnóstico.
```

### 6.4 Health Check
Avaliar uma rota segura como `/health`, podendo verificar:

```text
Aplicação       ✓
Banco de dados  ✓
AD              ✓ / ⚠
```

## 7. Ordem Recomendada de Implementação

| Prioridade | Melhoria |
|---|---|
| 1 | Histórico completo do patrimônio |
| 2 | Auditoria robusta |
| 3 | Busca e filtros avançados |
| 4 | Indicadores de inconsistências |
| 5 | QR Code |
| 6 | Etiquetas e impressão em lote |
| 7 | Importação com prévia e validação |
| 8 | Exportação filtrada |
| 9 | Ações em lote |
| 10 | Dashboard gerencial |
| 11 | Testes automatizados |
| 12 | Backup e restauração |
| 13 | Health check |
| 14 | Logs técnicos |

## 8. Diretrizes para Implementação

1. Fazer alterações incrementais.
2. Preservar funcionalidades existentes.
3. Não alterar regras de negócio sem necessidade.
4. Evitar refatorações amplas para problemas pontuais.
5. Preservar autenticação, AD, RBAC, permissões e auditoria.
6. Validar alterações antes da produção.
7. Criar testes para regras críticas.
8. Manter documentação atualizada.
9. Evitar duplicação de funcionalidades.
10. Priorizar integridade dos dados patrimoniais.
11. Priorizar segurança e rastreabilidade.
12. Documentar a justificativa técnica de alterações importantes.

## 9. Melhorias que Não Devem Ser Prioridade Agora

Evitar mudanças grandes apenas por modernização, como:
- Refazer toda a interface sem necessidade.
- Trocar o framework sem necessidade concreta.
- Refatorar toda a aplicação de uma vez.
- Migrar o banco apenas por preferência tecnológica.
- Alterar funcionalidades estáveis sem benefício mensurável.

A evolução deve ser orientada por problemas reais e ganhos concretos.

## Conclusão

A evolução do SisPatrimônio Pro deve priorizar quatro pilares:

```text
        SIS PATRIMÔNIO PRO
               │
    ┌──────────┼──────────┐
    ↓          ↓          ↓
 Segurança  Integridade  Produtividade
    │          │          │
    └──────────┼──────────┘
               ↓
          Rastreabilidade
               ↓
        Gestão Patrimonial
```

O núcleo do sistema — patrimônio, movimentação, responsáveis, localização, manutenção, auditoria, segurança e integridade dos dados — deve ser fortalecido antes de ampliar significativamente o escopo.
