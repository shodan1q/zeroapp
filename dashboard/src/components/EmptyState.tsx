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
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <Icon className="w-12 h-12 text-gray-300 mb-4" />
      <h3 className="text-base font-medium text-gray-600 mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-gray-400 mb-4 text-center max-w-sm">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="px-4 py-2 text-sm font-medium text-white bg-gray-900 rounded-lg hover:bg-gray-800 transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
