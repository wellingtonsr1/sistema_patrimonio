"""Testes da correção de localização na importação CSV de equipamentos."""

import io

from app.models.location import Location
from app.models.asset import Asset
from app.services.location_service import LocationService
from app.services.import_service import parse_csv, execute_import
from app.models.movement import Movement


CSV_LOCALIZACAO_VALIDA = """\
tombamento;equipamento;categoria;localização
TEST001;Computador;DESKTOP;Sala de TI
"""

CSV_OUTRA_LOCALIZACAO = """\
tombamento;equipamento;categoria;localizacao
TEST002;Impressora;PRINTER;Laboratório
"""

CSV_LOCALIZACAO_VAZIA = """\
tombamento;equipamento;categoria;localização
TEST003;Monitor;MONITOR;
"""

CSV_LOCALIZACAO_INEXISTENTE = """\
tombamento;equipamento;categoria;loc
TEST004;Mouse;OTHER;Local_Inexistente_TESTE
"""

# REMOVIDO: CSV_LOCALIZACAO_INEXISTENTE_2 nao usado

CSV_MULTIPLOS_EQ = """\
tombamento;equipamento;categoria;localizacao
TEST101;Notebook A;NOTEBOOK;Sala de TI
TEST102;Notebook B;NOTEBOOK;Laboratório
TEST103;Tablet C;SMARTPHONE;Diretoria
TEST104;Mouse D;OTHER;Almoxarifado
"""

CSV_MESMA_LOCALIZACAO = """\
tombamento;equipamento;categoria;loc
TEST201;Caderno A;OTHER;Sala de TI
TEST202;Caneta B;OTHER;Sala de TI
TEST203;Regra C;OTHER;Sala de TI
"""

CSV_MESMA_LOCALIZACAO_ALT = """\
tombamento;equipamento;categoria;localização
TEST211;Caderno X;OTHER;Sala de TI
TEST212;Caneta Y;OTHER;Sala de TI
TEST213;Regra Z;OTHER;Sala de TI
"""

CSV_SEM_LOCALIZACAO = """\
tombamento;equipamento;categoria
TEST301;Projetor;OTHER
"""

CSV_COM_ALIAS_LOCALIZACAO = """\
tombamento;equipamento;categoria;localization
TEST_AL;Mouse;OTHER;Sala de TI
"""


def _criar_locacoes_base(db):
    """Garante as localizações usadas nos testes."""
    locs = [
        ("Sala de TI", "Matriz", "TI"),
        ("Laboratório", "Matriz", "TI"),
        ("Diretoria", "Matriz", " administrativo"),
        ("Almoxarifado", "Matriz", "Logística"),
    ]
    ids = {}
    for nome, branch, dept in locs:
        existing = LocationService.get_by_name(db, nome)
        if not existing:
            loc = Location(name=nome, branch=branch, department=dept)
            db.add(loc)
            db.flush()
            ids[nome] = loc.id
        else:
            ids[nome] = existing.id
    db.commit()
    return ids


def test_import_localizacao_valida(db_session):
    locs = _criar_locacoes_base(db_session)
    rows, errs = parse_csv(CSV_LOCALIZACAO_VALIDA)
    assert errs == []
    assert len(rows) == 1

    result = execute_import(rows, db_session, skip_duplicates=False)
    assert result["imported"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == []

    asset = db_session.query(Asset).filter(Asset.tag == "TEST001").first()
    assert asset is not None
    assert asset.location_id == locs["Sala de TI"]
    # confirmacao final: a localizacao do asset reflete o nome do csv
    assert asset.location is not None
    assert asset.location.name == "Sala de TI"


def test_import_outra_localizacao(db_session):
    locs = _criar_locacoes_base(db_session)
    rows, errs = parse_csv(CSV_OUTRA_LOCALIZACAO)
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    assert result["imported"] == 1

    asset = db_session.query(Asset).filter(Asset.tag == "TEST002").first()
    assert asset.location_id == locs["Laboratório"]
    assert asset.location is not None
    assert asset.location.name == "Laboratório"


def test_import_localizacao_vazia(db_session):
    locs = _criar_locacoes_base(db_session)
    rows, errs = parse_csv(CSV_LOCALIZACAO_VAZIA)
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    # coluna localização com valor vazio -> linha importada sem local
    assert result["imported"] == 1
    assert result["errors"] == []

    asset = db_session.query(Asset).filter(Asset.tag == "TEST003").first()
    assert asset.location_id is None
    assert asset.location is None


def test_import_localizacao_inexistente(db_session):
    locs = _criar_locacoes_base(db_session)
    rows, errs = parse_csv(CSV_LOCALIZACAO_INEXISTENTE)
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    # localizacao inexistente: importa sem local, sem crash
    assert result["imported"] == 1
    assert result["errors"] == []

    asset = db_session.query(Asset).filter(Asset.tag == "TEST004").first()
    assert asset is not None
    assert asset.location_id is None
    assert asset.location is None
    # confirma mecanismo de fallback Estoque Central somente para esse cenario
    mov = db_session.query(Movement).filter(Movement.asset_id==asset.id).first()
    assert mov.destination_location_name == "Estoque Central"


def test_import_localizacao_valida_nao_importa_com_local_inexistente(db_session):
    locs = _criar_locacoes_base(db_session)
    csv = """\
tombamento;equipamento;categoria;localização
TEST_LI;Notebook;NOTEBOOK;Sala_Inexistente
"""
    rows, errs = parse_csv(csv)
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    # localizacao inexistente nao deve importar
    assert result["imported"] == 0
    assert len(result["errors"]) == 1
    assert "Sala_Inexistente" in result["errors"][0]

    asset = db_session.query(Asset).filter(Asset.tag == "TEST_LI").first()
    assert asset is None


def test_import_multiplos_equipamentos(db_session):
    locs = _criar_locacoes_base(db_session)
    rows, errs = parse_csv(CSV_MULTIPLOS_EQ)
    assert errs == []
    assert len(rows) == 4

    result = execute_import(rows, db_session, skip_duplicates=False)
    assert result["imported"] == 4

    asset_rows = db_session.query(Asset).filter(
        Asset.tag.in_(["TEST101", "TEST102", "TEST103", "TEST104"])
    ).all()
    por_tag = {a.tag: a for a in asset_rows}
    assert por_tag["TEST101"].location_id == locs["Sala de TI"]
    assert por_tag["TEST101"].location.name == "Sala de TI"
    assert por_tag["TEST102"].location_id == locs["Laboratório"]
    assert por_tag["TEST102"].location.name == "Laboratório"
    assert por_tag["TEST103"].location_id == locs["Diretoria"]
    assert por_tag["TEST103"].location.name == "Diretoria"
    assert por_tag["TEST104"].location_id == locs["Almoxarifado"]
    assert por_tag["TEST104"].location.name == "Almoxarifado"


def test_import_misma_localizacao(db_session):
    locs = _criar_locacoes_base(db_session)

    rows, errs = parse_csv(CSV_MESMA_LOCALIZACAO_ALT)
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    assert result["imported"] == 3

    sala_ti = locs["Sala de TI"]
    for tag in ["TEST211", "TEST212", "TEST213"]:
        asset = db_session.query(Asset).filter(Asset.tag == tag).first()
        assert asset is not None
        assert asset.location_id == sala_ti
        assert asset.location.name == "Sala de TI"


def test_import_sem_localizacao(db_session):
    locs = _criar_locacoes_base(db_session)
    rows, errs = parse_csv(CSV_SEM_LOCALIZACAO)
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    # CSV sem coluna localização: importa sem local
    assert result["imported"] == 1
    assert result["errors"] == []

    asset = db_session.query(Asset).filter(Asset.tag == "TEST301").first()
    assert asset.location_id is None
    assert asset.location is None


def test_import_com_locacao_alias_localization(db_session):
    locs = _criar_locacoes_base(db_session)
    csv = """\
tombamento;equipamento;categoria;localization
TEST_AL1;Console;OTHER;Sala de TI
"""
    rows, errs = parse_csv(csv)
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    assert result["imported"] == 1

    asset = db_session.query(Asset).filter(Asset.tag == "TEST_AL1").first()
    assert asset.location_id == locs["Sala de TI"]
    assert asset.location is not None
    assert asset.location.name == "Sala de TI"


def test_import_com_alias_loc(db_session):
    locs = _criar_locacoes_base(db_session)
    csv = """\
tombamento;equipamento;categoria;loc
TEST_LOC;Impressora;PRINTER;Sala de TI
"""
    rows, errs = parse_csv(csv)
    # coluna 'loc' nao eh alias atualmente; o parser aceita, mas a linha
    # nao tem coluna de localização reconhecida, entao deve ser importada sem local
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    assert result["imported"] == 1
    assert result["errors"] == []

    asset = db_session.query(Asset).filter(Asset.tag == "TEST_LOC").first()
    assert asset.location_id is None
    assert asset.location is None


def test_import_localizacao_com_acento(db_session):
    locs = _criar_locacoes_base(db_session)
    csv = """\
tombamento;equipamento;categoria;localização
TEST_ACENTO;Tablet;SMARTPHONE;Sala de TI
"""
    rows, errs = parse_csv(csv)
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    assert result["imported"] == 1

    asset = db_session.query(Asset).filter(Asset.tag == "TEST_ACENTO").first()
    assert asset.location_id == locs["Sala de TI"]
    assert asset.location is not None
    assert asset.location.name == "Sala de TI"


def test_import_nao_substitui_estoque_centralQuandoLocalValida(db_session):
    locs = _criar_locacoes_base(db_session)

    csv = """\
tombamento;equipamento;categoria;localização
TEST_EC;Webcam;OTHER;Sala de TI
"""
    rows, errs = parse_csv(csv)
    assert errs == []

    result = execute_import(rows, db_session, skip_duplicates=False)
    assert result["imported"] == 1

    asset = db_session.query(Asset).filter(Asset.tag == "TEST_EC").first()
    assert asset.location_id == locs["Sala de TI"]
    assert asset.location is not None
    assert asset.location.name == "Sala de TI"
