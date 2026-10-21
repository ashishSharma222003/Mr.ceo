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
| Tools / MCP | LangChain tools: built-in Python tools (`app/tools/`) + MCP servers via `langchain-mcp-adapters`, both managed as editable DB skills |
| LLM provider | Anthropic (`langchain-anthropic`) or local Ollama (`langchain-ollama`), chosen by `LLM_PROVIDER` |
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
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `ollama` |
| `ANTHROPIC_API_KEY` | *(empty)* | With provider `anthropic`, **empty = fake mode** (see below) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `MANAGER_MODEL` | provider default | Model for the Manager (`claude-sonnet-5-5` / `llama3.1`) |
| `DEFAULT_AGENT_MODEL` | provider default | Model given to agents created without one |

### Using Ollama

```bash
ollama serve                      # if it isn't already running
ollama pull llama3.1              # pick a model that supports tool calling
# .env
LLM_PROVIDER=ollama
```

Models must support **tool calling** (e.g. `llama3.1`, `qwen2.5`, `mistral-nemo`), because the Manager delegates and updates the tasklist through tools. Small models are noticeably worse at this than Claude. A model name can carry its own provider prefix, so one install can mix both: an agent with `"model": "anthropic:claude-sonnet-5-5"` or `"model": "ollama:qwen2.5:7b"`. Without a prefix, `LLM_PROVIDER` decides. If the LLM can't be reached (server down, model not pulled, bad key), `POST /api/chat` returns 502 with the reason, and a failing sub-agent task is marked `failed`.

### Fake mode

If `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` is empty, no LLM is called (Ollama never uses fake mode):
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
    ├── models.py        # DB tables: Agent, Task, ChatMessage, Todo, Skill (+ status enums)
    ├── schemas.py       # Request/response bodies (Agent*, Skill*, Todo*, Chat*)
    ├── routes/          # HTTP layer (thin: validation + calling services/DB)
    │   ├── agents.py    # Agent CRUD
    │   ├── skills.py    # Skill CRUD (builtin + MCP), editable at runtime
    │   ├── todos.py     # Tasklist: user can add / rename / remove items
    │   ├── tasks.py     # Task read endpoints + SSE event stream
    │   └── chat.py      # Talk to the Manager
    ├── tools/           # Built-in Python tools (LangChain StructuredTools)
    │   ├── registry.py  # BUILTIN_TOOLS dict + @builtin_tool decorator
    │   ├── calculator.py, clock.py   # example tools
    │   └── __init__.py  # importing the package registers every tool
    └── services/        # Business logic
        ├── manager.py   # Manager agent: delegation + tasklist tools; notified when tasks end
        ├── tasklist_tools.py  # Manager tools: get_tasklist, add_todo, rename_todo, remove_todo, complete_todo
        ├── todos.py     # Tasklist DB operations (+ SSE events)
        ├── runner.py    # Runs one task on one sub-agent in the background
        ├── skills.py    # Loads DB skills -> LangChain tools (+ MCP) for a sub-agent; seeds defaults
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
| `model` | str | Model name, optionally `provider:model`. Default: `DEFAULT_AGENT_MODEL` or the provider default |
| `skills` | list[str] (JSON) | Names of `Skill` rows; each resolves to real tools (see 6.6) |
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

### `Skill`
An editable capability that agents reference by name.

| Field | Type | Notes |
|---|---|---|
| `id` | int | PK |
| `name` | str | Unique. What `Agent.skills` contains |
| `description` / `instructions` | str | Shown to the agent in its system prompt |
| `type` | str | `builtin` or `mcp` |
| `tool_key` | str \| null | `builtin`: name of a Python tool in `app/tools` |
| `mcp_config` | JSON \| null | `mcp`: a `langchain-mcp-adapters` connection (needs `transport`) |

### `Todo`
One item of a conversation's tasklist, owned by the Manager.

| Field | Type | Notes |
|---|---|---|
| `id` | int | PK |
| `thread_id` | str | Manager conversation (indexed) |
| `title` | str | |
| `status` | enum | `todo` → `in_progress` (set on delegation) → `done` (**only the Manager sets this**) |
| `task_id` | int \| null | Latest sub-agent `Task` working on it |
| `created_at` / `updated_at` | datetime | |

### `ChatMessage`
Every chat message, saved in the same SQLite file as the checkpoints.

| Field | Type | Notes |
|---|---|---|
| `id` | int | PK |
| `thread_id` | str | Manager conversation id (indexed) |
| `role` | str | `user`, `manager`, `agent`, or `system` (internal `[UPDATE]` reports sent to the Manager) |
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
| POST | `/api/agents` | Create an agent (`name`, `role_prompt`, optional `model`, `skills`) → 201. Unknown skill names → 422 (see `/api/skills`) |
| GET | `/api/agents/{id}` | Get one agent (404 if missing) |
| PATCH | `/api/agents/{id}` | Partial update; only fields you send change |
| DELETE | `/api/agents/{id}` | Delete the agent **and all its tasks** → 204 |

### Skills: `routes/skills.py`
| Method | Path | Description |
|---|---|---|
| GET | `/api/skills` | List skills |
| GET | `/api/skills/builtin-tools` | Python tools a `builtin` skill can point at (`tool_key`) |
| POST | `/api/skills` | Create (`name`, `type`, + `tool_key` or `mcp_config`, optional `description`, `instructions`) → 201. Invalid → 422, duplicate name → 409 |
| GET | `/api/skills/{id}` | Get one (404 if missing) |
| PATCH | `/api/skills/{id}` | Partial update. Renaming also renames it in every agent's `skills` |
| DELETE | `/api/skills/{id}` | Delete; it is removed from every agent's `skills` → 204 |

### Tasklist: `routes/todos.py`
| Method | Path | Description |
|---|---|---|
| GET | `/api/threads/{thread_id}/todos` | The conversation's tasklist |
| POST | `/api/threads/{thread_id}/todos` | Add an item (`{"title": "..."}`) → 201 |
| PATCH | `/api/todos/{id}` | Rename (`{"title": "..."}`). **Status cannot be set by users** |
| DELETE | `/api/todos/{id}` | Remove an item → 204 |

### Chat: `routes/chat.py`
| Method | Path | Description |
|---|---|---|
| POST | `/api/chat` | Send a message to the Manager |
| GET | `/api/chat/{thread_id}/messages` | Saved messages of a thread, oldest first |

Request: `{ "message": "...", "thread_id": "optional" }`
Response: `{ "thread_id": "...", "reply": "...", "tasks": [Task, ...], "todos": [Todo, ...] }`

- Omit `thread_id` to start a new conversation; a new one is generated and returned.
- Send the same `thread_id` back to continue the conversation, so the Manager and the sub-agents remember earlier messages.
- `reply` is the Manager's text. `tasks` are the tasks it **just created** (they're still running, so poll or listen on SSE for results).

### Tasks and live events: `routes/tasks.py`
| Method | Path | Description |
|---|---|---|
| GET | `/api/tasks` | All tasks, newest first |
| GET | `/api/tasks/{id}` | One task (404 if missing) |
| GET | `/api/events` | **SSE stream**: `task.updated`, `todo.updated`, `todo.deleted`, `chat.message` |

SSE event format:
```
event: task.updated
data: {"id": 3, "agent_id": 1, "status": "running", "result": null, ...}   # full Task as JSON
```
A `task.updated` event is emitted when a task is created (`pending`), starts (`running`), and finishes (`done`/`failed`).

Other events carry JSON too: `todo.updated` / `todo.deleted` (the full Todo) on every tasklist change, and `chat.message` (`{thread_id, role: "manager", content}`) when the Manager posts a message on its own, e.g. after a sub-agent finishes. Show it in the chat window for that thread.

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
  │                          • tasklist tools: get_tasklist, add_todo, rename_todo, remove_todo, complete_todo
  │                          • system prompt: "delegate, keep the tasklist" + the current tasklist
  │                          • checkpointer = shared memory, keyed by thread_id
  │                        Manager decides which tool(s) to call
  │
  ▼  (each tool call)
_dispatch()           1. INSERT Task(status=pending)
                      2. publish SSE "task.updated"
                      2b. link a Todo (the given todo_id, or auto-create one) → in_progress
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
        real mode → tools, prompt = load_skills(agent.skills)
                    create_agent(model=agent.model, tools=tools,
                                 system_prompt=role_prompt + skills prompt,
                                 checkpointer=shared memory)
                    invoke with task.instruction on thread "<thread_id>:<agent_id>"
  3. success → status = done,   result = agent output
     exception → status = failed, result = error message
  4. finished_at = now → commit → SSE "task.updated"
```

After the task ends, `run_task` calls `manager.notify_task_finished(task_id)` (see 6.7).

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

### 6.6 Skills, tools and MCP

**Tools are plain LangChain tools.** Built-in tools are `StructuredTool`s, and MCP tools come from `langchain-mcp-adapters` as LangChain tools, so both are passed directly to `create_agent(tools=[...])`.

**Skills live in the database** (`skill` table, `/api/skills`) so they can be edited at runtime. An agent's `skills` is a list of skill names. On every task, `runner.py` calls `load_skills(session, agent.skills)` (in `services/skills.py`), which resolves each name to tools and adds a short "you can use these skills" note (description + instructions) to the sub-agent's system prompt. Edits to a skill or to an agent's skills apply to the next task.

| Type | What the skill row holds | Tools the agent gets |
|---|---|---|
| `builtin` | `tool_key` → a Python tool in `app/tools/` | That one tool |
| `mcp` | `mcp_config` (connection JSON) | All tools the MCP server exposes |

Default skills for every built-in tool (`calculator`, `current_time`) are created at startup if missing. Your edits are never overwritten.

**Add your own Python tool** (code can't be stored in the DB, so it lives in `app/tools/`):

```python
# app/tools/word_count.py
from .registry import builtin_tool

@builtin_tool("word_count", "Count the words in a text.")
def word_count(text: str) -> str:
    return str(len(text.split()))
```

Add `word_count` to the import line in `app/tools/__init__.py` and restart. A default skill `word_count` appears in `GET /api/skills`. Then give an agent `"skills": ["word_count"]`. Use `async def` for I/O-bound tools.

**Add an MCP server**: no code or restart needed, just create a skill:

```bash
curl -X POST localhost:8000/api/skills -H 'content-type: application/json' -d '{
  "name": "filesystem", "type": "mcp",
  "description": "Read files in /data",
  "mcp_config": {"transport": "stdio", "command": "npx",
                 "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]}
}'
```

`streamable_http` works too: `{"transport": "streamable_http", "url": "http://localhost:9000/mcp", "headers": {...}}`. If an MCP server fails to start or connect, it is logged and skipped, and the task still runs without those tools.

Notes: skills apply to sub-agents only; the Manager's tools are the delegation and tasklist tools. `mcp_config` can contain secrets and is returned by `GET /api/skills`, so don't expose this API without auth. A stdio MCP server runs as a local process with the backend's permissions, so only add servers you trust.

### 6.7 Tasklist and task-completion updates

Each conversation (`thread_id`) has a tasklist (`Todo` rows). The Manager manages it **through tool calls** (`services/tasklist_tools.py`): `get_tasklist`, `add_todo`, `rename_todo`, `remove_todo`, `complete_todo`. The current list is also put into its system prompt on every run, so it always sees the user's edits.

```
User/Manager add todos ──▶ Manager delegates (todo_id) ──▶ Todo = in_progress
                                                              │
sub-agent finishes (runner.py) ◀──────────────────────────────┘
  │
  ▼  notify_task_finished(task_id)
Manager gets "[UPDATE] Sub-agent X finished task #N. Result: ..." on the same thread
  │   (one Manager run per thread at a time: a per-thread lock)
  ▼
Manager checks the result → complete_todo(id) → writes a message for the user
  │
  ▼
saved as ChatMessage + SSE "todo.updated" and "chat.message"
```

Rules:
- **Only the Manager marks items done**, and only after a sub-agent's report. The user REST API can add, rename and remove items but not change status.
- If a task **fails**, the Manager is told, leaves the todo `in_progress` and tells the user.
- Delegating without a `todo_id` auto-creates an item, so all work is tracked.
- Fake mode (no API key) mimics this: the item is marked done on success, and a canned manager message is posted.
- Real mode costs one extra Manager LLM call per finished sub-agent task.

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
- **Notifications are in-process**: if the server stops while a task runs, the Manager is never told and the todo stays `in_progress`.
- **Skills have no per-agent config or auth**: an MCP server is shared by every agent that names it, and MCP tools are loaded by opening a new connection per task (no pooling). There is no approval step before a tool runs.
- **No auth** on any endpoint; CORS is the only protection.
- **No migrations**: `create_all` only creates missing tables. It won't alter existing ones when models change (delete `mrceo.db` in dev).
- **Tasks in flight are lost on restart**: a task left `pending`/`running` when the server stops is never resumed or marked failed.
- **No task cancellation or retry** endpoints.

---

## 9. Roadmap: sub-agent ↔ sub-agent collaboration (TODO)

**Today:** hub-and-spoke. Sub-agents are isolated (they only have their skills as tools) and every handoff goes through the Manager: the `[UPDATE]` message comes back, the Manager reads it, then delegates the next step. This costs one Manager LLM call per hop and the Manager may paraphrase away detail. It is fine for linear pipelines (research → write → review).

Options for letting agents work with each other, in recommended order:

- [ ] **Option 2: direct peer calls (`ask_agent`) — recommended next.**
  - Give sub-agents an `ask_agent(name, question)` tool (plus `list_agents`). It creates a child `Task` for the target agent, runs it inline and returns the result to the caller, with no Manager `[UPDATE]`.
  - Add `parent_task_id` and `depth` to `Task`; reject calls past `depth >= 3` and calls to self or into a cycle.
  - Add an allowlist on `Agent` (e.g. `can_contact: list[int]`) so the Manager/user controls who may talk to whom.
  - Add a per-task call budget (max peer calls) to stop cost blowups and A↔B loops.
  - Show child tasks under their parent in the UI so work stays visible.
- [ ] **Option 3: shared workspace (blackboard).** Agents read/write shared artifacts per thread (files, notes, DB rows) and see each other's outputs without calling each other. Good for large outputs (documents, code); not interactive. Add once agents start passing big artifacts.
- [ ] **Option 1 stays as the default** for planning and tracking: the Manager owns the tasklist, and peer calls are an optimisation, not a replacement.

## 10. Test notes: local Ollama

### 2026-10-20: `deepseek-r1:7b` (CPU only): flow NOT verified

- The Manager wrote a plan in prose and made no tool calls (`tasks: []`, `todos: []`) after 3m16s. r1 is weak at tool calling, and Ollama's default 4096 context is small for the Manager prompt plus tool schemas. The model has since been removed.

### 2026-10-21: `bonsai-2:4b` (GTX 1650 Ti, 4 GB VRAM): flow verified

Setup: `LLM_PROVIDER=ollama`, `MANAGER_MODEL=bonsai-2:4b`, `DEFAULT_AGENT_MODEL=bonsai-2:4b`, one agent "Calculator" with the `calculator` skill, fresh DB.

- Asked the Manager to have the Calculator compute `(17*23)+5`. The Manager called `add_todo` + `delegate`, the sub-agent ran in the background and returned `396` (correct), the `[UPDATE]` came back, the Manager completed the todo and told the user. Whole round trip about 2m20s.
- **Bug found:** the model called `add_todo` and then `delegate` *without* `todo_id`, so `_dispatch` created a second todo. Result: todo #1 `done`, todo #2 `todo` forever (duplicate). Small models skip optional args.
- TODOs:
  - [ ] In `_dispatch`, if `todo_id` is missing, reuse the thread's newest unlinked `todo` item with the same/similar title instead of always creating a new one.
  - [ ] Re-test with a larger or less quantized model (this one is Q2_0) for multi-agent plans and harder tasks.
  - [ ] Try a larger context for Ollama (`num_ctx`) in `make_model`.
  - [ ] Strip r1-style `<think>` content from replies if a reasoning model is used.
