from datetime import datetime

from sqlalchemy import Column, DateTime, Integer

from app.database import Base


class SetupClaim(Base):
    """
    Reivindicação atômica do primeiro acesso (singleton `id=1`).

    A chave primária é a garantia de exclusividade: apenas UMA requisição
    consegue inserir esta linha. Quem reivindica cria o primeiro
    administrador no mesmo commit; as requisições concorrentes recebem
    violação de unicidade (ou bloqueio de escrita do SQLite) e são
    redirecionadas ao login, sem criar um segundo administrador.

    A linha existe apenas para serializar o bootstrap: depois que o primeiro
    administrador é criado, o fluxo de primeiro acesso já fica desabilitado
    por existir usuário no banco.
    """

    __tablename__ = "setup_claims"

    id = Column(Integer, primary_key=True)  # singleton: sempre 1
    claimed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<SetupClaim(id={self.id}, claimed_at='{self.claimed_at}')>"
