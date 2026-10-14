from fastapi import APIRouter

from . import (
    accounts,
    dashboard,
    glance,
    holdings,
    imports,
    insights,
    items,
    liabilities,
    link,
    me,
    mobile,
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
            recurring, dashboard, glance, sync, tokens, mobile, imports):
    router.include_router(mod.router)
