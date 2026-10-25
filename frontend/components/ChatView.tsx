'use client';

import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { referenceTodo, send, useStore } from '@/lib/store';
import type { ChatMessage } from '@/lib/types';
import ApprovalCard from './ApprovalCard';
import { TaskChip } from './bits';
import { ArrowUp } from './icons';
import Message from './Message';
import Text from './Text';

const isChat = (m: ChatMessage) => m.agent_id == null && (m.role === 'user' || m.role === 'manager');

const SUGGESTIONS = [
  'Research our top three competitors',
  'Create a sub-agent that writes blog posts',
  'Plan a product launch checklist',
];

export default function ChatView() {
  const loaded = useStore((s) => s.loaded);
  const messages = useStore((s) => s.messages);
  const pending = useStore((s) => s.pending);
  const sending = useStore((s) => s.sending);
  const streams = useStore((s) => s.streams);
  const error = useStore((s) => s.error);
  const approval = useStore((s) => s.approval);
  const reference = useStore((s) => s.reference);
  const chat = useMemo(() => messages.filter(isChat), [messages]);
  const [draft, setDraft] = useState('');
  const scroller = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);

  const writing = Object.entries(streams).filter(([, s]) => s.text);
  const streamLen = writing.reduce((n, [, s]) => n + s.text.length, 0);

  // Show the optimistic bubble only until the server's copy of the message arrives.
  const userCount = chat.filter((m) => m.role === 'user').length;
  const showPending = !!pending && userCount <= pending.base;
  const empty = loaded && chat.length === 0 && !showPending && writing.length === 0 && !approval;

  // Keep the newest message in view, unless the reader has scrolled up.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 200) el.scrollTop = el.scrollHeight;
  }, [chat.length, showPending, sending, streamLen, approval?.id]);

  // Coming here from "Request changes": put the cursor in the box.
  useLayoutEffect(() => {
    if (reference != null) field.current?.focus();
  }, [reference]);

  const grow = () => {
    const el = field.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  };

  const submit = () => {
    const text = draft.trim();
    if (!text || sending || approval) return;
    setDraft('');
    requestAnimationFrame(grow);
    void send(text);
    requestAnimationFrame(() => {
      const el = scroller.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  };

  const placeholder = approval
    ? 'Answer the approval request first'
    : reference != null
      ? 'Describe what should change…'
      : 'Message the Manager';

  return (
    <div className="chat" data-empty={empty}>
      <div className="chat-scroll" ref={scroller}>
        {empty ? (
          <div className="hero">
            <h1>What should we get done?</h1>
            <p>The Manager plans the work, hands it to your sub-agents and checks the results.</p>
          </div>
        ) : (
          <ol className="thread" aria-live="polite">
            {chat.map((m) => (
              <Message key={m.id} m={m} />
            ))}
            {pending && showPending && (
              <li className="m-user">
                <div className="bubble">
                  <Text text={pending.text} />
                </div>
              </li>
            )}
            {writing.map(([run, s]) => (
              <li key={run} className="m-ai" data-streaming={!s.done}>
                <Text text={s.text} linkTasks />
              </li>
            ))}
            {approval && <ApprovalCard key={approval.id} approval={approval} />}
            {sending && writing.length === 0 && (
              <li className="m-ai" aria-label="Manager is thinking">
                <span className="typing">
                  <i /> <i /> <i />
                </span>
              </li>
            )}
          </ol>
        )}
      </div>

      <div className="composer">
        {error && (
          <div className="err" role="alert">
            {error}
          </div>
        )}
        <form
          className="composer-card"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          {reference != null && (
            <div className="composer-ref">
              <TaskChip id={reference} onClear={() => referenceTodo(null)} />
            </div>
          )}
          <div className="composer-row">
            <textarea
              ref={field}
              rows={1}
              value={draft}
              placeholder={placeholder}
              aria-label="Message the Manager"
              onChange={(e) => {
                setDraft(e.target.value);
                grow();
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <button className="send" aria-label="Send" disabled={!draft.trim() || sending || !!approval}>
              <ArrowUp />
            </button>
          </div>
        </form>
        {empty ? (
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                className="suggestion"
                onClick={() => {
                  setDraft(s);
                  field.current?.focus();
                }}
              >
                {s}
              </button>
            ))}
          </div>
        ) : (
          <p className="composer-hint">Enter to send · Shift + Enter for a new line</p>
        )}
      </div>
    </div>
  );
}
