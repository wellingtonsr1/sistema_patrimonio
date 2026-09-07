"""
Tarefa: Implementar suporte à coluna de localização na importação CSV de equipamentos.

Objetivo:
  - Ler a coluna de localização do CSV (se presente).
  - Resolver o nome da localização para um location_id via LocationService.get_by_name.
  - Atribuir location_id ao Asset criado.
  - Usar o nome resolvido (ex: "IPMJP - DAF - Setor de Suporte") no Movement de
    aquisição, em vez do hardcoded "Estoque Central".
  - Se a localização não for encontrada no cadastro: importar com location_id NULL e
    registrar aviso na importação (não falhar a linha inteira, a menos que a regra de
    negócio o exija).

Escopo mínimo recomendado (nesta ordem):
  1) Adicionar alias(es) de coluna para localização no COLUMN_ALIASES de
     app/services/import_service.py (ex: "localização", "localizacao", "local", "loc").
  2) Ler o valor da localização em execute_import a partir da row normalizada.
  3) Resolver location_id via LocationService.get_by_name(db, nome).
  4) Se encontrado: definir location_id e um nome de localização completa para o
     Movement; se não encontrado: location_id=None e aviso/erro na importação.
  5) Criar Asset(location_id=...) e Movement(destination_location_id=..., destination_location_name=...).
  6) Incluir a localização no preview_import (opcional, mas recomendado para visibilidade).
  7) Atualizar a documentação do formato CSV aceito (import.html e docstring do módulo)
     para listar a coluna de localização como opcional.

Restrições / decisões pendentes para confirmar antes de implementar:
  - Qual(is) nome(s) de coluna aceitos? Sugestão: "localização", "localizacao", "local", "loc".
  - Comportamento quando a localização não é encontrada no cadastro:
      A) importar com location_id=NULL + aviso (comportamento "estoque")
      B) importar com location_id=NULL + erro na linha (fatal para a linha)
      C) pular a linha silenciosamente
    A opção mais alinhada com o sistema atual parece ser A, mas confirmar.
  - Deve o sistema aceitar localização por nome (texto) ou também por ID (location_id)?
    Sugestão: nome por padrão; ID opcional se houver alias "location_id".
  - O campo de localização deve aparecer no preview da importação?
    Sugestão: sim, incluir coluna "Localização" na tabela preview.

Arquivos provavelmente envolvidos:
  - app/services/import_service.py   (parser aliases + execute_import + preview_import)
  - app/web/templates/assets/import.html (preview: coluna de localização)
  - app/services/asset_service.py   (referência de como AssetService.create trata location)
  - app/web/templates/assets/import.html (documentação do formato CSV aceito)

Arquivos NÃO a tocar (decisão já consolidada, não mudar nesta tarefa):
  - app/models/asset.py            (o campo location_id já existe e é nullable)
  - app/models/location.py         (localizações já são cadastradas separadamente)
  - app/services/location_service.py
  - app/web/templates/assets/form.html (cadastro manual não é o escopo aqui)
  - app/services/movement_service.py  (movimentação manual não é o escopo aqui)

Critérios de aceitação (sugestão):
  - CSV com "localização = Sala de TI" e "Sala de TI" cadastrada como Location →
    Asset.location_id = id da localização correspondente e Movement.destination_location_name
    reflete o nome resolvido.
  - CSV com localização inexistente → location_id NULL e aviso na importação (não crash).
  - CSV sem coluna de localização → comportamento inalterado (location_id NULL, fallback Estoque Central).
  - Preview mostra a localização quando a coluna está presente.

NÃO avança sem confirmar as decisões pendentes antes de reescrever o código.
"""
