import { useState, useMemo } from 'react';
import { Search, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';

interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  /** Enable a global search input above the table */
  searchable?: boolean;
  /** Placeholder text for the search box */
  searchPlaceholder?: string;
  /** Optional footer element (e.g. Pagination) */
  footer?: React.ReactNode;
}

/**
 * Production-grade data table with column sorting and optional global search.
 * Built on @tanstack/react-table v8, styled like Prefect/Dagster tables.
 */
export default function DataTable<T>({
  data,
  columns,
  searchable = false,
  searchPlaceholder = 'Search…',
  footer,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState('');

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    globalFilterFn: 'includesString',
  });

  const headerGroups = useMemo(() => table.getHeaderGroups(), [table, sorting]);

  return (
    <div>
      {searchable && (
        <div className="mb-3">
          <div className="relative w-full max-w-sm">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={globalFilter}
              onChange={(e) => setGlobalFilter(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-spine-500 focus:border-spine-500 bg-white placeholder:text-gray-400"
              aria-label="Search table"
            />
          </div>
        </div>
      )}
      <div className="bg-white rounded-xl border border-gray-200/80 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50/80 text-left text-xs text-gray-500">
            {headerGroups.map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className={`px-5 py-3 font-medium ${header.column.getCanSort() ? 'cursor-pointer select-none hover:text-gray-700' : ''}`}
                    onClick={header.column.getToggleSortingHandler()}
                    aria-sort={
                      header.column.getIsSorted() === 'asc'
                        ? 'ascending'
                        : header.column.getIsSorted() === 'desc'
                          ? 'descending'
                          : 'none'
                    }
                  >
                    <span className="inline-flex items-center gap-1.5">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getCanSort() && (
                        <span className="text-gray-300">
                          {header.column.getIsSorted() === 'asc'
                            ? <ArrowUp size={12} className="text-spine-500" />
                            : header.column.getIsSorted() === 'desc'
                              ? <ArrowDown size={12} className="text-spine-500" />
                              : <ArrowUpDown size={12} />}
                        </span>
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-gray-100/80">
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="hover:bg-gray-50/50 transition-colors">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-5 py-3">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {footer && <div className="border-t border-gray-100 px-4 py-3">{footer}</div>}
      </div>
    </div>
  );
}
