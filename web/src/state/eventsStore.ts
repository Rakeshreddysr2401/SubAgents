import { create } from "zustand";

interface EventsState {
  /** True while the /events EventSource is open. */
  connected: boolean;
  /** Bump counters: panels refetch whenever these change. */
  remindersBump: number;
  shoppingBump: number;
  /** Guardian mode, kept in sync across the UI toggle and voice commands. */
  guardianEnabled: boolean;
  setConnected: (connected: boolean) => void;
  bumpReminders: () => void;
  bumpShopping: () => void;
  setGuardianEnabled: (guardianEnabled: boolean) => void;
}

/** Written by EventsBridge (the single /events subscription owner); read by
 * panels and the wake-word indicator. */
export const useEventsStore = create<EventsState>((set) => ({
  connected: false,
  remindersBump: 0,
  shoppingBump: 0,
  guardianEnabled: false,
  setConnected: (connected) => set({ connected }),
  bumpReminders: () => set((s) => ({ remindersBump: s.remindersBump + 1 })),
  bumpShopping: () => set((s) => ({ shoppingBump: s.shoppingBump + 1 })),
  setGuardianEnabled: (guardianEnabled) => set({ guardianEnabled }),
}));
