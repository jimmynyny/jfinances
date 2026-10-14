import { useState } from "react";
import { Button, KeyValue, Money, Num, Skeleton, formatDate, useToast } from "@mooney/ui";
import { useAsset, useSaveAsset } from "../api/hooks";
import type { Account } from "../api/types";
import { ApiError } from "../api/client";
import { AssetFields, bodyOf, draftFrom, homesFor, problems, type AssetForm } from "./AssetFields";

const NEEDS: Record<string, string> = {
  address: "its street address", city: "its city", state: "its state", zip: "its ZIP",
  vin: "its VIN", mileage: "its mileage", location: "where it's kept",
};

const monthName = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { month: "long", year: "numeric" });

/**
 * An offline home's or car's market value: the latest monthly estimate, what it
 * was based on, when the next one comes, and the details it needs (GET/PUT
 * /accounts/{id}/asset). Estimates come once a month on their own; nothing here
 * asks for one.
 */
export function MarketValue({ account, accounts }: { account: Account; accounts: Account[] }) {
  const q = useAsset(account.id);
  const save = useSaveAsset();
  const { toast, error } = useToast();
  const [form, setForm] = useState<AssetForm | null>(null);
  const info = q.data;
  if (q.isLoading) return <Skeleton lines={3} />;
  if (!info || !info.kind) return null;
  const kind = info.kind;
  const last = info.valuations.find((v) => v.status === "ok" && v.value != null);
  const latest = info.valuations[0];
  const det = info.details;
  const on = info.valuation_enabled !== false;
  const home = det?.garage_account_id ? accounts.find((x) => x.id === det.garage_account_id) : undefined;
  const bad = form ? problems(kind, form) : {};

  if (form) {
    return (
      <form className="mu-stack" onSubmit={(e) => {
        e.preventDefault();
        save.mutate({ id: account.id, body: bodyOf(kind, form) }, {
          onSuccess: () => { setForm(null); toast("Saved"); },
          onError: (err) => error(err instanceof ApiError ? err.message : "Could not save"),
        });
      }}>
        <span className="mu-caption">{kind === "home" ? "the home" : "the car"}</span>
        <AssetFields kind={kind} value={form} onChange={setForm} homes={homesFor(accounts, account.id)} />
        <div className="mu-row">
          <Button type="submit" variant="primary" loading={save.isPending} disabled={Object.keys(bad).length > 0}>Save</Button>
          <Button type="button" variant="quiet" onClick={() => setForm(null)}>Cancel</Button>
        </div>
      </form>
    );
  }

  const items = [];
  if (last) {
    items.push({ key: "estimate", value: <><Money value={last.value!} cents={false} />{last.low != null && last.high != null
      ? <span className="mu-caption"> (<Money value={last.low} cents={false} /> – <Money value={last.high} cents={false} />)</span> : null}</> });
    items.push({ key: "as of", value: formatDate(last.as_of, { year: true }) });
    const comps = typeof last.detail?.comparables === "number" ? last.detail.comparables : null;
    const miles = typeof last.inputs?.miles === "number" ? last.inputs.miles : null;
    items.push({ key: "based on", value: kind === "home"
      ? `${comps ? `${comps} comparable sales` : "comparable sales"} near the address`
      : <>what a dealer would ask{miles != null ? <>, at <Num>{miles.toLocaleString()}</Num> miles</> : null}</> });
  }
  if (kind === "vehicle" && det) {
    if (det.vehicle_label) items.push({ key: "vehicle", value: det.vehicle_label });
    if (det.mileage != null) {
      items.push({ key: "mileage", value: <><Num>{(info.projected_miles ?? det.mileage).toLocaleString()}</Num> now
        <span className="mu-caption"> ({det.mileage.toLocaleString()} on {formatDate(det.mileage_as_of ?? "", { year: true })}, {(det.miles_per_month ?? 1000).toLocaleString()} a month)</span></> });
    }
    if (home || info.priced_at_zip) items.push({ key: "kept at", value: home ? home.name : `ZIP ${info.priced_at_zip}` });
  }
  if (kind === "home" && det?.address_line) {
    items.push({ key: "address", value: [det.address_line, [det.city, det.state].filter(Boolean).join(", "), det.zip].filter(Boolean).join(" · ") });
  }

  return (
    <div className="mu-stack">
      <div className="mu-row" style={{ justifyContent: "space-between" }}>
        <span className="mu-caption">market value</span>
        <Button size="sm" variant="quiet" onClick={() => setForm(draftFrom({ ...(det ?? {}), valuation_enabled: on }))}>
          {det ? "Edit details" : kind === "home" ? "Add its address" : "Add VIN and mileage"}
        </Button>
      </div>
      {!on ? (
        <span className="mu-caption">Kept by hand: market values are off for it.</span>
      ) : info.missing.length > 0 ? (
        <span className="mu-caption">Needs {info.missing.map((m) => NEEDS[m] ?? m).join(", ")} to be valued from market data once a month.</span>
      ) : info.next_month ? (
        <span className="mu-caption">Valued from market data once a month; the next estimate comes in {monthName(info.next_month)}.</span>
      ) : null}
      {latest && latest.status !== "ok" && latest.status !== "pending" && (
        <span className="mu-caption">{monthName(latest.month)}: {latest.status === "skipped" ? "held back (the month's requests were used up)" : latest.status === "no_value" ? "no estimate for it" : "the estimate didn't come through"}{latest.error ? ` (${latest.error})` : ""}; it's asked again next month.</span>
      )}
      {items.length > 0 && <KeyValue items={items} />}
    </div>
  );
}
