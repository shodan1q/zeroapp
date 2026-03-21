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
    circle: 'bg-gray-200 text-gray-400',
    icon: Circle,
  },
  active: {
    circle: 'bg-blue-500 text-white animate-pulse',
    icon: Loader2,
  },
  completed: {
    circle: 'bg-emerald-500 text-white',
    icon: Check,
  },
  failed: {
    circle: 'bg-red-500 text-white',
    icon: X,
  },
};

function lineColor(left: PipelineStage['status'], right: PipelineStage['status']): string {
  if (left === 'completed' && (right === 'completed' || right === 'active')) {
    return 'bg-emerald-400';
  }
  if (left === 'failed' || right === 'failed') {
    return 'bg-red-300';
  }
  return 'bg-gray-200';
}

export default function PipelineView({
  stages,
  currentDemand,
  elapsed,
  retryCount,
  maxRetries,
}: PipelineViewProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
      {/* Pipeline stages */}
      <div className="flex items-start overflow-x-auto pb-2">
        {stages.map((stage, i) => {
          const config = statusConfig[stage.status];
          const Icon = config.icon;
          return (
            <div key={i} className="flex items-start flex-1 min-w-0">
              <div className="flex flex-col items-center min-w-[72px]">
                <div
                  className={clsx(
                    'w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0',
                    config.circle
                  )}
                >
                  <Icon
                    className={clsx('w-4 h-4', {
                      'animate-spin': stage.status === 'active',
                    })}
                  />
                </div>
                <span className="text-xs text-gray-600 mt-2 text-center leading-tight">
                  {stage.name}
                </span>
                {stage.detail && (
                  <span className="text-[10px] text-gray-400 mt-0.5 text-center">
                    {stage.detail}
                  </span>
                )}
              </div>
              {i < stages.length - 1 && (
                <div className="flex-1 flex items-center pt-4 px-1 min-w-[24px]">
                  <div
                    className={clsx(
                      'h-0.5 w-full rounded-full',
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
        <div className="mt-4 pt-4 border-t border-gray-100 flex items-center gap-4 text-sm text-gray-600">
          {currentDemand && (
            <span className="truncate flex-1">
              当前需求：<span className="font-medium text-gray-800">{currentDemand}</span>
            </span>
          )}
          {elapsed !== undefined && (
            <span className="flex items-center gap-1 flex-shrink-0">
              <Clock className="w-3.5 h-3.5 text-gray-400" />
              {formatElapsed(elapsed)}
            </span>
          )}
          {retryCount !== undefined && maxRetries !== undefined && (
            <span className="flex items-center gap-1 flex-shrink-0 bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-2.5 py-0.5 text-xs font-medium">
              <RotateCcw className="w-3 h-3" />
              重试 {retryCount}/{maxRetries}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
