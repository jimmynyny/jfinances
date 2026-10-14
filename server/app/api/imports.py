"""Bank exports into a linked account's history (services/importer.py).

The browser sends the file itself (base64 in JSON: no multipart parser, and
nothing is stored but its name and hash). Preview reads and classifies without
writing; import applies the same reading with the person's confirmed columns
and ticks. docs/80 "Imports".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import current_user, dashboard_only
from ..auth.human import Principal
from ..db import get_session
from ..models import Account, Import
from ..services import importer
from ..services import statement as st
from ._common import ApiError, parse_uuid

router = APIRouter()


class FileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=200)
    #: The file's bytes, base64. 5 MB at most once decoded.
    content_b64: str = Field(min_length=4, max_length=7_200_000)
    account_id: str | None = None
    #: A CSV's columns as confirmed (statement.Mapping); omitted: worked out from the file.
    mapping: dict | None = None


class ApplyIn(FileIn):
    account_id: str
    #: Rows in the connection's period that the person ticked to add anyway (their `index`).
    include: list[int] = Field(default_factory=list, max_length=50_000)


def _account(sess: Session, account_id: str | None) -> Account | None:
    if not account_id:
        return None
    a = sess.get(Account, parse_uuid(account_id, "account_id"))
    if a is None:
        raise ApiError(404, "not_found", "account not found")
    if not importable(a):
        raise ApiError(400, "bad_request", "history can be imported into linked bank and card accounts only")
    return a


def importable(a: Account) -> bool:
    return importer.importable(a)


def _read(sess: Session, body: FileIn, a: Account | None) -> tuple[bytes, st.Parsed, Account | None]:
    try:
        raw = importer.read_file(body.content_b64)
    except importer.ImportProblem as e:
        raise ApiError(400, "bad_file", str(e)) from e
    mapping = st.Mapping.from_json(body.mapping) if body.mapping else importer.profile_mapping(sess, raw, body.filename)
    probe = st.parse(raw, body.filename, liability=bool(a and a.is_liability), mapping=mapping)
    if a is None:
        a = importer.suggest_account(sess, probe)
    parsed = importer.read(sess, a, raw, body.filename, mapping) if a is not None else probe
    if not parsed.rows:
        detail = "; ".join(parsed.problems[:3]) or "no transactions found"
        raise ApiError(400, "bad_file", f"couldn't read transactions from this file ({detail})")
    return raw, parsed, a


@router.post("/imports/preview")
def preview(body: FileIn, _: Principal = Depends(dashboard_only), sess: Session = Depends(get_session)):
    """What importing this file would do. Writes nothing."""
    raw, parsed, a = _read(sess, body, _account(sess, body.account_id))
    if a is None:
        # No account chosen and none recognized: the columns and rows still show, statuses wait for one.
        return {"account_id": None, "format": parsed.format, "account_hint": parsed.account_hint,
                "columns": [{"index": c.index, "header": c.header, "samples": c.samples, "role": c.role}
                            for c in parsed.columns],
                "mapping": parsed.mapping.json() if parsed.mapping else None, "date_ambiguous": parsed.date_ambiguous,
                "counts": {"total": len(parsed.rows)}, "rows": [], "problems": parsed.problems[:20]}
    return {**importer.preview(sess, a, parsed), "account_hint": parsed.account_hint}


@router.post("/imports", status_code=201)
def apply(body: ApplyIn, p: Principal = Depends(dashboard_only), sess: Session = Depends(get_session)):
    a = _account(sess, body.account_id)
    raw, parsed, a = _read(sess, body, a)
    imp = importer.apply(sess, a, parsed, raw=raw, filename=body.filename, include=set(body.include),
                         user_id=p.user_id)
    from ..jobs.queue import enqueue
    enqueue(sess, "detect_recurring", {})  # longer history finds more subscriptions
    return importer.import_json(imp)


@router.get("/imports")
def list_imports(account_id: str | None = Query(default=None), _: Principal = Depends(current_user),
                 sess: Session = Depends(get_session)):
    q = select(Import).order_by(Import.created_at.desc()).limit(200)
    if account_id:
        q = q.where(Import.account_id == parse_uuid(account_id, "account_id"))
    return {"imports": [importer.import_json(i) for i in sess.execute(q).scalars()]}


@router.delete("/imports/{import_id}")
def undo(import_id: str, _: Principal = Depends(dashboard_only), sess: Session = Depends(get_session)):
    imp = sess.get(Import, parse_uuid(import_id))
    if imp is None:
        raise ApiError(404, "not_found", "import not found")
    if imp.status == "undone":
        raise ApiError(409, "conflict", "already undone")
    removed = importer.undo(sess, imp)
    return {**importer.import_json(imp), "removed": removed}
