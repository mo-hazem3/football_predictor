import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { Loading } from "./components/States";
import { HomePage } from "./pages/HomePage";

// The chart pages pull in Recharts (the bulk of the bundle), so they load on demand and the landing page stays light.
const PlayerPage = lazy(() => import("./pages/PlayerPage").then((m) => ({ default: m.PlayerPage })));
const TeamsPage = lazy(() => import("./pages/TeamsPage").then((m) => ({ default: m.TeamsPage })));
const InsightsPage = lazy(() => import("./pages/InsightsPage").then((m) => ({ default: m.InsightsPage })));
const MethodPage = lazy(() => import("./pages/MethodPage").then((m) => ({ default: m.MethodPage })));

export function NotFound() {
  return (
    <section className="hero">
      <h1>Page not found</h1>
      <p>
        <Link to="/">Back to search</Link>
      </p>
    </section>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<Loading label="Loading page" />}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="players/:id" element={<PlayerPage />} />
          <Route path="teams" element={<TeamsPage />} />
          <Route path="insights" element={<InsightsPage />} />
          <Route path="method" element={<MethodPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

export function App({ client }: { client?: QueryClient }) {
  const queryClient = client ?? new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
