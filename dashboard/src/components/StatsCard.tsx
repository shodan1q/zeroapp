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

const colorMap = {
  blue: { bg: 'bg-blue-50', text: 'text-blue-600' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600' },
  purple: { bg: 'bg-purple-50', text: 'text-purple-600' },
  amber: { bg: 'bg-amber-50', text: 'text-amber-600' },
  indigo: { bg: 'bg-indigo-50', text: 'text-indigo-600' },
  gray: { bg: 'bg-gray-50', text: 'text-gray-600' },
};

export default function StatsCard({ title, value, icon: Icon, color, trend }: StatsCardProps) {
  const colors = colorMap[color];

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm text-gray-500 mb-1">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          {trend && (
            <div className="flex items-center mt-2 gap-1">
              {trend.direction === 'up' && (
                <TrendingUp className="w-4 h-4 text-emerald-500" />
              )}
              {trend.direction === 'down' && (
                <TrendingDown className="w-4 h-4 text-red-500" />
              )}
              {trend.direction === 'flat' && (
                <Minus className="w-4 h-4 text-gray-400" />
              )}
              <span
                className={clsx('text-xs font-medium', {
                  'text-emerald-600': trend.direction === 'up',
                  'text-red-600': trend.direction === 'down',
                  'text-gray-500': trend.direction === 'flat',
                })}
              >
                {trend.value}%
              </span>
            </div>
          )}
        </div>
        <div className={clsx('w-12 h-12 rounded-full flex items-center justify-center', colors.bg)}>
          <Icon className={clsx('w-6 h-6', colors.text)} />
        </div>
      </div>
    </div>
  );
}
