# API Reference

Base URL: `http://localhost:2024`.

**Auth**: when `AUTH_DISABLED=false` (see `docs/setup.md`), every endpoint below
except `/auth/signup`, `/auth/login`, `/auth/refresh`, `/health`, and `/events`
requires a session — either the httpOnly `access_token` cookie set by
`/auth/login`/`/auth/signup`/`/auth/refresh`, or an `Authorization: Bearer <jwt>`
header for non-browser clients (checked before the cookie). With
`AUTH_DISABLED=true` (the dev default) every request maps to `default_user` and
none of this is enforced. Full design: [CLAUDE.md → Auth & Sessions](../CLAUDE.md#auth--sessions-src-apiauthpy).

## Auth

### POST /auth/signup

`{ "email": "...", "password": "..." }` (password ≥ 8 chars) → creates the
account, sets session cookies, returns `{ "id": "...", "email": "..." }`.
`409` if the email is already registered.

### POST /auth/login

`{ "email": "...", "password": "..." }` → sets session cookies, returns the
same user shape. `401` on wrong email/password (same message for both, to
avoid leaking which emails are registered).

### POST /auth/refresh

No body; reads the `refresh_token` cookie. Rotates it (old one is deleted from
Redis and can't be reused) and issues a fresh access + refresh pair. `401` and
clears cookies if the refresh token is missing, expired, or already used.

### POST /auth/logout

Revokes the refresh token server-side and clears both cookies.

### GET /auth/me

Returns `{ "id": "...", "email": "..." }` for the current session.

### POST /auth/change-password

`{ "current_password": "...", "new_password": "..." }`. `401` if
`current_password` is wrong.

### DELETE /auth/account

`{ "password": "..." }`. Deletes the user and cascades to all their
`chat_threads`. `401` if the password is wrong.

## GET /threads

List the current user's conversations, most recently active first:

```json
[{ "id": "...", "title": "...", "created_at": "...", "updated_at": "..." }]
```

A thread only appears here after its first `/chat` message (the title is
derived from that message).

## GET /threads/{thread_id}/messages

Same shape as `GET /history/{thread_id}` (below) plus `title`. `404` if the
thread doesn't exist or isn't owned by the current user.

## PATCH /threads/{thread_id}

`{ "title": "..." }` → renames the thread. `404` if not owned by the caller.

## DELETE /threads/{thread_id}

Removes the thread's ownership row (the sidebar entry). `404` if not owned by
the caller.

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
`404` if the thread doesn't exist or isn't owned by the current user (ownership
is tracked separately from the checkpoint — see `GET /threads`).

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

**Auth**: the browser's WS handshake carries the `access_token` cookie
automatically (same-origin); a non-browser client can pass `?token=<jwt>`
instead. The connection is closed before `accept()` — code `4401` if
unauthenticated, `4403` if `thread_id` is already owned by a different user. A
brand-new `thread_id` has no owner yet, so it's let through (ownership is
attributed on the first `/chat` call for that thread).

## GET /events

SSE channel the browser subscribes to for wake-word triggers. Emits
`start_voice` when `/trigger_voice` is called; otherwise heartbeats.

## POST /trigger_voice

Called by `wake_word.py`. Pushes a `start_voice` event onto `/events`.

## GET /health

`{"status": "ok", "service": "subagents"}`

## Rate limiting

`/chat` and `/upload` are limited to `RATE_LIMIT_PER_MINUTE` (default 20) per
user per minute; exceeding returns HTTP 429. `/auth/signup` and `/auth/login`
are separately rate-limited (by client IP and by email, respectively) to slow
down account-creation abuse and password brute-forcing.
