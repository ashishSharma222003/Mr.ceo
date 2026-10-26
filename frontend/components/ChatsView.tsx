'use client';

import Link from 'next/link';
import { memo, useMemo, useState } from 'react';
import { deleteChat, openChat, showNewChat, useStore } from '@/lib/store';
import { ago } from '@/lib/status';
import type { Thread } from '@/lib/types';
import { ChatIcon, Compose, Search, Trash } from './icons';

const PAGE = 50;

const Row = memo(function Row({ thread, current }: { thread: Thread; current: boolean }) {
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const n = thread.open_tasks;
  const sub = [thread.team === 'own' && 'Own team', n ? `${n} open task${n === 1 ? '' : 's'}` : 'No open tasks'].filter(
    Boolean,
  );

  const remove = async () => {
    if (!confirm) return setConfirm(true);
    try {
      await deleteChat(thread.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setConfirm(false);
    }
  };

  return (
    <li className="chat-row">
      <Link className="row" href="/" onClick={() => void openChat(thread.id)}>
        <span className="chat-row-icon" aria-hidden>
          <ChatIcon />
        </span>
        <span className="row-main">
          <span className="row-title">{thread.title}</span>
          <span className="row-sub">{error ?? sub.join(' · ')}</span>
        </span>
        <span className="row-meta">
          {current && <span className="state-pill">Open</span>}
          <time>{ago(thread.updated_at)}</time>
        </span>
      </Link>
      <button
        className={confirm ? 'mini danger' : 'icon-btn chat-row-del'}
        aria-label={`Delete chat ${thread.title}`}
        title="Delete chat, its tasks and its own sub-agents"
        onClick={() => void remove()}
        onBlur={() => setConfirm(false)}
      >
        {confirm ? 'Delete?' : <Trash />}
      </button>
    </li>
  );
});

/** Every conversation with the Manager. The sidebar and chat header only show the latest few. */
export default function ChatsView() {
  const loaded = useStore((s) => s.loaded);
  const threads = useStore((s) => s.threads);
  const threadId = useStore((s) => s.threadId);
  const [query, setQuery] = useState('');
  const [shown, setShown] = useState(PAGE);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? threads.filter((t) => t.title.toLowerCase().includes(q)) : threads;
  }, [threads, query]);

  return (
    <div className="page">
      <div className="page-inner">
        <header className="page-head">
          <h1>Chats</h1>
          <label className="search">
            <Search />
            <input
              type="search"
              value={query}
              placeholder="Search"
              aria-label="Search chats"
              onChange={(e) => {
                setQuery(e.target.value);
                setShown(PAGE);
              }}
            />
          </label>
          <button className="pill primary" onClick={() => showNewChat(true)}>
            <Compose /> New chat
          </button>
        </header>

        {!loaded ? (
          <ul className="rows" aria-hidden>
            {[0, 1, 2].map((i) => (
              <li key={i} className="row skeleton" />
            ))}
          </ul>
        ) : rows.length === 0 ? (
          <div className="empty">
            <strong>{query ? 'No matches' : 'No chats yet'}</strong>
            {!query && 'Start one with New chat.'}
          </div>
        ) : (
          <>
            <ul className="rows">
              {rows.slice(0, shown).map((t) => (
                <Row key={t.id} thread={t} current={t.id === threadId} />
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
