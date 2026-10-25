import { memo } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { TaskChip } from './bits';

const plugins = [remarkGfm];

// Raw HTML in LLM output is not rendered (react-markdown escapes it), and links open safely in a new tab.
// "Task #3" written by the Manager becomes a link to #task-3, rendered as a clickable task chip.
const components = {
  a: ({ href, ...props }: React.ComponentProps<'a'>) => {
    const task = href?.match(/^#task-(\d+)$/);
    if (task) return <TaskChip id={Number(task[1])} inline />;
    return <a {...props} href={href} target="_blank" rel="noopener noreferrer" />;
  },
};

const TASK_REF = /(?<![[\w])[Tt]ask #(\d+)\b(?!\]\()/g;

/** GitHub-flavoured markdown: headings, lists, tables, task lists, code blocks, links.
 * `linkTasks`: make "Task #N" mentions clickable. */
export default memo(function Text({ text, linkTasks }: { text: string; linkTasks?: boolean }) {
  return (
    <div className="md">
      <Markdown remarkPlugins={plugins} components={components}>
        {linkTasks ? text.replace(TASK_REF, '[Task #$1](#task-$1)') : text}
      </Markdown>
    </div>
  );
});
