import type {
  Agent,
  Approval,
  Decision,
  AgentInput,
  ChatMessage,
  ChatResponse,
  Skill,
  Task,
  Team,
  Thread,
  Todo,
} from './types';

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function req<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}/api${path}`, {
    method,
    // Only send a content-type when there is a body, so GETs stay "simple" requests (no preflight).
    ...(body !== undefined && {
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new Error(msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const agents = () => req<Agent[]>('/agents');
export const createAgent = (b: AgentInput) => req<Agent>('/agents', 'POST', b);
export const updateAgent = (id: number, b: Partial<AgentInput>) => req<Agent>(`/agents/${id}`, 'PATCH', b);
export const deleteAgent = (id: number) => req<void>(`/agents/${id}`, 'DELETE');

export const skills = () => req<Skill[]>('/skills');

export const tasks = () => req<Task[]>('/tasks');

export const threads = () => req<Thread[]>('/threads');
export const createThread = (team: Team) => req<Thread>('/threads', 'POST', { team });
export const deleteThread = (id: string) => req<void>(`/threads/${id}`, 'DELETE');
export const messages = (thread: string) => req<ChatMessage[]>(`/chat/${thread}/messages`);
export const chat = (message: string, thread_id: string, todo_id?: number) =>
  req<ChatResponse>('/chat', 'POST', { message, thread_id, todo_id });

export const approvals = (thread: string) => req<Approval[]>(`/threads/${thread}/approvals`);
export const resolveApproval = (id: number, decisions: Decision[]) =>
  req<ChatResponse>(`/approvals/${id}/resolve`, 'POST', { decisions });

export const todos = (thread: string) => req<Todo[]>(`/threads/${thread}/todos`);
export const addTodo = (thread: string, title: string, description = '') =>
  req<Todo>(`/threads/${thread}/todos`, 'POST', { title, description });
export const editTodo = (id: number, b: { title?: string; description?: string }) =>
  req<Todo>(`/todos/${id}`, 'PATCH', b);
export const approveTodo = (id: number) => req<Todo>(`/todos/${id}/approve`, 'POST');
export const removeTodo = (id: number) => req<void>(`/todos/${id}`, 'DELETE');
