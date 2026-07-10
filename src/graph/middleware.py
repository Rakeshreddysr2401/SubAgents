"""Agent middlewares shared by every swarm agent.

All middlewares here implement BOTH wrap_model_call and awrap_model_call —
the graph runs exclusively via astream, but langchain requires the sync hook
too (and tests may drive agents synchronously).

Ordering in _make_agent matters:

    [dynamic_prompt, ResilientModelMiddleware, KeepOnlyLatestBridge,
     LiveClockMiddleware, HumanInTheLoopMiddleware]

ResilientModelMiddleware sits outermost among the wrap_model_call hooks so a
retry/fallback re-runs the inner request transforms; LiveClockMiddleware sits
INSIDE KeepOnlyLatestBridge so the clock SystemMessage it appends is never
mistaken for a handoff bridge and pruned.
"""

from __future__ import annotations

import logging
from datetime import datetime

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.errors import GraphInterrupt

logger = logging.getLogger(__name__)


# ── Handoff-bridge pruning ──────────────────────────────────────────────────

def _prune_stale_bridges(request: ModelRequest) -> ModelRequest:
    """Drop stale handoff-bridge SystemMessages from history.

    Bridges are the only SystemMessages inside `messages` (the agent's own
    system prompt travels separately). Old bridges from earlier turns would
    tell the model it is a *different* agent — keep only the most recent one.
    """
    system_indices = [
        i for i, m in enumerate(request.messages) if isinstance(m, SystemMessage)
    ]
    if len(system_indices) > 1:
        stale = set(system_indices[:-1])
        pruned = [m for i, m in enumerate(request.messages) if i not in stale]
        return request.override(messages=pruned)
    return request


class KeepOnlyLatestBridge(AgentMiddleware):
    """Prune stale handoff-bridge SystemMessages (sync + async)."""

    def wrap_model_call(self, request, handler):
        return handler(_prune_stale_bridges(request))

    async def awrap_model_call(self, request, handler):
        return await handler(_prune_stale_bridges(request))


# ── Trailing per-turn context: live clock + recalled memories ───────────────

def _time_context() -> str:
    """A live clock line, evaluated fresh on every model call.

    Agents need this to resolve relative times ("at 5", "tomorrow") into
    absolute ISO-8601 datetimes for tools like create_reminder. Minute
    resolution keeps retries within the same minute byte-identical.
    """
    now = datetime.now().astimezone().replace(second=0, microsecond=0)
    return (
        f"Current date & time: {now.isoformat()} ({now.tzname()}). "
        "Use this when interpreting relative times like 'at 5' or 'tomorrow'."
    )


def _with_clock(request: ModelRequest) -> ModelRequest:
    """Build the trailing SystemMessage: recalled memories + the live clock.

    Everything that changes per turn goes HERE, at the very END of the
    request, never into the system prompt: content at position 0 invalidates
    the whole llama.cpp KV prefix, while a trailing message re-prefills only
    the tail. (Memories used to live in the system prompt — that forced a
    full slot re-prefill on every single turn.)
    """
    parts = []
    memories = request.state.get("recalled_memories") or []
    if memories:
        parts.append(
            "## What you remember about this user\n"
            + "\n".join(f"- {m}" for m in memories)
        )
    parts.append(_time_context())
    return request.override(
        messages=[*request.messages, SystemMessage(content="\n\n".join(parts))]
    )


class LiveClockMiddleware(AgentMiddleware):
    """Append per-turn context (memories + time) as a TRAILING SystemMessage.

    The message exists only in the model request — never persisted to state.
    Must sit INSIDE KeepOnlyLatestBridge so the bridge pruner never sees it.
    """

    def wrap_model_call(self, request, handler):
        return handler(_with_clock(request))

    async def awrap_model_call(self, request, handler):
        return await handler(_with_clock(request))


# ── Image stripping for text-only agents ────────────────────────────────────

_IMAGE_PLACEHOLDER = (
    "[camera frame omitted — this agent cannot see images; "
    "transfer_to_conversation for visual questions]"
)


def _strip_image_blocks(request: ModelRequest) -> ModelRequest:
    """Replace image blocks with a stable text placeholder.

    Camera frames land in shared history (capture_webcam tool results). A
    text-only agent (swiggy/instamart/dineout/tracker/planner) can't use
    them, but would still pay their (huge) token cost on every prefill of its
    KV slot. The placeholder is byte-identical across calls, so the stripped
    history stays cache-stable.
    """
    changed = False
    messages = []
    for m in request.messages:
        content = m.content
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "image_url" for b in content
        ):
            blocks = [
                b for b in content
                if not (isinstance(b, dict) and b.get("type") == "image_url")
            ]
            blocks.append({"type": "text", "text": _IMAGE_PLACEHOLDER})
            messages.append(m.model_copy(update={"content": blocks}))
            changed = True
        else:
            messages.append(m)
    return request.override(messages=messages) if changed else request


class StripImagesMiddleware(AgentMiddleware):
    """Drop image blocks from the request for agents that can't see.

    Request-only (never persisted): the conversation agent still sees the
    full frames when control returns to it.
    """

    def wrap_model_call(self, request, handler):
        return handler(_strip_image_blocks(request))

    async def awrap_model_call(self, request, handler):
        return await handler(_strip_image_blocks(request))


# ── Primary/fallback resilience ─────────────────────────────────────────────

DEGRADED_OFFLINE_REPLY = (
    "I can't reach my language model server right now, so I can't help with "
    "that just yet. Please check that the model server is running (Settings → "
    "LLM health shows its status) and try again."
)
DEGRADED_ERROR_REPLY = (
    "Something went wrong while talking to my language model. Please try "
    "again — if it keeps happening, check the server logs."
)


class ResilientModelMiddleware(AgentMiddleware):
    """pi5's safe_invoke policy at the create_agent middleware seam.

    - Primary in cooldown + fallback configured → call the fallback directly
      (no connect attempt against a known-dead server).
    - Connection-class failure → one visible retry on the primary, then mark
      it down for the cooldown window and try the fallback.
    - Request-shaped failure → no fallback (it would fail the same way).
    - Never raises: total failure returns a degraded AIMessage so the SSE
      stream still emits a normal delta + done instead of an error event.

    Deliberately NOT langchain's ModelFallbackMiddleware: that retries per
    call with no memory, so a dead primary costs a connect timeout on every
    single turn; the cooldown window is the product feature.
    """

    def wrap_model_call(self, request, handler):
        from src.configs.llm import get_fallback_llm
        from src.services import llm_registry as reg

        fallback = get_fallback_llm()
        if fallback is not None and not reg.primary_available():
            try:
                response = handler(request.override(model=fallback))
                reg.report_fallback_used()
                return response
            except GraphInterrupt:
                raise
            except Exception:
                logger.exception("Fallback LLM failed while primary is down")
                return _degraded(DEGRADED_OFFLINE_REPLY)

        try:
            response = handler(request)
            reg.report_primary_success()
            return response
        except GraphInterrupt:
            raise
        except Exception as exc:
            if not reg.is_connection_error(exc):
                logger.exception("Primary LLM request error (no fallback attempted)")
                return _degraded(DEGRADED_ERROR_REPLY)
            try:  # one visible retry on the primary
                response = handler(request)
                reg.report_primary_success()
                return response
            except GraphInterrupt:
                raise
            except Exception as exc2:
                if not reg.is_connection_error(exc2):
                    logger.exception("Primary LLM request error on retry")
                    return _degraded(DEGRADED_ERROR_REPLY)
                reg.report_primary_failure()
                if fallback is not None:
                    try:
                        response = handler(request.override(model=fallback))
                        reg.report_fallback_used()
                        return response
                    except GraphInterrupt:
                        raise
                    except Exception:
                        logger.exception("Fallback LLM failed after primary went down")
                return _degraded(DEGRADED_OFFLINE_REPLY)

    async def awrap_model_call(self, request, handler):
        from src.configs.llm import get_fallback_llm
        from src.services import llm_registry as reg

        fallback = get_fallback_llm()
        if fallback is not None and not reg.primary_available():
            try:
                response = await handler(request.override(model=fallback))
                reg.report_fallback_used()
                return response
            except GraphInterrupt:
                raise
            except Exception:
                logger.exception("Fallback LLM failed while primary is down")
                return _degraded(DEGRADED_OFFLINE_REPLY)

        try:
            response = await handler(request)
            reg.report_primary_success()
            return response
        except GraphInterrupt:
            raise
        except Exception as exc:
            if not reg.is_connection_error(exc):
                logger.exception("Primary LLM request error (no fallback attempted)")
                return _degraded(DEGRADED_ERROR_REPLY)
            try:  # one visible retry on the primary
                response = await handler(request)
                reg.report_primary_success()
                return response
            except GraphInterrupt:
                raise
            except Exception as exc2:
                if not reg.is_connection_error(exc2):
                    logger.exception("Primary LLM request error on retry")
                    return _degraded(DEGRADED_ERROR_REPLY)
                reg.report_primary_failure()
                if fallback is not None:
                    try:
                        response = await handler(request.override(model=fallback))
                        reg.report_fallback_used()
                        return response
                    except GraphInterrupt:
                        raise
                    except Exception:
                        logger.exception("Fallback LLM failed after primary went down")
                return _degraded(DEGRADED_OFFLINE_REPLY)


def _degraded(text: str) -> ModelResponse:
    return ModelResponse(result=[AIMessage(content=text)])
