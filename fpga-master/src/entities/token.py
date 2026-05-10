from dataclasses import dataclass, field
from typing import Optional


ROLES = ("admin", "operator", "viewer")

ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}


@dataclass
class ClusterToken:
    token_id: str
    token: str
    role: str
    description: str
    created_at: int
    expires_at: Optional[int]
    is_root: bool = False

    def to_dict(self) -> dict:
        return {
            "token_id": self.token_id,
            "token": self.token,
            "role": self.role,
            "description": self.description,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "is_root": self.is_root,
        }

    def to_safe_dict(self) -> dict:
        """Dict without plaintext token value (for listings)."""
        d = self.to_dict()
        d.pop("token", None)
        return d
