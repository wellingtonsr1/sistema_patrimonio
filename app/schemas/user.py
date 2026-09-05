from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool
    is_admin: bool
    auth_provider: str
    last_login: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserWithPermissions(UserRead):
    """Retorno de /auth/me e /auth/login com as permissões efetivas do usuário."""
    permissions: List[str] = []