def test_api_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_api_create_asset_and_move(client):
    # 1. Cria local via API
    loc_res = client.post("/api/v1/locations", json={
        "name": "Laboratório TI",
        "branch": "Matriz",
        "department": "TI"
    })
    assert loc_res.status_code == 201
    loc_id = loc_res.json()["id"]

    # 2. Cria Colaborador via API
    cust_res = client.post("/api/v1/custodians", json={
        "registration_code": "MAT-9999",
        "name": "Ana Silva",
        "email": "ana.silva@empresa.com",
        "role": "Engenheira",
        "department": "TI"
    })
    assert cust_res.status_code == 201
    cust_id = cust_res.json()["id"]

    # 3. Cria Ativo via API
    asset_res = client.post("/api/v1/assets", json={
        "tag": "PAT-77001",
        "name": "Notebook Dell XPS 13",
        "category": "NOTEBOOK",
        "purchase_value": 8500.0,
        "initial_location_id": loc_id
    })
    assert asset_res.status_code == 201
    asset_id = asset_res.json()["id"]

    # 4. Registra Movimentação via API REST
    move_res = client.post("/api/v1/movements", json={
        "asset_id": asset_id,
        "movement_type": "ALOCACAO_CAUTELA",
        "destination_custodian_id": cust_id,
        "reason": "Alocação para novos projetos",
        "operator_name": "API Tester"
    })
    assert move_res.status_code == 201
    move_id = move_res.json()["id"]

    # 5. Consulta a timeline do equipamento pela API
    timeline_res = client.get(f"/api/v1/assets/{asset_id}/timeline")
    assert timeline_res.status_code == 200
    timeline = timeline_res.json()
    assert len(timeline) == 2

    # 6. Consulta os dados do Termo de Responsabilidade pela API
    term_res = client.get(f"/api/v1/movements/{move_id}/term")
    assert term_res.status_code == 200
    term_data = term_res.json()
    assert term_data["custodian"]["name"] == "Ana Silva"
    assert term_data["asset"]["tag"] == "PAT-77001"


# ============================================
# Violações de unicidade devem retornar 400 (não 500)
# ============================================


def test_api_duplicate_custodian_email_returns_400(client):
    base = {
        "registration_code": "MAT-1001",
        "name": "Primeiro",
        "email": "duplicado@empresa.com",
        "role": "Analista",
        "department": "RH",
    }
    assert client.post("/api/v1/custodians", json=base).status_code == 201

    res = client.post("/api/v1/custodians", json={**base, "registration_code": "MAT-1002", "name": "Segundo"})
    assert res.status_code == 400
    assert "E-mail já cadastrado" in res.json()["detail"]


def test_api_duplicate_custodian_registration_on_update_returns_400(client):
    for code, name, email in [("MAT-2001", "Um", "um@empresa.com"), ("MAT-2002", "Dois", "dois@empresa.com")]:
        res = client.post("/api/v1/custodians", json={
            "registration_code": code, "name": name, "email": email, "role": "Dev", "department": "TI"
        })
        assert res.status_code == 201

    # Tenta alterar a matrícula do segundo para a matrícula do primeiro
    second_id = [c["id"] for c in client.get("/api/v1/custodians").json() if c["registration_code"] == "MAT-2002"][0]
    res = client.put(f"/api/v1/custodians/{second_id}", json={"registration_code": "MAT-2001"})
    assert res.status_code == 400
    assert "Matrícula já cadastrada" in res.json()["detail"]


def test_api_duplicate_asset_serial_returns_400(client):
    # Bem A com serial
    assert client.post("/api/v1/assets", json={
        "tag": "PAT-3001", "name": "Notebook A", "category": "NOTEBOOK", "serial_number": "SN-0001"
    }).status_code == 201

    # Bem B sem serial (candidato a receber serial duplicado via PUT)
    b_res = client.post("/api/v1/assets", json={"tag": "PAT-3002", "name": "Notebook B", "category": "NOTEBOOK"})
    assert b_res.status_code == 201
    asset_b_id = b_res.json()["id"]

    # Mesmo serial em outro tombamento → 400 no create
    res = client.post("/api/v1/assets", json={
        "tag": "PAT-3003", "name": "Notebook C", "category": "NOTEBOOK", "serial_number": "SN-0001"
    })
    assert res.status_code == 400
    assert "número de série" in res.json()["detail"]

    # PUT tentando assumir serial de outro bem → 400 no update
    res2 = client.put(f"/api/v1/assets/{asset_b_id}", json={"serial_number": "SN-0001"})
    assert res2.status_code == 400
    assert "número de série" in res2.json()["detail"]


def test_api_duplicate_location_name_on_update_returns_400(client):
    assert client.post("/api/v1/locations", json={
        "name": "Sala A", "branch": "Matriz", "department": "TI"
    }).status_code == 201
    assert client.post("/api/v1/locations", json={
        "name": "Sala B", "branch": "Matriz", "department": "TI"
    }).status_code == 201

    res = client.put("/api/v1/locations/2", json={"name": "Sala A"})
    assert res.status_code == 400
    assert "nome" in res.json()["detail"]


def test_web_custodian_duplicate_email_shows_friendly_error(client):
    assert client.post("/api/v1/custodians", json={
        "registration_code": "MAT-4001", "name": "Existente", "email": "existe@empresa.com",
        "role": "Analista", "department": "RH",
    }).status_code == 201

    res = client.post(
        "/custodians/new",
        data={
            "registration_code": "MAT-4002",
            "name": "Novo",
            "email": "existe@empresa.com",
            "role": "Dev",
            "department": "TI",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "error=" in res.headers["location"]

    # A página do formulário exibe a mensagem amigável
    page = client.get(res.headers["location"])
    assert page.status_code == 200
    assert "E-mail já cadastrado" in page.text
