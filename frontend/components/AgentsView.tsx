'use client';

import { memo, useMemo } from 'react';
import { openForm, useStore } from '@/lib/store';
import type { Agent } from '@/lib/types';
import { initials } from './bits';
import { Plus } from './icons';

const Card = memo(function Card({ agent, done, active }: { agent: Agent; done: number; active: number }) {
  const chat = useStore((s) => (agent.thread_id ? s.threads.find((t) => t.id === agent.thread_id)?.title : undefined));
  return (
    <li>
      <button className="agent-card" onClick={() => openForm({ id: agent.id })} aria-label={`Edit ${agent.name}`}>
        <span className="agent-top">
          <span className="avatar" aria-hidden>
            {initials(agent.name)}
          </span>
          <span className="agent-name">
            <b>{agent.name}</b>
            <span>{agent.model}</span>
          </span>
          {active > 0 && (
            <span className="state-pill" data-state="running">
              Working
            </span>
          )}
        </span>
        <span className="agent-role">{agent.role_prompt}</span>
        {agent.skills.length > 0 && (
          <span className="chips">
            {agent.skills.map((s) => (
              <span key={s} className="chip">
                {s}
              </span>
            ))}
          </span>
        )}
        <span className="agent-foot">
          {done} task{done === 1 ? '' : 's'} done
          {chat && <> · Only in &ldquo;{chat}&rdquo;</>}
        </span>
      </button>
    </li>
  );
});

export default function AgentsView() {
  const loaded = useStore((s) => s.loaded);
  const agents = useStore((s) => s.agents);
  const tasks = useStore((s) => s.tasks);

  const stats = useMemo(() => {
    const m = new Map<number, { done: number; active: number }>();
    for (const t of Object.values(tasks)) {
      const s = m.get(t.agent_id) ?? { done: 0, active: 0 };
      if (t.status === 'done') s.done++;
      if (t.status === 'pending' || t.status === 'running') s.active++;
      m.set(t.agent_id, s);
    }
    return m;
  }, [tasks]);

  return (
    <div className="page">
      <div className="page-inner">
        <header className="page-head">
          <h1>Agents</h1>
          <button className="pill primary" onClick={() => openForm({})}>
            <Plus /> New sub-agent
          </button>
        </header>
        <p className="page-lead">
          Sub-agents do the work the Manager hands out. Give each one a clear role and the skills it needs. The Manager
          can also propose new ones; you approve them in Chat.
        </p>
        {loaded && agents.length === 0 ? (
          <div className="empty">
            <strong>No sub-agents yet</strong>
            Create one, or ask the Manager in Chat to propose one.
          </div>
        ) : (
          <ul className="agent-grid">
            {agents.map((a) => (
              <Card key={a.id} agent={a} done={stats.get(a.id)?.done ?? 0} active={stats.get(a.id)?.active ?? 0} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
