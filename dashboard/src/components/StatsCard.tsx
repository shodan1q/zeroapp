'use client';

import { type LucideIcon, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import clsx from 'clsx';

interface StatsCardProps {
  title: string;
  value: number | string;
  icon: LucideIcon;
  color: 'blue' | 'emerald' | 'purple' | 'amber' | 'indigo' | 'gray';
  trend?: { value: number; direction: 'up' | 'down' | 'flat' };
}

const chipColorMap = {
  blue: 'icon-chip-blue',
  emerald: 'icon-chip-green',
  purple: 'icon-chip-purple',
  amber: 'icon-chip-amber',
  indigo: 'icon-chip-purple',
  gray: 'icon-chip-slate',
};

export default function StatsCard({ title, value, icon: Icon, color, trend }: StatsCardProps) {
  return (
    <div className="glass glass-hover p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="mb-1.5 text-sm text-gray-500 dark:text-slate-400">{title}</p>
          <p className="text-3xl font-bold tracking-tight tabular-nums text-gray-900 dark:text-slate-100">
            {value}
          </p>
          {trend && (
            <div className="mt-2 flex items-center gap-1">
              {trend.direction === 'up' && (
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              )}
              {trend.direction === 'down' && (
                <TrendingDown className="h-4 w-4 text-red-500" />
              )}
              {trend.direction === 'flat' && (
                <Minus className="h-4 w-4 text-gray-400 dark:text-slate-500" />
              )}
              <span
                className={clsx('text-xs font-medium tabular-nums', {
                  'text-emerald-600 dark:text-emerald-400': trend.direction === 'up',
                  'text-red-600 dark:text-red-400': trend.direction === 'down',
                  'text-gray-500 dark:text-slate-400': trend.direction === 'flat',
                })}
              >
                {trend.value}%
              </span>
            </div>
          )}
        </div>
        <span className={clsx('icon-chip', chipColorMap[color])}>
          <Icon className="h-5 w-5" />
        </span>
      </div>
    </div>
  );
}
