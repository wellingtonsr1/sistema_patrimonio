import io

from app.models.custodian import Custodian
from app.services.custodian_import_service import (
    parse_custodian_csv,
    preview_custodian_import,
    execute_custodian_import,
    _parse_bool,
)


CSV_VALID = """matricula;nome;email;cargo;setor;cpf;ativo
MAT-2001;Ana Souza;ana.souza@empresa.com;Analista de RH;Recursos Humanos;123.456.789-00;sim
MAT-2002;Bruno Lima;bruno.lima@empresa.com;Desenvolvedor;TI;987.654.321-00;nao
MAT-2003;carla mendes;CARLA.MENDES@empresa.com;Designer;UX;;
"""


def test_parse_custodian_csv_normalizes_columns(db_session):
    """Cabeçalhos com acentos/variantes, e-mail em caixa alta e coluna extra devem ser tratados"""
    csv_content = """Matrícula;Nome Completo;E-mail Corporativo;Função;Departamento;CPF;Status
MAT-3001;Ana Souza;ana.souza@empresa.com;Analista;RH;123.456.789-00;ativo
MAT-3002;Bruno Lima;bruno.lima@empresa.com;Dev;TI;;inativo
"""
    rows, errors = parse_custodian_csv(csv_content)

    assert errors == []
    assert len(rows) == 2

    row1 = rows[0]
    assert row1["registration_code"] == "MAT-3001"
    assert row1["name"] == "Ana Souza"
    assert row1["role"] == "Analista"
    assert row1["department"] == "RH"
    assert row1["is_active"] == "ativo"


def test_parse_custodian_csv_reports_missing_required_fields(db_session):
    """Linhas sem campos obrigatórios geram erros e são descartadas"""
    csv_content = """matricula;nome;email;cargo;setor
MAT-4001;Ana Souza;ana@empresa.com;;TI
;Bruno Lima;bruno@empresa.com;Dev;TI
MAT-4002;;nao-e-email;Dev;TI
"""
    rows, errors = parse_custodian_csv(csv_content)

    assert rows == []
    assert len(errors) == 4
    assert any("cargo é obrigatório" in e for e in errors)
    assert any("matricula é obrigatória" in e for e in errors)
    assert any("nome é obrigatório" in e for e in errors)
    assert any("email inválido" in e for e in errors)


def test_execute_custodian_import_creates_records(db_session):
    rows, errors = parse_custodian_csv(CSV_VALID)
    assert errors == []
    assert len(rows) == 3

    result = execute_custodian_import(rows, db_session)

    assert result["imported"] == 3
    assert result["skipped"] == 0
    assert result["errors"] == []
    assert db_session.query(Custodian).count() == 3

    ana = db_session.query(Custodian).filter(Custodian.registration_code == "MAT-2001").first()
    assert ana is not None
    assert ana.name == "Ana Souza"
    assert ana.is_active is True

    bruno = db_session.query(Custodian).filter(Custodian.registration_code == "MAT-2002").first()
    assert bruno.is_active is False

    carla = db_session.query(Custodian).filter(Custodian.registration_code == "MAT-2003").first()
    assert carla.email == "carla.mendes@empresa.com"
    assert carla.is_active is True  # valor vazio → padrão ativo


def test_execute_custodian_import_skip_and_update_duplicates(db_session):
    # Cria um colaborador que será duplicado no CSV
    from app.services.custodian_service import CustodianService
    from app.schemas.custodian import CustodianCreate

    CustodianService.create(db_session, CustodianCreate(
        registration_code="MAT-2001",
        name="Ana Souza Antiga",
        email="ana.souza@empresa.com",
        role="Estagiária",
        department="RH",
    ))

    rows, errors = parse_custodian_csv(CSV_VALID)
    assert errors == []

    # Com skip_duplicates=True a duplicata é ignorada
    result = execute_custodian_import(rows, db_session, skip_duplicates=True)
    assert result["imported"] == 2
    assert result["skipped"] == 1

    # Com skip_duplicates=False o cadastro existente é atualizado
    result = execute_custodian_import(rows, db_session, skip_duplicates=False)
    assert result["imported"] == 3
    assert result["skipped"] == 0

    ana = db_session.query(Custodian).filter(Custodian.registration_code == "MAT-2001").first()
    assert ana.name == "Ana Souza"
    assert ana.role == "Analista de RH"
    assert ana.is_active is True


def test_preview_custodian_import_counts_duplicates(db_session):
    from app.services.custodian_service import CustodianService
    from app.schemas.custodian import CustodianCreate

    CustodianService.create(db_session, CustodianCreate(
        registration_code="MAT-2001",
        name="Ana Souza",
        email="ana.souza@empresa.com",
        role="Analista",
        department="RH",
    ))

    rows, _ = parse_custodian_csv(CSV_VALID)
    preview = preview_custodian_import(rows, db_session)

    assert preview["total"] == 3
    assert preview["duplicates"] == 1
    assert preview["new_items"] == 2
    dup = [p for p in preview["previews"] if p["is_duplicate"]]
    assert len(dup) == 1
    assert dup[0]["registration_code"] == "MAT-2001"
    assert dup[0]["existing_custodian_id"] is not None


def test_api_import_custodians_csv(client):
    csv_content = """matricula;nome;email;cargo;setor
MAT-5001;Paula Rocha;paula.rocha@empresa.com;Advogada;Jurídico
MAT-5002;Rafael Pinto;rafael.pinto@empresa.com;Contador;Financeiro
"""
    response = client.post(
        "/api/v1/custodians/import/csv",
        files={"file": ("colaboradores.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["imported"] == 2
    assert result["skipped"] == 0
    assert result["errors"] == []
    assert result["parse_errors"] == []

    # Confirma a persistência via endpoint de listagem
    list_res = client.get("/api/v1/custodians")
    assert list_res.status_code == 200
    names = {c["name"] for c in list_res.json()}
    assert {"Paula Rocha", "Rafael Pinto"} <= names


def test_api_import_custodians_csv_rejects_invalid_file(client):
    response = client.post(
        "/api/v1/custodians/import/csv",
        files={"file": ("colaboradores.txt", io.BytesIO(b"matricula;nome").read(), "text/plain")},
    )
    assert response.status_code == 400


def test_web_import_page_renders(client):
    response = client.get("/custodians/import")
    assert response.status_code == 200
    assert "Importar Colaboradores via CSV" in response.text


def test_custodians_list_links_to_report_page(client):
    response = client.get("/custodians")
    assert response.status_code == 200
    assert "/reports/custodians" in response.text
    assert "Exportar CSV" in response.text


def test_web_custodians_report_page_renders(client):
    response = client.get("/reports/custodians")
    assert response.status_code == 200
    assert "Relação de Colaboradores" in response.text
    assert "/api/v1/reports/custodians/csv" in response.text  # botão Baixar CSV
    assert "Imprimir" in response.text


def test_web_import_upload_preview_and_confirm(client):
    csv_content = """matricula;nome;email;cargo;setor
MAT-6001;Paula Rocha;paula.rocha@empresa.com;Advogada;Jurídico
"""
    # Upload gera a pré-visualização
    upload = client.post(
        "/custodians/import",
        files={"file": ("colaboradores.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        data={"skip_duplicates": "true"},
    )
    assert upload.status_code == 200
    assert "Pré-visualização da Importação" in upload.text
    assert "MAT-6001" in upload.text

    # Confirma a importação com os dados que a página envia no textarea oculto
    confirm = client.post(
        "/custodians/import/confirm",
        data={
            "csv_data": '[{"registration_code": "MAT-6001", "name": "Paula Rocha", '
                        '"email": "paula.rocha@empresa.com", "role": "Advogada", "department": "Jurídico"}]',
            "skip_duplicates": "true",
        },
    )
    assert confirm.status_code == 200
    assert "Importação Concluída com Sucesso" in confirm.text

    # Registro persistido e visível na listagem
    list_res = client.get("/api/v1/custodians")
    codes = {c["registration_code"] for c in list_res.json()}
    assert "MAT-6001" in codes


def test_web_import_unchecked_skip_duplicates_updates_existing(client):
    """Checkbox 'Pular duplicatas' desmarcado deve atualizar registros existentes"""
    # Cria colaborador existente via API
    create = client.post("/api/v1/custodians", json={
        "registration_code": "MAT-8001",
        "name": "Nome Antigo",
        "email": "antigo@empresa.com",
        "role": "Estagiário",
        "department": "RH",
    })
    assert create.status_code == 201

    csv_content = "matricula;nome;email;cargo;setor\nMAT-8001;Nome Novo;antigo@empresa.com;Analista;RH\n"

    # Upload SEM o campo skip_duplicates (browser não envia checkbox desmarcado)
    upload = client.post(
        "/custodians/import",
        files={"file": ("colaboradores.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert upload.status_code == 200
    # O preview deve propagar skip_duplicates=false para o formulário de confirmação
    assert 'name="skip_duplicates" value="false"' in upload.text

    # Confirma usando o valor do preview
    confirm = client.post(
        "/custodians/import/confirm",
        data={
            "csv_data": '[{"registration_code": "MAT-8001", "name": "Nome Novo", '
                        '"email": "antigo@empresa.com", "role": "Analista", "department": "RH"}]',
            "skip_duplicates": "false",
        },
    )
    assert confirm.status_code == 200
    assert "Importação Concluída com Sucesso" in confirm.text

    # O cadastro existente foi ATUALIZADO (não pulado)
    list_res = client.get("/api/v1/custodians")
    rows = [c for c in list_res.json() if c["registration_code"] == "MAT-8001"]
    assert len(rows) == 1
    assert rows[0]["name"] == "Nome Novo"
    assert rows[0]["role"] == "Analista"


def test_api_export_custodians_csv_and_round_trip(client):
    # Cria colaboradores via importação para depois exportá-los
    csv_content = """matricula;nome;email;cargo;setor;cpf;ativo
MAT-7001;Fernanda Dias;fernanda.dias@empresa.com;Contadora;Financeiro;111.222.333-44;sim
MAT-7002;Otávio Rocha;otavio.rocha@empresa.com;Analista;TI;555.666.777-88;nao
"""
    imp = client.post(
        "/api/v1/custodians/import/csv",
        files={"file": ("in.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert imp.status_code == 200
    assert imp.json()["imported"] == 2

    # Exporta o CSV de colaboradores
    exp = client.get("/api/v1/reports/custodians/csv")
    assert exp.status_code == 200
    assert "attachment; filename=colaboradores.csv" in exp.headers["content-disposition"]
    assert "text/csv" in exp.headers["content-type"]

    text = exp.content.decode("utf-8")
    assert text.splitlines()[0] == "matricula;nome;email;cargo;setor;cpf;ativo"
    assert "MAT-7001" in text and "Fernanda Dias" in text
    assert "não" in text  # colaborador inativo exportado

    # Round-trip: o arquivo exportado é aceito pelo parser de importação
    rows, errors = parse_custodian_csv(text)
    assert errors == []
    assert len(rows) == 2
    by_code = {r["registration_code"]: r for r in rows}
    assert by_code["MAT-7001"]["cpf"] == "111.222.333-44"
    # A coluna 'ativo' exportada como "não" é interpretada corretamente na reimportação
    assert _parse_bool(by_code["MAT-7002"]["is_active"]) is False
