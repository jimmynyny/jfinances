import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { AppShell, Badge, type NavItem } from "@mooney/ui";
import { useMe } from "./api/hooks";
import { ApiError } from "./api/client";
import { SyncIndicator } from "./components/SyncIndicator";
import { OverviewPage } from "./pages/Overview";
import { AccountsPage } from "./pages/Accounts";
import { TransactionsPage } from "./pages/Transactions";
import { InvestmentsPage } from "./pages/Investments";
import { LiabilitiesPage } from "./pages/Liabilities";
import { SettingsPage } from "./pages/Settings";
import { LinkOAuthPage } from "./pages/LinkOAuth";
import { NotFoundPage } from "./pages/NotFound";
import { DeniedPage } from "./pages/Denied";

const TITLES: Record<string, string> = {
  "/": "Overview",
  "/accounts": "Accounts",
  "/transactions": "Transactions",
  "/investments": "Investments",
  "/liabilities": "Liabilities",
  "/settings": "Settings",
  "/link/oauth": "Connecting…",
};

const NAV = [
  {
    items: [
      { to: "/", label: "Overview", icon: <Glyph d="M3 3h4v4H3zM9 3h4v4H9zM3 9h4v4H3zM9 9h4v4H9z" /> },
      { to: "/accounts", label: "Accounts", icon: <Glyph d="M2 5h12M2 8h12M2 11h12" /> },
      { to: "/transactions", label: "Transactions", icon: <Glyph d="M3 5h10l-2-2M13 11H3l2 2" /> },
      { to: "/investments", label: "Investments", icon: <Glyph d="M2 12l4-5 3 3 5-6" /> },
      { to: "/liabilities", label: "Liabilities", icon: <Glyph d="M3 13V6l5-3 5 3v7M6 13V9h4v4" /> },
    ],
  },
  { label: "manage", items: [{ to: "/settings", label: "Settings", icon: <Glyph d="M8 5a3 3 0 100 6 3 3 0 000-6zM8 1v2M8 13v2M1 8h2M13 8h2" /> }] },
];

function Glyph({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="square" aria-hidden>
      <path d={d} />
    </svg>
  );
}

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark" | "auto">(() => {
    try { return (localStorage.getItem("jf.theme") as "light" | "dark" | null) ?? "auto"; } catch { return "auto"; }
  });
  useEffect(() => {
    if (theme === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    try { if (theme === "auto") localStorage.removeItem("jf.theme"); else localStorage.setItem("jf.theme", theme); } catch { /* ignore */ }
  }, [theme]);
  return [theme, setTheme] as const;
}

export function App() {
  const loc = useLocation();
  const me = useMe();
  const [theme, setTheme] = useTheme();
  const env = (import.meta.env.VITE_APP_ENV as string | undefined) ?? (window.location.hostname.includes("sandbox") ? "sandbox" : null);

  if (me.error instanceof ApiError && (me.error.status === 401 || me.error.status === 403)) {
    return <DeniedPage error={me.error} />;
  }

  const title = TITLES[loc.pathname] ?? "jfinances";
  const nextTheme = theme === "auto" ? "light" : theme === "light" ? "dark" : "auto";

  return (
    <AppShell
      brand="jfinances"
      brandAside={env ? <Badge tone="accent" dot={false}>{env}</Badge> : undefined}
      groups={NAV}
      renderLink={(it: NavItem, cls) => (
        <NavLink to={it.to} end={it.to === "/"} className={cls}>
          {it.icon}
          {it.label}
        </NavLink>
      )}
      title={title}
      topbar={<SyncIndicator />}
      footer={
        <>
          <span>{me.data?.email ?? "…"}</span>
          <button className="jf-theme" onClick={() => setTheme(nextTheme)}>
            theme: {theme} → {nextTheme}
          </button>
        </>
      }
    >
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/accounts" element={<AccountsPage />} />
        <Route path="/transactions" element={<TransactionsPage />} />
        <Route path="/investments" element={<InvestmentsPage />} />
        <Route path="/liabilities" element={<LiabilitiesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/link/oauth" element={<LinkOAuthPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
