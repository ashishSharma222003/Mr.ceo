'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { memo, useEffect, useMemo } from 'react';
import { boot, useStore } from '@/lib/store';
import type { Todo } from '@/lib/types';
import { Dot, useTodoState } from './bits';
import { AgentsIcon, ChatIcon, TasksIcon } from './icons';

const AgentForm = dynamic(() => import('./AgentForm'), { ssr: false });

const SideTask = memo(function SideTask({ todo, active }: { todo: Todo; active: boolean }) {
  const state = useTodoState(todo);
  return (
    <li>
      <Link className="side-task" href={`/tasks/${todo.id}`} aria-current={active ? 'page' : undefined}>
        <Dot state={state} />
        <span>{todo.title}</span>
      </Link>
    </li>
  );
});

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const live = useStore((s) => s.live);
  const todos = useStore((s) => s.todos);

  useEffect(() => void boot(), []);

  const toApprove = useMemo(() => todos.filter((t) => t.status === 'review').length, [todos]);
  // Waiting-for-you first, then the newest work.
  const open = useMemo(
    () =>
      todos
        .filter((t) => t.status !== 'done')
        .sort((a, b) => Number(b.status === 'review') - Number(a.status === 'review') || b.id - a.id)
        .slice(0, 8),
    [todos],
  );

  const nav = [
    { href: '/', label: 'Chat', icon: <ChatIcon />, on: path === '/' },
    { href: '/tasks', label: 'Tasks', icon: <TasksIcon />, on: path.startsWith('/tasks'), badge: toApprove },
    { href: '/agents', label: 'Agents', icon: <AgentsIcon />, on: path.startsWith('/agents') },
  ];

  const rail = path === '/'; // the chat workspace brings its own task list: keep the app nav slim

  return (
    <div className="shell" data-rail={rail}>
      <aside className="side">
        <div className="side-brand">
          <span className="logo" aria-hidden>
            M
          </span>
          <span className="brand-name">Mr.ceo</span>
        </div>
        <nav className="side-nav" aria-label="Main">
          {nav.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className="nav-item"
              title={n.label}
              aria-current={n.on ? 'page' : undefined}
            >
              {n.icon}
              <span>{n.label}</span>
              {!!n.badge && (
                <em className="badge" aria-label={`${n.badge} waiting for approval`}>
                  {n.badge}
                </em>
              )}
            </Link>
          ))}
        </nav>
        {!rail && open.length > 0 && (
          <section className="side-section" aria-label="Open tasks">
            <h2>Open tasks</h2>
            <ul>
              {open.map((t) => (
                <SideTask key={t.id} todo={t} active={path === `/tasks/${t.id}`} />
              ))}
            </ul>
          </section>
        )}
        <div className="side-foot" role="status">
          <i data-on={live} aria-hidden title={live ? 'Connected' : 'Connecting…'} />
          <span>{live ? 'Connected' : 'Connecting…'}</span>
        </div>
      </aside>
      <main className="main">{children}</main>
      <AgentForm />
    </div>
  );
}
