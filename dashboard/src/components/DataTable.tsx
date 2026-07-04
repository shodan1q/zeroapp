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
    <div className="glass overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="table-head">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
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
                <tr key={`skeleton-${i}`} className="table-row">
                  {columns.map((col) => (
                    <td key={col.key}>
                      <SkeletonRow />
                    </td>
                  ))}
                </tr>
              ))}

            {!loading && data.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="py-16">
                  <div className="flex flex-col items-center justify-center gap-3">
                    <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-gray-100/80 dark:bg-[#161d45]/80">
                      <Inbox className="h-6 w-6 text-gray-400 dark:text-slate-500" />
                    </span>
                    <span className="text-sm text-gray-400 dark:text-slate-500">{emptyText}</span>
                  </div>
                </td>
              </tr>
            )}

            {!loading &&
              data.map((row, rowIdx) => (
                <tr
                  key={rowIdx}
                  className={clsx(
                    'table-row text-gray-700 dark:text-slate-300',
                    onRowClick && 'cursor-pointer'
                  )}
                  onClick={() => onRowClick?.(row)}
                >
                  {columns.map((col) => (
                    <td key={col.key}>
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
        <div className="flex items-center justify-between border-t border-gray-100 dark:border-[#1e2756]/70 px-4 py-3">
          <span className="text-xs text-gray-500 dark:text-slate-400 tabular-nums">
            共 {pagination.total} 条
          </span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => pagination.onChange(pagination.page - 1)}
              disabled={pagination.page <= 1}
              className="btn btn-secondary btn-sm px-2"
            >
              <ChevronLeft className="h-4 w-4" />
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
                  <span
                    key={`e-${idx}`}
                    className="px-1.5 text-sm text-gray-400 dark:text-slate-500"
                  >
                    ...
                  </span>
                ) : (
                  <button
                    key={item}
                    onClick={() => pagination.onChange(item as number)}
                    className={clsx(
                      'btn btn-sm h-8 w-8 px-0 tabular-nums',
                      item === pagination.page ? 'btn-primary' : 'btn-secondary'
                    )}
                  >
                    {item}
                  </button>
                )
              )}
            <button
              onClick={() => pagination.onChange(pagination.page + 1)}
              disabled={pagination.page >= totalPages}
              className="btn btn-secondary btn-sm px-2"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
