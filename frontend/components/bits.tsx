'use client';

import Link from 'next/link';
import { createContext, memo, useContext, useMemo } from 'react';
import { inTeam, useStore } from '@/lib/store';
import { STATE_LABEL, todoState, type TodoState } from '@/lib/status';
import type { Todo } from '@/lib/types';
import { Check, X } from './icons';

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');

/** The open chat and the sub-agents that work in it. */
export function useTeam() {
  const agents = useStore((s) => s.agents);
  const thread = useStore((s) => s.threads.find((t) => t.id === s.threadId));
  const team = useMemo(() => agents.filter((a) => inTeam(thread, a)), [agents, thread]);
  return { thread, team };
}

/** Live status of a tasklist item, combining the todo with its latest sub-agent task. */
export function useTodoState(todo: Todo | undefined): TodoState {
  const task = useStore((s) => (todo?.task_id != null ? s.tasks[todo.task_id] : undefined));
  return todo ? todoState(todo, task) : 'todo';
}

export function Dot({ state }: { state: TodoState }) {
  return (
    <span className="dot" data-state={state} aria-hidden>
      {state === 'done' && <Check />}
      {state === 'failed' && <X />}
    </span>
  );
}

export function StatePill({ state }: { state: TodoState }) {
  return (
    <span className="state-pill" data-state={state}>
      {STATE_LABEL[state]}
    </span>
  );
}

/** Set by the chat workspace: opening a task there focuses it in place instead of navigating. */
export const OpenTask = createContext<((id: number) => void) | null>(null);

/** "Task #3 · Title": how a task reference looks to the user. Opens the task (in the workspace, or
 * its page) unless removable. `inline` is the compact form used inside Manager replies. */
export const TaskChip = memo(function TaskChip({
  id,
  onClear,
  inline,
}: {
  id: number;
  onClear?: () => void;
  inline?: boolean;
}) {
  const title = useStore((s) => s.todos.find((t) => t.id === id)?.title);
  const open = useContext(OpenTask);
  const cls = inline ? 'task-chip inline' : 'task-chip';
  if (inline && title == null) return <>Task #{id}</>; // unknown id: leave the text alone
  const label = (
    <>
      <b>Task #{id}</b>
      {title && <span>{title}</span>}
    </>
  );
  if (onClear) {
    return (
      <span className={cls}>
        {label}
        <button type="button" aria-label="Remove task reference" onClick={onClear}>
          <X />
        </button>
      </span>
    );
  }
  return open ? (
    <button type="button" className={cls} onClick={() => open(id)} title="Show this task">
      {label}
    </button>
  ) : (
    <Link className={cls} href={`/tasks/${id}`}>
      {label}
    </Link>
  );
});
