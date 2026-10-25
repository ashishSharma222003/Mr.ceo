'use client';

import { useState } from 'react';
import { resolveApproval, useStore } from '@/lib/store';
import type { Approval, Decision } from '@/lib/types';

const TITLES: Record<string, string> = {
  create_subagent: 'Create sub-agent',
  update_subagent: 'Edit sub-agent',
  create_skill: 'Create skill',
  update_skill: 'Edit skill',
};

const show = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v, null, 2));
/** Text fields are edited as text; everything else (lists, objects) as JSON. */
const parse = (orig: unknown, raw: string) => (typeof orig === 'string' ? raw : JSON.parse(raw));

export default function ApprovalCard({ approval }: { approval: Approval }) {
  const busy = useStore((s) => s.sending);
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>[]>(() =>
    approval.actions.map((a) => Object.fromEntries(Object.entries(a.args).map(([k, v]) => [k, show(v)]))),
  );
  const [bad, setBad] = useState<string | null>(null);

  const approve = () => void resolveApproval(approval.actions.map(() => ({ type: 'approve' })));
  const reject = () => void resolveApproval(approval.actions.map(() => ({ type: 'reject' })));
  const saveEdit = () => {
    try {
      const decisions: Decision[] = approval.actions.map((a, i) => ({
        type: 'edit',
        edited_args: Object.fromEntries(Object.entries(drafts[i]).map(([k, raw]) => [k, parse(a.args[k], raw)])),
      }));
      setBad(null);
      void resolveApproval(decisions);
    } catch {
      setBad('A list or object field is not valid JSON.');
    }
  };

  return (
    <li className="approval" aria-label="Approval needed">
      <div className="approval-head">Needs your approval</div>
      {approval.actions.map((a, i) => (
        <div className="approval-action" key={i}>
          <strong>{TITLES[a.name] ?? a.name}</strong>
          <dl>
            {Object.entries(a.args).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                {editing ? (
                  <textarea
                    value={drafts[i][k]}
                    rows={typeof v === 'string' && v.length < 60 ? 1 : 4}
                    aria-label={k}
                    onChange={(e) => setDrafts((d) => d.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))}
                  />
                ) : (
                  <dd>{show(v)}</dd>
                )}
              </div>
            ))}
          </dl>
        </div>
      ))}
      {bad && <div className="err">{bad}</div>}
      <div className="approval-buttons">
        {editing ? (
          <>
            <button className="pill" disabled={busy} onClick={() => setEditing(false)}>Cancel</button>
            <button className="pill primary" disabled={busy} onClick={saveEdit}>Approve changes</button>
          </>
        ) : (
          <>
            <button className="pill danger" disabled={busy} onClick={reject}>Reject</button>
            <button className="pill" disabled={busy} onClick={() => setEditing(true)}>Edit</button>
            <button className="pill primary" disabled={busy} onClick={approve}>Approve</button>
          </>
        )}
      </div>
    </li>
  );
}
