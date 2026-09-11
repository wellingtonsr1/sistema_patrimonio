import enum
from typing import Dict


# Rótulos em linguagem natural exibidos na interface.
# O `value` do enum continua sendo o identificador técnico (banco, APIs, filtros).
_LABELS: Dict[str, str] = {
    # AssetStatus
    "DISPONIVEL": "Disponível",
    "EM_USO": "Em Uso",
    "EM_MANUTENCAO": "Em Manutenção",
    "EM_TRANSITO": "Em Trânsito",
    "BAIXADO": "Baixado",
    # AssetCondition
    "NOVO": "Novo",
    "EXCELENTE": "Excelente",
    "BOM": "Bom",
    "REGULAR": "Regular",
    "RUIM": "Ruim",
    "INSERVIVEL": "Inservível",
    # AssetCategory
    "NOTEBOOK": "Notebook",
    "DESKTOP": "Desktop",
    "MONITOR": "Monitor",
    "SERVIDOR": "Servidor",
    "REDE_E_CONECTIVIDADE": "Rede e Conectividade",
    "IMPRESSORA": "Impressora",
    "SMARTPHONE_TABLET": "Smartphone / Tablet",
    "MOBILIARIO": "Mobiliário",
    "VEICULO": "Veículo",
    "EQUIPAMENTO_GERAL": "Equipamento Geral",
    "OUTROS": "Outros",
    # MovementType
    "ENTRADA_AQUISICAO": "Entrada por Aquisição",
    "ALOCACAO_CAUTELA": "Alocação / Cautela",
    "TRANSFERENCIA_LOCAL": "Transferência de Local",
    "ENVIO_MANUTENCAO": "Envio para Manutenção",
    "RETORNO_MANUTENCAO": "Retorno de Manutenção",
    "DEVOLUCAO_ESTOQUE": "Devolução ao Estoque",
    "BAIXA_DESCARTE": "Baixa / Descarte",
    "ATUALIZACAO_ESTADO": "Atualização de Estado",
    # MaintenanceType
    "PREVENTIVA": "Preventiva",
    "CORRETIVA": "Corretiva",
    "UPGRADE": "Upgrade",
    # MaintenanceStatus
    "AGENDADA": "Agendada",
    "EM_ANDAMENTO": "Em Andamento",
    "CONCLUIDA": "Concluída",
    "CANCELADA": "Cancelada",
}


class _LabeledEnum(str, enum.Enum):
    """Enum com rótulo pronto para exibição ao usuário final.

    Em templates use `label`; `value` permanece como identificador técnico
    (persistência, queries, filtros e CSS, ex.: `status-pill-{{ status.value }}`).
    """

    @property
    def label(self) -> str:
        return _LABELS.get(self.value, self.value)


class AssetStatus(_LabeledEnum):
    AVAILABLE = "DISPONIVEL"            # Disponível no estoque
    IN_USE = "EM_USO"                   # Alocado / Em uso por colaborador ou setor
    IN_MAINTENANCE = "EM_MANUTENCAO"    # Em manutenção técnica
    IN_TRANSIT = "EM_TRANSITO"          # Em transferência / transporte
    WRITTEN_OFF = "BAIXADO"             # Descartado / Baixado / Leiloado / Perdido


class AssetCondition(_LabeledEnum):
    NEW = "NOVO"                        # Novo / Na caixa
    EXCELLENT = "EXCELENTE"             # Excelente estado
    GOOD = "BOM"                        # Bom estado de funcionamento
    FAIR = "REGULAR"                    # Regular com marcas de uso
    POOR = "RUIM"                       # Danificado / Necessita reparo
    UNSERVICEABLE = "INSERVIVEL"        # Sem condições de uso / Sucata


class AssetCategory(_LabeledEnum):
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


class MovementType(_LabeledEnum):
    ACQUISITION = "ENTRADA_AQUISICAO"         # Cadastro inicial e entrada no acervo
    ALLOCATION = "ALOCACAO_CAUTELA"           # Entrega / Cautela para colaborador
    TRANSFER = "TRANSFERENCIA_LOCAL"          # Mudança de filial / prédio / sala
    MAINTENANCE_OUT = "ENVIO_MANUTENCAO"      # Envio para assistência/conserto
    MAINTENANCE_IN = "RETORNO_MANUTENCAO"     # Retorno da manutenção
    RETURN_STOCK = "DEVOLUCAO_ESTOQUE"        # Devolução ao estoque (ex: demissão ou troca)
    WRITE_OFF = "BAIXA_DESCARTE"              # Descarte/baixa definitiva
    STATUS_UPDATE = "ATUALIZACAO_ESTADO"      # Vistoria / Mudança de estado de conservação


class MaintenanceType(_LabeledEnum):
    PREVENTIVE = "PREVENTIVA"
    CORRECTIVE = "CORRETIVA"
    UPGRADE = "UPGRADE"


class MaintenanceStatus(_LabeledEnum):
    SCHEDULED = "AGENDADA"
    IN_PROGRESS = "EM_ANDAMENTO"
    COMPLETED = "CONCLUIDA"
    CANCELLED = "CANCELADA"
