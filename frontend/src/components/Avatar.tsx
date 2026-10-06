/** Initials on a gradient disc: the data has no player photos, so this gives each player a face without hotlinking any. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function Avatar({ name, large = false }: { name: string; large?: boolean }) {
  return (
    <span className={`avatar${large ? " lg" : ""}`} aria-hidden="true">
      {initials(name)}
    </span>
  );
}
