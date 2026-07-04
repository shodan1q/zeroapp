import clsx from 'clsx';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

const statusBadgeMap: Record<string, string> = {
  pending: 'badge-info',
  '待评估': 'badge-info',
  evaluating: 'badge-info',
  '评估中': 'badge-info',
  approved: 'badge-success',
  '已通过': 'badge-success',
  rejected: 'badge-error',
  '已拒绝': 'badge-error',
  developing: 'badge-warning',
  '开发中': 'badge-warning',
  building: 'badge-warning',
  '构建中': 'badge-warning',
  live: 'badge-success',
  '已上架': 'badge-success',
  failed: 'badge-error',
  '失败': 'badge-error',
  running: 'badge-info',
};

const neutralBadge =
  'inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 font-medium text-gray-600 dark:border-[#1e2756] dark:bg-[#161d45]/60 dark:text-slate-400';

export default function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const badgeClass = statusBadgeMap[status];

  return (
    <span
      className={clsx(
        badgeClass || neutralBadge,
        size === 'sm' ? 'px-2.5 py-0.5 text-xs' : 'px-3 py-1 text-sm'
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {status}
    </span>
  );
}
