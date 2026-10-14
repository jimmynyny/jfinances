"""Phone audit: every page and open state in headless Chrome at the given widths,
flagging text that is clipped, cut by its container, off-screen, overlapping or
touching (detect.js), with scroll-by-scroll screenshots (docs/70 "Phone widths").

Run against the local stack (Vite on :5173, API with DEV_LOGIN_EMAIL):

    uv run python ops/phone_audit/audit.py /tmp/audit 402 360 768 1280
    SCHEMES=light uv run python ops/phone_audit/audit.py /tmp/audit-light 402
    python3 ops/phone_audit/sheets.py /tmp/audit /tmp/audit/sheets 402   # needs Pillow

Writes <outdir>/<width>-<scheme>-<state>~NN.png and <outdir>/issues.json, and
prints one line per state; all zeros is clean.
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333
BASE = os.environ.get("AUDIT_BASE", "http://127.0.0.1:5173")
HERE = os.path.dirname(os.path.abspath(__file__))
DETECT = open(os.path.join(HERE, "detect.js")).read()

CLICK_FIRST_ACCOUNT = """(() => {
  const b = document.querySelector('.jf-acct__openbtn');
  if (b) { b.click(); return b.textContent } return null })()"""
CLICK_FIRST_TXN = """(() => {
  const r = document.querySelector('tbody tr, .jf-txn, [data-txn]');
  if (r) { (r.querySelector('button') || r).click(); return r.textContent.slice(0,40) } return null })()"""
CLICK_TEXT = """((sel, re) => {
  const el = [...document.querySelectorAll(sel)].find(e => new RegExp(re).test(e.textContent.trim()));
  if (el) { el.click(); return el.textContent.trim().slice(0,40) } return null })"""
OPEN_MENU = """(() => { const t = document.querySelector('.mu-side__toggle'); t && t.click(); return !!t })()"""

PAGES = [
    ("overview", "/", {}, []),
    ("overview-edit", "/", {}, [CLICK_TEXT + "('button', '^Edit dashboard$')"]),
    ("accounts", "/accounts", {}, []),
    ("accounts-drawer", "/accounts", {}, [CLICK_FIRST_ACCOUNT]),
    ("transactions", "/transactions", {}, []),
    ("transactions-drawer", "/transactions", {}, [CLICK_FIRST_TXN]),
    ("investments", "/investments", {}, []),
    ("liabilities", "/liabilities", {}, []),
    ("insights-cashflow", "/insights", {"jf.insights.tab": "cashflow"}, []),
    ("insights-spending", "/insights", {"jf.insights.tab": "spending"}, []),
    ("insights-subscriptions", "/insights", {"jf.insights.tab": "subscriptions"}, []),
    ("insights-wealth", "/insights", {"jf.insights.tab": "wealth"}, []),
    ("settings", "/settings", {}, []),
    ("import", "/import", {}, []),
    ("menu", "/", {}, [OPEN_MENU]),
    ("notfound", "/nope", {}, []),
]


class Page:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method, params=None, timeout=30):
        self.n += 1
        mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=timeout))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(method)

    async def js(self, expr):
        r = await self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            return {"__error__": r["exceptionDetails"].get("text"), "detail": str(r["exceptionDetails"])[:300]}
        return r.get("result", {}).get("value")

    async def settle(self, max_s=10):
        """Wait for the SPA to finish loading: no skeletons, no pending fetches for a moment."""
        t0 = time.time()
        await asyncio.sleep(0.8)
        while time.time() - t0 < max_s:
            busy = await self.js("document.readyState !== 'complete'"
                                 " || document.querySelectorAll('.mu-skel, [aria-busy=\"true\"]').length")
            if not busy:
                break
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.6)


async def run(outdir, widths, schemes):
    os.makedirs(outdir, exist_ok=True)
    prof = os.path.join(outdir, ".chrome")
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}",
                             "--hide-scrollbars", "--disable-gpu", "--no-first-run", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")
        target = json.load(urllib.request.urlopen(req))
        report = {}
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=2**28) as ws:
            p = Page(ws)
            await p.call("Page.enable")
            await p.call("Runtime.enable")
            for width in widths:
                for scheme in schemes:
                    await p.call("Emulation.setDeviceMetricsOverride",
                                 {"width": width, "height": 844, "deviceScaleFactor": 2, "mobile": True})
                    await p.call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
                    await p.call("Emulation.setEmulatedMedia",
                                 {"features": [{"name": "prefers-color-scheme", "value": scheme}]})
                    for name, path, storage, actions in PAGES:
                        await p.call("Page.navigate", {"url": BASE + "/"})
                        await p.settle(6)
                        await p.js("localStorage.clear(); " + "".join(
                            f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});" for k, v in storage.items()))
                        await p.call("Page.navigate", {"url": BASE + path})
                        await p.settle()
                        notes = []
                        for a in actions:
                            notes.append(await p.js(a))
                            await p.settle(4)
                        found = await p.js(DETECT)
                        key = f"{width}-{scheme}-{name}"
                        report[key] = {"actions": notes, **(found if isinstance(found, dict) else {"error": found})}
                        m = await p.call("Page.getLayoutMetrics")
                        h = int(m["cssContentSize"]["height"])
                        overlay = await p.js("!!document.querySelector('.mu-drawer, .mu-side[data-open]')")
                        steps = 1 if overlay else min(-(-h // 780), 14)
                        for i in range(steps):
                            await p.js(f"window.scrollTo(0, {i * 780})")
                            await asyncio.sleep(0.35)
                            shot = await p.call("Page.captureScreenshot", {"format": "png"})
                            with open(os.path.join(outdir, f"{key}~{i:02d}.png"), "wb") as f:
                                f.write(base64.b64decode(shot["data"]))
                        await p.js("window.scrollTo(0, 0)")
                        r = report[key]
                        counts = " ".join(f"{label}={len(r.get(kind, []))}" for label, kind in (
                            ("clipped", "clipped"), ("overflow", "overflow"),
                            ("collide", "collisions"), ("touch", "touching")))
                        print(f"{key:40s} h={h:5d} {counts} hscroll={r.get('hscroll')}", flush=True)
        with open(os.path.join(outdir, "issues.json"), "w") as f:
            json.dump(report, f, indent=1)
    finally:
        proc.terminate()


if __name__ == "__main__":
    out = sys.argv[1]
    widths = [int(w) for w in sys.argv[2:]] or [402]
    schemes = os.environ.get("SCHEMES", "dark").split(",")
    asyncio.run(run(out, widths, schemes))
