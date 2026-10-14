from fastapi import APIRouter

from . import (
    accounts,
    dashboard,
    holdings,
    insights,
    items,
    liabilities,
    link,
    me,
    networth,
    overview,
    performance,
    recurring,
    sync,
    tokens,
    transactions,
)

router = APIRouter(prefix="/api/v1")
for mod in (me, overview, networth, accounts, items, link, transactions, holdings, performance, liabilities, insights,
            recurring, dashboard, sync, tokens):
    router.include_router(mod.router)
