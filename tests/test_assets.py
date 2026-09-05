import pytest
from datetime import datetime, timedelta
from app.models.enums import AssetStatus, AssetCondition, AssetCategory
from app.schemas.asset import AssetCreate, AssetUpdate
from app.services.asset_service import AssetService


def test_asset_crud_and_depreciation(db_session):
    """Testa cadastro, atualização e cálculo contábil de depreciação"""
    purchase_dt = datetime.utcnow() - timedelta(days=365)  # 1 ano atrás
    
    asset = AssetService.create(db_session, AssetCreate(
        tag="PAT-88001",
        name="Servidor Web NGINX",
        category=AssetCategory.SERVER,
        brand="Dell",
        model="PowerEdge",
        serial_number="SV-88001",
        purchase_date=purchase_dt,
        purchase_value=10000.00,
        condition=AssetCondition.NEW
    ))

    assert asset.id is not None
    assert asset.tag == "PAT-88001"
    assert asset.purchase_value == 10000.00

    # Testa cálculo de depreciação linear (20% ao ano = 20% em 1 ano)
    deprec = AssetService.calculate_depreciation(asset, annual_rate=0.20)
    assert deprec["initial_value"] == 10000.00
    assert 1800.0 <= deprec["depreciated_amount"] <= 2200.0  # Aproximadamente 20%
    assert 7800.0 <= deprec["current_value"] <= 8200.0

    # Atualização de cadastro
    updated = AssetService.update(db_session, asset.id, AssetUpdate(
        notes="Atualizado com 64GB de memória adicional",
        condition=AssetCondition.GOOD
    ))

    assert updated.notes == "Atualizado com 64GB de memória adicional"
    assert updated.condition == AssetCondition.GOOD
