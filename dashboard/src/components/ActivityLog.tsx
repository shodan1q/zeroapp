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

const typeColors: Record<string, string> = {
  info: 'bg-blue-50 text-blue-700 border-blue-200',
  success: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  error: 'bg-red-50 text-red-700 border-red-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
};

const defaultTypeColor = 'bg-gray-50 text-gray-700 border-gray-200';

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
      className="bg-gray-50 border border-gray-200 rounded-xl overflow-y-auto max-h-64 p-3"
    >
      {visibleEvents.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-4">暂无日志</p>
      )}
      <div className="space-y-1">
        {visibleEvents.map((event, i) => (
          <div key={i} className="flex items-start gap-2 font-mono text-sm leading-relaxed">
            <span className="text-gray-400 flex-shrink-0 text-xs pt-0.5">
              {event.timestamp}
            </span>
            <span
              className={clsx(
                'inline-flex items-center rounded-full border px-1.5 py-0 text-[10px] font-medium flex-shrink-0',
                typeColors[event.type] || defaultTypeColor
              )}
            >
              {event.type}
            </span>
            <span className="text-gray-700 break-all">{event.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
