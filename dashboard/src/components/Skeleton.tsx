import clsx from 'clsx';

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={clsx('glass space-y-4 p-5', className)}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 space-y-2.5">
          <div className="h-3 w-20 animate-pulse rounded-md bg-gray-200/80 dark:bg-[#1e2756]/70" />
          <div className="h-7 w-28 animate-pulse rounded-md bg-gray-200/80 dark:bg-[#1e2756]/70" />
        </div>
        <div className="h-10 w-10 animate-pulse rounded-xl bg-gray-200/80 dark:bg-[#1e2756]/70" />
      </div>
    </div>
  );
}

export function SkeletonRow({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        'h-4 animate-pulse rounded-md bg-gray-200/80 dark:bg-[#1e2756]/70',
        className
      )}
    />
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
            'h-3 animate-pulse rounded-md bg-gray-200/80 dark:bg-[#1e2756]/70',
            i === lines - 1 ? 'w-2/3' : 'w-full'
          )}
        />
      ))}
    </div>
  );
}
