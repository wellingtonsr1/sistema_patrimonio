import os

# Configurações de autenticação para os testes (devem vir antes dos imports do app)
os.environ.setdefault("AUTH_PBKDF2_ITERATIONS", "1000")   # hash rápido nos testes
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.services.auth_service import create_user

# Banco de dados de teste SQLite em memória compartilhado usando StaticPool
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_USERNAME = "testuser"
TEST_PASSWORD = "teste@1234"


@pytest.fixture(scope="function")
def db_session():
    """Cria as tabelas no banco de teste antes de cada teste e limpa ao final"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _create_test_user():
    """Cria o usuário de teste usado pelo fixture `client`."""
    db = TestingSessionLocal()
    try:
        return create_user(
            db,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            full_name="Usuário de Teste",
            is_admin=True,
        )
    finally:
        db.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Cliente autenticado (sessão válida) para os testes que exercitam o fluxo normal."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        _create_test_user()
        login = test_client.post(
            "/api/v1/auth/login",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        )
        assert login.status_code == 200, login.text
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def unauth_client(db_session):
    """Cliente SEM sessão, para testar bloqueio de acesso não autenticado."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()