from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth.deps import current_user
from ..auth.human import Principal
from ..config import settings

router = APIRouter()


@router.get("/me")
def me(p: Principal = Depends(current_user)):
    s = settings()
    return {
        "email": p.email,
        "display_name": p.display_name,
        "role": p.role,
        "via": p.via,
        "session_expires_at": p.session_expires_at.isoformat() if p.session_expires_at else None,
        "env": s.app_env,
        "plaid_env": s.plaid_env,
    }
