import io
import csv
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.asset import Asset
from app.models.movement import Movement
from app.models.custodian import Custodian
from app.services.asset_service import AssetService
from app.services.custodian_service import CustodianService


class ReportService:
    @staticmethod
    def generate_inventory_csv(db: Session, assets: Optional[List[Asset]] = None) -> str:
        """Gera um arquivo CSV completo com todos os bens e seus dados contábeis/fiscais"""
        if assets is None:
            assets, _ = AssetService.get_all(db, limit=10000)

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

        # Cabeçalho
        writer.writerow([
            "Tombamento / Tag",
            "Nome do Bem",
            "Categoria",
            "Marca",
            "Modelo",
            "Número de Série",
            "Status",
            "Condição",
            "Localização Atual",
            "Responsável Atual",
            "Data Aquisição",
            "Valor de Compra (R$)",
            "Depreciação Acumulada (R$)",
            "Valor Contábil Atual (R$)",
            "Nota Fiscal",
            "Fornecedor"
        ])

        for asset in assets:
            deprec = AssetService.calculate_depreciation(asset)
            loc_name = f"{asset.location.branch} - {asset.location.department}" if asset.location else "Não alocado"
            cust_name = f"{asset.custodian.name} ({asset.custodian.registration_code})" if asset.custodian else "Estoque / Livre"
            dt_purchase = asset.purchase_date.strftime("%d/%m/%Y") if asset.purchase_date else ""

            writer.writerow([
                asset.tag,
                asset.name,
                asset.category.value,
                asset.brand or "",
                asset.model or "",
                asset.serial_number or "",
                asset.status.value,
                asset.condition.value,
                loc_name,
                cust_name,
                dt_purchase,
                f"{asset.purchase_value:.2f}",
                f"{deprec['depreciated_amount']:.2f}",
                f"{deprec['current_value']:.2f}",
                asset.invoice_number or "",
                asset.supplier or ""
            ])

        return output.getvalue()

    @staticmethod
    def generate_custodians_csv(db: Session, custodians: Optional[List[Custodian]] = None) -> str:
        """
        Gera um CSV com todos os colaboradores no mesmo formato aceito pela
        importação via CSV (colunas: matricula;nome;email;cargo;setor;cpf;ativo).
        """
        if custodians is None:
            custodians = CustodianService.get_all(db)

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

        writer.writerow([
            "matricula",
            "nome",
            "email",
            "cargo",
            "setor",
            "cpf",
            "ativo",
        ])

        for c in custodians:
            writer.writerow([
                c.registration_code,
                c.name,
                c.email,
                c.role,
                c.department,
                c.cpf or "",
                "sim" if c.is_active else "não",
            ])

        return output.getvalue()

    @staticmethod
    def generate_movements_csv(db: Session, movements: Optional[List[Movement]] = None) -> str:
        """Gera um CSV com a trilha de auditoria e fluxo de movimentação"""
        if movements is None:
            movements = db.query(Movement).order_by(Movement.timestamp.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

        writer.writerow([
            "Código Movimentação",
            "Data e Hora",
            "Tombamento",
            "Equipamento",
            "Tipo de Movimento",
            "Origem (Local)",
            "Origem (Responsável)",
            "Destino (Local)",
            "Destino (Responsável)",
            "Status Resultante",
            "Motivo / Justificativa",
            "Operador do Registro",
            "Termo de Cautela"
        ])

        for m in movements:
            tag = m.asset.tag if m.asset else "N/A"
            name = m.asset.name if m.asset else "N/A"
            writer.writerow([
                m.movement_uuid,
                m.timestamp.strftime("%d/%m/%Y %H:%M:%S"),
                tag,
                name,
                m.movement_type.value,
                m.origin_location_name or "-",
                m.origin_custodian_name or "-",
                m.destination_location_name or "-",
                m.destination_custodian_name or "-",
                m.new_status.value,
                m.reason,
                m.operator_name,
                m.term_code or "-"
            ])

        return output.getvalue()
