export interface User {
  id: string;
  email: string;
}

export interface Thread {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export type MessageRole = "human" | "ai";

export interface StoredMessage {
  role: MessageRole;
  content: string;
}

export interface ThreadMessagesResponse {
  thread_id: string;
  title?: string;
  messages: StoredMessage[];
}

export interface Todo {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

export interface ToolCallEvent {
  id: string;
  name: string;
  args: unknown;
  agent: string;
}

export interface ToolResultEvent {
  id: string;
  name: string;
  result_preview: string;
  agent: string;
}

export interface ActionRequest {
  name: string;
  args: Record<string, unknown>;
  description?: string;
}

export interface ReviewConfig {
  action_name: string;
  allowed_decisions: ("approve" | "edit" | "reject" | "respond")[];
}

export interface InterruptEvent {
  id: string;
  action_requests: ActionRequest[];
  review_configs: ReviewConfig[];
}

/** Mirrors langchain.agents.middleware.human_in_the_loop.Decision. */
export type ResumeDecision =
  | { type: "approve" }
  | { type: "edit"; edited_action: { name: string; args: Record<string, unknown> } }
  | { type: "reject"; message?: string }
  | { type: "respond"; message: string };

/** Chat SSE event shapes — must match src/api/chat.py's documented contract. */
export type ChatEvent =
  | { delta: string }
  | { agent: string }
  | { tool_call: ToolCallEvent }
  | { tool_result: ToolResultEvent }
  | { interrupt: InterruptEvent }
  | { done: true; thread_id: string; active_agent?: string }
  | { error: string };
