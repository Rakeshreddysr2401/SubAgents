import { create } from "zustand";

export interface Toast {
  id: number;
  kind: "reminder" | "guardian" | "info";
  title: string;
  body: string;
  /** Persistent toasts stay until dismissed; others auto-dismiss. */
  persistent: boolean;
}

interface NotificationsState {
  toasts: Toast[];
  push: (toast: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;
const AUTO_DISMISS_MS = 6000;

export const useNotificationsStore = create<NotificationsState>((set) => ({
  toasts: [],
  push: (toast) => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts, { ...toast, id }] }));
    if (!toast.persistent) {
      setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
      }, AUTO_DISMISS_MS);
    }
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
