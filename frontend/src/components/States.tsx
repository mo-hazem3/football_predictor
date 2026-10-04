import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ApiError } from "../api/client";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <p role="status" className="muted">
      {label}…
    </p>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  const hint = error instanceof ApiError && error.status === 0 ? " Start it with: cd backend && python manage.py runserver" : "";
  return (
    <div role="alert" className="error">
      {message}
      {hint}
    </div>
  );
}

/** Renders loading / error / data for a query so every section handles all three the same way. */
export function Async<T>({ query, label, children }: { query: UseQueryResult<T>; label?: string; children: (data: T) => ReactNode }) {
  if (query.isPending) return <Loading label={label} />;
  if (query.isError) return <ErrorBox error={query.error} />;
  return <>{children(query.data)}</>;
}
