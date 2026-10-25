'use client';

import { useEffect, useRef, useState } from 'react';
import { focusTodo, useStore } from '@/lib/store';
import AgentPane from './AgentPane';
import { OpenTask } from './bits';
import ChatView from './ChatView';
import { PanelLeft, PanelRight } from './icons';
import TaskPane from './TaskPane';

type Side = 'left' | 'right';
type Layout = { left: number; right: number; leftOpen: boolean; rightOpen: boolean };

const LIMITS = { left: [220, 480], right: [240, 520] } as const;
const DEFAULTS: Layout = { left: 300, right: 320, leftOpen: true, rightOpen: true };
const COLLAPSE_AT = 140; // dragging a pane narrower than this closes it
const KEY = 'mrceo.workspace';
const clamp = (n: number, [lo, hi]: readonly [number, number]) => Math.min(hi, Math.max(lo, n));

/** Chat page: tasks | Manager chat | sub-agents. Side panes resize by dragging the divider,
 * collapse with their button (or by dragging them nearly shut) and reopen from the chat toolbar. */
export default function ChatWorkspace() {
  const root = useRef<HTMLDivElement>(null);
  const layout = useRef<Layout>({ ...DEFAULTS });
  const [open, setOpen] = useState({ left: true, right: true });
  const [mobile, setMobile] = useState<'tasks' | 'chat' | 'agents'>('chat');
  const toApprove = useStore((s) => s.todos.filter((t) => t.status === 'review').length);
  const reference = useStore((s) => s.reference);

  // "Request changes" puts a task chip in the composer: on a phone, show the chat to type in.
  useEffect(() => {
    if (reference != null) setMobile('chat');
  }, [reference]);

  // Widths go straight to CSS variables while dragging (no React render per pointer move).
  const apply = () => {
    const el = root.current;
    if (!el) return;
    const l = layout.current;
    el.style.setProperty('--wl', l.leftOpen ? `${l.left}px` : '0px');
    el.style.setProperty('--wr', l.rightOpen ? `${l.right}px` : '0px');
  };
  const save = () => {
    try {
      localStorage.setItem(KEY, JSON.stringify(layout.current));
    } catch {}
  };
  const toggle = (side: Side, value?: boolean) => {
    const key = side === 'left' ? 'leftOpen' : 'rightOpen';
    layout.current[key] = value ?? !layout.current[key];
    if (layout.current[key] && layout.current[side] < LIMITS[side][0]) layout.current[side] = DEFAULTS[side];
    setOpen({ left: layout.current.leftOpen, right: layout.current.rightOpen });
    apply();
    save();
  };

  useEffect(() => {
    try {
      Object.assign(layout.current, JSON.parse(localStorage.getItem(KEY) ?? '{}'));
    } catch {}
    setOpen({ left: layout.current.leftOpen, right: layout.current.rightOpen });
    apply();
  }, []);

  const drag = (side: Side) => (e: React.PointerEvent<HTMLDivElement>) => {
    const el = root.current;
    if (!el) return;
    e.preventDefault();
    const sash = e.currentTarget;
    sash.setPointerCapture(e.pointerId);
    const rect = el.getBoundingClientRect(); // read once, before any writes
    el.dataset.dragging = 'true';
    const move = (ev: PointerEvent) => {
      const raw = side === 'left' ? ev.clientX - rect.left : rect.right - ev.clientX;
      const key = side === 'left' ? 'leftOpen' : 'rightOpen';
      const shut = raw < COLLAPSE_AT;
      if (shut !== !layout.current[key]) {
        layout.current[key] = !shut;
        setOpen({ left: layout.current.leftOpen, right: layout.current.rightOpen });
      }
      if (!shut) layout.current[side] = clamp(raw, LIMITS[side]);
      apply();
    };
    const up = () => {
      sash.removeEventListener('pointermove', move);
      sash.removeEventListener('pointerup', up);
      delete el.dataset.dragging;
      save();
    };
    sash.addEventListener('pointermove', move);
    sash.addEventListener('pointerup', up);
  };

  const nudge = (side: Side) => (e: React.KeyboardEvent) => {
    const step = e.key === 'ArrowLeft' ? -16 : e.key === 'ArrowRight' ? 16 : 0;
    if (!step) return;
    e.preventDefault();
    layout.current[side] = clamp(layout.current[side] + (side === 'left' ? step : -step), LIMITS[side]);
    apply();
    save();
  };

  const reset = (side: Side) => () => {
    layout.current[side] = DEFAULTS[side];
    apply();
    save();
  };

  // Open a task in place: highlight it on the left, show its sub-agent conversation on the right.
  const openTask = (id: number) => {
    focusTodo(id);
    if (!layout.current.leftOpen) toggle('left', true);
    if (!layout.current.rightOpen) toggle('right', true);
    setMobile('agents');
  };

  const sash = (side: Side) => (
    <div
      className={`ws-sash ws-sash-${side}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={side === 'left' ? 'Resize tasks' : 'Resize sub-agents'}
      tabIndex={0}
      data-hidden={!open[side]}
      onPointerDown={drag(side)}
      onKeyDown={nudge(side)}
      onDoubleClick={reset(side)}
    />
  );

  return (
    <OpenTask.Provider value={openTask}>
      <div className="ws" ref={root} data-mobile={mobile}>
        <nav className="ws-tabs" role="tablist" aria-label="Panels">
          {(
            [
              ['tasks', toApprove ? `Tasks · ${toApprove}` : 'Tasks'],
              ['chat', 'Chat'],
              ['agents', 'Sub-agents'],
            ] as const
          ).map(([id, label]) => (
            <button key={id} role="tab" aria-selected={mobile === id} onClick={() => setMobile(id)}>
              {label}
            </button>
          ))}
        </nav>
        <section
          className="ws-pane ws-left"
          aria-label="Open tasks"
          data-open={open.left}
          data-mobile-show={mobile === 'tasks'}
        >
          <TaskPane onCollapse={() => toggle('left', false)} />
        </section>
        {sash('left')}
        <section className="ws-center" aria-label="Chat with the Manager">
          <div className="ws-bar">
            <button
              className="icon-btn"
              aria-label={open.left ? 'Hide tasks' : 'Show tasks'}
              aria-pressed={open.left}
              title={open.left ? 'Hide tasks' : 'Show tasks'}
              onClick={() => toggle('left')}
            >
              <PanelLeft />
            </button>
            <h2>Manager</h2>
            <button
              className="icon-btn"
              aria-label={open.right ? 'Hide sub-agents' : 'Show sub-agents'}
              aria-pressed={open.right}
              title={open.right ? 'Hide sub-agents' : 'Show sub-agents'}
              onClick={() => toggle('right')}
            >
              <PanelRight />
            </button>
          </div>
          <ChatView />
        </section>
        {sash('right')}
        <section
          className="ws-pane ws-right"
          aria-label="Sub-agents"
          data-open={open.right}
          data-mobile-show={mobile === 'agents'}
        >
          <AgentPane onCollapse={() => toggle('right', false)} />
        </section>
      </div>
    </OpenTask.Provider>
  );
}
