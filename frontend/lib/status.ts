import type { Task, Todo } from './types';

export type TodoState = 'todo' | 'running' | 'checking' | 'approval' | 'done' | 'failed';

/** One visual state per todo, combining the Manager's todo status with the sub-agent task. */
export function todoState(todo: Todo, task?: Task): TodoState {
  if (todo.status === 'done') return 'done';
  if (todo.status === 'review') return 'approval';
  if (task?.status === 'failed') return 'failed';
  if (todo.status === 'in_progress') return task?.status === 'done' ? 'checking' : 'running';
  return 'todo';
}

export const STATE_LABEL: Record<TodoState, string> = {
  todo: 'To do',
  running: 'Working',
  checking: 'Manager reviewing',
  approval: 'Waiting for your approval',
  done: 'Done',
  failed: 'Failed',
};

/** DB datetimes come back naive (UTC); SSE ones carry an offset. Normalise both. */
export function ts(s: string): number {
  const iso = s.replace(' ', 'T');
  return Date.parse(/[zZ]$|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
}

export const day = (s: string) =>
  new Date(ts(s)).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });

export const clock = (s: string) =>
  new Date(ts(s)).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

/** "just now", "5m ago", "3h ago", "2d ago", then a date. */
export function ago(s: string): string {
  const sec = (Date.now() - ts(s)) / 1000;
  if (sec < 60) return 'just now';
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  if (sec < 7 * 86400) return `${Math.floor(sec / 86400)}d ago`;
  return day(s);
}
