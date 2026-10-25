const base = {
  viewBox: '0 0 16 16',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
};

export const Plus = () => <svg {...base}><path d="M8 3v10M3 8h10" /></svg>;
export const X = () => <svg {...base}><path d="M4 4l8 8M12 4l-8 8" /></svg>;
export const Check = () => <svg {...base} strokeWidth={2.2}><path d="M3.5 8.5l3 3 6-7" /></svg>;
export const ArrowUp = () => <svg {...base} strokeWidth={2}><path d="M8 13V3M3.5 7.5L8 3l4.5 4.5" /></svg>;
export const Pencil = () => <svg {...base}><path d="M10.5 3.5l2 2M3 13l.5-2.5 7-7 2 2-7 7L3 13z" /></svg>;
export const ChatIcon = () => <svg {...base}><path d="M2.5 7.5c0-2.8 2.5-4.5 5.5-4.5s5.5 1.7 5.5 4.5S11 12 8 12c-.7 0-1.4-.1-2-.3L3 13l.8-2.4C3 9.8 2.5 8.7 2.5 7.5z" /></svg>;
export const TasksIcon = () => <svg {...base}><path d="M2.5 4l1.2 1.2L6 3M2.5 9l1.2 1.2L6 8M8.5 4.3h5M8.5 9.3h5M3 13.3h10.5" /></svg>;
export const AgentsIcon = () => <svg {...base}><circle cx="6" cy="5.5" r="2.3" /><path d="M1.8 13c.5-2.2 2.2-3.5 4.2-3.5s3.7 1.3 4.2 3.5M10.5 3.4a2.2 2.2 0 010 4.2M12 9.8c1.2.5 2 1.6 2.2 3.2" /></svg>;
export const ChevronLeft = () => <svg {...base}><path d="M10 3L5 8l5 5" /></svg>;
export const Search = () => <svg {...base}><circle cx="7" cy="7" r="4.3" /><path d="M10.2 10.2L13.5 13.5" /></svg>;
export const Trash = () => <svg {...base}><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5" /></svg>;
export const PanelLeft = () => <svg {...base}><rect x="2" y="3" width="12" height="10" rx="2" /><path d="M6 3v10" /></svg>;
export const PanelRight = () => <svg {...base}><rect x="2" y="3" width="12" height="10" rx="2" /><path d="M10 3v10" /></svg>;
export const ChevronRight = () => <svg {...base}><path d="M6 3l5 5-5 5" /></svg>;
