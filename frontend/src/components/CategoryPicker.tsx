import { Input, Select } from "@mooney/ui";

/** The bank's own category: no override. */
export const BANK = "__bank__";

/** A pick from the list, or a name typed in (which wins when there is one). */
export interface CategoryChoice {
  pick: string;
  typed: string;
}

/** "FOOD_AND_DRINK" → "food and drink". */
export const categoryWords = (c: string) => c.toLowerCase().replace(/_/g, " ").trim();

/**
 * The category a choice stores: a typed name that reads like one already in use
 * is that one (so "Dining out" and "DINING_OUT" never split); a new name is kept
 * in the bank's style ("HOME_REPAIRS"), which every list shows as "home repairs".
 * `null` puts the bank's category back; `undefined` means nothing is chosen yet.
 */
export function resolveCategory(v: CategoryChoice, categories: string[]): { category: string | null | undefined; isNew: boolean } {
  const typed = v.typed.trim().replace(/\s+/g, " ");
  if (typed) {
    const same = categories.find((c) => categoryWords(c) === categoryWords(typed));
    return same ? { category: same, isNew: false } : { category: typed.toUpperCase().replace(/ /g, "_"), isNew: true };
  }
  if (v.pick === BANK) return { category: null, isNew: false };
  return { category: v.pick || undefined, isNew: false };
}

/** Pick a category already in use (or the bank's own), or type a new one. */
export function CategoryPicker({ categories, value, onChange, bankLabel }: {
  categories: string[];
  value: CategoryChoice;
  onChange: (v: CategoryChoice) => void;
  /** How the bank's own category reads here, e.g. "food and drink"; omitted for several transactions. */
  bankLabel?: string;
}) {
  // One option per name as it reads ("Dining out" and "DINING_OUT" are one), sorted the way they read.
  const seen = new Set<string>();
  const options = [...categories]
    .sort((a, b) => categoryWords(a).localeCompare(categoryWords(b)) || (a === a.toUpperCase() ? -1 : 1))
    .filter((c) => !seen.has(categoryWords(c)) && seen.add(categoryWords(c)))
    .map((c) => ({ value: c, label: categoryWords(c) }));
  const typing = value.typed.trim() !== "";
  const r = resolveCategory(value, categories);
  return (
    <div className="mu-stack">
      <Select label="Category" placeholder="Choose a category" value={typing ? "" : value.pick} disabled={typing}
        onChange={(e) => onChange({ pick: e.target.value, typed: "" })}
        options={[{ value: BANK, label: bankLabel ? `the bank's (${bankLabel})` : "each one's bank category" }, ...options]} />
      <Input label="Or a new category" placeholder="e.g. home repairs" value={value.typed}
        onChange={(e) => onChange({ pick: value.pick, typed: e.target.value })}
        help={!typing ? undefined : r.isNew ? `Adds “${categoryWords(r.category!)}” as a new category.` : `“${categoryWords(r.category!)}” is already a category; it will be used.`} />
    </div>
  );
}
