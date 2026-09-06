from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import DATABASE_URL

# Configuração do SQLite com suporte a multithreading no FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency para obter sessão do banco de dados no FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_schema_migrations():
    """
    Migrações leves e idempotentes para tabelas já existentes (SQLite).

    `Base.metadata.create_all` cria apenas tabelas novas; para adicionar
    colunas em tabelas existentes (ex: `users` com dados reais) usamos
    `ALTER TABLE ... ADD COLUMN` apenas quando a coluna ainda não existe.
    Nenhum dado existente é alterado ou removido.
    """
    with engine.connect() as conn:
        # Colunas de proteção contra força bruta em `users`
        existing_users_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
        if "failed_login_attempts" not in existing_users_cols:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0 NOT NULL"
            ))
        if "locked_until" not in existing_users_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN locked_until DATETIME"))

        # Integração Active Directory: colunas adicionais em `users`
        # (autônoma: usuários locais permanecem NULL em todas)
        for _col, _ddl in (
            ("ad_object_guid", "VARCHAR(64)"),
            ("ad_dn", "VARCHAR(400)"),
            ("ad_last_sync", "DATETIME"),
        ):
            if _col not in existing_users_cols:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {_col} {_ddl}"))

        # Origem da atribuição de perfil em `user_roles` ('local' | 'ad')
        existing_user_roles_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(user_roles)"))
        }
        if "assigned_by" not in existing_user_roles_cols:
            conn.execute(text(
                "ALTER TABLE user_roles ADD COLUMN assigned_by VARCHAR(20) "
                "DEFAULT 'local' NOT NULL"
            ))

        conn.commit()


def init_db():
    """Inicializa as tabelas do banco de dados"""
    # Importa todos os modelos para garantir que estão registrados no Base.metadata
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ensure_schema_migrations()
