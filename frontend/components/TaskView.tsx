'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { approveTodo, editTodo, referenceTodo, removeTodo, useStore } from '@/lib/store';
import { day } from '@/lib/status';
import type { Todo } from '@/lib/types';
import Attempt from './Attempt';
import { StatePill, useTodoState } from './bits';
import { ChevronLeft, Pencil, Trash } from './icons';
import Message from './Message';
import Text from './Text';

type Tab = 'conversation' | 'work';

function Editor({ todo, done }: { todo: Todo; done: () => void }) {
  const [title, setTitle] = useState(todo.title);
  const [description, setDescription] = useState(todo.description);
  return (
    <form
      className="editor"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim()) void editTodo(todo.id, { title: title.trim(), description: description.trim() });
        done();
      }}
    >
      <label className="field">
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus required />
      </label>
      <label className="field">
        Description
        <textarea rows={4} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <div className="actions">
        <span className="spacer" />
        <button type="button" className="pill" onClick={done}>
          Cancel
        </button>
        <button className="pill primary">Save</button>
      </div>
    </form>
  );
}

export default function TaskView({ id }: { id: number }) {
  const router = useRouter();
  const loaded = useStore((s) => s.loaded);
  const todo = useStore((s) => s.todos.find((t) => t.id === id));
  const allTasks = useStore((s) => s.tasks);
  const messages = useStore((s) => s.messages);
  const agents = useStore((s) => s.agents);
  const state = useTodoState(todo);
  const [tab, setTab] = useState<Tab>('conversation');
  const [editing, setEditing] = useState(false);
  const [full, setFull] = useState(false);

  // Every attempt the sub-agent made at this task (rework creates a new one).
  const attempts = useMemo(
    () =>
      Object.values(allTasks)
        .filter((t) => t.todo_id === id)
        .sort((a, b) => a.id - b.id),
    [allTasks, id],
  );
  const latest = attempts[attempts.length - 1];
  const agent = latest && agents.find((a) => a.id === latest.agent_id)?.name;

  // The user <-> Manager conversation about this task: the request that created it (and the
  // Manager's answer), plus every message tagged with it (change requests, reports, reviews).
  const conversation = useMemo(() => {
    const own = messages.filter((m) => m.agent_id == null && m.todo_id === id);
    const origin = todo?.origin_message_id;
    const start = origin != null ? messages.find((m) => m.id === origin) : undefined;
    const answer = start && messages.find((m) => m.id > start.id && m.agent_id == null && m.role === 'manager');
    const all = new Map([start, answer, ...own].filter((m) => m != null).map((m) => [m.id, m]));
    return [...all.values()].sort((a, b) => a.id - b.id);
  }, [messages, id, todo?.origin_message_id]);

  if (!todo) {
    return (
      <div className="page">
        <div className="page-inner narrow">
          {loaded ? (
            <div className="empty">
              <strong>Task not found</strong>
              It may have been deleted.
              <Link className="pill" href="/tasks">
                Back to tasks
              </Link>
            </div>
          ) : (
            <div className="skeleton block" aria-label="Loading" />
          )}
        </div>
      </div>
    );
  }

  const askManager = () => {
    referenceTodo(todo.id);
    router.push('/');
  };

  return (
    <div className="page">
      <div className="task-page">
        <Link className="back" href="/tasks">
          <ChevronLeft /> Tasks
        </Link>

        <div className="task-layout">
          <div className="task-main">
            <header className="task-head">
              <div className="task-head-top">
                <StatePill state={state} />
                <span className="spacer" />
                <button className="icon-btn" aria-label="Edit task" onClick={() => setEditing(true)}>
                  <Pencil />
                </button>
                <button
                  className="icon-btn"
                  aria-label="Delete task"
                  onClick={() => {
                    if (confirm('Delete this task?')) {
                      void removeTodo(todo.id);
                      router.push('/tasks');
                    }
                  }}
                >
                  <Trash />
                </button>
              </div>
              {editing ? (
                <Editor todo={todo} done={() => setEditing(false)} />
              ) : (
                <>
                  <h1>{todo.title}</h1>
                  <p className="task-meta">
                    Task #{todo.id}
                    {agent && ` · ${agent}`} · created {day(todo.created_at)}
                    {attempts.length > 1 && ` · ${attempts.length} attempts`}
                  </p>
                  {todo.description && <p className="task-desc">{todo.description}</p>}
                </>
              )}
            </header>

            {state === 'approval' && (
              <div className="decision">
                <p>The Manager checked this work. Approve it, or tell the Manager what to change.</p>
                <div className="actions">
                  <button className="pill" onClick={askManager}>
                    Request changes
                  </button>
                  <button className="pill primary" onClick={() => void approveTodo(todo.id)}>
                    Approve
                  </button>
                </div>
              </div>
            )}

            {(todo.summary || latest?.result) && (
              <section className="result" data-state={state}>
                <h2>{state === 'failed' ? 'What went wrong' : 'What was done'}</h2>
                <p>{todo.summary || latest?.summary || (state === 'failed' ? latest?.result : '')}</p>
                {latest?.result && latest.status === 'done' && (
                  <>
                    <button className="link-btn" aria-expanded={full} onClick={() => setFull((f) => !f)}>
                      {full ? 'Hide full response' : 'Show full response'}
                    </button>
                    {full && (
                      <div className="result-full">
                        <Text text={latest.result} />
                      </div>
                    )}
                  </>
                )}
              </section>
            )}
            {(state === 'running' || state === 'checking') && (
              <section className="result" data-state={state}>
                <span className="working">
                  <i />{' '}
                  {state === 'running'
                    ? `${agent ?? 'The sub-agent'} is working on it…`
                    : 'The Manager is reviewing the result…'}
                </span>
              </section>
            )}

            {state !== 'approval' && state !== 'done' && (
              <button className="pill ask" onClick={askManager}>
                Ask the Manager about this task
              </button>
            )}
          </div>

          <aside className="task-side" aria-label="Task history">
            <div className="seg" role="tablist" aria-label="Task history">
              <button role="tab" aria-selected={tab === 'conversation'} onClick={() => setTab('conversation')}>
                Conversation <span>{conversation.length}</span>
              </button>
              <button role="tab" aria-selected={tab === 'work'} onClick={() => setTab('work')}>
                Sub-agent work <span>{attempts.length}</span>
              </button>
            </div>

            {tab === 'conversation' ? (
              conversation.length ? (
                <ol className="thread compact">
                  {conversation.map((m) => (
                    <Message key={m.id} m={m} showTask={false} />
                  ))}
                </ol>
              ) : (
                <div className="empty">No conversation about this task yet.</div>
              )
            ) : attempts.length ? (
              <ol className="attempts">
                {attempts.map((t, i) => (
                  <Attempt key={t.id} task={t} n={i + 1} />
                ))}
              </ol>
            ) : (
              <div className="empty">Not delegated to a sub-agent yet.</div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
