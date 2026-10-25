import { useSyncExternalStore } from 'react';
import * as api from './api';
import type { Agent, AgentInput, Approval, ChatMessage, Decision, Skill, Task, Todo } from './types';

/** The app is a single conversation with the Manager, so there is one fixed thread. */
export const THREAD = 'main';

export type FormTarget = { id?: number } | null;

/** A Manager reply being written right now, fed by live token events. Sub-agents don't stream. */
export interface Stream {
  msg: string; // id of the LLM message; when it changes the text starts over
  text: string;
  done: boolean; // no more tokens; kept on screen until the saved message is loaded
}

interface State {
  loaded: boolean;
  live: boolean;
  threadId: string;
  agents: Agent[];
  skills: Skill[];
  tasks: Record<number, Task>;
  todos: Todo[];
  reference: number | null; // task the next message is about
  focus: number | null; // task opened in the chat workspace (highlighted left, its work shown right)
  approval: Approval | null; // the Manager is paused until the user answers this
  messages: ChatMessage[];
  streams: Record<string, Stream>;
  pending: { text: string; base: number } | null; // optimistic user bubble
  sending: boolean;
  error: string | null;
  form: FormTarget;
}

const initial: State = {
  loaded: false,
  live: false,
  threadId: THREAD,
  agents: [],
  skills: [],
  tasks: {},
  todos: [],
  reference: null,
  focus: null,
  approval: null,
  messages: [],
  streams: {},
  pending: null,
  sending: false,
  error: null,
  form: null,
};

let state = initial;
const listeners = new Set<() => void>();

function set(patch: Partial<State> | ((s: State) => Partial<State>)) {
  state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) };
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};

/** Select primitives or slices that keep their identity; never build a new object in a selector. */
export function useStore<T>(select: (s: State) => T): T {
  return useSyncExternalStore(
    subscribe,
    () => select(state),
    () => select(initial),
  );
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

// ---------- loading ----------

let msgTimer: ReturnType<typeof setTimeout> | undefined;

async function loadMessages() {
  const id = state.threadId;
  if (!id) return;
  try {
    const messages = await api.messages(id);
    if (state.threadId === id) set({ messages });
  } catch {}
}

/** Coalesce bursts of events into one fetch. */
export function scheduleMessages() {
  clearTimeout(msgTimer);
  msgTimer = setTimeout(() => void loadMessages(), 120);
}

async function loadThread(id: string) {
  try {
    const [todos, messages, approvals] = await Promise.all([api.todos(id), api.messages(id), api.approvals(id)]);
    if (state.threadId === id)
      set({ todos, messages, approval: approvals.find((a) => a.status === 'pending') ?? null });
  } catch (e) {
    if (state.threadId === id) set({ error: message(e) });
  }
}

async function loadShared() {
  const [agents, tasks] = await Promise.all([api.agents(), api.tasks()]);
  set({ agents, tasks: Object.fromEntries(tasks.map((t) => [t.id, t])) });
}

let booted = false;

export async function boot() {
  if (booted) return;
  booted = true;
  try {
    await loadShared();
    await loadThread(THREAD);
  } catch (e) {
    set({ error: `Can't reach the backend (${message(e)})` });
  }
  set({ loaded: true });
  connect();
}

// ---------- token streams ----------

interface Delta {
  thread_id: string;
  run: string;
  msg: string;
  text: string;
}

// Tokens arrive far faster than the screen refreshes: collect them here and publish once per frame.
let live: Record<string, Stream> = {};
let frame = 0;

function flush() {
  frame = 0;
  set({ streams: { ...live } });
}

function token(d: Delta) {
  const cur = live[d.run];
  const text = cur && cur.msg === d.msg ? cur.text + d.text : d.text;
  live[d.run] = { msg: d.msg, text, done: false };
  if (!frame) frame = requestAnimationFrame(flush);
}

/** The saved message is the source of truth: load it first, then drop the finished streams. */
async function settle(match: (s: Stream) => boolean = () => true) {
  await loadMessages();
  let changed = false;
  for (const [run, s] of Object.entries(live)) {
    if (s.done && match(s)) {
      delete live[run];
      changed = true;
    }
  }
  if (changed) flush();
}

// ---------- live events (SSE) ----------

function connect() {
  const es = new EventSource(`${api.API_URL}/api/events`);
  let opened = false;
  const on = (type: string, fn: (data: any) => void) =>
    es.addEventListener(type, (e) => fn(JSON.parse((e as MessageEvent).data)));

  es.onopen = () => {
    set({ live: true });
    if (opened) void resync(); // reconnect: pick up anything missed
    opened = true;
  };
  es.onerror = () => set({ live: false }); // EventSource retries by itself

  on('task.updated', (t: Task) => {
    set((s) => ({ tasks: { ...s.tasks, [t.id]: t } }));
    if (t.thread_id === state.threadId) scheduleMessages();
  });
  on('todo.updated', (t: Todo) => {
    if (t.thread_id === state.threadId) set((s) => ({ todos: upsert(s.todos, t) }));
  });
  on('todo.deleted', (t: Todo) => set((s) => ({ todos: s.todos.filter((x) => x.id !== t.id) })));
  on('approval.requested', (a: Approval) => {
    if (a.thread_id === state.threadId) set({ approval: a });
  });
  on('approval.resolved', (a: Approval) => {
    if (a.thread_id === state.threadId) set((s) => (s.approval?.id === a.id ? { approval: null } : {}));
  });
  on('agent.updated', (a: Agent) =>
    set((s) => ({
      agents: s.agents.some((x) => x.id === a.id) ? s.agents.map((x) => (x.id === a.id ? a : x)) : [...s.agents, a],
    })),
  );
  on('skill.updated', () => void loadSkills());
  on('chat.message', (m: { thread_id: string }) => {
    if (m.thread_id === state.threadId) void settle();
  });
  on('chat.delta', (d: Delta) => d.thread_id === state.threadId && token(d));
  on('stream.end', (d: { run: string }) => {
    if (!live[d.run]) return;
    live[d.run] = { ...live[d.run], done: true };
    flush();
    // Safety net: if no "saved" signal follows, drop it anyway once the message is loaded.
    setTimeout(() => void settle((s) => s === live[d.run]), 4000);
  });
}

async function resync() {
  try {
    await loadShared();
    await loadThread(THREAD);
  } catch {}
}

const upsert = (list: Todo[], t: Todo) =>
  (list.some((x) => x.id === t.id) ? list.map((x) => (x.id === t.id ? t : x)) : [...list, t]).sort(
    (a, b) => a.id - b.id,
  );

// ---------- chat ----------

export async function send(text: string) {
  if (state.sending || state.approval || !text.trim()) return;
  const id = THREAD;
  const base = state.messages.filter((m) => m.role === 'user' && m.agent_id == null).length;
  const todoId = state.reference ?? undefined;
  set({ sending: true, error: null, pending: { text, base }, reference: null });
  try {
    const r = await api.chat(text, id, todoId);
    if (state.threadId === id) {
      set((s) => ({
        todos: r.todos,
        tasks: { ...s.tasks, ...Object.fromEntries(r.tasks.map((t) => [t.id, t])) },
      }));
    }
  } catch (e) {
    if (state.threadId === id) set({ error: message(e) });
  } finally {
    set({ sending: false, pending: null });
    await settle();
  }
}

/** Answer the Manager's pending approval request; it resumes and replies. */
export async function resolveApproval(decisions: Decision[]) {
  const a = state.approval;
  if (!a || state.sending) return;
  set({ sending: true, error: null });
  try {
    const r = await api.resolveApproval(a.id, decisions);
    set((s) => ({
      approval: null,
      todos: r.todos,
      tasks: { ...s.tasks, ...Object.fromEntries(r.tasks.map((t) => [t.id, t])) },
    }));
  } catch (e) {
    set({ error: message(e) });
  } finally {
    set({ sending: false });
    await settle();
    await loadThread(THREAD); // a new approval may have been requested, or agents changed
  }
}

// ---------- tasklist ----------

export async function addTodo(title: string) {
  const id = THREAD;
  if (!title.trim()) return;
  try {
    const t = await api.addTodo(id, title.trim());
    set((s) => ({ todos: upsert(s.todos, t) }));
  } catch (e) {
    set({ error: message(e) });
  }
}

export async function editTodo(id: number, patch: { title?: string; description?: string }) {
  try {
    const t = await api.editTodo(id, patch);
    set((s) => ({ todos: upsert(s.todos, t) }));
  } catch (e) {
    set({ error: message(e) });
  }
}

export async function approveTodo(id: number) {
  try {
    const t = await api.approveTodo(id);
    set((s) => ({ todos: upsert(s.todos, t) }));
  } catch (e) {
    set({ error: message(e) });
  }
}

/** "Request changes": attach the task to the next chat message. The Manager gets the real id,
 * the user only sees a "Task #n" chip. The caller navigates to the chat. */
export const referenceTodo = (id: number | null) => set({ reference: id });

export const focusTodo = (id: number | null) => set({ focus: id });

export async function removeTodo(id: number) {
  const prev = state.todos;
  set({ todos: prev.filter((t) => t.id !== id) }); // optimistic
  try {
    await api.removeTodo(id);
  } catch (e) {
    set({ todos: prev, error: message(e) });
  }
}

// ---------- agents ----------

export const openForm = (form: FormTarget) => set({ form });
export const closeForm = () => set({ form: null });

export async function loadSkills() {
  try {
    set({ skills: await api.skills() });
  } catch {}
}

/** Throws on failure so the form can show the backend's message (e.g. unknown skills). */
export async function saveAgent(id: number | undefined, input: AgentInput) {
  const agent =
    id == null
      ? await api.createAgent({ ...input, model: input.model || null })
      : await api.updateAgent(id, { ...input, ...(input.model ? {} : { model: undefined }) });
  set((s) => ({
    agents: s.agents.some((a) => a.id === agent.id)
      ? s.agents.map((a) => (a.id === agent.id ? agent : a))
      : [...s.agents, agent],
    form: null,
  }));
}

export async function deleteAgent(id: number) {
  await api.deleteAgent(id);
  set((s) => ({
    agents: s.agents.filter((a) => a.id !== id),
    tasks: Object.fromEntries(Object.entries(s.tasks).filter(([, t]) => t.agent_id !== id)),
    form: null,
  }));
  await loadThread(THREAD); // todos/messages of that agent are gone
}
