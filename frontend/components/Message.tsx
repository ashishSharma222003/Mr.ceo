import { memo } from 'react';
import { clock } from '@/lib/status';
import type { ChatMessage } from '@/lib/types';
import { TaskChip } from './bits';
import Text from './Text';

/** One turn of the user <-> Manager conversation. The Manager speaks as plain text (no bubble),
 * the user in a soft bubble, system reports as a quiet event line. */
export default memo(function Message({ m, showTask = true }: { m: ChatMessage; showTask?: boolean }) {
  if (m.role === 'system') {
    const failed = m.content.includes(' FAILED ');
    return (
      <li className="m-event" data-failed={failed}>
        <span>{failed ? 'Sub-agent failed' : 'Sub-agent reported back'}</span>
        <time>{clock(m.created_at)}</time>
      </li>
    );
  }
  // Skip the header chip when the reply already names the task inline.
  const named = m.todo_id != null && new RegExp(`task #${m.todo_id}\\b`, 'i').test(m.content);
  const chip = showTask && m.todo_id != null && !named && <TaskChip id={m.todo_id} />;
  if (m.role === 'user') {
    return (
      <li className="m-user">
        <div className="bubble">
          {chip}
          <Text text={m.content} />
        </div>
      </li>
    );
  }
  return (
    <li className="m-ai">
      {chip}
      <Text text={m.content} linkTasks />
    </li>
  );
});
