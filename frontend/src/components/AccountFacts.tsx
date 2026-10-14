import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Input, KeyValue, Money, Num, Segmented, formatDate, formatMoney, useToast } from "@mooney/ui";
import { ApiError, api } from "../api/client";
import { useSaveTerms } from "../api/hooks";
import type { AccountDetails, DetailFact, DetailSection, FactSource, TermsField, TermsKey, TermsValues } from "../api/types";

const ordinal = (n: number) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};

/** 297 → "297 months · 24 yr 9 mo". */
function monthsText(n: number): string {
  const y = Math.floor(n / 12), m = n % 12;
  if (n < 12) return `${n} month${n === 1 ? "" : "s"}`;
  return `${n} months · ${m ? `${y} yr ${m} mo` : `${y} year${y === 1 ? "" : "s"}`}`;
}

/** Where a value came from, when it wasn't the bank: entered, or worked out from the others. */
export function SourceTag({ source }: { source: FactSource | null | undefined }) {
  if (!source || source === "bank") return null;
  return source === "you"
    ? <span className="jf-src jf-src--you" title="You entered this">entered</span>
    : <span className="jf-src jf-src--calc" title="Worked out from the other figures">calc</span>;
}

function formatted(format: string, v: number | string | boolean): ReactNode {
  switch (format) {
    case "money": return <Money value={Number(v)} />;
    case "money0": return <Money value={Number(v)} cents={false} />;
    case "pct": return <Num>{`${Number(v)}%`}</Num>;
    case "ratio": return <Num>{`${Math.round(Number(v) * 100)}%`}</Num>;
    case "date": return formatDate(String(v), { year: true });
    case "months": return monthsText(Number(v));
    case "day": return `the ${ordinal(Number(v))}`;
    case "count": return <Num>{String(v)}</Num>;
    default: return String(v);
  }
}

function FactValue({ f, tag = true }: { f: DetailFact; tag?: boolean }) {
  return (
    <>
      {formatted(f.format, f.value as number | string | boolean)}
      {f.note ? <span className="mu-caption"> {f.note}</span> : null}
      {tag && <SourceTag source={f.source} />}
    </>
  );
}

/**
 * The panel's sections. A fact the bank doesn't report and nothing could work
 * out shows "add" when it can be entered (`onAdd` opens the form at that field).
 */
export function DetailSections({ sections, onAdd }: { sections: DetailSection[]; onAdd?: (field: TermsKey) => void }) {
  return (
    <>
      {sections.map((s) => {
        // A section that is all worked out (its note says so) doesn't tag every row.
        const tags = s.facts.some((f) => f.value != null && f.source !== "calc");
        const items = s.facts
          .filter((f) => f.value != null || (f.field && onAdd))
          .map((f) => ({
            key: f.label,
            value: f.value != null ? <FactValue f={f} tag={tags} />
              : <button type="button" className="mu-linkbtn" onClick={() => onAdd!(f.field!)}>add</button>,
          }));
        if (items.length === 0 && !s.note) return null;
        return (
          <section key={s.key} className="jf-facts" aria-label={s.title}>
            <span className="mu-caption">{s.title}</span>
            {s.note && <p className="jf-facts__note">{s.note}</p>}
            {items.length > 0 && <KeyValue items={items} />}
          </section>
        );
      })}
    </>
  );
}

/** The account's latest transactions, with a way to all of them. */
export function RecentActivity({ rows, accountId }: { rows: AccountDetails["recent"]; accountId: string }) {
  const navigate = useNavigate();
  if (rows.length === 0) return null;
  return (
    <section className="jf-facts" aria-label="Recent activity">
      <div className="mu-row" style={{ justifyContent: "space-between" }}>
        <span className="mu-caption">recent activity</span>
        <button type="button" className="mu-linkbtn" onClick={() => navigate(`/transactions?account=${accountId}`)}>all transactions</button>
      </div>
      <div className="jf-recent">
        {rows.map((t) => (
          <div key={t.id} className="jf-recent__row">
            <span className="mu-mono jf-recent__date">{formatDate(t.date)}</span>
            <span className="jf-recent__name">{t.name}{t.pending ? <span className="mu-caption"> · pending</span> : null}</span>
            <Money value={-t.amount} signed plus />
          </div>
        ))}
      </div>
    </section>
  );
}

/** Common terms, one tap each. */
const TERM_PICKS: Record<string, Array<[number, string]>> = {
  mortgage: [[180, "15 yr"], [240, "20 yr"], [360, "30 yr"]],
  loan: [[36, "3 yr"], [48, "4 yr"], [60, "5 yr"], [72, "6 yr"]],
  student: [[120, "10 yr"], [240, "20 yr"], [300, "25 yr"]],
};

function clean(raw: string): string {
  return raw.replace(/[$,%\s]/g, "");
}

/** The value as the API takes it, or an error to show under the field. */
function parse(f: TermsField, raw: string): { value: number | string | null; error: string | null } {
  const t = raw.trim();
  if (!t) return { value: null, error: null };
  if (f.format === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(t)) return { value: null, error: "a date" };
    if (t > new Date().toISOString().slice(0, 10)) return { value: null, error: "not in the future" };
    return { value: t, error: null };
  }
  if (f.format === "choice") return { value: t, error: null };
  const n = Number(clean(t));
  if (!Number.isFinite(n)) return { value: null, error: "a number" };
  const whole = f.format === "months" || f.format === "day";
  if (whole && !Number.isInteger(n)) return { value: null, error: "a whole number" };
  if (f.min != null && n < f.min) return { value: null, error: `at least ${f.min}` };
  if (f.max != null && n > f.max) return { value: null, error: `at most ${f.max.toLocaleString()}` };
  return { value: whole ? n : clean(t), error: null };
}

function shown(f: TermsField, v: number | string | null): string {
  if (v == null) return "—";
  if (f.format === "money") return formatMoney(Number(v));
  if (f.format === "pct") return `${Number(v)}%`;
  if (f.format === "date") return formatDate(String(v), { year: true });
  if (f.format === "months") return monthsText(Number(v));
  if (f.format === "day") return `the ${ordinal(Number(v))}`;
  return String(v);
}

/**
 * What the bank doesn't report, filled in by hand. As the person types, the
 * server works out the rest (a preview that saves nothing) and shows it below.
 */
export function TermsForm({ accountId, details, focus, onDone }: {
  accountId: string;
  details: AccountDetails;
  focus?: TermsKey | null;
  onDone: () => void;
}) {
  const editable = details.fields.filter((f) => f.bank == null);
  const reported = details.fields.filter((f) => f.bank != null);
  const [vals, setVals] = useState<Record<string, string>>(() =>
    Object.fromEntries(editable.map((f) => [f.key, details.terms[f.key] == null ? "" : String(details.terms[f.key])])));
  const parsed = useMemo(() => Object.fromEntries(editable.map((f) => [f.key, parse(f, vals[f.key] ?? "")])), [vals]); // eslint-disable-line react-hooks/exhaustive-deps
  const invalid = Object.values(parsed).some((p) => p.error);
  const body = useMemo<TermsValues>(() => Object.fromEntries(editable.map((f) => [f.key, parsed[f.key]!.value])), [parsed]); // eslint-disable-line react-hooks/exhaustive-deps
  const bodyKey = JSON.stringify(body);
  const [preview, setPreview] = useState<AccountDetails | null>(null);
  const save = useSaveTerms();
  const { toast, error } = useToast();
  const refs = useRef<Record<string, HTMLInputElement | null>>({});

  useEffect(() => {
    if (focus) refs.current[focus]?.focus();
  }, [focus]);

  // Live preview, a beat after typing stops; invalid input keeps the last good one.
  useEffect(() => {
    if (invalid) return;
    let live = true;
    const t = window.setTimeout(() => {
      api.previewTerms(accountId, JSON.parse(bodyKey) as TermsValues).then((d) => { if (live) setPreview(d); }).catch(() => undefined);
    }, 350);
    return () => { live = false; window.clearTimeout(t); };
  }, [accountId, bodyKey, invalid]);

  const set = (key: TermsKey, v: string) => setVals((cur) => ({ ...cur, [key]: v }));
  const picks = TERM_PICKS[details.kind] ?? [];
  const what = details.kind === "credit" ? "card issuer" : details.kind === "depository" ? "bank" : "lender";

  return (
    <div className="mu-stack">
      <p className="jf-facts__note">Fill in what the {what} doesn&apos;t report. Leave anything you don&apos;t know blank: the rest is worked out from what you give.</p>
      {reported.length > 0 && (
        <KeyValue items={reported.map((f) => ({ key: f.label, value: <>{shown(f, f.bank)}<span className="mu-caption"> from the {what}</span></> }))} />
      )}
      <div className="jf-terms">
        {editable.map((f) => {
          const err = parsed[f.key]?.error ?? null;
          const tip = details.suggestions[f.key];
          const helpText = tip ? undefined : f.help ?? undefined;
          if (f.format === "choice") {
            return (
              <div key={f.key} className="mu-field jf-terms__wide">
                <span className="mu-label">{f.label}</span>
                <Segmented size="sm" aria-label={f.label}
                  options={[{ value: "", label: "—" }, ...(f.options ?? []).map((o) => ({ value: o, label: o }))]}
                  value={vals[f.key] ?? ""} onChange={(v) => set(f.key, v)} />
              </div>
            );
          }
          return (
            <div key={f.key} className={f.key === "payment_amount" || f.key === "term_months" ? "jf-terms__wide" : undefined}>
              <Input
                ref={(el) => { refs.current[f.key] = el; }}
                label={f.format === "pct" ? `${f.label} (%)` : f.label}
                type={f.format === "date" ? "date" : "text"}
                inputMode={f.format === "date" ? undefined : f.format === "months" || f.format === "day" ? "numeric" : "decimal"}
                mono={f.format !== "date"}
                value={vals[f.key] ?? ""}
                placeholder={f.format === "pct" ? "6.125" : f.format === "day" ? "15" : f.format === "months" ? "360" : f.format === "money" ? "0.00" : undefined}
                onChange={(e) => set(f.key, e.target.value)}
                error={err ?? undefined}
                help={helpText}
              />
              {f.format === "months" && picks.length > 0 && (
                <div className="mu-row jf-terms__picks">
                  {picks.map(([n, label]) => (
                    <button key={n} type="button" className="mu-linkbtn" onClick={() => set(f.key, String(n))}>{label}</button>
                  ))}
                </div>
              )}
              {tip && !vals[f.key] && (
                <div className="jf-terms__tip">
                  <button type="button" className="mu-linkbtn" onClick={() => set(f.key, String(tip.value))}>
                    use {f.format === "day" ? `the ${ordinal(Number(tip.value))}` : formatMoney(Number(tip.value))}
                  </button>
                  <span className="mu-caption"> {tip.why}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {preview && (
        <div className="jf-terms__preview">
          <DetailSections sections={preview.sections.filter((s) => ["terms", "payoff", "card", "savings"].includes(s.key))} />
        </div>
      )}
      <div className="mu-row">
        <Button variant="primary" disabled={invalid} loading={save.isPending}
          onClick={() => save.mutate({ id: accountId, terms: body }, {
            onSuccess: () => { toast("Details saved"); onDone(); },
            onError: (e) => error(e instanceof ApiError ? e.message : "Could not save. Try again."),
          })}>
          Save
        </Button>
        <Button variant="quiet" onClick={onDone}>Cancel</Button>
      </div>
    </div>
  );
}
