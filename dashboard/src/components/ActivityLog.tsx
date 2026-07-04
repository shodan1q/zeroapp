'use client';

import { useEffect, useRef } from 'react';
import clsx from 'clsx';

interface ActivityEvent {
  timestamp: string;
  type: string;
  message: string;
}

interface ActivityLogProps {
  events: ActivityEvent[];
  maxLines?: number;
}

const typeBadges: Record<string, string> = {
  info: 'badge-info',
  success: 'badge-success',
  error: 'badge-error',
  warning: 'badge-warning',
};

const defaultTypeBadge =
  'inline-flex items-center rounded-full border border-gray-200 bg-gray-50 font-medium text-gray-600 dark:border-[#1e2756] dark:bg-[#161d45]/60 dark:text-slate-400';

const typeDots: Record<string, string> = {
  info: 'bg-blue-500',
  success: 'bg-emerald-500',
  error: 'bg-red-500',
  warning: 'bg-amber-500',
};

export default function ActivityLog({ events, maxLines = 100 }: ActivityLogProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [events]);

  const visibleEvents = events.slice(-maxLines);

  return (
    <div
      ref={containerRef}
      className="max-h-64 overflow-y-auto rounded-xl border border-gray-200/60 dark:border-[#1e2756]/60 bg-gray-50/70 dark:bg-[#0a0e27]/60 backdrop-blur-xl p-2"
    >
      {visibleEvents.length === 0 && (
        <p className="py-6 text-center text-sm text-gray-400 dark:text-slate-500">暂无日志</p>
      )}
      <div className="space-y-0.5">
        {visibleEvents.map((event, i) => (
          <div
            key={i}
            className="flex items-start gap-2 rounded-lg px-2 py-1 text-sm leading-relaxed transition-colors hover:bg-blue-600/4 dark:hover:bg-blue-400/6"
          >
            <span
              className={clsx(
                'mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full',
                typeDots[event.type] || 'bg-gray-400 dark:bg-slate-500'
              )}
            />
            <span className="flex-shrink-0 pt-0.5 font-mono text-xs tabular-nums text-gray-400 dark:text-slate-500">
              {event.timestamp}
            </span>
            <span
              className={clsx(
                'flex-shrink-0 px-1.5 py-0 text-[10px]',
                typeBadges[event.type] || defaultTypeBadge
              )}
            >
              {event.type}
            </span>
            <span className="break-all font-mono text-xs leading-5 text-gray-700 dark:text-slate-300">
              {event.message}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
