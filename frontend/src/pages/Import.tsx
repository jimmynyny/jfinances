import { businessSuffix } from "../components/BusinessMark";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Badge, Button, Checkbox, EmptyState, Money, Page, PageHeader, Panel, Segmented, Select, Skeleton, Tabs,
  formatDate, formatMoney, useToast,
} from "@mooney/ui";
import { ApiError, api, fileToBase64 } from "../api/client";
import { useAccounts, useImportChanged, useImports } from "../api/hooks";
import type { Account, ImportMapping, ImportPreview, ImportRecord, ImportRole, ImportRowStatus } from "../api/types";

const MAX_BYTES = 5 * 1024 * 1024;
const PAGE = 200;

const ROLE_OPTIONS: Array<{ value: ImportRole | ""; label: string }> = [
  { value: "", label: "not used" },
  { value: "date", label: "date (posted)" },
  { value: "auth_date", label: "date (of purchase)" },
  { value: "description", label: "description" },
  { value: "memo", label: "memo / details" },
  { value: "amount", label: "amount" },
  { value: "debit", label: "money out" },
  { value: "credit", label: "money in" },
  { value: "balance", label: "running balance" },
  { value: "category", label: "bank's category" },
  { value: "type", label: "debit / credit type" },
];
const ROLES = ROLE_OPTIONS.map((o) => o.value).filter(Boolean) as ImportRole[];
const DATE_FORMATS = [
  { value: "%m/%d/%Y", label: "10/14/2026" }, { value: "%m/%d/%y", label: "10/14/26" },
  { value: "%Y-%m-%d", label: "2026-10-14" }, { value: "%d/%m/%Y", label: "14/10/2026 (day first)" },
  { value: "%d/%m/%y", label: "14/10/26 (day first)" }, { value: "%m-%d-%Y", label: "10-14-2026" },
  { value: "%Y/%m/%d", label: "2026/10/14" }, { value: "%d-%b-%Y", label: "14-Oct-2026" },
  { value: "%d %b %Y", label: "14 Oct 2026" }, { value: "%b %d, %Y", label: "Oct 14, 2026" },
  { value: "%d.%m.%Y", label: "14.10.2026" }, { value: "%Y%m%d", label: "20261014" },
];
const STATUS_TEXT: Record<ImportRowStatus, string> = {
  new: "new",
  matched: "already here",
  duplicate: "already imported",
  review: "to review",
};
const STATUS_TONE: Record<ImportRowStatus, "good" | "neutral" | "warn" | "accent"> = {
  new: "good", matched: "neutral", duplicate: "neutral", review: "warn",
};

/** Linked bank, card and investment accounts, and offline ones kept by hand as a bank or card. */
const importable = (a: Account) => !a.closed_at && (a.kind === "plaid"
  ? a.type === "depository" || a.type === "credit" || a.type === "investment"
  : ["cash", "credit_cards", "other_assets", "other_liabilities"].includes(a.group ?? ""));

/**
 * Bank exports (CSV, QFX, OFX) into a linked account's history, for the years
 * a connection doesn't reach, and investment statements (QFX, OFX) into an
 * investment account's: its trades, contributions and past value. The file is read and every row sorted before
 * anything is saved: rows the connection has are matched, not added; rows in
 * its period that it doesn't have wait for a tick; re-uploads add nothing.
 */
export function ImportPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const accounts = useAccounts();
  const eligible = (accounts.data ?? []).filter(importable);
  const [accountId, setAccountId] = useState(params.get("account") ?? "");
  const [file, setFile] = useState<{ name: string; b64: string } | null>(null);
  const [mapping, setMapping] = useState<ImportMapping | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [reading, setReading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [tab, setTab] = useState<"all" | ImportRowStatus>("all");
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [shown, setShown] = useState(PAGE);
  const [done, setDone] = useState<ImportRecord | null>(null);
  const [saving, setSaving] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const changed = useImportChanged();
  const { toast, error } = useToast();
  const seq = useRef(0);

  async function read(next: { file?: { name: string; b64: string }; accountId?: string; mapping?: ImportMapping | null }) {
    const f = next.file ?? file;
    if (!f) return;
    const id = ++seq.current;
    setReading(true);
    setProblem(null);
    try {
      const p = await api.previewImport({
        filename: f.name, content_b64: f.b64,
        account_id: (next.accountId ?? accountId) || null,
        mapping: next.mapping === undefined ? mapping : next.mapping,
      });
      if (id !== seq.current) return; // a newer read is on its way
      setPreview(p);
      setMapping(p.mapping);
      if (!(next.accountId ?? accountId) && p.account_id) setAccountId(p.account_id);
      setTicked((t) => new Set([...t].filter((i) => p.rows.some((r) => r.index === i && r.status === "review"))));
    } catch (e) {
      if (id === seq.current) { setPreview(null); setProblem(e instanceof ApiError ? e.message : "Couldn't read that file."); }
    } finally {
      if (id === seq.current) setReading(false);
    }
  }

  async function onFile(f: File | undefined) {
    if (!f) return;
    setDone(null);
    if (f.size > MAX_BYTES) { setProblem("Files up to 5 MB: export a shorter date range."); return; }
    const next = { name: f.name, b64: await fileToBase64(f) };
    setFile(next);
    setMapping(null);
    setTicked(new Set());
    setTab("all");
    setShown(PAGE);
    void read({ file: next, mapping: null });
  }

  function choose(change: Partial<ImportMapping>, what: string) {
    if (!mapping) return;
    const m: ImportMapping = { ...mapping, ...change, chosen: [...new Set([...mapping.chosen, what])] };
    setMapping(m);
    void read({ mapping: m });
  }

  function setRole(col: number, role: ImportRole | "") {
    if (!mapping) return;
    const change: Partial<ImportMapping> = {};
    for (const r of ROLES) if (mapping[r] === col) change[r] = null;
    if (role) {
      change[role] = col;
      if (role === "amount") { change.debit = null; change.credit = null; }
      if (role === "debit" || role === "credit") change.amount = null;
    }
    choose(change, "columns");
  }

  async function doImport() {
    if (!file || !preview || !accountId) return;
    setSaving(true);
    try {
      const r = await api.applyImport({ filename: file.name, content_b64: file.b64, account_id: accountId, mapping, include: [...ticked] });
      setDone(r);
      setPreview(null);
      setFile(null);
      changed();
      toast(r.format === "invofx" ? `Imported ${r.rows_added} entr${r.rows_added === 1 ? "y" : "ies"}` : `Imported ${r.rows_added} transaction${r.rows_added === 1 ? "" : "s"}`);
    } catch (e) {
      error(e instanceof ApiError ? e.message : "The import failed. Nothing was saved.");
    } finally {
      setSaving(false);
    }
  }

  const c = preview?.counts;
  const rows = useMemo(() => (preview?.rows ?? []).filter((r) => tab === "all" || r.status === tab), [preview, tab]);
  const adding = (c?.new ?? 0) + ticked.size;
  const account = eligible.find((a) => a.id === accountId);
  useEffect(() => setShown(PAGE), [tab]);

  return (
    <Page>
      <PageHeader title="Import history" subtitle="Bank exports (CSV, QFX or OFX) and investment statements (QFX or OFX): history a connection doesn't reach, or an offline account's transactions." />

      <Panel caption="file">
        <div className="mu-stack">
          <div className="jf-import__pick">
            <Select label="Account" placeholder="Choose the account…" value={accountId}
              options={eligible.map((a) => ({ value: a.id, label: `${a.name}${a.mask ? ` ··${a.mask}` : ""}${businessSuffix(a.is_business)}` }))}
              onChange={(e) => { setAccountId(e.target.value); if (file) void read({ accountId: e.target.value }); }} />
            <div className="mu-field">
              <span className="mu-label">Export</span>
              <input ref={picker} type="file" accept=".csv,.ofx,.qfx,.txt,text/csv" hidden onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ""; }} />
              <Button onClick={() => picker.current?.click()} loading={reading}>{file ? "Choose another file" : "Choose a file"}</Button>
            </div>
          </div>
          {file && <span className="mu-caption">{file.name}</span>}
          {problem && <span className="jf-import__problem" role="alert">{problem}</span>}
          {!file && !done && (
            <ul className="jf-import__how">
              <li>Download your account&apos;s activity from the bank&apos;s website as CSV, QFX or OFX; for a brokerage or 401(k), the QFX or OFX statement.</li>
              <li>Nothing is saved until you press Import. The columns are worked out for you; check them below.</li>
              <li>Rows your connection already has are matched, not added. Re-uploading the same or an overlapping file adds nothing new.</li>
              <li>A bank the app can&apos;t connect to: add it as an offline account (cash), then import its exports here whenever you like. Its transactions count in Insights and subscriptions like any other.</li>
              <li>If the file has a running balance, those become the account&apos;s exact past balances.</li>
            </ul>
          )}
        </div>
      </Panel>

      {done && <DonePanel r={done} onAnother={() => { setDone(null); picker.current?.click(); }}
        onView={() => navigate(done.format === "invofx" ? "/investments" : `/transactions?account=${done.account_id}`)} />}

      {reading && !preview && <Skeleton lines={6} />}
      {preview && (
        <>
          {!preview.account_id ? (
            <Panel caption="account">
              <span className="mu-caption">Choose which account this file is for{preview.account_hint ? ` (it mentions ··${preview.account_hint})` : preview.format === "venmo" ? " (a Venmo statement)" : ""}; then every row is checked against what it already has.</span>
            </Panel>
          ) : (
            <Panel caption="what importing does">
              <div className="mu-stack">
                <div className="jf-import__counts">
                  <Count n={c?.new ?? 0} label="new" tone="good" />
                  <Count n={c?.matched ?? 0} label="already here" />
                  <Count n={c?.review ?? 0} label="to review" tone="warn" />
                  <Count n={c?.duplicate ?? 0} label="already imported" />
                </div>
                <p className="jf-facts__note">
                  {preview.range ? <>{c?.total} rows from {formatDate(preview.range.from, { year: true })} to {formatDate(preview.range.to, { year: true })}. </> : null}
                  {preview.connection_from ? <>Your connection has this account from {formatDate(preview.connection_from, { year: true })}; rows from then on are only matched, or added if you tick them. </> : null}
                  {account?.kind === "manual" ? <>It&apos;s an offline account: every new row is added, and the file&apos;s balances keep the account&apos;s balance up to date. </> : null}
                  {preview.balances ? (preview.format === "invofx"
                    ? <>The statement&apos;s holdings and the funds&apos; prices give the account&apos;s value for {preview.balances.days} days ({formatDate(preview.balances.from, { year: true })} – {formatDate(preview.balances.to, { year: true })}). </>
                    : <>{preview.format === "venmo" ? "The statement's opening balance" : "The running balance"} sets {preview.balances.days} days of exact balances. </>) : null}
                </p>
                {(preview.notes ?? []).map((n) => <p key={n} className="jf-facts__note">{n}</p>)}
                {preview.gap && (
                  <p className="jf-import__warn">
                    The file ends {preview.gap.days} days before your connection&apos;s history starts ({formatDate(preview.gap.from)} – {formatDate(preview.gap.to, { year: true })}), so balances before the gap can be off by whatever happened in it.
                    {preview.balances ? " The file's running balance corrects for that." : " An export that reaches the connection's start closes the gap."}
                  </p>
                )}
                {(c?.problems ?? 0) > 0 && <p className="jf-import__warn">{c?.problems} rows couldn&apos;t be read and are left out ({preview.problems.slice(0, 2).join("; ")}).</p>}
                <div className="mu-row">
                  <Button variant="primary" disabled={adding === 0 || !accountId} loading={saving} onClick={() => void doImport()}>
                    {adding === 0 ? "Nothing new to import" : `Import ${adding} transaction${adding === 1 ? "" : "s"}`}
                  </Button>
                  {account && <span className="mu-caption">into {account.name}</span>}
                </div>
              </div>
            </Panel>
          )}

          {preview.format === "csv" && mapping && (
            <MappingPanel preview={preview} mapping={mapping} onRole={setRole} onChoose={choose} reading={reading} />
          )}

          {preview.account_id && preview.rows.length > 0 && (
            <Panel flush caption="rows" actions={tab === "review" && (c?.review ?? 0) > 0 ? (
              <Button size="sm" variant="quiet" onClick={() => setTicked(ticked.size ? new Set() : new Set(preview.rows.filter((r) => r.status === "review").map((r) => r.index)))}>
                {ticked.size ? "Untick all" : "Tick all"}
              </Button>
            ) : undefined}>
              <div className="jf-import__tabs">
                <Tabs aria-label="Rows" value={tab} onChange={setTab} items={[
                  { value: "all", label: `all ${c?.total ?? 0}` },
                  { value: "new", label: `new ${c?.new ?? 0}` },
                  { value: "review", label: `to review ${c?.review ?? 0}` },
                  { value: "matched", label: `already here ${c?.matched ?? 0}` },
                  { value: "duplicate", label: `already imported ${c?.duplicate ?? 0}` },
                ]} />
              </div>
              <div className="jf-import__rows">
                {rows.slice(0, shown).map((r) => (
                  <div key={r.index} className="mu-listrow">
                    <span className="mu-mono mu-listrow__lead">{formatDate(r.date)}</span>
                    <div className="mu-listrow__main">
                      <div className="mu-listrow__title">{r.description}</div>
                      <div className="mu-caption">
                        <Badge dot={false} tone={STATUS_TONE[r.status]}>{STATUS_TEXT[r.status]}</Badge>
                        {r.status === "review" ? <> not in what your connection sent</> : null}
                        {r.match ? <> matches {formatDate(r.match.date)} {r.match.name}</> : null}
                        {r.balance != null ? <> · balance {formatMoney(r.balance)}</> : null}
                      </div>
                    </div>
                    <div className="mu-listrow__value"><Money value={-r.amount} signed plus /></div>
                    {r.status === "review" && (
                      <div className="mu-listrow__actions">
                        <Checkbox label="add" checked={ticked.has(r.index)} onChange={(e) => setTicked((t) => {
                          const n = new Set(t);
                          if (e.target.checked) n.add(r.index); else n.delete(r.index);
                          return n;
                        })} />
                      </div>
                    )}
                  </div>
                ))}
                {rows.length === 0 && <EmptyState glyph="·" title="No rows here" description="Nothing in the file falls in this group." />}
              </div>
              {rows.length > shown && (
                <div className="jf-pager">
                  <span>{shown} of {rows.length}</span>
                  <Button size="sm" variant="quiet" onClick={() => setShown((s) => s + PAGE)}>Show more</Button>
                </div>
              )}
              {(preview.rows_shown ?? 0) < (c?.total ?? 0) && (
                <div className="jf-pager"><span>The newest {preview.rows_shown} rows are listed; all {c?.total} are imported.</span></div>
              )}
            </Panel>
          )}
        </>
      )}

      {accountId && <PastImports accountId={accountId} />}
    </Page>
  );
}

function Count({ n, label, tone }: { n: number; label: string; tone?: "good" | "warn" }) {
  return (
    <div className={`jf-import__count${tone ? ` jf-import__count--${tone}` : ""}`}>
      <span className="jf-import__count-n">{n.toLocaleString()}</span>
      <span className="mu-caption">{label}</span>
    </div>
  );
}

function signNote(p: ImportPreview): string {
  const s = p.sign;
  if (!s) return "";
  if (s.basis === "matched") return `checked: ${s.agree} rows your connection already has agree`;
  if (s.basis === "type") return "from the type column";
  if (s.basis === "chosen") return "as you set it";
  return "a guess (most rows are spending): check a few rows below";
}

function MappingPanel({ preview, mapping, onRole, onChoose, reading }: {
  preview: ImportPreview;
  mapping: ImportMapping;
  onRole: (col: number, role: ImportRole | "") => void;
  onChoose: (change: Partial<ImportMapping>, what: string) => void;
  reading: boolean;
}) {
  const single = mapping.amount != null;
  return (
    <Panel caption="how the file is read" actions={reading ? <span className="mu-caption">reading…</span> : undefined}>
      <div className="mu-stack">
        <p className="jf-facts__note">Each column&apos;s role was worked out from its name and contents. Change any that are wrong; the rows below update.</p>
        <div className="jf-import__cols">
          {/* a trailing comma's nameless, empty column isn't worth a choice */}
          {preview.columns.filter((col) => col.samples.length > 0 || !/^column \d+$/.test(col.header)).map((col) => (
            <div key={col.index} className="jf-import__col">
              <div className="jf-import__col-head">
                <strong>{col.header}</strong>
                <span className="mu-caption">{col.samples.join(" · ") || "empty"}</span>
              </div>
              <Select aria-label={`${col.header}: role`} value={col.role ?? ""} options={ROLE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                onChange={(e) => onRole(col.index, e.target.value as ImportRole | "")} />
            </div>
          ))}
        </div>
        <div className="jf-import__pick">
          <Select label="Dates read as" value={mapping.date_format ?? ""} options={DATE_FORMATS}
            help={preview.date_ambiguous ? "Every date fits both month-first and day-first: check this." : undefined}
            onChange={(e) => onChoose({ date_format: e.target.value }, "date_format")} />
          {single && (
            <div className="mu-field">
              <span className="mu-label">Money out is</span>
              <Segmented size="sm" aria-label="Which amounts are money out" value={String(mapping.sign)}
                options={[
                  { value: "-1", label: "negative" }, { value: "1", label: "positive" },
                  ...(mapping.type != null ? [{ value: "0", label: "per type column" }] : []),
                ]}
                onChange={(v) => onChoose({ sign: Number(v) }, "sign")} />
              <span className="mu-caption">{signNote(preview)}</span>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

function DonePanel({ r, onAnother, onView }: { r: ImportRecord; onAnother: () => void; onView: () => void }) {
  const investments = r.format === "invofx";
  return (
    <Panel caption="imported">
      <div className="mu-stack">
        {investments ? (
          <p className="jf-facts__note">
            Added {r.rows_added} entr{r.rows_added === 1 ? "y" : "ies"}{r.rows_matched ? `, matched ${r.rows_matched} the connection already had` : ""}
            {r.balances_added ? `, and valued the account for ${r.balances_added} days` : ""}. Net worth and investment performance now include them.
          </p>
        ) : (
          <p className="jf-facts__note">
            Added {r.rows_added} transaction{r.rows_added === 1 ? "" : "s"}{r.rows_matched ? `, matched ${r.rows_matched} the connection already had` : ""}
            {r.balances_added ? `, and set ${r.balances_added} days of balances` : ""}. Balance history and insights now include them;
            subscriptions are looked for again in the background.
          </p>
        )}
        <div className="mu-row">
          <Button variant="primary" onClick={onView}>{investments ? "See the account" : "See the transactions"}</Button>
          <Button variant="quiet" onClick={onAnother}>Import another file</Button>
        </div>
      </div>
    </Panel>
  );
}

function PastImports({ accountId }: { accountId: string }) {
  const q = useImports(accountId);
  const changed = useImportChanged();
  const { toast, error } = useToast();
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const list = q.data ?? [];
  if (list.length === 0) return null;
  return (
    <Panel caption="earlier imports">
      <div className="mu-stack">
        {list.map((r) => (
          <div key={r.id} className="mu-listrow">
            <div className="mu-listrow__main">
              <div className="mu-listrow__title">{r.filename} {r.status === "undone" && <Badge dot={false}>undone</Badge>}</div>
              <div className="mu-caption">
                {r.date_from && r.date_to ? `${formatDate(r.date_from, { year: true })} – ${formatDate(r.date_to, { year: true })} · ` : ""}
                {r.rows_added} added · {r.rows_matched} matched{r.balances_added ? ` · ${r.balances_added} balances` : ""}
                {r.created_at ? ` · ${formatDate(r.created_at.slice(0, 10), { year: true })}` : ""}
              </div>
            </div>
            {r.status === "applied" && (
              <div className="mu-listrow__actions">
                {confirm === r.id ? (
                  <>
                    <Button size="sm" variant="danger" loading={busy === r.id} onClick={() => {
                      setBusy(r.id);
                      api.undoImport(r.id).then((x) => { toast(`Removed ${x.removed ?? 0} imported transactions`); changed(); })
                        .catch((e) => error(e instanceof ApiError ? e.message : "Couldn't undo. Try again."))
                        .finally(() => { setBusy(null); setConfirm(null); });
                    }}>Remove its rows</Button>
                    <Button size="sm" variant="quiet" onClick={() => setConfirm(null)}>Keep</Button>
                  </>
                ) : (
                  <Button size="sm" variant="quiet" onClick={() => setConfirm(r.id)}>Undo</Button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
