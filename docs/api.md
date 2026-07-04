# API Reference

Base URL: `http://localhost:2024`. Auth: `Authorization: Bearer <jwt>` — required
only when `AUTH_DISABLED=false`; otherwise requests map to `default_user`.

## POST /chat

Run a turn and stream the response as Server-Sent Events.

**Query params**: `thread_id` (optional; a UUID is generated if omitted)
**Body**:
```json
{ "query": "order me a dosa", "always_speak": false }
```

**SSE events** (each is a JSON object on a `data:` line):

| Event | When | Shape |
|---|---|---|
| token delta | 0..n times | `{"delta": "<text>"}` |
| done | once, on success | `{"done": true, "thread_id": "...", "active_agent": "conversation\|swiggy\|tracker"}` |
| error | on failure/timeout | `{"error": "<message>"}` |

Tokens must be concatenated in order to form the reply. (A legacy
`{"text": "..."}` full-response event is still handled by the frontend for
backward compatibility but is no longer emitted.)

## GET /history/{thread_id}

Returns the stored conversation for a thread from the LangGraph checkpoint.

```json
{ "thread_id": "...", "messages": [ {"role": "human", "content": "..."}, {"role": "ai", "content": "..."} ] }
```

## POST /upload

Ingest a document into the user's RAG corpus. `multipart/form-data` with a
`file` field. Allowed: `.pdf`, `.txt`, `.md`. Max size `UPLOAD_MAX_BYTES`
(default 10 MB).

```json
{ "doc_id": "uuid-or-null", "filename": "notes.pdf", "chunks": 12 }
```

## WS /ws/frames

WebSocket for webcam frames. Query param `thread_id`. Send base64-JPEG text
frames (browser) or binary JPEG (Jetson). The latest frame per thread is stored
in Redis with a TTL and consumed by the `capture_webcam` tool.

## GET /events

SSE channel the browser subscribes to for wake-word triggers. Emits
`start_voice` when `/trigger_voice` is called; otherwise heartbeats.

## POST /trigger_voice

Called by `wake_word.py`. Pushes a `start_voice` event onto `/events`.

## GET /health

`{"status": "ok", "service": "subagents"}`

## Rate limiting

`/chat` and `/upload` are limited to `RATE_LIMIT_PER_MINUTE` (default 20) per
user per minute; exceeding returns HTTP 429.
