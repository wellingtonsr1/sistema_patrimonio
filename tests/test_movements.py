import pytest
from app.models.enums import AssetStatus, AssetCondition, AssetCategory, MovementType
from app.schemas.asset import AssetCreate
from app.schemas.custodian import CustodianCreate
from app.schemas.location import LocationCreate
from app.schemas.movement import MovementCreate
from app.services.asset_service import AssetService
from app.services.custodian_service import CustodianService
from app.services.location_service import LocationService
from app.services.movement_service import MovementService


def test_asset_creation_registers_initial_movement(db_session):
    """Verifica se ao criar um equipamento o primeiro fluxo (ENTRADA_AQUISICAO) é gravado automaticamente"""
    loc = LocationService.create(db_session, LocationCreate(
        name="TI Central", branch="Matriz", department="TI"
    ))
    
    asset = AssetService.create(db_session, AssetCreate(
        tag="PAT-99001",
        name="Dell Latitude 5440",
        category=AssetCategory.NOTEBOOK,
        purchase_value=5500.0,
        initial_location_id=loc.id
    ))

    assert asset.id is not None
    assert asset.status == AssetStatus.AVAILABLE

    # Verifica se o primeiro movimento foi gerado
    # (a timeline retorna dicts: {'type': 'movement'|'audit', 'data': Movement|AuditLog, ...})
    timeline = MovementService.get_timeline_for_asset(db_session, asset.id)
    assert len(timeline) == 1
    assert timeline[0]["type"] == "movement"
    assert timeline[0]["data"].movement_type == MovementType.ACQUISITION
    assert timeline[0]["data"].destination_location_id == loc.id
    assert "Tombamento inicial" in timeline[0]["data"].reason


def test_allocation_and_custody_flow(db_session):
    """Testa o fluxo completo de alocação de equipamento a um colaborador e geração do termo"""
    loc = LocationService.create(db_session, LocationCreate(name="TI", branch="SP", department="TI"))
    cust = CustodianService.create(db_session, CustodianCreate(
        registration_code="MAT-5001",
        name="Rodrigo Santos",
        email="rodrigo@empresa.com",
        role="Dev",
        department="TI"
    ))

    asset = AssetService.create(db_session, AssetCreate(
        tag="PAT-99002",
        name="MacBook Air M2",
        category=AssetCategory.NOTEBOOK,
        initial_location_id=loc.id
    ))

    # Executa Alocação
    movement = MovementService.create_movement(db_session, MovementCreate(
        asset_id=asset.id,
        movement_type=MovementType.ALLOCATION,
        destination_custodian_id=cust.id,
        reason="Entrega de computador de trabalho",
        operator_name="Admin TI"
    ))

    assert movement.new_status == AssetStatus.IN_USE
    assert movement.term_code is not None
    assert "TR-" in movement.term_code

    # Verifica atualização no ativo
    db_session.refresh(asset)
    assert asset.status == AssetStatus.IN_USE
    assert asset.custodian_id == cust.id

    # Verifica histórico completo do fluxo
    # (a timeline retorna dicts: {'type': 'movement'|'audit', 'data': Movement|AuditLog, ...})
    timeline = MovementService.get_timeline_for_asset(db_session, asset.id)
    assert len(timeline) == 2
    assert timeline[0]["type"] == "movement"
    assert timeline[0]["data"].movement_type == MovementType.ALLOCATION
    assert timeline[1]["data"].movement_type == MovementType.ACQUISITION


def test_return_to_stock_flow(db_session):
    """Testa o fluxo de devolução do equipamento ao estoque"""
    loc = LocationService.create(db_session, LocationCreate(name="TI", branch="SP", department="TI"))
    cust = CustodianService.create(db_session, CustodianCreate(
        registration_code="MAT-5002",
        name="Fernanda Lima",
        email="fernanda@empresa.com",
        role="Designer",
        department="UX"
    ))

    asset = AssetService.create(db_session, AssetCreate(
        tag="PAT-99003",
        name="Monitor 27 Pol",
        category=AssetCategory.MONITOR,
        initial_location_id=loc.id,
        initial_custodian_id=cust.id
    ))

    assert asset.status == AssetStatus.IN_USE

    # Executa Devolução ao Estoque
    movement = MovementService.create_movement(db_session, MovementCreate(
        asset_id=asset.id,
        movement_type=MovementType.RETURN_STOCK,
        destination_location_id=loc.id,
        reason="Devolução de monitor por migração para home office",
        operator_name="Admin TI"
    ))

    db_session.refresh(asset)
    assert asset.status == AssetStatus.AVAILABLE
    assert asset.custodian_id is None
    assert movement.movement_type == MovementType.RETURN_STOCK


def test_cannot_move_written_off_asset(db_session):
    """Garante que equipamentos descartados/baixados não possam ser movimentados"""
    asset = AssetService.create(db_session, AssetCreate(
        tag="PAT-99004",
        name="Nobreak Antigo",
        category=AssetCategory.EQUIPMENT
    ))

    # Baixa o equipamento
    MovementService.create_movement(db_session, MovementCreate(
        asset_id=asset.id,
        movement_type=MovementType.WRITE_OFF,
        reason="Sucata sem conserto",
        operator_name="Admin"
    ))

    db_session.refresh(asset)
    assert asset.status == AssetStatus.WRITTEN_OFF

    # Tenta movimentar novamente
    with pytest.raises(ValueError, match="já foi baixado"):
        MovementService.create_movement(db_session, MovementCreate(
            asset_id=asset.id,
            movement_type=MovementType.TRANSFER,
            reason="Tentativa inválida de transferir sucata",
            operator_name="Admin"
        ))


def test_term_page_qr_code_points_to_term_route(client, db_session):
    """O QR Code de validação do termo deve apontar para a rota web do termo"""
    cust = CustodianService.create(db_session, CustodianCreate(
        registration_code="MAT-7100",
        name="Teste QR",
        email="qr@empresa.com",
        role="Dev",
        department="TI"
    ))
    asset = AssetService.create(db_session, AssetCreate(
        tag="PAT-99010",
        name="Notebook Teste",
        category=AssetCategory.NOTEBOOK
    ))
    movement = MovementService.create_movement(db_session, MovementCreate(
        asset_id=asset.id,
        movement_type=MovementType.ALLOCATION,
        destination_custodian_id=cust.id,
        reason="Teste do QR code do termo",
        operator_name="Admin"
    ))
    assert movement.term_code is not None

    response = client.get(f"/movements/{movement.id}/term")
    assert response.status_code == 200
    # O QR deve validar na página do termo, não numa rota inexistente
    assert f"/movements/{movement.id}/term" in response.text
