from __future__ import annotations

from enum import StrEnum


class Code(StrEnum):
    NO_CREDENTIAL = "auth.missing_credential"
    BAD_ACCESS_JWT = "auth.bad_access_jwt"
    BAD_TOKEN = "auth.bad_token"
    NOT_ALLOWED = "auth.not_allowed"
    FORBIDDEN = "auth.forbidden"
    NOT_CONFIGURED = "auth.not_configured"


class AuthError(Exception):
    def __init__(self, code: Code, message: str, status: int = 401):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
