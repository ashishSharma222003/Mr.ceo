'use client';

import Link from 'next/link';
import { memo, useContext, useMemo } from 'react';
import { focusTodo, openForm, useStore } from '@/lib/store';
import { ago } from '@/lib/status';
import type { Agent, Task } from '@/lib/types';
import AttemptList from './Attempt';
import { initials, OpenTask, StatePill, useTeam, useTodoState } from './bits';
import { ChevronLeft, ChevronRight, Plus } from './icons';

/** Opens a task in place (workspace) or links to its page. */
function TaskLink({
  todoId,
  children,
  ...rest
}: { todoId: number | null; children: React.ReactNode; className: string } & Record<`data-${string}`, string>) {
  const open = useContext(OpenTask);
  if (open && todoId != null) {
    return (
      <button type="button" {...rest} onClick={() => open(todoId)}>
        {children}
      </button>
    );
  }
  return (
    <Link {...rest} href={todoId != null ? `/tasks/${todoId}` : '/tasks'}>
      {children}
    </Link>
  );
}

const busy = (t: Task) => t.status === 'pending' || t.status === 'running';

const AgentRow = memo(function AgentRow({ agent, current, last }: { agent: Agent; current?: Task; last?: Task }) {
  const title = useStore((s) => {
    const t = current ?? last;
    return t?.todo_id != null ? s.todos.find((x) => x.id === t.todo_id)?.title : undefined;
  });
  const task = current ?? last;
  return (
    <li className="pa-agent" data-busy={!!current}>
      <button className="pa-who" onClick={() => openForm({ id: agent.id })} title={`Edit ${agent.name}`}>
        <span className="avatar sm" aria-hidden>
          {initials(agent.name)}
          <i />
        </span>
        <span className="pa-name">
          <b>{agent.name}</b>
          <span>{agent.model}</span>
        </span>
      </button>
      {task && (
        <TaskLink className="pa-now" todoId={task.todo_id}>
          <span>{current ? 'Working on' : task.status === 'failed' ? 'Failed' : 'Last finished'}</span>
          <b>{title ?? task.instruction}</b>
        </TaskLink>
      )}
      {!task && <p className="pa-idle">No tasks yet</p>}
      {agent.skills.length > 0 && (
        <span className="chips">
          {agent.skills.map((s) => (
            <span key={s} className="chip">
              {s}
            </span>
          ))}
        </span>
      )}
    </li>
  );
});

const ActivityRow = memo(function ActivityRow({ task }: { task: Task }) {
  const agent = useStore((s) => s.agents.find((a) => a.id === task.agent_id)?.name ?? 'Sub-agent');
  const title = useStore((s) => (task.todo_id != null ? s.todos.find((t) => t.id === task.todo_id)?.title : undefined));
  const asker = useStore((s) => {
    const blocked = task.helps_task_id != null ? s.tasks[task.helps_task_id] : undefined;
    return blocked && (s.agents.find((a) => a.id === blocked.agent_id)?.name ?? 'a sub-agent');
  });
  const verb = asker
    ? busy(task)
      ? `is helping ${asker} with`
      : task.status === 'failed'
        ? `couldn't help ${asker} with`
        : `helped ${asker} with`
    : busy(task)
      ? 'is working on'
      : task.status === 'failed'
        ? 'failed'
        : task.help_request
          ? 'asked for help with'
          : 'finished';
  return (
    <li>
      <TaskLink className="pa-act" todoId={task.todo_id} data-status={task.status}>
        <i aria-hidden />
        <span>
          <b>{agent}</b> {verb} <em>{title ?? task.instruction}</em>
        </span>
        <time>{ago(task.finished_at ?? task.created_at)}</time>
      </TaskLink>
    </li>
  );
});

/** A focused task: its sub-agent conversation, attempt by attempt. */
function TaskFocus({ id }: { id: number }) {
  const todo = useStore((s) => s.todos.find((t) => t.id === id));
  const tasks = useStore((s) => s.tasks);
  const state = useTodoState(todo);
  const attempts = useMemo(
    () =>
      Object.values(tasks)
        .filter((t) => t.todo_id === id)
        .sort((a, b) => a.id - b.id),
    [tasks, id],
  );
  return (
    <div className="pa-focus">
      <div className="pa-focus-head">
        <button className="link-btn back-btn" onClick={() => focusTodo(null)}>
          <ChevronLeft /> All sub-agents
        </button>
        <div className="pa-focus-title">
          <span className="pa-focus-id">Task #{id}</span>
          {todo && <StatePill state={state} />}
        </div>
        <h3>{todo?.title ?? 'Task not found'}</h3>
        <Link className="link-btn" href={`/tasks/${id}`}>
          Open task page
        </Link>
      </div>
      {attempts.length ? (
        <AttemptList tasks={attempts} />
      ) : (
        <div className="empty small">Not delegated to a sub-agent yet.</div>
      )}
    </div>
  );
}

/** Right pane of the chat workspace: who the sub-agents are and what they are doing, or the
 * conversation of the task the user opened. */
export default function AgentPane({ onCollapse }: { onCollapse: () => void }) {
  const { thread, team: agents } = useTeam();
  const tasks = useStore((s) => s.tasks);
  const threadId = useStore((s) => s.threadId);
  const focus = useStore((s) => s.focus);
  const own = thread?.team === 'own';
  // In an own-team chat, new sub-agents belong to it; elsewhere they join the shared library.
  const create = () => openForm(own ? { threadId } : {});

  const { current, last, recent } = useMemo(() => {
    const list = Object.values(tasks)
      .filter((t) => t.thread_id === threadId)
      .sort((a, b) => b.id - a.id);
    const current = new Map<number, Task>();
    const last = new Map<number, Task>();
    for (const t of list) {
      if (busy(t) && !current.has(t.agent_id)) current.set(t.agent_id, t);
      if (!busy(t) && !last.has(t.agent_id)) last.set(t.agent_id, t);
    }
    return { current, last, recent: list.slice(0, 12) };
  }, [tasks, threadId]);

  const working = current.size;

  return (
    <>
      <div className="pane-head">
        <h2>{own ? 'Team' : 'Sub-agents'}</h2>
        {agents.length > 0 && <span className="count">{working ? `${working} working` : `${agents.length}`}</span>}
        <span className="spacer" />
        <button className="icon-btn" aria-label="New sub-agent" title="New sub-agent" onClick={create}>
          <Plus />
        </button>
        <button className="icon-btn" aria-label="Collapse sub-agents" title="Collapse" onClick={onCollapse}>
          <ChevronRight />
        </button>
      </div>
      <div className="pane-scroll">
        {focus != null ? (
          <TaskFocus id={focus} />
        ) : agents.length === 0 ? (
          <div className="empty small">
            <strong>{own ? 'Build your team' : 'No sub-agents'}</strong>
            {own
              ? 'This chat starts with no sub-agents. Ask the Manager to propose the ones the work needs, or add one yourself. They stay in this chat.'
              : 'Create one, or ask the Manager to propose one.'}
            <button className="pill" onClick={create}>
              New sub-agent
            </button>
          </div>
        ) : (
          <ul className="pa-agents">
            {agents.map((a) => (
              <AgentRow key={a.id} agent={a} current={current.get(a.id)} last={last.get(a.id)} />
            ))}
          </ul>
        )}
        {focus == null && recent.length > 0 && (
          <section className="pa-activity">
            <h3>Activity</h3>
            <ul>
              {recent.map((t) => (
                <ActivityRow key={t.id} task={t} />
              ))}
            </ul>
          </section>
        )}
      </div>
    </>
  );
}
