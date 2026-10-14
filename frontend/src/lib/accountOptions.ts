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

export function accountFilterLabel(a: Account): string {
  // Some institutions already end the name with the mask ("Brokerage - ****3184"): show it once.
  const tail = /[\s-]*\*+(\w+)\s*$/.exec(a.name);
  const name = tail && tail[1] === a.mask ? a.name.slice(0, tail.index) : a.name;
  const inst = a.institution_name ? `${a.institution_name}: ` : "";
  return `${inst}${name}${a.mask ? `\u00a0··${a.mask}` : ""}${a.closed_at ? " (closed)" : ""}`;
}
