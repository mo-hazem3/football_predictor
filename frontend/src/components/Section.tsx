import type { ReactNode } from "react";

export function Section({ title, lede, children, id }: { title: string; lede?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="card" aria-labelledby={id ? `${id}-title` : undefined} id={id}>
      <h2 id={id ? `${id}-title` : undefined}>{title}</h2>
      {lede && <p className="lede">{lede}</p>}
      {children}
    </section>
  );
}

export function Notice({ children, kind = "warn" }: { children: ReactNode; kind?: "warn" | "info" }) {
  return <div className={`notice${kind === "info" ? " info" : ""}`}>{children}</div>;
}
