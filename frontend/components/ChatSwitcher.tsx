'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { openChat, RECENT_CHATS, showNewChat, useStore } from '@/lib/store';
import { ago } from '@/lib/status';
import { ChevronDown, ChevronRight, Compose } from './icons';

/** The chat header's title: shows the open chat and drops down the most recent chats. */
export default function ChatSwitcher() {
  const threads = useStore((s) => s.threads);
  const threadId = useStore((s) => s.threadId);
  const current = threads.find((t) => t.id === threadId);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('pointerdown', away);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('pointerdown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  return (
    <div className="chats" ref={root}>
      <button className="chats-btn" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen((o) => !o)}>
        <span className="chats-title">{current?.title ?? 'Manager'}</span>
        {current?.team === 'own' && <span className="team-badge">Own team</span>}
        <ChevronDown />
      </button>
      {open && (
        <div className="chats-menu" role="dialog" aria-label="Recent chats">
          <button
            className="chats-new"
            onClick={() => {
              setOpen(false);
              showNewChat(true);
            }}
          >
            <Compose /> New chat
          </button>
          <ul>
            {threads.slice(0, RECENT_CHATS).map((t) => (
              <li key={t.id} className="chats-row" aria-current={t.id === threadId || undefined}>
                <button
                  className="chats-item"
                  onClick={() => {
                    setOpen(false);
                    void openChat(t.id);
                  }}
                >
                  <b>{t.title}</b>
                  <small>
                    {ago(t.updated_at)}
                    {t.team === 'own' && ' · Own team'}
                  </small>
                </button>
              </li>
            ))}
          </ul>
          <Link className="chats-all" href="/chats" onClick={() => setOpen(false)}>
            See all chats <span>{threads.length}</span>
            <ChevronRight />
          </Link>
        </div>
      )}
    </div>
  );
}
