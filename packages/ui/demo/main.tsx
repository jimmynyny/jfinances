import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "../src/styles/tokens.css";
import "../src/styles/base.css";
import "../src/styles/components.css";
import "../src/styles/charts.css";
import {
  AppShell, AreaChart, Badge, BarChart, Button, Checkbox, DataTable, Delta, DonutChart, Drawer, EmptyState,
  IconButton, Input, KeyValue, Meter, Money, Page, PageHeader, Panel, Segmented, Select, Skeleton, StatTile,
  Tabs, ToastProvider, useToast, type Column,
} from "@mooney/ui";

const days = Array.from({ length: 60 }, (_, i) => {
  const d = new Date(2026, 7, 1 + i);
  const iso = d.toISOString().slice(0, 10);
  const net = 660000 + i * 450 + Math.sin(i / 4) * 2500;
  return { date: iso, net, assets: net + 240000, liabilities: 240000 - i * 60 };
});

const months = [
  { label: "May", income: 8200, expenses: 4860 },
  { label: "Jun", income: 8100, expenses: 5120 },
  { label: "Jul", income: 9300, expenses: 4400 },
  { label: "Aug", income: 8200, expenses: 5900 },
  { label: "Sep", income: 8600, expenses: 4700 },
  { label: "Oct", income: 8200, expenses: 3719 },
];

interface Row { id: string; name: string; inst: string; bal: number; share: number; }
const rows: Row[] = [
  { id: "1", name: "Everyday checking", inst: "Chase ··4821", bal: 15234.75, share: 0.23 },
  { id: "2", name: "Joint savings", inst: "Ally ··9016", bal: 50107.55, share: 0.77 },
  { id: "3", name: "Joint credit card", inst: "Amex ··2084", bal: -2828.99, share: 0.04 },
];

function Gallery() {
  const [range, setRange] = useState<"1m" | "3m" | "1y">("3m");
  const [tab, setTab] = useState<"a" | "b">("a");
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const { toast, error } = useToast();
  const cols: Column<Row>[] = [
    { key: "name", header: "Account", cell: (r) => <><div>{r.name}</div><div className="mu-caption">{r.inst}</div></>, sortValue: (r) => r.name },
    { key: "share", header: "Share", cell: (r) => <Meter ratio={r.share} label={`${Math.round(r.share * 100)}%`} tone="series" color="var(--mu-series-1)" /> },
    { key: "bal", header: "Balance", numeric: true, cell: (r) => <Money value={r.bal} signed />, sortValue: (r) => r.bal },
  ];
  document.documentElement.dataset.theme = theme;
  return (
    <AppShell
      brand="@mooney/ui"
      brandAside={<Badge tone="accent" dot={false}>gallery</Badge>}
      groups={[{ label: "sections", items: [{ to: "#tokens", label: "Tokens" }, { to: "#primitives", label: "Primitives" }, { to: "#charts", label: "Charts" }] }]}
      renderLink={(it, cls) => <a href={it.to} className={cls}>{it.label}</a>}
      title="Component gallery"
      topbar={<Segmented size="sm" options={[{ value: "light", label: "light" }, { value: "dark", label: "dark" }]} value={theme} onChange={setTheme} />}
      footer={<span>every component, once</span>}
    >
      <Page>
        <PageHeader title="Gallery" subtitle="Copy from here when building another dashboard." actions={<><Button variant="quiet" onClick={() => toast("Saved")}>Toast</Button><Button variant="primary" onClick={() => error("Sync failed: item needs re-link")}>Error toast</Button></>} />

        <h2 id="tokens">Stat tiles</h2>
        <div className="mu-grid mu-grid--4">
          <StatTile hero label="net worth" value={<Money value={687041.79} cents={false} mono={false} />} delta={<Delta amount={23542.96} pct={3.5} label="1 month" />} trend={days.slice(-12).map((d) => d.net)} />
          <StatTile label="cash" value={<Money value={65342.3} cents={false} mono={false} />} delta={<Delta amount={1826.1} pct={2.9} />} tone="wash" />
          <StatTile label="credit cards" value={<Money value={2828.99} cents={false} mono={false} />} delta={<Delta amount={-63.03} pct={-2.2} upIsGood={false} />} />
          <StatTile label="accounts needing attention" value="1" note="Chase · login required" tone="neg" />
        </div>

        <h2 id="primitives">Primitives</h2>
        <Panel caption="buttons" actions={<IconButton label="More" size="sm" variant="ghost">…</IconButton>}>
          <div className="mu-row">
            <Button>Default</Button><Button variant="primary">Primary</Button><Button variant="quiet">Quiet</Button><Button variant="ghost">Ghost</Button><Button variant="danger">Remove</Button><Button size="sm">Small</Button><Button loading>Loading</Button><Button disabled>Disabled</Button>
          </div>
        </Panel>
        <Panel caption="fields">
          <div className="mu-grid mu-grid--3">
            <Input label="Account name" placeholder="Everyday checking" />
            <Input label="Value" mono defaultValue="300625.05" help="As of today" />
            <Select label="Category" options={[{ value: "real_estate", label: "Real estate" }, { value: "vehicle", label: "Vehicle" }]} placeholder="Choose…" />
          </div>
          <div className="mu-row" style={{ marginTop: 12 }}>
            <Checkbox label="Hidden from overview" /><Badge tone="good">active</Badge><Badge tone="warn">needs re-link</Badge><Badge tone="critical">error</Badge><Badge>manual</Badge>
          </div>
        </Panel>
        <div className="mu-grid mu-grid--2">
          <Panel caption="tabs + segmented">
            <Tabs items={[{ value: "a", label: "Holdings" }, { value: "b", label: "Activity" }]} value={tab} onChange={setTab} />
            <div style={{ marginTop: 12 }}><Segmented options={[{ value: "1m", label: "1m" }, { value: "3m", label: "3m" }, { value: "1y", label: "1y" }]} value={range} onChange={setRange} /></div>
            <div style={{ marginTop: 12 }}><Button variant="quiet" onClick={() => setOpen(true)}>Open drawer</Button></div>
          </Panel>
          <Panel caption="key / value">
            <KeyValue items={[{ key: "interest rate", value: "6.125%" }, { key: "next payment", value: "Nov 1, 2026" }, { key: "minimum", value: <Money value={1385} /> }]} />
            <div style={{ marginTop: 12 }}><Skeleton lines={3} /></div>
          </Panel>
        </div>
        <Panel caption="table" flush>
          <DataTable columns={cols} rows={rows} rowKey={(r) => r.id} defaultSort={{ key: "bal", dir: "desc" }} onRowClick={() => setOpen(true)} />
        </Panel>
        <EmptyState title="No accounts connected" description="Connect a bank or add an offline asset to start tracking." action={<Button variant="primary">Connect account</Button>} />

        <h2 id="charts">Charts</h2>
        <Panel caption="net worth" actions={<Segmented size="sm" options={[{ value: "1m", label: "1m" }, { value: "3m", label: "3m" }, { value: "1y", label: "1y" }]} value={range} onChange={setRange} />}>
          <AreaChart data={days} series={[{ key: "net", label: "Net worth" }]} />
        </Panel>
        <div className="mu-grid mu-grid--2">
          <Panel caption="assets vs liabilities (two series)"><AreaChart data={days} series={[{ key: "assets", label: "Assets" }, { key: "liabilities", label: "Liabilities" }]} fill="wash" height={200} /></Panel>
          <Panel caption="income vs expenses"><BarChart data={months} series={[{ key: "income", label: "Income" }, { key: "expenses", label: "Expenses" }]} /></Panel>
        </div>
        <Panel caption="allocation">
          <DonutChart centerLabel="assets" slices={[{ key: "inv", label: "Investments", value: 542301 }, { key: "re", label: "Real estate", value: 300625 }, { key: "cash", label: "Cash", value: 65342 }, { key: "veh", label: "Vehicles", value: 20739 }]} />
        </Panel>
      </Page>
      <Drawer open={open} onClose={() => setOpen(false)} title="Edit transaction" footer={<><Button variant="quiet" onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" onClick={() => { setOpen(false); toast("Saved"); }}>Save changes</Button></>}>
        <Input label="Category" defaultValue="Groceries" />
        <Input label="Notes" placeholder="Optional" />
      </Drawer>
    </AppShell>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ToastProvider>
      <Gallery />
    </ToastProvider>
  </StrictMode>,
);
