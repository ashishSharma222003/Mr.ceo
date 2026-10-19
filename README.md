# Mr.ceo

A platform where users create **sub-agents with specific roles or skills**, then give instructions to a single **Manager**. The Manager breaks the work down, delegates it to the right sub-agents, and they work **in the background**, sending updates as they finish.

## Status

> Idea stage. No code yet. This README is updated as the project progresses.

## The Idea

```
USER ──► Manager ──► Agent (role a)
                 ├─► Agent (role b)
                 └─► Agent (role c)
            │
            └──► User Response
```

1. The user gives an instruction to the Manager.
2. The Manager plans the work and routes tasks to the required sub-agents.
3. Sub-agents run in the background, so the user isn't blocked waiting.
4. Results flow back to the Manager, which sends progress updates and a final response to the user.

### Core concepts

- **Manager:** the single entry point. It plans, routes, tracks tasks, and summarizes results.
- **Sub-agent:** user-defined configuration (name, role prompt, tools, model, permissions), not custom code. One generic runner executes any of them.
- **Task:** a first-class record (id, assigned agent, status, result, logs). Both the Manager and the UI read from it.
- **Updates:** live progress streamed to the UI, plus notifications for long-running jobs.

## Planned Architecture

```
User ─► API ─► Manager (LLM: plan + route)
                  │ creates Task records
                  ▼
             Job queue
                  │
        ┌─────────┼─────────┐
     Worker    Worker    Worker   (each runs one sub-agent)
        │         │         │
        └────► Task DB ─► event stream (SSE) ─► UI
```

## Planned Stack

**Backend** (`/backend`)
- Python, FastAPI, Pydantic v2
- Postgres (SQLAlchemy 2 async, Alembic)
- Redis + async task queue (ARQ or Taskiq)
- SSE for live updates
- Agent layer: LangGraph or Claude Agent SDK (to be decided)

**Frontend** (`/frontend`)
- Next.js, React, TypeScript
- Tailwind CSS + shadcn/ui
- TanStack Query, Zustand
- Typed API client generated from FastAPI's OpenAPI schema
- Possible: assistant-ui / Vercel AI SDK for chat, React Flow for an agent/task canvas

## Core Screens (to design first)

- Chat with the Manager
- Task board / live timeline
- Agent builder
- Agent detail
- Settings

## Roadmap

- [ ] Decide agent framework (LangGraph vs Claude Agent SDK)
- [ ] Design the core screens and design system
- [ ] Scaffold backend and frontend, plus docker-compose (Postgres, Redis)
- [ ] Vertical slice: message, Manager dispatches a fake task, worker runs it, SSE streams progress, UI shows result
- [ ] Real Manager routing and sub-agent runner
- [ ] Agent builder UI
- [ ] Auth
- [ ] Limits and safety: per-task step, token, and time caps; human approval for risky actions

## Open Questions

- Auth in v1 or later?
- LangGraph or Claude Agent SDK for the agent layer?
- Single-user first, or multi-tenant from the start?

## Project Structure

```
Mr.ceo/
├── backend/     # FastAPI service (empty for now)
├── frontend/    # Next.js app (empty for now)
└── README.md
```
