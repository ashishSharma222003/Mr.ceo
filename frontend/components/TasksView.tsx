'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { memo, useMemo, useState } from 'react';
import { addTodo, useStore } from '@/lib/store';
import { ago } from '@/lib/status';
import type { Todo } from '@/lib/types';
import { Dot, StatePill, useTodoState } from './bits';
import { Plus, Search } from './icons';

type Filter = 'open' | 'review' | 'done';
const PAGE = 50; // completed work grows without bound: render it in pages

const Row = memo(function Row({ todo }: { todo: Todo }) {
  const state = useTodoState(todo);
  const agent = useStore((s) => {
    const task = todo.task_id != null ? s.tasks[todo.task_id] : undefined;
    return task ? s.agents.find((a) => a.id === task.agent_id)?.name : undefined;
  });
  const sub = todo.summary || todo.description;
  return (
    <li>
      <Link className="row" href={`/tasks/${todo.id}`}>
        <Dot state={state} />
        <span className="row-main">
          <span className="row-title">{todo.title}</span>
          {sub && <span className="row-sub">{sub}</span>}
        </span>
        <span className="row-meta">
          {state === 'approval' && <StatePill state={state} />}
          {agent && <span className="row-agent">{agent}</span>}
          <time>{ago(todo.updated_at)}</time>
        </span>
      </Link>
    </li>
  );
});

export default function TasksView() {
  const loaded = useStore((s) => s.loaded);
  const todos = useStore((s) => s.todos);
  const initial = useSearchParams().get('f');
  const [filter, setFilter] = useState<Filter>(initial === 'done' || initial === 'review' ? initial : 'open');
  const [query, setQuery] = useState('');
  const [shown, setShown] = useState(PAGE);
  const [draft, setDraft] = useState('');

  const groups = useMemo(() => {
    const newest = (a: Todo, b: Todo) => b.updated_at.localeCompare(a.updated_at);
    return {
      // Items waiting for the user's sign-off first, then the rest, oldest first (a queue).
      open: todos
        .filter((t) => t.status !== 'done')
        .sort((a, b) => Number(b.status === 'review') - Number(a.status === 'review') || a.id - b.id),
      review: todos.filter((t) => t.status === 'review').sort(newest),
      done: todos.filter((t) => t.status === 'done').sort(newest),
    };
  }, [todos]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = groups[filter];
    return q ? list.filter((t) => `${t.title} ${t.description} ${t.summary ?? ''}`.toLowerCase().includes(q)) : list;
  }, [groups, filter, query]);

  const tabs: [Filter, string][] = [
    ['open', 'Open'],
    ['review', 'Needs approval'],
    ['done', 'Completed'],
  ];

  return (
    <div className="page">
      <div className="page-inner">
        <header className="page-head">
          <h1>Tasks</h1>
          <label className="search">
            <Search />
            <input
              type="search"
              value={query}
              placeholder="Search"
              aria-label="Search tasks"
              onChange={(e) => {
                setQuery(e.target.value);
                setShown(PAGE);
              }}
            />
          </label>
        </header>

        <div className="seg" role="tablist" aria-label="Filter tasks">
          {tabs.map(([id, label]) => (
            <button
              key={id}
              role="tab"
              aria-selected={filter === id}
              onClick={() => {
                setFilter(id);
                setShown(PAGE);
              }}
            >
              {label}
              <span>{groups[id].length}</span>
            </button>
          ))}
        </div>

        {filter === 'open' && (
          <form
            className="new-task"
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
              placeholder="Add a task for the Manager…"
              aria-label="Add a task"
            />
          </form>
        )}

        {!loaded ? (
          <ul className="rows" aria-hidden>
            {[0, 1, 2].map((i) => (
              <li key={i} className="row skeleton" />
            ))}
          </ul>
        ) : rows.length === 0 ? (
          <div className="empty">
            <strong>
              {query
                ? 'No matches'
                : filter === 'done'
                  ? 'Nothing completed yet'
                  : filter === 'review'
                    ? 'All caught up'
                    : 'No open tasks'}
            </strong>
            {!query &&
              (filter === 'done'
                ? 'Tasks you approve end up here.'
                : filter === 'review'
                  ? 'Work the Manager has checked will wait here for your approval.'
                  : 'Ask the Manager for something in Chat, or add a task above.')}
          </div>
        ) : (
          <>
            <ul className="rows">
              {rows.slice(0, shown).map((t) => (
                <Row key={t.id} todo={t} />
              ))}
            </ul>
            {rows.length > shown && (
              <button className="pill more" onClick={() => setShown((n) => n + PAGE)}>
                Show more ({rows.length - shown})
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
