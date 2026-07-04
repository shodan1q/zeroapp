import { type LucideIcon, Inbox } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export default function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-16 fade-in-up">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-gray-100 to-gray-50 ring-1 ring-gray-200/70 dark:from-[#161d45] dark:to-[#111738] dark:ring-[#1e2756]">
        <Icon className="h-7 w-7 text-gray-400 dark:text-slate-500" />
      </div>
      <h3 className="mb-1 text-base font-medium text-gray-700 dark:text-slate-300">{title}</h3>
      {description && (
        <p className="mb-5 max-w-sm text-center text-sm text-gray-400 dark:text-slate-500">
          {description}
        </p>
      )}
      {action && (
        <button onClick={action.onClick} className="btn btn-primary">
          {action.label}
        </button>
      )}
    </div>
  );
}
