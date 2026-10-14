import { Checkbox, Input, Select } from "@mooney/ui";
import type { Account, AssetDraft, PropertyType } from "../api/types";

/**
 * What a monthly market value needs (docs/80 "Valuations"): a home's address, or
 * a car's VIN, mileage, how far it's driven a month and where it's kept (one of
 * the household's homes, whose ZIP prices it, or an address typed in). Values
 * are asked for once a month by the server; nothing here asks for one.
 */
export const PACES = [100, 250, 500, 750, 1000, 1500, 2000];
const PROPERTY_TYPES: PropertyType[] = ["Single Family", "Condo", "Townhouse", "Multi-Family", "Manufactured", "Land"];
const VIN = /^[A-HJ-NPR-Z0-9]{17}$/;
const ZIP = /^\d{5}(-\d{4})?$/;
/** The "Kept at" choice for an address typed in, not one of the homes. */
export const ELSEWHERE = "__elsewhere__";

export type AssetKind = "home" | "vehicle";

/** The draft the form edits, with the vehicle's "kept at" as a choice. */
export interface AssetForm extends AssetDraft {
  kept_at?: string;
}

export function draftFrom(d: AssetDraft | null | undefined): AssetForm {
  const x = d ?? {};
  return { ...x, miles_per_month: x.miles_per_month ?? 1000, valuation_enabled: x.valuation_enabled ?? true,
    kept_at: x.garage_account_id ?? (x.zip ? ELSEWHERE : "") };
}

/** The body for PUT /accounts/{id}/asset (or the `asset` of a new offline account). */
export function bodyOf(kind: AssetKind, f: AssetForm): AssetDraft {
  const blank = (v: unknown) => (typeof v === "string" ? v.trim() || null : v ?? null);
  if (kind === "home") {
    return { valuation_enabled: f.valuation_enabled ?? true, address_line: blank(f.address_line) as string | null,
      city: blank(f.city) as string | null, state: (blank(f.state) as string | null)?.toUpperCase() ?? null,
      zip: blank(f.zip) as string | null, property_type: f.property_type ?? null,
      bedrooms: f.bedrooms ?? null, bathrooms: f.bathrooms ?? null, square_feet: f.square_feet ?? null };
  }
  const home = f.kept_at && f.kept_at !== ELSEWHERE ? f.kept_at : null;
  return { valuation_enabled: f.valuation_enabled ?? true, vin: (blank(f.vin) as string | null)?.toUpperCase() ?? null,
    mileage: f.mileage ?? null, miles_per_month: f.miles_per_month ?? 1000, garage_account_id: home,
    address_line: home ? null : blank(f.address_line) as string | null, city: home ? null : blank(f.city) as string | null,
    state: home ? null : ((blank(f.state) as string | null)?.toUpperCase() ?? null), zip: home ? null : blank(f.zip) as string | null };
}

/** What's wrong with the draft, field by field (empty fields are allowed: the value just waits for them). */
export function problems(kind: AssetKind, f: AssetForm): Partial<Record<keyof AssetForm, string>> {
  const out: Partial<Record<keyof AssetForm, string>> = {};
  if (f.zip && !ZIP.test(f.zip.trim())) out.zip = "Five digits";
  if (f.state && !/^[A-Za-z]{2}$/.test(f.state.trim())) out.state = "Two letters";
  if (kind === "vehicle" && f.vin && !VIN.test(f.vin.trim().toUpperCase())) out.vin = "17 letters and digits (no I, O or Q)";
  return out;
}

const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(/[,\s]/g, "")));

export function AssetFields({ kind, value, onChange, homes }: {
  kind: AssetKind;
  value: AssetForm;
  onChange: (v: AssetForm) => void;
  /** The household's offline homes (with an address), for where a car is kept. */
  homes: Array<{ account: Account; zip: string | null; place: string }>;
}) {
  const set = (patch: Partial<AssetForm>) => onChange({ ...value, ...patch });
  const bad = problems(kind, value);
  const address = (
    <>
      <Input label={kind === "home" ? "Street address" : "Garage street address"} placeholder="12 Elm St"
        value={value.address_line ?? ""} onChange={(e) => set({ address_line: e.target.value })} />
      <div className="jf-asset__row">
        <Input label="City" value={value.city ?? ""} onChange={(e) => set({ city: e.target.value })} />
        <Input label="State" placeholder="NJ" maxLength={2} value={value.state ?? ""} error={bad.state}
          onChange={(e) => set({ state: e.target.value.toUpperCase() })} />
        <Input label="ZIP" mono inputMode="numeric" placeholder="07042" value={value.zip ?? ""} error={bad.zip}
          onChange={(e) => set({ zip: e.target.value })} />
      </div>
    </>
  );
  return (
    <div className="mu-stack">
      {kind === "home" ? (
        <>
          {address}
          <Select label="Kind of home" placeholder="Let the market data decide" value={value.property_type ?? ""}
            options={PROPERTY_TYPES.map((t) => ({ value: t, label: t.toLowerCase() }))}
            onChange={(e) => set({ property_type: (e.target.value || null) as PropertyType | null })} />
          <div className="jf-asset__row">
            <Input label="Bedrooms" mono inputMode="numeric" value={value.bedrooms ?? ""} onChange={(e) => set({ bedrooms: num(e.target.value) })} />
            <Input label="Bathrooms" mono inputMode="decimal" value={value.bathrooms ?? ""} onChange={(e) => set({ bathrooms: num(e.target.value) })} />
            <Input label="Square feet" mono inputMode="numeric" value={value.square_feet ?? ""} onChange={(e) => set({ square_feet: num(e.target.value) })} />
          </div>
          <span className="mu-caption">Bedrooms, bathrooms and size are optional: the market data looks them up from the address.</span>
        </>
      ) : (
        <>
          <Input label="VIN" mono placeholder="17 letters and digits" maxLength={17} value={value.vin ?? ""} error={bad.vin}
            help="On the driver's side of the dashboard, the door jamb, or the registration."
            onChange={(e) => set({ vin: e.target.value.toUpperCase() })} />
          <div className="jf-asset__row">
            <Input label="Mileage now" mono inputMode="numeric" placeholder="30000" value={value.mileage ?? ""}
              onChange={(e) => set({ mileage: num(e.target.value) })} />
            <Select label="Miles a month" value={String(value.miles_per_month ?? 1000)}
              options={PACES.map((p) => ({ value: String(p), label: p.toLocaleString() }))}
              onChange={(e) => set({ miles_per_month: Number(e.target.value) })} />
          </div>
          <span className="mu-caption">Between your updates, the mileage counts up at this pace (a city car might do 100–250 a month).</span>
          <Select label="Kept at" placeholder="Choose where it's kept" value={value.kept_at ?? ""}
            options={[...homes.map((h) => ({ value: h.account.id, label: `${h.account.name}${h.place ? ` · ${h.place}` : ""}` })),
              { value: ELSEWHERE, label: "Another address…" }]}
            help="Car prices are local: the ZIP where it's kept prices it."
            onChange={(e) => set({ kept_at: e.target.value })} />
          {value.kept_at === ELSEWHERE && address}
        </>
      )}
      <Checkbox label="Update its value from market data once a month" checked={value.valuation_enabled ?? true}
        onChange={(e) => set({ valuation_enabled: e.target.checked })} />
    </div>
  );
}

/** The household's offline homes, as places a car can be kept. */
export function homesFor(accounts: Account[], except?: string) {
  return accounts.filter((a) => a.kind === "manual" && a.manual_category === "real_estate" && !a.closed_at && a.id !== except)
    .map((a) => ({ account: a, zip: a.asset_zip ?? null, place: a.asset_place ?? "" }));
}
