# Mr.ceo

A platform where users create **sub-agents with specific roles or skills**, then give instructions to a single **Manager**. The Manager breaks the work down, delegates it to the right sub-agents, and they work **in the background**, sending updates as they finish.

## Status

> Working prototype: FastAPI backend (Manager + sub-agents, SSE) and a Next.js frontend (tasks, Manager chat, sub-agent conversations). This README is updated as the project progresses.

## Getting Started

Requirements: Python 3.11+ and Node.js 20+. Run the backend and the frontend in two terminals.

**1. Backend** (http://localhost:8000, API docs at `/docs`)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

With no `ANTHROPIC_API_KEY` the backend runs in fake mode (no LLM calls), so you can try the whole flow for free. For real models, create `backend/.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
# or use a local model:
# LLM_PROVIDER=ollama
```

**2. Frontend** (http://localhost:3000)

```bash
cd frontend
cp .env.example .env.local       # NEXT_PUBLIC_API_URL, default http://localhost:8000
npm install
npm run dev
```

Open http://localhost:3000, create a sub-agent with the **+** in the right pane, then message the Manager.

Other frontend commands: `npm run typecheck`, `npm run build && npm start`.

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

## Project Structure

```
Mr.ceo/
├── backend/     # FastAPI service (see backend/README.md)
├── frontend/    # Next.js app (see frontend/README.md)
└── README.md
```

![Querry Processing](image.png) 
![Query compeleted](image-1.png)