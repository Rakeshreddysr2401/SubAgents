import { beforeEach, describe, expect, it, vi } from "vitest";

// The vitest jsdom env can ship Node's stub localStorage (no-op functions
// missing entirely) — install a real in-memory one before the store loads.
const memory = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => memory.get(k) ?? null,
  setItem: (k: string, v: string) => void memory.set(k, v),
  removeItem: (k: string) => void memory.delete(k),
  clear: () => memory.clear(),
});
Object.defineProperty(window, "localStorage", {
  value: globalThis.localStorage,
  configurable: true,
});

import { useThemeStore } from "./themeStore";

describe("themeStore", () => {
  beforeEach(() => {
    memory.clear();
  });

  it("stamps data-theme on the document root", () => {
    useThemeStore.getState().setTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    useThemeStore.getState().setTheme("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("persists the choice", () => {
    useThemeStore.getState().setTheme("dark");
    expect(memory.get("subagents-theme")).toBe("dark");
  });

  it("toggle flips the theme", () => {
    useThemeStore.getState().setTheme("light");
    useThemeStore.getState().toggle();
    expect(useThemeStore.getState().theme).toBe("dark");
    useThemeStore.getState().toggle();
    expect(useThemeStore.getState().theme).toBe("light");
  });
});
