'use client';

import { useEffect, useRef, useState } from 'react';
import { closeForm, deleteAgent, loadSkills, saveAgent, useStore } from '@/lib/store';

function Fields({ id }: { id?: number }) {
  const agent = useStore((s) => s.agents.find((a) => a.id === id));
  const skills = useStore((s) => s.skills);
  const [name, setName] = useState(agent?.name ?? '');
  const [prompt, setPrompt] = useState(agent?.role_prompt ?? '');
  const [model, setModel] = useState(agent?.model ?? '');
  const [picked, setPicked] = useState<string[]>(agent?.skills ?? []);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => void loadSkills(), []);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <form
      method="dialog"
      onSubmit={(e) => {
        e.preventDefault();
        void run(() => saveAgent(id, { name: name.trim(), role_prompt: prompt.trim(), model: model.trim(), skills: picked }));
      }}
    >
      <h3>{id == null ? 'New sub-agent' : 'Edit sub-agent'}</h3>
      <label className="field">
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus placeholder="Researcher" />
      </label>
      <label className="field">
        Role
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          required
          rows={4}
          placeholder="You research topics and report concise, sourced findings."
        />
      </label>
      <label className="field">
        Model
        <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="Default (e.g. anthropic:claude-sonnet-5-5)" />
      </label>
      {skills.length > 0 && (
        <fieldset className="field" style={{ border: 0, padding: 0 }}>
          Skills
          <div className="checks">
            {skills.map((s) => (
              <label key={s.id} className="check" title={s.description}>
                <input
                  type="checkbox"
                  checked={picked.includes(s.name)}
                  onChange={(e) => setPicked((p) => (e.target.checked ? [...p, s.name] : p.filter((n) => n !== s.name)))}
                />
                {s.name}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      {error && <div className="err" role="alert" style={{ margin: 0 }}>{error}</div>}
      <div className="actions">
        {id != null && (
          <button
            type="button"
            className="pill danger"
            disabled={busy}
            onClick={() => (confirm ? void run(() => deleteAgent(id)) : setConfirm(true))}
          >
            {confirm ? 'Delete agent and its tasks?' : 'Delete'}
          </button>
        )}
        <span className="spacer" />
        <button type="button" className="pill" onClick={closeForm}>
          Cancel
        </button>
        <button className="pill primary" disabled={busy || !name.trim() || !prompt.trim()}>
          Save
        </button>
      </div>
    </form>
  );
}

export default function AgentForm() {
  const form = useStore((s) => s.form);
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (form && !d.open) d.showModal();
    if (!form && d.open) d.close();
  }, [form]);

  return (
    <dialog ref={ref} onClose={closeForm} onClick={(e) => e.target === ref.current && closeForm()}>
      {form && <Fields key={form.id ?? 'new'} id={form.id} />}
    </dialog>
  );
}
