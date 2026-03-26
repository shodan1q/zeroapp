import clsx from 'clsx';

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        'bg-white/70 dark:bg-[#111738]/60 backdrop-blur-xl border border-white/40 dark:border-[#1e2756]/50 rounded-xl shadow-sm p-6 space-y-4',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <div className="space-y-2 flex-1">
          <div className="h-3 w-20 bg-gray-200 rounded animate-pulse" />
          <div className="h-7 w-28 bg-gray-200 rounded animate-pulse" />
        </div>
        <div className="w-12 h-12 bg-gray-200 rounded-full animate-pulse" />
      </div>
    </div>
  );
}

export function SkeletonRow({ className }: { className?: string }) {
  return (
    <div className={clsx('h-4 bg-gray-200 rounded animate-pulse', className)} />
  );
}

export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={clsx('space-y-2', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={clsx(
            'h-3 bg-gray-200 rounded animate-pulse',
            i === lines - 1 ? 'w-2/3' : 'w-full'
          )}
        />
      ))}
    </div>
  );
}
