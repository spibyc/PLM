import contextvars
import uuid
from dataclasses import dataclass, field

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


@dataclass
class Actor:
    """Who is performing an action. Every write service requires one."""

    user_id: uuid.UUID | None
    username: str
    full_name: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    session_id: uuid.UUID | None = None
    ip: str | None = None
    user_agent: str | None = None

    def has(self, perm: str) -> bool:
        return perm in self.permissions

    @classmethod
    def system(cls, name: str) -> "Actor":
        return cls(user_id=None, username=f"system:{name}", full_name=f"System ({name})")
