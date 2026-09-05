"""
Script de dados de demonstração (Seed) para o SisPatrimônio Pro.
Popula o banco com locais, colaboradores, equipamentos e histórico de movimentações.
"""

from datetime import datetime, timedelta
from app.database import SessionLocal, init_db, Base, engine
from app.models.enums import AssetStatus, AssetCondition, AssetCategory, MovementType, MaintenanceType, MaintenanceStatus
from app.models.asset import Asset
from app.schemas.location import LocationCreate
from app.schemas.custodian import CustodianCreate
from app.schemas.asset import AssetCreate
from app.schemas.movement import MovementCreate
from app.schemas.maintenance import MaintenanceCreate
from app.services.location_service import LocationService
from app.services.custodian_service import CustodianService
from app.services.asset_service import AssetService
from app.services.movement_service import MovementService
from app.services.maintenance_service import MaintenanceService


def seed():
    print("Iniciando carga de dados de demonstração...")
    # Recria as tabelas
    Base.metadata.drop_all(bind=engine)
    init_db()
    
    db = SessionLocal()

    try:
        # 1. Locais
        print("-> Cadastrando locais e setores...")
        loc_ti = LocationService.create(db, LocationCreate(
            name="Matriz SP - TI - Suporte e Infraestrutura",
            branch="Matriz São Paulo",
            building="Torre A",
            floor="7º Andar",
            room="Sala 701",
            department="Tecnologia da Informação",
            manager_name="Rodrigo Nogueira",
            description="Laboratório de manutenção e estoque de informática."
        ))

        loc_dev = LocationService.create(db, LocationCreate(
            name="Matriz SP - Engenharia de Software",
            branch="Matriz São Paulo",
            building="Torre A",
            floor="8º Andar",
            room="Open Space 802",
            department="Desenvolvimento de Software",
            manager_name="Ana Paula Castro",
            description="Área dos times de produto e desenvolvimento."
        ))

        loc_datacenter = LocationService.create(db, LocationCreate(
            name="Matriz SP - Data Center Principal",
            branch="Matriz São Paulo",
            building="Subsolo 1",
            floor="SS1",
            room="Sala Cofre DC-01",
            department="Infraestrutura e Redes",
            manager_name="Rodrigo Nogueira",
            description="Ambiente climatizado e redundante para servidores."
        ))

        loc_rj = LocationService.create(db, LocationCreate(
            name="Filial Rio - Escritório Comercial",
            branch="Filial Rio de Janeiro",
            building="Edifício Porto Atlântico",
            floor="12º Andar",
            room="Sala 1204",
            department="Comercial e Vendas",
            manager_name="Juliana Ramos",
            description="Escritório regional de vendas e relacionamento."
        ))

        # 2. Colaboradores (Custodiantes)
        print("-> Cadastrando colaboradores...")
        c1 = CustodianService.create(db, CustodianCreate(
            registration_code="MAT-1010",
            name="Lucas Fernandes Silveira",
            email="lucas.silveira@empresa.com",
            cpf="111.222.333-44",
            role="Engenheiro de Software Sênior",
            department="Desenvolvimento de Software"
        ))

        c2 = CustodianService.create(db, CustodianCreate(
            registration_code="MAT-1025",
            name="Mariana Souza Lima",
            email="mariana.lima@empresa.com",
            cpf="222.333.444-55",
            role="Product Designer / UX",
            department="Desenvolvimento de Software"
        ))

        c3 = CustodianService.create(db, CustodianCreate(
            registration_code="MAT-1038",
            name="Gabriel Oliveira Santos",
            email="gabriel.santos@empresa.com",
            cpf="333.444.555-66",
            role="Executivo de Contas Sênior",
            department="Comercial e Vendas"
        ))

        c4 = CustodianService.create(db, CustodianCreate(
            registration_code="MAT-1090",
            name="Beatriz Mendonça",
            email="beatriz.mendonca@empresa.com",
            cpf="444.555.666-77",
            role="Analista de Suporte e Redes",
            department="Tecnologia da Informação"
        ))

        # 3. Equipamentos (Bens)
        print("-> Cadastrando equipamentos e gerando fluxo inicial...")
        
        # Notebook 1 - Lucas (Em Uso com histórico de movimentações)
        nb1 = AssetService.create(db, AssetCreate(
            tag="PAT-00101",
            name="MacBook Pro 16' M3 Pro 36GB 512GB",
            category=AssetCategory.NOTEBOOK,
            brand="Apple",
            model="MacBook Pro 16",
            serial_number="C02XG182MD6R",
            specifications="Apple M3 Pro 12-core CPU, 18-core GPU, 36GB RAM Unificada, 512GB SSD, Space Black. Acompanha carregador MagSafe 140W.",
            purchase_date=datetime.utcnow() - timedelta(days=240),
            purchase_value=21999.00,
            invoice_number="NF-e 881240",
            supplier="Apple Computer Brasil Ltda",
            warranty_expiry=datetime.utcnow() + timedelta(days=125),
            condition=AssetCondition.EXCELLENT,
            initial_location_id=loc_ti.id,
            notes="Equipamento top de linha para desenvolvimento."
        ))

        # Movimentação 2 do Notebook 1: Alocação para Lucas com emissão de Termo de Cautela
        MovementService.create_movement(db, MovementCreate(
            asset_id=nb1.id,
            movement_type=MovementType.ALLOCATION,
            destination_custodian_id=c1.id,
            destination_location_id=loc_dev.id,
            reason="Entrega de equipamento de trabalho para o desenvolvedor.",
            operator_name="Beatriz Mendonça (TI)",
            notes="Colaborador assinou o termo de cautela no momento da entrega."
        ))

        # Notebook 2 - Mariana (Em Uso)
        nb2 = AssetService.create(db, AssetCreate(
            tag="PAT-00102",
            name="Dell XPS 15 9530 i9 32GB RTX 4070",
            category=AssetCategory.NOTEBOOK,
            brand="Dell",
            model="XPS 15 9530",
            serial_number="DL9941029XPS",
            specifications="Intel Core i9-13900H, 32GB DDR5, 1TB NVMe, Tela OLED 3.5K Touch, GeForce RTX 4070. Acompanha hub USB-C e carregador 130W.",
            purchase_date=datetime.utcnow() - timedelta(days=180),
            purchase_value=16499.00,
            invoice_number="NF-e 910482",
            supplier="Dell Computadores do Brasil",
            warranty_expiry=datetime.utcnow() + timedelta(days=185),
            condition=AssetCondition.EXCELLENT,
            initial_location_id=loc_ti.id
        ))
        MovementService.create_movement(db, MovementCreate(
            asset_id=nb2.id,
            movement_type=MovementType.ALLOCATION,
            destination_custodian_id=c2.id,
            destination_location_id=loc_dev.id,
            reason="Alocação de workstation móvel para atividades de Design de Produto e UX.",
            operator_name="Beatriz Mendonça (TI)"
        ))

        # Notebook 3 - Gabriel (Filial RJ)
        nb3 = AssetService.create(db, AssetCreate(
            tag="PAT-00103",
            name="ThinkPad T14s Gen 4 i7 16GB 512GB",
            category=AssetCategory.NOTEBOOK,
            brand="Lenovo",
            model="ThinkPad T14s Gen 4",
            serial_number="PF481029LN",
            specifications="Intel Core i7-1355U, 16GB LPDDR5, 512GB SSD, Tela 14' IPS Antirreflexo.",
            purchase_date=datetime.utcnow() - timedelta(days=90),
            purchase_value=8200.00,
            invoice_number="NF-e 954120",
            supplier="Lenovo Tecnologia Brasil",
            condition=AssetCondition.EXCELLENT,
            initial_location_id=loc_ti.id
        ))
        # Primeiro transferiu para filial RJ
        MovementService.create_movement(db, MovementCreate(
            asset_id=nb3.id,
            movement_type=MovementType.TRANSFER,
            destination_location_id=loc_rj.id,
            reason="Envio de equipamento via malote seguro para filial Rio de Janeiro.",
            operator_name="Beatriz Mendonça (TI)"
        ))
        # Depois alocou para Gabriel
        MovementService.create_movement(db, MovementCreate(
            asset_id=nb3.id,
            movement_type=MovementType.ALLOCATION,
            destination_custodian_id=c3.id,
            destination_location_id=loc_rj.id,
            reason="Cautela para o executivo de vendas regional.",
            operator_name="Juliana Ramos (Gerente RJ)"
        ))

        # Servidor no Data Center
        srv1 = AssetService.create(db, AssetCreate(
            tag="PAT-00201",
            name="Servidor Dell PowerEdge R760 2x Xeon 128GB",
            category=AssetCategory.SERVER,
            brand="Dell",
            model="PowerEdge R760",
            serial_number="SV-R760-99201",
            specifications="2x Intel Xeon Gold 6430 32-core, 128GB RDIMM DDR5, 4x 1.92TB SAS SSD em RAID 10, Fontes Redundantes 1400W.",
            purchase_date=datetime.utcnow() - timedelta(days=365),
            purchase_value=48500.00,
            invoice_number="NF-e 720199",
            supplier="Dell Computadores do Brasil",
            condition=AssetCondition.EXCELLENT,
            initial_location_id=loc_datacenter.id,
            notes="Servidor de virtualização do cluster principal (Host VMware ESXi 01)."
        ))

        # Monitor Disponível em Estoque
        mon1 = AssetService.create(db, AssetCreate(
            tag="PAT-00301",
            name="Monitor Dell UltraSharp 27' 4K U2723QE",
            category=AssetCategory.MONITOR,
            brand="Dell",
            model="UltraSharp U2723QE",
            serial_number="CN-0F9182-99120",
            specifications="Painel IPS Black 4K (3840x2160), 98% DCI-P3, Conexão USB-C com Power Delivery 90W, Hub RJ-45 integrado.",
            purchase_date=datetime.utcnow() - timedelta(days=60),
            purchase_value=3890.00,
            invoice_number="NF-e 981240",
            supplier="Dell Computadores do Brasil",
            condition=AssetCondition.NEW,
            initial_location_id=loc_ti.id,
            notes="Disponível no almoxarifado de TI para novas contratações."
        ))

        # Notebook em Manutenção Corretiva
        nb_maint = AssetService.create(db, AssetCreate(
            tag="PAT-00104",
            name="Notebook Dell Latitude 5430 i5 16GB",
            category=AssetCategory.NOTEBOOK,
            brand="Dell",
            model="Latitude 5430",
            serial_number="DL-LAT5430-8812",
            specifications="Intel Core i5-1245U, 16GB DDR4, 256GB SSD NVMe.",
            purchase_date=datetime.utcnow() - timedelta(days=400),
            purchase_value=6200.00,
            invoice_number="NF-e 681029",
            supplier="Dell Computadores",
            condition=AssetCondition.POOR,
            initial_location_id=loc_ti.id
        ))

        # Abre manutenção e envia para assistência
        MaintenanceService.create(db, MaintenanceCreate(
            asset_id=nb_maint.id,
            maintenance_type=MaintenanceType.CORRECTIVE,
            provider_name="Assistência Técnica Especializada Dell",
            description="Teclado parou de funcionar e bateria não retém mais que 30 minutos de carga.",
            cost=850.00
        ), operator="Beatriz Mendonça (TI)")

        # Equipamento Baixado / Descartado (Sucata)
        printer = AssetService.create(db, AssetCreate(
            tag="PAT-00050",
            name="Impressora HP LaserJet Pro M402dn",
            category=AssetCategory.PRINTER,
            brand="HP",
            model="LaserJet M402dn",
            serial_number="HP-LJ402-9901",
            specifications="Impressora monocromática 40ppm.",
            purchase_date=datetime.utcnow() - timedelta(days=1800),
            purchase_value=1800.00,
            invoice_number="NF-e 310290",
            condition=AssetCondition.UNSERVICEABLE,
            initial_location_id=loc_ti.id,
            notes="Equipamento com mais de 5 anos de uso, queima de placa lógica."
        ))
        MovementService.create_movement(db, MovementCreate(
            asset_id=printer.id,
            movement_type=MovementType.WRITE_OFF,
            reason="Laudo técnico constatou queima irrecuperável da placa lógica e fusor. Custo de reparo superior a 80% de um novo.",
            operator_name="Rodrigo Nogueira (Gerente TI)",
            notes="Encaminhado para descarte ecológico certificado."
        ))

        total_assets = db.query(Asset).count()
        print("-> Carga de dados de demonstração concluída com sucesso!")
        print(f"Total de Ativos Cadastrados: {total_assets}")
        
    finally:
        db.close()


if __name__ == "__main__":
    seed()
