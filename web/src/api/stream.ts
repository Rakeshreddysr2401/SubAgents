import { authFetch, parseJsonError } from "./client";
import type { ChatEvent, ResumeDecision } from "./types";

/**
 * Read an SSE (data:-line) response body and yield parsed events.
 *
 * Both /chat and /chat/resume are POSTs with a JSON body, so native
 * EventSource (GET-only) can't be used — this ports static/index.html's
 * manual reader loop: buffer bytes, only process up to the last newline (a
 * `data: ...` line can arrive split across chunks), JSON.parse each line.
 * Unknown keys on a parsed event are preserved so future event types don't
 * require touching this parser.
 */
async function* consumeSSE(response: Response): AsyncGenerator<ChatEvent> {
  if (!response.ok || !response.body) {
    throw new Error(await parseJsonError(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lastNewline = buffer.lastIndexOf("\n");
    if (lastNewline === -1) continue;
    const lines = buffer.slice(0, lastNewline).split("\n");
    buffer = buffer.slice(lastNewline + 1);

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        yield JSON.parse(line.slice(6)) as ChatEvent;
      } catch {
        // ignore malformed lines rather than aborting the whole stream
      }
    }
  }
}

export function streamChat(threadId: string, query: string, alwaysSpeak: boolean): AsyncGenerator<ChatEvent> {
  const url = new URL("/chat", window.location.origin);
  if (threadId) url.searchParams.set("thread_id", threadId);

  const responsePromise = authFetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, always_speak: alwaysSpeak }),
  });
  return consumeStreamed(responsePromise);
}

export function resumeChat(
  threadId: string,
  decisions: ResumeDecision[],
  alwaysSpeak: boolean,
): AsyncGenerator<ChatEvent> {
  const url = new URL("/chat/resume", window.location.origin);
  url.searchParams.set("thread_id", threadId);

  const responsePromise = authFetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decisions, always_speak: alwaysSpeak }),
  });
  return consumeStreamed(responsePromise);
}

async function* consumeStreamed(responsePromise: Promise<Response>): AsyncGenerator<ChatEvent> {
  const response = await responsePromise;
  yield* consumeSSE(response);
}
