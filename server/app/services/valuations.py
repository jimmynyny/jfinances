"""Market values for offline homes and vehicles, once a month (docs/80 "Valuations").

Homes: RentCast's value estimate (GET https://api.rentcast.io/v1/avm/value with
the address; a price and a low–high range from nearby comparable sales).
Vehicles: MarketCheck Price, Base tier (GET .../v2/predict/car/us/marketcheck_price
with the VIN, today's projected mileage and the ZIP; a dealer-retail price
prediction, with the MSRP), and once per VIN its Basic VIN Decoder to name the
car ("2020 Subaru Outback Limited").

The rule that matters: every request is recorded in `valuations` *before* it
is sent, and that table is unique per account, provider, kind and month, so an
asset is asked about at most once a calendar month whatever runs, reruns or
crashes. Each provider also has a monthly ceiling under its free tier (RentCast
bills every successful request past 50 a month and can't be capped on its side;
MarketCheck's free plan has 500): past it, requests wait for next month. Nobody
can ask sooner: there is no endpoint or button for it, only the daily job.

Keys come from the environment (RENTCAST_API_KEY, MARKETCHECK_API_KEY); one
travels in a header, the other in the query string, so errors keep only a
status code, never a URL or an exception's text, and httpx's request log is
off (logging.py).
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings, settings
from ..models import Account, AssetDetails, BalanceSnapshot, Valuation

log = logging.getLogger(__name__)

RENTCAST_URL = "https://api.rentcast.io/v1/avm/value"
MARKETCHECK_PRICE_URL = "https://api.marketcheck.com/v2/predict/car/us/marketcheck_price"
MARKETCHECK_DECODE_URL = "https://api.marketcheck.com/v2/decode/car/{vin}/specs"
#: Requests a provider may get in a calendar month, all assets together: under each free tier.
MONTHLY_CEILING = {"rentcast": 40, "marketcheck": 400}
#: Sandbox (and local) share production's keys, so their free requests: they get a sliver.
TESTING_CEILING = {"rentcast": 5, "marketcheck": 50}
#: The paces a person can choose for a car (miles a month); 1,000 until they do.
PACES = (100, 250, 500, 750, 1000, 1500, 2000)
DEFAULT_MILES_PER_MONTH = 1000
VIN = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
PROPERTY_TYPES = ("Single Family", "Condo", "Townhouse", "Multi-Family", "Manufactured", "Land")
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class ProviderError(RuntimeError):
    """A provider didn't give a value. The message is safe to keep (no URL, no key)."""


def month_of(d: date) -> date:
    return d.replace(day=1)


def kind_of(a: Account) -> str | None:
    """home | vehicle, for an offline account that can be valued."""
    if a.kind != "manual" or a.closed_at is not None:
        return None
    return {"real_estate": "home", "vehicle": "vehicle"}.get(a.manual_category or "")


def miles_per_month(det: AssetDetails) -> int:
    """The pace the person chose, else 1,000 a month."""
    return det.miles_per_month if det.miles_per_month in PACES else DEFAULT_MILES_PER_MONTH


def projected_miles(det: AssetDetails, today: date) -> int | None:
    """Today's mileage: the last reading, plus its pace for the time since."""
    if det.mileage is None:
        return None
    if det.mileage_as_of is None or det.mileage_as_of >= today:
        return det.mileage
    return det.mileage + round(miles_per_month(det) * (today - det.mileage_as_of).days / 30.44)


def vehicle_zip(sess: Session, det: AssetDetails) -> str | None:
    """Where a car is priced: the home it's kept at (that home's ZIP), else the ZIP typed for it."""
    if det.garage_account_id is not None:
        home = sess.get(AssetDetails, det.garage_account_id)
        if home is not None and home.zip:
            return home.zip
    return det.zip


def missing(a: Account, det: AssetDetails | None, sess: Session | None = None) -> list[str]:
    """What a valuation still needs from the person."""
    k = kind_of(a)
    if k is None:
        return []
    if det is None:
        return ["address", "city", "state", "zip"] if k == "home" else ["vin", "mileage", "location"]
    if k == "home":
        return [f for f, v in (("address", det.address_line), ("city", det.city), ("state", det.state),
                               ("zip", det.zip)) if not v]
    where = vehicle_zip(sess, det) if sess is not None else det.zip
    return [f for f, v in (("vin", det.vin), ("mileage", det.mileage), ("location", where)) if v in (None, "")]


def provider_for(a: Account) -> str | None:
    return {"home": "rentcast", "vehicle": "marketcheck"}.get(kind_of(a) or "")


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d.quantize(Decimal("0.01")) if d > 0 else None


def _get(client: httpx.Client, url: str, **kw) -> dict:
    """GET and JSON, or ProviderError carrying only what is safe to keep."""
    try:
        r = client.get(url, timeout=TIMEOUT, **kw)
    except httpx.HTTPError as e:
        raise ProviderError(f"no answer ({type(e).__name__})") from None
    if r.status_code != 200:
        raise ProviderError(f"HTTP {r.status_code}")
    try:
        body = r.json()
    except ValueError:
        raise ProviderError("not JSON") from None
    if not isinstance(body, dict):
        raise ProviderError("unexpected answer")
    return body


def rentcast_value(client: httpx.Client, det: AssetDetails, key: str) -> tuple[Decimal, Decimal | None,
                                                                             Decimal | None, dict]:
    params: dict[str, Any] = {"address": f"{det.address_line}, {det.city}, {det.state}, {det.zip}"}
    if det.property_type:
        params["propertyType"] = det.property_type
    for name, v in (("bedrooms", det.bedrooms), ("bathrooms", det.bathrooms), ("squareFootage", det.square_feet)):
        if v is not None:
            params[name] = str(v)
    body = _get(client, RENTCAST_URL, params=params, headers={"X-Api-Key": key, "Accept": "application/json"})
    price = _money(body.get("price"))
    if price is None:
        raise ProviderError("no price for this address")
    comps = body.get("comparables") or []
    return price, _money(body.get("priceRangeLow")), _money(body.get("priceRangeHigh")), {
        "comparables": len(comps) if isinstance(comps, list) else None,
        "property_type": body.get("propertyType"), "square_feet": body.get("squareFootage")}


def marketcheck_price(client: httpx.Client, det: AssetDetails, miles: int, zip_: str,
                      key: str) -> tuple[Decimal, dict]:
    body = _get(client, MARKETCHECK_PRICE_URL, params={
        "api_key": key, "vin": det.vin, "miles": str(miles), "zip": zip_, "dealer_type": "independent"})
    price = _money(body.get("marketcheck_price"))
    if price is None:
        raise ProviderError("no price for this VIN")
    return price, {"msrp": str(_money(body.get("msrp")) or "") or None, "basis": "dealer retail (independent)"}


def marketcheck_decode(client: httpx.Client, vin: str, key: str) -> str | None:
    body = _get(client, MARKETCHECK_DECODE_URL.format(vin=vin), params={"api_key": key})
    words = [str(body.get(k)).strip() for k in ("year", "make", "model", "trim") if body.get(k)]
    return " ".join(words)[:200] or None


def ceiling(provider: str, s: Settings) -> int:
    """The month's requests to a provider, in this environment."""
    full = MONTHLY_CEILING[provider]
    return full if s.app_env == "production" else min(full, TESTING_CEILING[provider])


def reserve(sess: Session, a: Account, provider: str, kind: str, today: date, inputs: dict,
            s: Settings) -> Valuation | None:
    """Record a request before it is sent. None: this asset was asked this month, or the
    provider's monthly ceiling is reached (then a `skipped` row holds the month)."""
    month = month_of(today)
    used = sess.execute(select(func.count()).select_from(Valuation).where(
        Valuation.provider == provider, Valuation.month == month, Valuation.status != "skipped")).scalar() or 0
    limit = ceiling(provider, s)
    over = used >= limit
    row = Valuation(account_id=a.id, provider=provider, kind=kind, month=month, as_of=today, inputs=inputs,
                    status="skipped" if over else "pending",
                    error=f"over the {limit} requests a month" if over else None)
    try:
        with sess.begin_nested():
            sess.add(row)
            sess.flush()
    except IntegrityError:
        return None  # asked already this month
    sess.commit()  # on record before anything is sent: a crash after the request still counts it
    return None if over else row


def _record_value(sess: Session, a: Account, value: Decimal, today: date) -> None:
    """The asset is worth this now: its balance, and today's point in its history.
    The market value wins over a value typed earlier the same day (the one typed
    when the asset was added); one typed after it wins in turn (PUT .../value).
    Balance and history always move together, or the headline and the charts disagree."""
    a.current_balance = value
    a.balance_updated_at = datetime.now(UTC)
    snap = sess.execute(select(BalanceSnapshot).where(BalanceSnapshot.account_id == a.id,
                                                      BalanceSnapshot.as_of == today)).scalar_one_or_none()
    if snap is None:
        sess.add(BalanceSnapshot(account_id=a.id, as_of=today, current_balance=value, source="valuation"))
    else:
        snap.current_balance, snap.source = value, "valuation"


def value_asset(sess: Session, a: Account, det: AssetDetails, today: date, client: httpx.Client,
                s: Settings) -> str:
    """Ask for this month's value if it's due. Returns what happened, for the job's log."""
    provider = provider_for(a)
    if provider is None or not det.valuation_enabled or missing(a, det, sess):
        return "not ready"
    key = s.rentcast_api_key if provider == "rentcast" else s.marketcheck_api_key
    if not key:
        return "no key"
    if provider == "marketcheck" and det.decoded_vin != det.vin:
        decode = reserve(sess, a, provider, "decode", today, {"vin": det.vin}, s)
        if decode is not None:
            try:
                label = marketcheck_decode(client, det.vin, key)
                det.vehicle_label, det.decoded_vin = label, det.vin
                decode.status, decode.detail = ("ok" if label else "no_value"), {"label": label}
            except ProviderError as e:
                decode.status, decode.error = "error", str(e)[:300]
            sess.commit()
    if provider == "rentcast":
        inputs = {"address": det.address_line, "city": det.city, "state": det.state, "zip": det.zip,
                  "property_type": det.property_type}
    else:
        inputs = {"vin": det.vin, "miles": projected_miles(det, today), "zip": vehicle_zip(sess, det),
                  "miles_per_month": miles_per_month(det)}
    row = reserve(sess, a, provider, "value", today, inputs, s)
    if row is None:
        return "already this month"
    try:
        if provider == "rentcast":
            value, low, high, detail = rentcast_value(client, det, key)
        else:
            value, detail = marketcheck_price(client, det, inputs["miles"], inputs["zip"], key)
            low = high = None
        row.status, row.value, row.low, row.high, row.detail = "ok", value, low, high, detail
        _record_value(sess, a, value, today)
        result = "valued"
    except ProviderError as e:
        row.status = "no_value" if str(e).startswith("no price") else "error"
        row.error = str(e)[:300]
        result = row.status
    sess.commit()
    return result


def run(sess: Session, today: date | None = None, client: httpx.Client | None = None,
        s: Settings | None = None) -> dict[str, int]:
    """Every offline home and vehicle whose month hasn't been asked yet."""
    today = today or datetime.now(UTC).date()
    s = s or settings()
    rows = sess.execute(select(Account, AssetDetails).join(AssetDetails, AssetDetails.account_id == Account.id)
                        .where(Account.kind == "manual", Account.closed_at.is_(None),
                               Account.manual_category.in_(("real_estate", "vehicle")))).all()
    counts: dict[str, int] = {}
    own = client is None
    client = client or httpx.Client(follow_redirects=False)
    try:
        for a, det in rows:
            what = value_asset(sess, a, det, today, client, s)
            counts[what] = counts.get(what, 0) + 1
    finally:
        if own:
            client.close()
    log.info("valuations: %s", counts)
    return counts


def details_json(a: Account, det: AssetDetails | None, sess: Session, today: date) -> dict:
    """What the account page shows: the inputs, what's missing, and the recent values."""
    history = sess.execute(select(Valuation).where(Valuation.account_id == a.id, Valuation.kind == "value")
                           .order_by(Valuation.month.desc()).limit(12)).scalars().all()
    asked = any(v.month == month_of(today) for v in history)
    nxt = month_of(today) if not asked else date(today.year + today.month // 12, today.month % 12 + 1, 1)
    out: dict[str, Any] = {
        "kind": kind_of(a), "provider": provider_for(a), "missing": missing(a, det, sess), "paces": list(PACES),
        "next_month": nxt.isoformat() if kind_of(a) else None,
        "valuations": [{"month": v.month.isoformat(), "as_of": v.as_of.isoformat(), "status": v.status,
                        "value": str(v.value) if v.value is not None else None,
                        "low": str(v.low) if v.low is not None else None,
                        "high": str(v.high) if v.high is not None else None,
                        "inputs": v.inputs, "detail": v.detail, "error": v.error} for v in history],
        "details": None,
    }
    if det is not None:
        out["valuation_enabled"] = det.valuation_enabled
        out["details"] = {
            "address_line": det.address_line, "city": det.city, "state": det.state, "zip": det.zip,
            "property_type": det.property_type, "bedrooms": det.bedrooms,
            "bathrooms": str(det.bathrooms) if det.bathrooms is not None else None, "square_feet": det.square_feet,
            "vin": det.vin, "mileage": det.mileage,
            "mileage_as_of": det.mileage_as_of.isoformat() if det.mileage_as_of else None,
            "miles_per_month": miles_per_month(det),
            "garage_account_id": str(det.garage_account_id) if det.garage_account_id else None,
            "vehicle_label": det.vehicle_label}
        out["projected_miles"] = projected_miles(det, today)
        out["priced_at_zip"] = vehicle_zip(sess, det) if kind_of(a) == "vehicle" else None
    return out
