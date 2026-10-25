'use client';

import { memo } from 'react';
import { useStore } from '@/lib/store';
import { clock, day } from '@/lib/status';
import type { Task } from '@/lib/types';
import Text from './Text';

/** One sub-agent attempt at a task: the Manager's instruction and the sub-agent's answer. */
export default memo(function Attempt({ task, n }: { task: Task; n: number }) {
  const agent = useStore((s) => s.agents.find((a) => a.id === task.agent_id)?.name ?? 'Sub-agent');
  const busy = task.status === 'pending' || task.status === 'running';
  return (
    <li className="attempt" data-status={task.status}>
      <div className="attempt-head">
        <b>Attempt {n}</b>
        <span>{agent}</span>
        <time>
          {day(task.created_at)}, {clock(task.created_at)}
        </time>
      </div>
      <div className="attempt-block">
        <span className="label">Manager → {agent}</span>
        <Text text={task.instruction} />
      </div>
      <div className="attempt-block" data-from="agent">
        <span className="label">{task.status === 'failed' ? 'Error' : `${agent} → Manager`}</span>
        {busy ? (
          <span className="working">
            <i /> Working on it…
          </span>
        ) : (
          <Text text={task.result ?? ''} />
        )}
      </div>
    </li>
  );
});
