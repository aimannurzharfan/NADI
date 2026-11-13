import "@fontsource-variable/inter";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { LANG } from "./lib/i18n";
import { SettingsProvider } from "./lib/settings";

document.documentElement.lang = LANG;

// Keep the last good data on screen while a request fails (the offline banner says so).
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 2000, refetchOnWindowFocus: false, placeholderData: (prev: unknown) => prev } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SettingsProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </SettingsProvider>
    </QueryClientProvider>
  </StrictMode>,
);
