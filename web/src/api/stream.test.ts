/** The SSE parser is contract-critical: token deltas must survive chunk
 * splits mid-line, and unknown event keys must pass through untouched. */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatEvent } from "./types";

const authFetchMock = vi.fn();

vi.mock("./client", () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
  parseJsonError: async (res: Response) => `HTTP ${res.status}`,
}));

import { resumeChat, streamChat } from "./stream";

function sseResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(stream, { status, headers: { "Content-Type": "text/event-stream" } });
}

async function collect(gen: AsyncGenerator<ChatEvent>): Promise<ChatEvent[]> {
  const events: ChatEvent[] = [];
  for await (const e of gen) events.push(e);
  return events;
}

beforeEach(() => {
  authFetchMock.mockReset();
});

describe("SSE stream parser", () => {
  it("parses whole events", async () => {
    authFetchMock.mockResolvedValue(sseResponse([
      'data: {"delta": "Hel"}\n\n',
      'data: {"delta": "lo"}\n\n',
      'data: {"done": true, "thread_id": "t1", "active_agent": "conversation"}\n\n',
    ]));
    const events = await collect(streamChat("t1", "hi", false));
    expect(events).toEqual([
      { delta: "Hel" },
      { delta: "lo" },
      { done: true, thread_id: "t1", active_agent: "conversation" },
    ]);
  });

  it("buffers a data line split across chunks", async () => {
    authFetchMock.mockResolvedValue(sseResponse([
      'data: {"del',
      'ta": "split token"}\n\ndata: {"done": true, "thread_id": "t1"}\n\n',
    ]));
    const events = await collect(streamChat("t1", "hi", false));
    expect(events[0]).toEqual({ delta: "split token" });
    expect(events).toHaveLength(2);
  });

  it("passes unknown event keys through (additive contract)", async () => {
    authFetchMock.mockResolvedValue(sseResponse([
      'data: {"progress": "Searching the web…"}\n\n',
      'data: {"brand_new_event": {"x": 1}}\n\n',
    ]));
    const events = await collect(streamChat("t1", "hi", false));
    expect(events[0]).toEqual({ progress: "Searching the web…" });
    expect(events[1]).toEqual({ brand_new_event: { x: 1 } });
  });

  it("skips malformed lines without aborting the stream", async () => {
    authFetchMock.mockResolvedValue(sseResponse([
      "data: {not json}\n\n",
      'data: {"delta": "still alive"}\n\n',
    ]));
    const events = await collect(streamChat("t1", "hi", false));
    expect(events).toEqual([{ delta: "still alive" }]);
  });

  it("ignores non-data lines (comments, blank lines)", async () => {
    authFetchMock.mockResolvedValue(sseResponse([
      ": heartbeat\n\n",
      'data: {"agent": "swiggy"}\n\n',
    ]));
    const events = await collect(streamChat("t1", "hi", false));
    expect(events).toEqual([{ agent: "swiggy" }]);
  });

  it("throws the parsed error body on a failed response", async () => {
    authFetchMock.mockResolvedValue(sseResponse([], 429));
    await expect(collect(streamChat("t1", "hi", false))).rejects.toThrow("HTTP 429");
  });

  it("sends checkpoint_id when forking (time travel)", async () => {
    authFetchMock.mockResolvedValue(sseResponse(['data: {"done": true, "thread_id": "t1"}\n\n']));
    await collect(streamChat("t1", "edited question", false, null, "ckpt-42"));
    const body = JSON.parse((authFetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.checkpoint_id).toBe("ckpt-42");
    expect(body.query).toBe("edited question");
  });

  it("resumeChat posts decisions to /chat/resume", async () => {
    authFetchMock.mockResolvedValue(sseResponse(['data: {"done": true, "thread_id": "t1"}\n\n']));
    await collect(resumeChat("t1", [{ type: "approve" }], false));
    const url = String(authFetchMock.mock.calls[0][0]);
    expect(url).toContain("/chat/resume");
    const body = JSON.parse((authFetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.decisions).toEqual([{ type: "approve" }]);
  });
});
