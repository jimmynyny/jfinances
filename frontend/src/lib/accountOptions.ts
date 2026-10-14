import type { SelectGroup } from "@mooney/ui";
import type { Account } from "../api/types";
import { groupAccounts } from "./groups";

/** The Account filter: a labelled section per type, in the Accounts page's
 * order (Cash, Investments, Credit cards, Loans), each entry "Chase: Sapphire
 * ··1234" and sorted so an institution's accounts sit together. Manual
 * accounts (homes, cars) never have transactions, so they are left out. */
export function accountFilterOptions(accounts: Account[] | undefined): SelectGroup[] {
  return groupAccounts((accounts ?? []).filter((a) => a.kind !== "manual")).map((g) => ({
    group: g.label,
    options: g.accounts
      .map((a) => ({ value: a.id, label: accountFilterLabel(a) }))
      .sort((x, y) => x.label.localeCompare(y.label, undefined, { sensitivity: "base", numeric: true })),
  }));
}

/** The name without a trailing copy of the mask ("Brokerage - ****3184", "Card **2480"): it is shown once, apart. */
export function nameWithoutMask(name: string, mask: string | null | undefined): string {
  const tail = /[\s-]*\*+(\w+)\s*$/.exec(name);
  return tail && tail[1] === mask ? name.slice(0, tail.index) : name;
}

export function accountFilterLabel(a: Account): string {
  const name = nameWithoutMask(a.name, a.mask);
  const inst = a.institution_name ? `${a.institution_name}: ` : "";
  // A select can't hold the briefcase, so business accounts say so in words.
  return `${inst}${name}${a.mask ? `\u00a0··${a.mask}` : ""}${a.is_business ? " · business" : ""}${a.closed_at ? " (closed)" : ""}`;
}
