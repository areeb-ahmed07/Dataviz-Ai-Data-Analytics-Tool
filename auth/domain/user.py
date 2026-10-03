import datetime
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class Role(str, Enum):
    USER = "user"
    ADMIN = "admin"

@dataclass
class UserDomain:
    id: Optional[int]
    username: str
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime.datetime
    theme: str = "light"
    notifications_enabled: bool = True
