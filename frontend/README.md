# Mr.ceo frontend

Next.js (App Router) + TypeScript, no UI libraries. Three panes: **Tasks** (the Manager's tasklist), **Manager chat**, **Sub-agents** (Manager ↔ sub-agent conversations).

```bash
cp .env.example .env.local   # NEXT_PUBLIC_API_URL, default http://localhost:8000
npm install
npm run dev                  # http://localhost:3000 (backend CORS already allows it)
npm run typecheck
```

- `lib/store.ts`: state, SSE (`/api/events`) and all actions; `lib/api.ts`: one function per backend endpoint.
- Live updates: `task.updated`, `todo.updated`, `todo.deleted`, `chat.message`. Messages are refetched (coalesced) when a task changes, since sub-agent messages have no event of their own.
- Thread ids are kept in localStorage because the backend has no "list threads" endpoint.
