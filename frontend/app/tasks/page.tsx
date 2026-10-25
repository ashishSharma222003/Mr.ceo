import { Suspense } from 'react';
import TasksView from '@/components/TasksView';

export const metadata = { title: 'Tasks · Mr.ceo' };

export default function Page() {
  // TasksView reads ?f= (the initial filter); search params need a Suspense boundary.
  return (
    <Suspense>
      <TasksView />
    </Suspense>
  );
}
