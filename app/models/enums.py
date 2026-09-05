import enum


class AssetStatus(str, enum.Enum):
    AVAILABLE = "DISPONIVEL"            # Disponível no estoque
    IN_USE = "EM_USO"                   # Alocado / Em uso por colaborador ou setor
    IN_MAINTENANCE = "EM_MANUTENCAO"    # Em manutenção técnica
    IN_TRANSIT = "EM_TRANSITO"          # Em transferência / transporte
    WRITTEN_OFF = "BAIXADO"             # Descartado / Baixado / Leiloado / Perdido


class AssetCondition(str, enum.Enum):
    NEW = "NOVO"                        # Novo / Na caixa
    EXCELLENT = "EXCELENTE"             # Excelente estado
    GOOD = "BOM"                        # Bom estado de funcionamento
    FAIR = "REGULAR"                    # Regular com marcas de uso
    POOR = "RUIM"                       # Danificado / Necessita reparo
    UNSERVICEABLE = "INSERVIVEL"        # Sem condições de uso / Sucata


class AssetCategory(str, enum.Enum):
    NOTEBOOK = "NOTEBOOK"
    DESKTOP = "DESKTOP"
    MONITOR = "MONITOR"
    SERVER = "SERVIDOR"
    NETWORKING = "REDE_E_CONECTIVIDADE"
    PRINTER = "IMPRESSORA"
    SMARTPHONE = "SMARTPHONE_TABLET"
    FURNITURE = "MOBILIARIO"
    VEHICLE = "VEICULO"
    EQUIPMENT = "EQUIPAMENTO_GERAL"
    OTHER = "OUTROS"


class MovementType(str, enum.Enum):
    ACQUISITION = "ENTRADA_AQUISICAO"         # Cadastro inicial e entrada no acervo
    ALLOCATION = "ALOCACAO_CAUTELA"           # Entrega / Cautela para colaborador
    TRANSFER = "TRANSFERENCIA_LOCAL"          # Mudança de filial / prédio / sala
    MAINTENANCE_OUT = "ENVIO_MANUTENCAO"      # Envio para assistência/conserto
    MAINTENANCE_IN = "RETORNO_MANUTENCAO"     # Retorno da manutenção
    RETURN_STOCK = "DEVOLUCAO_ESTOQUE"        # Devolução ao estoque (ex: demissão ou troca)
    WRITE_OFF = "BAIXA_DESCARTE"              # Descarte/baixa definitiva
    STATUS_UPDATE = "ATUALIZACAO_ESTADO"      # Vistoria / Mudança de estado de conservação


class MaintenanceType(str, enum.Enum):
    PREVENTIVE = "PREVENTIVA"
    CORRECTIVE = "CORRETIVA"
    UPGRADE = "UPGRADE"


class MaintenanceStatus(str, enum.Enum):
    SCHEDULED = "AGENDADA"
    IN_PROGRESS = "EM_ANDAMENTO"
    COMPLETED = "CONCLUIDA"
    CANCELLED = "CANCELADA"
