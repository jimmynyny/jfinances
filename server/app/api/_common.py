"""Shared helpers for routers: serialisation and errors."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from ..models import Account, PlaidItem


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail={"code": code, "message": message})


def money(v: Decimal | None) -> str | None:
    return None if v is None else format(Decimal(v).quantize(Decimal("0.01")), "f")


def num(v: Decimal | None) -> str | None:
    return None if v is None else format(Decimal(v).normalize(), "f")


def ts(v: datetime | date | None) -> str | None:
    return None if v is None else v.isoformat()


def parse_uuid(value: str, what: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as e:
        raise ApiError(400, "bad_request", f"invalid {what}") from e


def account_json(a: Account, item: PlaidItem | None = None) -> dict[str, Any]:
    item = item or a.item
    return {
        "id": str(a.id),
        "item_id": str(a.item_id) if a.item_id else None,
        "kind": a.kind,
        "name": a.name,
        "official_name": a.official_name,
        "mask": a.mask,
        "type": a.type,
        "subtype": a.subtype,
        "manual_category": a.manual_category,
        "iso_currency": a.iso_currency,
        "current_balance": money(a.current_balance),
        "available_balance": money(a.available_balance),
        "credit_limit": money(a.credit_limit),
        "balance_updated_at": ts(a.balance_updated_at),
        "is_liability": a.is_liability,
        "is_hidden": a.is_hidden,
        "display_order": a.display_order,
        "closed_at": ts(a.closed_at),
        "institution_name": item.institution_name if item else None,
        "institution_id": item.institution_id if item else None,
        "item_status": item.status if item else None,
    }


def item_json(it: PlaidItem) -> dict[str, Any]:
    return {
        "id": str(it.id),
        "plaid_item_id": it.item_id,
        "institution_id": it.institution_id,
        "institution_name": it.institution_name,
        "status": it.status,
        "error_code": it.error_code,
        "error_message": it.error_message,
        "consent_expires_at": ts(it.consent_expires_at),
        "transactions_status": it.transactions_status,
        "last_synced_at": ts(it.last_synced_at),
        "last_webhook_at": ts(it.last_webhook_at),
        "investments_synced_at": ts(it.investments_synced_at),
        "liabilities_synced_at": ts(it.liabilities_synced_at),
        "products": list(it.products or []),
        "account_count": len([a for a in it.accounts if a.closed_at is None]),
        "created_at": ts(it.created_at),
        "removed_at": ts(it.removed_at),
    }
