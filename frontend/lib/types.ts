export type TaskStatus = 'pending' | 'running' | 'done' | 'failed';
export type TodoStatus = 'todo' | 'in_progress' | 'review' | 'done';

export interface Agent {
  id: number;
  name: string;
  role_prompt: string;
  model: string;
  skills: string[];
  thread_id: string | null; // set: belongs only to that chat (its own team)
  created_at: string;
}

export interface Task {
  id: number;
  agent_id: number;
  instruction: string;
  thread_id: string | null;
  todo_id: number | null;
  status: TaskStatus;
  result: string | null; // full response from the sub-agent
  summary: string | null; // short plain-text brief for the user
  created_at: string;
  finished_at: string | null;
}

export interface Todo {
  id: number;
  thread_id: string;
  title: string;
  description: string;
  status: TodoStatus;
  summary: string | null; // what the sub-agent reported when the item was completed
  task_id: number | null;
  origin_message_id: number | null; // user message that led to this task
  created_at: string;
  updated_at: string;
}

/** role: "user" | "manager" | "agent" | "system". agent_id is set on Manager<->sub-agent messages. */
export interface ChatMessage {
  id: number;
  thread_id: string;
  role: string;
  content: string;
  agent_id: number | null;
  todo_id: number | null; // task the user message was about
  created_at: string;
}

/** "shared": works with the sub-agents you already have. "own": starts with none; the ones made in it stay in it. */
export type Team = 'shared' | 'own';

/** A conversation with the Manager. */
export interface Thread {
  id: string;
  title: string;
  team: Team;
  open_tasks: number; // tasklist items not done yet
  created_at: string;
  updated_at: string;
}

/** A tool call the Manager wants to make and needs the user's yes for. */
export interface ApprovalAction {
  name: string;
  args: Record<string, unknown>;
}

export interface Approval {
  id: number;
  thread_id: string;
  actions: ApprovalAction[];
  status: 'pending' | 'resolved';
  created_at: string;
}

export interface Decision {
  type: 'approve' | 'edit' | 'reject';
  edited_args?: Record<string, unknown>;
  message?: string;
}

export interface Skill {
  id: number;
  name: string;
  description: string;
  type: string;
}

export interface ChatResponse {
  thread_id: string;
  reply: string;
  tasks: Task[];
  todos: Todo[];
}

export interface AgentInput {
  name: string;
  role_prompt: string;
  model?: string | null;
  skills: string[];
  thread_id?: string | null;
}
