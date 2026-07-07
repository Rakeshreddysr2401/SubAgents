import { create } from "zustand";
import type { InterruptEvent, Todo } from "../api/types";

export interface ToolActivityItem {
  id: string;
  name: string;
  agent: string;
  args?: unknown;
  status: "calling" | "done";
  resultPreview?: string;
}

interface ChatStreamState {
  activeAgent: string;
  toolTimeline: ToolActivityItem[];
  pendingInterrupt: (InterruptEvent & { botId: string }) | null;
  todos: Todo[] | null;
  setActiveAgent: (agent: string) => void;
  addToolCall: (call: { id: string; name: string; agent: string; args?: unknown }) => void;
  addToolResult: (result: { id: string; name: string; agent: string; result_preview: string }) => void;
  setPendingInterrupt: (interrupt: (InterruptEvent & { botId: string }) | null) => void;
  setTodos: (todos: Todo[]) => void;
  resetTurn: () => void;
}

export const useChatStream = create<ChatStreamState>((set) => ({
  activeAgent: "conversation",
  toolTimeline: [],
  pendingInterrupt: null,
  todos: null,
  setActiveAgent: (agent) => set({ activeAgent: agent }),
  addToolCall: (call) =>
    set((state) => ({
      toolTimeline: [...state.toolTimeline, { ...call, status: "calling" }],
    })),
  addToolResult: (result) =>
    set((state) => ({
      toolTimeline: state.toolTimeline.map((item) =>
        item.id === result.id
          ? { ...item, status: "done", resultPreview: result.result_preview }
          : item,
      ),
    })),
  setPendingInterrupt: (interrupt) => set({ pendingInterrupt: interrupt }),
  setTodos: (todos) => set({ todos }),
  resetTurn: () => set({ toolTimeline: [], pendingInterrupt: null }),
}));
