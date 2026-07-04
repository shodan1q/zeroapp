'use client';

import { Check, X, Loader2, Circle, Clock, RotateCcw } from 'lucide-react';
import clsx from 'clsx';

interface PipelineStage {
  name: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  detail?: string;
}

interface PipelineViewProps {
  stages: PipelineStage[];
  currentDemand?: string;
  elapsed?: number;
  retryCount?: number;
  maxRetries?: number;
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}分${s}秒` : `${s}秒`;
}

const statusConfig = {
  pending: {
    circle:
      'bg-gray-100 text-gray-400 ring-1 ring-gray-200 dark:bg-[#161d45] dark:text-slate-500 dark:ring-[#1e2756]',
    icon: Circle,
  },
  active: {
    circle:
      'bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/40',
    icon: Loader2,
  },
  completed: {
    circle:
      'bg-gradient-to-br from-emerald-500 to-emerald-600 text-white shadow-md shadow-emerald-500/30',
    icon: Check,
  },
  failed: {
    circle:
      'bg-gradient-to-br from-red-500 to-rose-600 text-white shadow-md shadow-red-500/30',
    icon: X,
  },
};

function lineColor(left: PipelineStage['status'], right: PipelineStage['status']): string {
  if (left === 'completed' && (right === 'completed' || right === 'active')) {
    return 'bg-gradient-to-r from-emerald-400 to-emerald-500';
  }
  if (left === 'failed' || right === 'failed') {
    return 'bg-red-300 dark:bg-red-500/40';
  }
  return 'bg-gray-200 dark:bg-[#1e2756]';
}

export default function PipelineView({
  stages,
  currentDemand,
  elapsed,
  retryCount,
  maxRetries,
}: PipelineViewProps) {
  return (
    <div className="glass p-6">
      {/* Pipeline stages */}
      <div className="flex items-start overflow-x-auto pb-2">
        {stages.map((stage, i) => {
          const config = statusConfig[stage.status];
          const Icon = config.icon;
          return (
            <div key={i} className="flex min-w-0 flex-1 items-start">
              <div className="flex min-w-[72px] flex-col items-center">
                <div className="relative flex-shrink-0">
                  {stage.status === 'active' && (
                    <span className="absolute inset-0 animate-ping rounded-full bg-blue-500 opacity-30" />
                  )}
                  <div
                    className={clsx(
                      'relative flex h-9 w-9 items-center justify-center rounded-full transition-all duration-300',
                      config.circle
                    )}
                  >
                    <Icon
                      className={clsx('h-4 w-4', {
                        'animate-spin': stage.status === 'active',
                      })}
                    />
                  </div>
                </div>
                <span
                  className={clsx(
                    'mt-2 text-center text-xs leading-tight transition-colors',
                    stage.status === 'active'
                      ? 'font-medium text-blue-700 dark:text-blue-300'
                      : stage.status === 'pending'
                        ? 'text-gray-400 dark:text-slate-500'
                        : 'text-gray-600 dark:text-slate-300'
                  )}
                >
                  {stage.name}
                </span>
                {stage.detail && (
                  <span className="mt-0.5 text-center text-[10px] text-gray-400 dark:text-slate-500">
                    {stage.detail}
                  </span>
                )}
              </div>
              {i < stages.length - 1 && (
                <div className="flex min-w-[24px] flex-1 items-center px-1 pt-4">
                  <div
                    className={clsx(
                      'h-0.5 w-full rounded-full transition-colors duration-300',
                      lineColor(stage.status, stages[i + 1].status)
                    )}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Info bar */}
      {(currentDemand || elapsed !== undefined || retryCount !== undefined) && (
        <div className="mt-4 flex items-center gap-4 border-t border-gray-100 dark:border-[#1e2756]/70 pt-4 text-sm text-gray-600 dark:text-slate-400">
          {currentDemand && (
            <span className="flex-1 truncate">
              当前需求：
              <span className="font-medium text-gray-800 dark:text-slate-200">{currentDemand}</span>
            </span>
          )}
          {elapsed !== undefined && (
            <span className="flex flex-shrink-0 items-center gap-1 tabular-nums">
              <Clock className="h-3.5 w-3.5 text-gray-400 dark:text-slate-500" />
              {formatElapsed(elapsed)}
            </span>
          )}
          {retryCount !== undefined && maxRetries !== undefined && (
            <span className="badge-warning flex-shrink-0 tabular-nums">
              <RotateCcw className="h-3 w-3" />
              重试 {retryCount}/{maxRetries}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
