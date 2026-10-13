import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "../src/styles/fonts.css";
import "../src/styles/tokens.css";
import "../src/styles/base.css";
import "../src/styles/components.css";
import "../src/styles/charts.css";
import "../src/styles/pixel.css";
import {
  AppShell, AreaChart, Badge, BarChart, Button, Checkbox, DataTable, Delta, DonutChart, Drawer, EmptyState,
  IconButton, Input, KeyValue, Meter, Money, Page, PageHeader, Panel, Segmented, Select, Skeleton, StatTile,
  Tabs, ToastProvider, useToast, type Column,
  PixelBars, PixelCalendar, PixelMeter, PixelSparkline, Readout, Waffle, formatMoney,
} from "@mooney/ui";

const days = Array.from({ length: 60 }, (_, i) => {
  const d = new Date(2026, 7, 1 + i);
  const iso = d.toISOString().slice(0, 10);
  const net = 660000 + i * 450 + Math.sin(i / 4) * 2500;
  return { date: iso, net, assets: net + 240000, liabilities: 240000 - i * 60 };
});

// A year of daily net-worth changes for the calendar: drift up, paydays, a bad week.
const year = Array.from({ length: 365 }, (_, i) => {
  const d = new Date(2025, 9, 14 + i);
  const iso = d.toISOString().slice(0, 10);
  const pay = d.getDate() === 1 || d.getDate() === 15 ? 4200 : 0;
  const market = Math.round(Math.sin(i * 1.7) * 900 + Math.cos(i / 9) * 600 + (i > 200 && i < 208 ? -2600 : 0));
  return { date: iso, value: d.getDay() === 0 || d.getDay() === 6 ? (pay ? pay : 0) : market + pay };
});
const trend90 = Array.from({ length: 90 }, (_, i) => 48000 + i * 60 + Math.sin(i / 5) * 900);

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
      groups={[{ label: "sections", items: [{ to: "#pixel", label: "Pixel layer" }, { to: "#tokens", label: "Tokens" }, { to: "#primitives", label: "Primitives" }, { to: "#charts", label: "Charts" }] }]}
      renderLink={(it, cls) => <a href={it.to} className={cls}>{it.label}</a>}
      title="Component gallery"
      topbar={<Segmented size="sm" options={[{ value: "light", label: "light" }, { value: "dark", label: "dark" }]} value={theme} onChange={setTheme} />}
      footer={<span>every component, once</span>}
    >
      <Page>
        <PageHeader title="Gallery" subtitle="Copy from here when building another dashboard." actions={<><Button variant="quiet" onClick={() => toast("Saved")}>Toast</Button><Button variant="primary" onClick={() => error("Sync failed: item needs re-link")}>Error toast</Button></>} />

        <h2 id="pixel">Pixel layer</h2>
        <Panel marks caption="readout" actions={<Segmented size="sm" options={[{ value: "1m", label: "1m" }, { value: "3m", label: "3m" }, { value: "1y", label: "1y" }]} value={range} onChange={setRange} />}>
          <Readout label="net worth" value={formatMoney(1091443.89, { cents: false })} delta={<Delta amount={23542.96} pct={2.2} label="1 month" />} />
          <AreaChart data={days} series={[{ key: "net", label: "Net worth" }]} height={220} />
        </Panel>
        <div className="mu-grid mu-grid--3">
          <Panel caption="readout · lg"><Readout size="lg" label="assets" value={formatMoney(1333410, { cents: false })} note="18 accounts" /></Panel>
          <Panel caption="readout · md"><Readout size="md" label="liabilities" value={formatMoney(241966, { cents: false })} note="4 accounts" /></Panel>
          <Panel caption="pixel sparkline (90 days → 32 columns)">
            <div className="mu-stack">
              <PixelSparkline values={trend90} />
              <PixelSparkline values={trend90.map((v, i) => v - i * 140)} width={140} height={30} />
              <PixelSparkline values={Array(30).fill(655000)} />
            </div>
          </Panel>
        </div>
        <div className="mu-grid mu-grid--2">
          <Panel caption="pixel meters">
            <div className="mu-stack">
              <PixelMeter ratio={0.18} label="18% of limit" ariaLabel="Card utilization" />
              <PixelMeter ratio={0.46} tone="warn" label="46% of limit" ariaLabel="Card utilization" />
              <PixelMeter ratio={0.82} tone="neg" label="82% of limit" ariaLabel="Card utilization" />
              <PixelMeter ratio={0.37} tone="pos" label="37% paid" ariaLabel="Mortgage paid off" />
              <PixelMeter size="lg" cells={40} segments={[{ value: 542301, color: "var(--mu-series-1)", label: "Investments" }, { value: 300625, color: "var(--mu-series-2)", label: "Real estate" }, { value: 65342, color: "var(--mu-series-3)", label: "Cash" }, { value: 20739, color: "var(--mu-series-4)", label: "Vehicles" }]} />
              <PixelMeter size="sm" ratio={0.62} tone="ink" label="62%" ariaLabel="Weight" />
            </div>
          </Panel>
          <Panel caption="pixel bars: in vs out by month">
            <PixelBars data={months} series={[{ key: "income", label: "In" }, { key: "expenses", label: "Out" }]} />
          </Panel>
        </div>
        <div className="mu-grid mu-grid--2">
          <Panel caption="waffle: allocation">
            <Waffle slices={[{ key: "eq", label: "Equity", value: 241000 }, { key: "etf", label: "ETF", value: 188000 }, { key: "mf", label: "Mutual fund", value: 92000 }, { key: "fi", label: "Fixed income", value: 31000 }, { key: "cash", label: "Cash", value: 12500 }, { key: "crypto", label: "Crypto", value: 4100 }, { key: "other", label: "Other", value: 1900 }]} />
          </Panel>
          <Panel marks caption="pixel calendar: daily change">
            <PixelCalendar days={year} />
          </Panel>
        </div>

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
