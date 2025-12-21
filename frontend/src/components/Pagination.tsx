import { Button } from './UI';

interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
}

/**
 * Pagination controls with prev/next and page metadata.
 * Driven by PagedResponse.page envelope.
 */
export default function Pagination({ total, limit, offset, onPageChange }: PaginationProps) {
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  if (total <= limit) {
    return (
      <div className="px-4 py-2 text-xs text-gray-400 border-t">
        Showing {total} item{total !== 1 ? 's' : ''}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between px-4 py-2 border-t text-xs text-gray-500">
      <span>
        Showing {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="xs"
          disabled={!hasPrev}
          onClick={() => onPageChange(Math.max(0, offset - limit))}
        >
          ← Prev
        </Button>
        <span className="text-gray-400">
          Page {currentPage} of {totalPages}
        </span>
        <Button
          variant="secondary"
          size="xs"
          disabled={!hasNext}
          onClick={() => onPageChange(offset + limit)}
        >
          Next →
        </Button>
      </div>
    </div>
  );
}
