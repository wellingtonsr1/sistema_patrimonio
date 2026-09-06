from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base


class ADSettings(Base):
    """
    Configuração da integração com Active Directory / Samba AD (singleton id=1).

    Armazena em banco apenas os parâmetros NÃO sensíveis da conexão e o
    comportamento do provisionamento. A senha do usuário de serviço (bind)
    NUNCA é gravada no banco — vem de variáveis de ambiente (AD_BIND_PASSWORD).

    Prioridade: se existir linha no banco (enable_ad marcado), o administrador
    usa a tela Integração AD; as variáveis de ambiente AD_* continuam
    funcionando como fallback (config.py) para quem preferir operar por env.
    """
    __tablename__ = "ad_settings"

    id = Column(Integer, primary_key=True)  # singleton: sempre 1

    # --- Conexão ---
    enabled = Column(Boolean, default=False, nullable=False)
    server = Column(String(255), nullable=False, default="")
    port = Column(Integer, nullable=False, default=636)
    use_ldaps = Column(Boolean, default=True, nullable=False)
    verify_tls = Column(Boolean, default=True, nullable=False)       # validar certificado TLS
    base_dn = Column(String(255), nullable=False, default="")
    search_dn = Column(String(255), nullable=True)                   # escopo da busca de usuários (ou None = base_dn)
    bind_user = Column(String(255), nullable=True)                   # DN/upn do usuário de serviço (consulta)
    timeout_seconds = Column(Integer, nullable=False, default=10)

    # --- Provisionamento / vínculo ---
    auto_create_user = Column(Boolean, default=True, nullable=False)     # provisiona usuário no 1º login
    link_by_email = Column(Boolean, default=True, nullable=False)        # vincula colaborador por e-mail
    group_role_priority = Column(String(255), nullable=True)             # CSV de nomes de grupos; vazio = ordem de criação
    disabled_behavior = Column(String(20), default="deny", nullable=False)  # deny | block (conta desabilitada no AD)

    # --- Metadados ---
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<ADSettings(id={self.id}, server='{self.server}', enabled={self.enabled})>"
