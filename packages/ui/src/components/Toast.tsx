import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { cx } from "../lib/format";

export interface ToastItem {
  id: number;
  message: ReactNode;
  tone?: "default" | "error";
}

interface ToastApi {
  toast: (message: ReactNode, tone?: ToastItem["tone"]) => void;
  error: (message: ReactNode) => void;
}

const ToastCtx = createContext<ToastApi | null>(null);

export function ToastProvider({ children, ttlMs = 4500 }: { children: ReactNode; ttlMs?: number }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const toast = useCallback(
    (message: ReactNode, tone: ToastItem["tone"] = "default") => {
      const id = ++seq.current;
      setItems((xs) => [...xs, { id, message, tone }]);
      window.setTimeout(() => dismiss(id), ttlMs);
    },
    [dismiss, ttlMs],
  );
  const api = useMemo<ToastApi>(() => ({ toast, error: (m) => toast(m, "error") }), [toast]);
  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div className="mu-toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={cx("mu-toast", t.tone === "error" && "mu-toast--error")} role="status">
            <span>{t.message}</span>
            <button className="mu-toast__close" aria-label="Dismiss" onClick={() => dismiss(t.id)}>
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastCtx);
  if (!api) throw new Error("useToast must be used inside <ToastProvider>");
  return api;
}
