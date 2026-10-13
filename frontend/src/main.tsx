import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@mooney/ui";
import "@mooney/ui/styles.css";
import "./app.css";
import { App } from "./App";
import { ApiError } from "./api/client";

const queryClient = new QueryClient({
  defaultQueries: undefined,
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) => !(err instanceof ApiError && (err.status === 401 || err.status === 403 || err.status === 404)) && count < 2,
      refetchOnWindowFocus: true,
    },
  },
} as ConstructorParameters<typeof QueryClient>[0]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
