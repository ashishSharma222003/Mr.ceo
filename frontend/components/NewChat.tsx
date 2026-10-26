'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { showNewChat, startChat, useStore } from '@/lib/store';
import type { Agent, Team } from '@/lib/types';
import { initials } from './bits';

function Choice({ library }: { library: Agent[] }) {
  const [team, setTeam] = useState<Team>(library.length ? 'shared' : 'own');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const n = library.length;
  const router = useRouter();
  const path = usePathname();

  return (
    <form
      method="dialog"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await startChat(team);
          if (path !== '/') router.push('/'); // started from another page: go to the new chat
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
          setBusy(false);
        }
      }}
    >
      <div>
        <h3>New chat</h3>
        <p className="dialog-lead">Who should the Manager work with?</p>
      </div>
      <div className="team-options" role="radiogroup" aria-label="Team">
        <label className="team-option" data-disabled={!n}>
          <input
            type="radio"
            name="team"
            checked={team === 'shared'}
            disabled={!n}
            onChange={() => setTeam('shared')}
          />
          <span className="team-text">
            <b>Your sub-agents</b>
            <span>
              {n
                ? `Start with the ${n} sub-agent${n === 1 ? '' : 's'} you already have. New ones join them.`
                : 'You don’t have any sub-agents yet.'}
            </span>
            {n > 0 && (
              <span className="team-faces">
                {library.slice(0, 6).map((a) => (
                  <span key={a.id} className="avatar sm" title={a.name}>
                    {initials(a.name)}
                  </span>
                ))}
                {n > 6 && <span className="team-more">+{n - 6}</span>}
              </span>
            )}
          </span>
        </label>
        <label className="team-option">
          <input type="radio" name="team" checked={team === 'own'} onChange={() => setTeam('own')} />
          <span className="team-text">
            <b>Build a new team</b>
            <span>
              Start with no sub-agents. The Manager proposes the ones the work needs (you approve each), or you add them
              yourself. They stay in this chat.
            </span>
          </span>
        </label>
      </div>
      {error && (
        <div className="err" role="alert" style={{ margin: 0 }}>
          {error}
        </div>
      )}
      <div className="actions">
        <span className="spacer" />
        <button type="button" className="pill" onClick={() => showNewChat(false)}>
          Cancel
        </button>
        <button className="pill primary" disabled={busy}>
          Start chat
        </button>
      </div>
    </form>
  );
}

/** "New chat": asks whether to use the existing sub-agents or build a team just for this chat. */
export default function NewChat() {
  const open = useStore((s) => s.newChat);
  const agents = useStore((s) => s.agents);
  const library = useMemo(() => agents.filter((a) => a.thread_id == null), [agents]);
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-label="New chat"
      onClose={() => showNewChat(false)}
      onClick={(e) => e.target === ref.current && showNewChat(false)}
    >
      {open && <Choice library={library} />}
    </dialog>
  );
}
