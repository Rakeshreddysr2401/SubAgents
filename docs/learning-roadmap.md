# Learning Roadmap (Phase 2 — design only, no code yet)

Goal (PRD #4): the assistant should *fit its user better over time* — learn
preferences, habits, and routines, with something like a monthly "training"
cadence. This document describes how that will work on top of what the system
already captures today. Nothing here is implemented; it's the agreed direction
so current code keeps collecting the right raw material.

## What is already being collected (today)

| Signal | Where it lands | Written by |
|---|---|---|
| Long-term user facts ("likes dosa", "vegetarian") | Mem0 → Qdrant `mem0_memories`, user-scoped | `src/memory/post_turn.py` after every turn |
| Turn summaries (what was asked/answered) | Qdrant `history`, user-scoped | post-turn pipeline |
| Webcam-frame descriptions (what the camera saw) | Qdrant `history` | post-turn pipeline |
| Structured shopping behaviour | Postgres `shopping_items` (incl. purchased history) | shopping tools/panel |
| Reminder patterns (what/when the user schedules) | Postgres `reminders` (fired rows are kept) | reminder tools |
| Chat threads per user | Postgres `chat_threads` + LangGraph checkpoints | chat runtime |

This is deliberately everything a preference profile needs — no new collection
work is required for phase 2.

## Phase 2 design: monthly preference distillation

1. **Batch export** (monthly cron or manual command): for each user, pull
   - all Mem0 facts,
   - the last N `history` summaries,
   - shopping purchase history + reminder patterns.
2. **Distill** with the main LLM into a compact, structured *preference
   profile* (YAML/JSON: food preferences, active hours, recurring reminders,
   common requests, tone preferences). Keep it small — a profile is a prompt
   ingredient, not a dataset.
3. **Store** the profile per user (new Postgres table `user_profiles`, one
   JSON column + `generated_at`).
4. **Inject** at runtime through the *existing* seam: the `dynamic_prompt`
   middleware in `src/graph/swarm.py` already appends "What you remember about
   this user" from `recalled_memories`; the profile becomes a second, stable
   section there. No graph changes needed.
5. **Evaluate before replace**: keep the previous profile; a new monthly
   profile replaces the old one only after a sanity check (non-empty, schema
   valid). Rollback = keep previous row.

## Actual fine-tuning (later, optional)

If/when a local model is the daily driver (Ollama/llama.cpp), the same monthly
export can be reshaped into instruction pairs (user request → good assistant
reply, mined from positively-signalled turns) for a LoRA pass. Preconditions:
- an explicit feedback signal in the UI (👍/👎 per reply — small frontend task),
- enough volume per user (hundreds of pairs), and
- a repeatable eval set so a tuned model must beat the base before adoption.

Until those exist, prompt-injected profiles (steps 1–5) deliver most of the
value with none of the training risk — that's why they come first.

## Explicit non-goals for phase 2

- No cross-user learning (profiles are strictly per-user).
- No changes to Mem0's extraction pipeline.
- No automatic fine-tune deployment without a human check.
