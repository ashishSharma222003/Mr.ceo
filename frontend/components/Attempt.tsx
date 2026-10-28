'use client';

import { memo } from 'react';
import { useStore } from '@/lib/store';
import { clock, day } from '@/lib/status';
import type { Task } from '@/lib/types';
import Text from './Text';

const useAgentName = (id: number | undefined) =>
  useStore((s) => s.agents.find((a) => a.id === id)?.name ?? 'Sub-agent');

/** One sub-agent attempt at a task: the Manager's instruction and the sub-agent's answer. A helper
 * attempt (`helps_task_id`) is a colleague answering a blocked sub-agent, relayed by the Manager. */
const Attempt = memo(function Attempt({ task, n }: { task: Task; n: number }) {
  const agent = useAgentName(task.agent_id);
  const asker = useAgentName(useStore((s) => (task.helps_task_id != null ? s.tasks[task.helps_task_id]?.agent_id : undefined)));
  const helper = task.helps_task_id != null;
  const busy = task.status === 'pending' || task.status === 'running';
  return (
    <li className={helper ? 'attempt helper' : 'attempt'} data-status={task.status}>
      <div className="attempt-head">
        <b>{helper ? `Help for ${asker}` : `Attempt ${n}`}</b>
        <span>{agent}</span>
        <time>
          {day(task.created_at)}, {clock(task.created_at)}
        </time>
      </div>
      <div className="attempt-block">
        <span className="label">{helper ? `Manager → ${agent}, asking for ${asker}` : `Manager → ${agent}`}</span>
        <Text text={task.instruction} />
      </div>
      <div className="attempt-block" data-from="agent">
        <span className="label">
          {task.status === 'failed' ? 'Error' : helper ? `${agent} → ${asker}, via the Manager` : `${agent} → Manager`}
        </span>
        {busy ? (
          <span className="working">
            <i /> Working on it…
          </span>
        ) : (
          <Text text={task.result ?? ''} />
        )}
      </div>
      {task.help_request && !helper && (
        <div className="attempt-block" data-from="help">
          <span className="label">{agent} needs help</span>
          <Text text={task.help_request} />
        </div>
      )}
    </li>
  );
});

/** A task's attempts in order. Helper attempts are not numbered: they belong to the attempt they help. */
export default function AttemptList({ tasks }: { tasks: Task[] }) {
  let n = 0;
  return (
    <ol className="attempts">
      {tasks.map((t) => (
        <Attempt key={t.id} task={t} n={t.helps_task_id == null ? ++n : n} />
      ))}
    </ol>
  );
}
