# Mr.ceo Backend

A FastAPI service where you talk to a **Manager** (an LLM agent) and it delegates work to **sub-agents** you define. Sub-agents run in the background, and their progress streams to the frontend in real time.

```
User ──chat──▶ Manager (LLM) ──tool calls──▶ Sub-agents (LLM, background) ──▶ Task results
                                                                  │
                                           SSE /api/events ◀──────┘ (live status updates)
```

---

## 1. Tech stack

| Concern | Choice |
|---|---|
| Web framework | FastAPI (async) + Uvicorn |
| Database | SQLite via SQLModel + SQLAlchemy async (`aiosqlite`) |
| LLM orchestration | LangChain `create_agent` (+ LangGraph SQLite checkpointer for memory) |
| LLM provider | Anthropic (`langchain-anthropic`) |
| Memory / chat history | `AsyncSqliteSaver` checkpointer + `ChatMessage` table, in the same SQLite file as the app DB |
| Live updates | Server-Sent Events (`sse-starlette`) |
| Config | `pydantic-settings` (reads `.env`) |

---

## 2. Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit as needed
uvicorn app.main:app --reload --port 8000
```

- API docs (Swagger): http://localhost:8000/docs
- Health check: `GET /health` → `{"status": "ok"}`
- Tables are created automatically on startup (`init_db()`); there are no migrations. The checkpointer tables (`checkpoints`, `writes`) are created by `init_checkpointer()` in the same file.

### Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./mrceo.db` | DB connection string. Must be SQLite: the checkpointer opens the same file |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed frontend origins (JSON list) |
| `ANTHROPIC_API_KEY` | *(empty)* | **Empty = fake mode** (see below) |
| `MANAGER_MODEL` | `claude-sonnet-5-5` | Model used by the Manager |

### Fake mode

If `ANTHROPIC_API_KEY` is empty, no LLM is called:
- The Manager sends your message to **every** agent.
- Each agent waits 3 seconds and returns a canned result.

This lets you build and test the frontend and the whole task lifecycle without spending tokens.

---

## 3. Project structure

```
backend/
├── .env.example
├── requirements.txt
└── app/
    ├── main.py          # App creation, CORS, router mounting, startup (init_db, init_checkpointer), /health
    ├── config.py        # Settings (env vars)
    ├── db.py            # Async engine, session factory, init_db, get_session dependency
    ├── models.py        # DB tables: Agent, Task, ChatMessage (+ TaskStatus enum)
    ├── schemas.py       # Request/response bodies (AgentCreate, AgentUpdate, ChatRequest, ChatResponse)
    ├── routes/          # HTTP layer (thin: validation + calling services/DB)
    │   ├── agents.py    # Agent CRUD
    │   ├── tasks.py     # Task read endpoints + SSE event stream
    │   └── chat.py      # Talk to the Manager
    └── services/        # Business logic
        ├── manager.py   # Manager agent: builds delegation tools, dispatches tasks
        ├── runner.py    # Runs one task on one sub-agent in the background
        ├── memory.py    # Conversation memory (SQLite checkpointer), chat-message saving, thread-id helper
        └── events.py    # In-memory pub/sub that feeds the SSE endpoint
```

Layering: **routes → services → db/models**. Routes never contain LLM logic; services never know about HTTP.

---

## 4. Data model

### `Agent`
A sub-agent definition. Created by the user, fully data-driven. There is no code per agent.

| Field | Type | Notes |
|---|---|---|
| `id` | int | PK |
| `name` | str | Shown to the Manager and used to name its tool |
| `role_prompt` | str | The agent's system prompt (who it is, what it does) |
| `model` | str | Anthropic model id, default `claude-sonnet-5-5` |
| `skills` | list[str] (JSON) | Currently appended to the prompt as text (see TODOs) |
| `created_at` | datetime (UTC) | |

### `Task`
One unit of work given to one agent.

| Field | Type | Notes |
|---|---|---|
| `id` | int | PK |
| `agent_id` | int | FK → `agent.id` |
| `instruction` | str | What the Manager asked the agent to do |
| `thread_id` | str \| null | The Manager conversation this task belongs to |
| `status` | enum | `pending` → `running` → `done` \| `failed` |
| `result` | str \| null | Agent output, or the error message if failed |
| `created_at` / `finished_at` | datetime | |

### `ChatMessage`
Every chat message, saved in the same SQLite file as the checkpoints.

| Field | Type | Notes |
|---|---|---|
| `id` | int | PK |
| `thread_id` | str | Manager conversation id (indexed) |
| `role` | str | `user`, `manager` or `agent` |
| `content` | str | Message text |
| `agent_id` | int \| null | FK → `agent.id`; set for Manager ↔ sub-agent messages |
| `created_at` | datetime (UTC) | |

---

## 5. API reference

All routes are mounted under `/api` (except `/health`).

### Agents: `routes/agents.py`
| Method | Path | Description |
|---|---|---|
| GET | `/api/agents` | List all agents |
| POST | `/api/agents` | Create an agent (`name`, `role_prompt`, optional `model`, `skills`) → 201 |
| GET | `/api/agents/{id}` | Get one agent (404 if missing) |
| PATCH | `/api/agents/{id}` | Partial update; only fields you send change |
| DELETE | `/api/agents/{id}` | Delete the agent **and all its tasks** → 204 |

### Chat: `routes/chat.py`
| Method | Path | Description |
|---|---|---|
| POST | `/api/chat` | Send a message to the Manager |
| GET | `/api/chat/{thread_id}/messages` | Saved messages of a thread, oldest first |

Request: `{ "message": "...", "thread_id": "optional" }`
Response: `{ "thread_id": "...", "reply": "...", "tasks": [Task, ...] }`

- Omit `thread_id` to start a new conversation; a new one is generated and returned.
- Send the same `thread_id` back to continue the conversation, so the Manager and the sub-agents remember earlier messages.
- `reply` is the Manager's text. `tasks` are the tasks it **just created** (they're still running, so poll or listen on SSE for results).

### Tasks and live events: `routes/tasks.py`
| Method | Path | Description |
|---|---|---|
| GET | `/api/tasks` | All tasks, newest first |
| GET | `/api/tasks/{id}` | One task (404 if missing) |
| GET | `/api/events` | **SSE stream** of `task.updated` events |

SSE event format:
```
event: task.updated
data: {"id": 3, "agent_id": 1, "status": "running", "result": null, ...}   # full Task as JSON
```
An event is emitted when a task is created (`pending`), starts (`running`), and finishes (`done`/`failed`).

---

## 6. End-to-end flow

### 6.1 Creating agents
`POST /api/agents` stores a row in `agent`. That's it: no restart or registration is needed. The Manager reads the agent list from the DB on every message.

### 6.2 Chatting: the main flow

```
POST /api/chat {message, thread_id?}
  │
  ▼
routes/chat.py        generate thread_id if missing → manager.handle_message(...)
  │
  ▼
services/manager.py   load all Agents from DB
  │                   ├─ no agents        → "You have no agents yet. Create one first."
  │                   ├─ no API key       → FAKE MODE: dispatch message to every agent
  │                   └─ API key present  → build Manager LLM agent:
  │                          • one tool per sub-agent: delegate_to_<name>_<id>
  │                            (description = agent's role + skills)
  │                          • system prompt: "never do the work, delegate"
  │                          • checkpointer = shared memory, keyed by thread_id
  │                        Manager decides which tool(s) to call
  │
  ▼  (each tool call)
_dispatch()           1. INSERT Task(status=pending)
                      2. publish SSE "task.updated"
                      3. asyncio.create_task(run_task(task.id))  ← fire & forget
                      4. return immediately: "Task #N started on 'X'"
  │
  ▼
HTTP response returns right away with the Manager's reply + the new tasks
(the sub-agents are still working)
```

### 6.3 Background task execution (`services/runner.py`)

```
run_task(task_id)                       # runs in its own DB session, outside the request
  1. status = running  → commit → SSE "task.updated"
  2. _execute(agent, task):
        fake mode → sleep 3s, return canned text
        real mode → create_agent(model=agent.model,
                                 system_prompt=role_prompt (+ skills list),
                                 checkpointer=shared memory)
                    invoke with task.instruction on thread "<thread_id>:<agent_id>"
  3. success → status = done,   result = agent output
     exception → status = failed, result = error message
  4. finished_at = now → commit → SSE "task.updated"
```

The frontend therefore: `POST /api/chat` → show the reply → listen to `GET /api/events` and update each task card as `task.updated` events arrive.

### 6.4 Memory and threads (`services/memory.py`)

Conversation history lives in a LangGraph `AsyncSqliteSaver` checkpointer. It uses the same SQLite file as the app DB (`DATABASE_URL`) and is opened at startup in `main.py`, so history survives restarts. There are two kinds of thread:

| Thread | Key | Holds |
|---|---|---|
| Manager | `<thread_id>` | User ↔ Manager conversation |
| Sub-agent | `<thread_id>:<agent_id>` | Manager ↔ that one sub-agent |

So in one conversation, a follow-up like "now make it shorter" is delegated to the same agent, which remembers what it did before. **Agent config (prompt, model, skills) is not stored in memory.** It is read fresh from the DB on every run, so editing an agent via `PATCH` takes effect on its next task, while its conversation history is kept.

**Chat log.** Separately from the checkpoints (which hold LangGraph state), `save_message()` writes readable rows to the `chatmessage` table:
- your messages (`user`) and the Manager's replies (`manager`);
- each instruction the Manager sends to a sub-agent (`manager`, with `agent_id`) and the sub-agent's result (`agent`, with `agent_id`).

Failed task errors are not saved as chat messages; they stay on `Task.result`. Read a thread with `GET /api/chat/{thread_id}/messages`.

### 6.5 Events (`services/events.py`)
A tiny in-memory pub/sub. Each connected SSE client gets an `asyncio.Queue`; `publish()` pushes to all of them. Clients are removed when they disconnect.

---

## 7. Key design decisions

- **Agents are data, not code.** Any number of agents can be created at runtime, and the Manager's tools are rebuilt from the DB per message.
- **Delegation is asynchronous.** The chat request never waits for sub-agents, so the UI stays responsive and tasks run in parallel.
- **Strict layering.** Routes are thin, and all LLM and orchestration logic lives in `services/`.
- **Fake mode** makes the full flow testable without an API key.

---

## 8. Known limitations and TODOs

- **Memory is SQLite-only**: `memory.py` derives the checkpointer path from `DATABASE_URL`, so switching the app DB to Postgres needs a different checkpointer.
- **Events are in-process** (`events.py`): works for a single server instance only. Swap for Redis to scale out.
- **Skills are text only**: they're listed in the sub-agent's prompt, not wired as real tools (`tools=[]` in `runner.py`).
- **No auth** on any endpoint; CORS is the only protection.
- **No migrations**: `create_all` only creates missing tables. It won't alter existing ones when models change (delete `mrceo.db` in dev).
- **Tasks in flight are lost on restart**: a task left `pending`/`running` when the server stops is never resumed or marked failed.
- **No task cancellation or retry** endpoints.
