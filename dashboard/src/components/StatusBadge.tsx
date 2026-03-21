import clsx from 'clsx';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

const statusColorMap: Record<string, string> = {
  pending: 'bg-gray-50 text-gray-700 border-gray-200',
  '待评估': 'bg-gray-50 text-gray-700 border-gray-200',
  evaluating: 'bg-blue-50 text-blue-700 border-blue-200',
  '评估中': 'bg-blue-50 text-blue-700 border-blue-200',
  approved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  '已通过': 'bg-emerald-50 text-emerald-700 border-emerald-200',
  rejected: 'bg-red-50 text-red-700 border-red-200',
  '已拒绝': 'bg-red-50 text-red-700 border-red-200',
  developing: 'bg-purple-50 text-purple-700 border-purple-200',
  '开发中': 'bg-purple-50 text-purple-700 border-purple-200',
  building: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  '构建中': 'bg-indigo-50 text-indigo-700 border-indigo-200',
  live: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  '已上架': 'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed: 'bg-red-50 text-red-700 border-red-200',
  '失败': 'bg-red-50 text-red-700 border-red-200',
  running: 'bg-blue-50 text-blue-700 border-blue-200',
};

const defaultColor = 'bg-gray-50 text-gray-700 border-gray-200';

export default function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const colorClasses = statusColorMap[status] || defaultColor;

  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full border font-medium',
        colorClasses,
        size === 'sm' ? 'px-2.5 py-0.5 text-xs' : 'px-3 py-1 text-sm'
      )}
    >
      {status}
    </span>
  );
}
