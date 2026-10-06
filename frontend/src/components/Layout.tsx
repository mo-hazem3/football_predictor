import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { PlayerSearch } from "./Searches";

type Theme = "auto" | "light" | "dark";
const NEXT: Record<Theme, Theme> = { auto: "light", light: "dark", dark: "auto" };

function readTheme(): Theme {
  try {
    const v = localStorage.getItem("theme");
    return v === "light" || v === "dark" ? v : "auto";
  } catch {
    return "auto"; // storage can be blocked (private windows); the app works without it
  }
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    if (theme === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return (
    <button type="button" className="toggle" onClick={() => setTheme(NEXT[theme])} aria-label={`Theme: ${theme}. Click to change.`}>
      Theme: {theme}
    </button>
  );
}

export function Layout() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <div className="container inner">
          <NavLink to="/" className="brand">
            <span className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 17 9 11 13 15 21 6" />
                <polyline points="15 6 21 6 21 12" />
              </svg>
            </span>
            Football comps
          </NavLink>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>
              Players
            </NavLink>
            <NavLink to="/teams">Teams</NavLink>
            <NavLink to="/insights">Insights</NavLink>
            <NavLink to="/method">How far to trust it</NavLink>
          </nav>
          <PlayerSearch compact />
          <ThemeToggle />
        </div>
      </header>
      <main id="main" className="container">
        <Outlet />
      </main>
      <footer className="site-footer">
        <div className="container">
          Built on open data (Understat, FBref, Transfermarkt). Attacking output only, five leagues, 2014 to 2025. A portfolio project; not betting or
          transfer advice.
        </div>
      </footer>
    </>
  );
}
