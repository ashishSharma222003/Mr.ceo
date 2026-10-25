'use client';

import Link from 'next/link';
import { memo, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { addTodo, approveTodo, referenceTodo, useStore } from '@/lib/store';
import { STATE_LABEL } from '@/lib/status';
import type { Todo } from '@/lib/types';
import { Dot, OpenTask, useTodoState } from './bits';
import { ChevronLeft, ChevronRight, Plus } from './icons';

const Item = memo(function Item({ todo }: { todo: Todo }) {
  const state = useTodoState(todo);
  const agent = useStore((s) => {
    const task = todo.task_id != null ? s.tasks[todo.task_id] : undefined;
    return task ? s.agents.find((a) => a.id === task.agent_id)?.name : undefined;
  });
  const open = useContext(OpenTask);
  const focused = useStore((s) => s.focus === todo.id);
  const ref = useRef<HTMLLIElement>(null);

  // Opened from a chip in the chat: bring it into view.
  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [focused]);

  const body = (
    <>
      <Dot state={state} />
      <span className="pt-text">
        <span className="pt-title">
          <span className="pt-id">#{todo.id}</span> {todo.title}
        </span>
        <span className="pt-sub">
          {STATE_LABEL[state]}
          {agent && ` · ${agent}`}
        </span>
      </span>
    </>
  );
  return (
    <li className="pt-item" data-state={state} data-focused={focused} ref={ref}>
      {open ? (
        <button className="pt-link" onClick={() => open(todo.id)} aria-current={focused || undefined}>
          {body}
        </button>
      ) : (
        <Link className="pt-link" href={`/tasks/${todo.id}`}>
          {body}
        </Link>
      )}
      {state === 'approval' && (
        <div className="pt-actions">
          <button className="mini" onClick={() => referenceTodo(todo.id)}>
            Request changes
          </button>
          <button className="mini primary" onClick={() => void approveTodo(todo.id)}>
            Approve
          </button>
        </div>
      )}
    </li>
  );
});

function Group({ label, items }: { label: string; items: Todo[] }) {
  if (!items.length) return null;
  return (
    <section className="pt-group">
      <h3>
        {label} <span>{items.length}</span>
      </h3>
      <ul>
        {items.map((t) => (
          <Item key={t.id} todo={t} />
        ))}
      </ul>
    </section>
  );
}

/** Left pane of the chat workspace: open work only. Completed tasks live on /tasks. */
export default function TaskPane({ onCollapse }: { onCollapse: () => void }) {
  const loaded = useStore((s) => s.loaded);
  const todos = useStore((s) => s.todos);
  const [draft, setDraft] = useState('');

  const g = useMemo(
    () => ({
      review: todos.filter((t) => t.status === 'review'),
      doing: todos.filter((t) => t.status === 'in_progress'),
      todo: todos.filter((t) => t.status === 'todo'),
      done: todos.filter((t) => t.status === 'done').length,
    }),
    [todos],
  );
  const open = g.review.length + g.doing.length + g.todo.length;

  return (
    <>
      <div className="pane-head">
        <h2>Tasks</h2>
        {open > 0 && <span className="count">{open} open</span>}
        <span className="spacer" />
        <button className="icon-btn" aria-label="Collapse tasks" title="Collapse" onClick={onCollapse}>
          <ChevronLeft />
        </button>
      </div>
      <div className="pane-scroll">
        {loaded && open === 0 ? (
          <div className="empty small">
            <strong>Nothing open</strong>
            Ask the Manager for something, or add a task below.
          </div>
        ) : (
          <>
            <Group label="Needs your approval" items={g.review} />
            <Group label="In progress" items={g.doing} />
            <Group label="To do" items={g.todo} />
          </>
        )}
      </div>
      <div className="pane-foot">
        <form
          className="pt-add"
          onSubmit={(e) => {
            e.preventDefault();
            void addTodo(draft);
            setDraft('');
          }}
        >
          <Plus />
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a task"
            aria-label="Add a task"
          />
        </form>
        <Link className="pt-done" href="/tasks?f=done">
          Completed tasks <span>{g.done}</span>
          <ChevronRight />
        </Link>
      </div>
    </>
  );
}
