import { create } from "zustand";

export type Theme = "light" | "dark";

const STORAGE_KEY = "subagents-theme";

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** window.localStorage can throw (private browsing) or be shadowed by a broken
 * global (Node's experimental localStorage in tests) — degrade to in-memory. */
function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(theme: Theme) {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // non-persistent session — theme still applies for this tab
  }
}

function initialTheme(): Theme {
  const stored = readStored();
  if (stored === "light" || stored === "dark") return stored;
  return systemTheme();
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: initialTheme(),
  setTheme: (theme) => {
    writeStored(theme);
    applyTheme(theme);
    set({ theme });
  },
  toggle: () => get().setTheme(get().theme === "dark" ? "light" : "dark"),
}));

// Stamp the attribute immediately at module load (before first paint) so
// there is no light-mode flash for dark-theme users.
applyTheme(useThemeStore.getState().theme);
