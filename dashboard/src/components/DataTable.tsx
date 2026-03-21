'use client';

import { Inbox, ChevronLeft, ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import { SkeletonRow } from './Skeleton';

interface Column<T> {
  key: string;
  title: string;
  render?: (value: any, row: T) => React.ReactNode;
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  emptyText?: string;
  onRowClick?: (row: T) => void;
  pagination?: {
    page: number;
    pageSize: number;
    total: number;
    onChange: (page: number) => void;
  };
}

export default function DataTable<T extends Record<string, any>>({
  columns,
  data,
  loading = false,
  emptyText = '暂无数据',
  onRowClick,
  pagination,
}: DataTableProps<T>) {
  const totalPages = pagination
    ? Math.ceil(pagination.total / pagination.pageSize)
    : 0;

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                  style={col.width ? { width: col.width } : undefined}
                >
                  {col.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`skeleton-${i}`} className="border-b border-gray-100">
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3">
                      <SkeletonRow />
                    </td>
                  ))}
                </tr>
              ))}

            {!loading && data.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="py-16">
                  <div className="flex flex-col items-center justify-center text-gray-400">
                    <Inbox className="w-10 h-10 text-gray-300 mb-2" />
                    <span className="text-sm">{emptyText}</span>
                  </div>
                </td>
              </tr>
            )}

            {!loading &&
              data.map((row, rowIdx) => (
                <tr
                  key={rowIdx}
                  className={clsx(
                    'border-b border-gray-100 transition-colors',
                    onRowClick && 'cursor-pointer hover:bg-gray-50'
                  )}
                  onClick={() => onRowClick?.(row)}
                >
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3 text-sm text-gray-700">
                      {col.render ? col.render(row[col.key], row) : row[col.key]}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pagination && totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
          <span className="text-sm text-gray-500">
            共 {pagination.total} 条
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => pagination.onChange(pagination.page - 1)}
              disabled={pagination.page <= 1}
              className={clsx(
                'p-1.5 rounded-md border border-gray-200 transition-colors',
                pagination.page <= 1
                  ? 'text-gray-300 cursor-not-allowed'
                  : 'text-gray-600 hover:bg-gray-50'
              )}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => {
                if (totalPages <= 7) return true;
                if (p === 1 || p === totalPages) return true;
                return Math.abs(p - pagination.page) <= 1;
              })
              .reduce<(number | 'ellipsis')[]>((acc, p, idx, arr) => {
                if (idx > 0 && p - (arr[idx - 1] as number) > 1) {
                  acc.push('ellipsis');
                }
                acc.push(p);
                return acc;
              }, [])
              .map((item, idx) =>
                item === 'ellipsis' ? (
                  <span key={`e-${idx}`} className="px-2 text-gray-400 text-sm">
                    ...
                  </span>
                ) : (
                  <button
                    key={item}
                    onClick={() => pagination.onChange(item as number)}
                    className={clsx(
                      'w-8 h-8 text-sm rounded-md border transition-colors',
                      item === pagination.page
                        ? 'bg-gray-900 text-white border-gray-900'
                        : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                    )}
                  >
                    {item}
                  </button>
                )
              )}
            <button
              onClick={() => pagination.onChange(pagination.page + 1)}
              disabled={pagination.page >= totalPages}
              className={clsx(
                'p-1.5 rounded-md border border-gray-200 transition-colors',
                pagination.page >= totalPages
                  ? 'text-gray-300 cursor-not-allowed'
                  : 'text-gray-600 hover:bg-gray-50'
              )}
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
