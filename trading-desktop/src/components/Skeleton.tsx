/**
 * Loading Skeleton Components
 *
 * Placeholder UI elements that pulse while content is loading.
 * Provides better perceived performance than spinners.
 */

import './Skeleton.css';

interface SkeletonProps {
  /** Width of the skeleton (default: 100%) */
  width?: string | number;
  /** Height of the skeleton (default: 1em) */
  height?: string | number;
  /** Border radius (default: 4px) */
  borderRadius?: string | number;
  /** Additional CSS class */
  className?: string;
}

/**
 * Basic skeleton element - a pulsing placeholder
 */
export function Skeleton({
  width = '100%',
  height = '1em',
  borderRadius = '4px',
  className = '',
}: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
        borderRadius: typeof borderRadius === 'number' ? `${borderRadius}px` : borderRadius,
      }}
    />
  );
}

/**
 * Skeleton for text content - multiple lines
 */
export function SkeletonText({
  lines = 3,
  className = '',
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`skeleton-text ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          width={i === lines - 1 ? '60%' : '100%'}
          height="0.875em"
          className="skeleton-line"
        />
      ))}
    </div>
  );
}

/**
 * Skeleton for a table row
 */
export function SkeletonTableRow({
  columns = 4,
  className = '',
}: {
  columns?: number;
  className?: string;
}) {
  return (
    <tr className={`skeleton-table-row ${className}`}>
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i}>
          <Skeleton height="1em" width={i === 0 ? '80%' : '60%'} />
        </td>
      ))}
    </tr>
  );
}

/**
 * Skeleton for a data table with header
 */
export function SkeletonTable({
  rows = 5,
  columns = 4,
  className = '',
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <table className={`skeleton-table ${className}`}>
      <thead>
        <tr>
          {Array.from({ length: columns }).map((_, i) => (
            <th key={i}>
              <Skeleton height="1em" width="70%" />
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {Array.from({ length: rows }).map((_, i) => (
          <SkeletonTableRow key={i} columns={columns} />
        ))}
      </tbody>
    </table>
  );
}

/**
 * Skeleton for a card/panel
 */
export function SkeletonCard({
  hasHeader = true,
  lines = 3,
  className = '',
}: {
  hasHeader?: boolean;
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`skeleton-card ${className}`}>
      {hasHeader && (
        <div className="skeleton-card-header">
          <Skeleton width="40%" height="1.25em" />
        </div>
      )}
      <div className="skeleton-card-body">
        <SkeletonText lines={lines} />
      </div>
    </div>
  );
}

/**
 * Skeleton for widget content
 */
export function SkeletonWidget({
  type = 'list',
  className = '',
}: {
  type?: 'list' | 'chart' | 'stats';
  className?: string;
}) {
  if (type === 'chart') {
    return (
      <div className={`skeleton-widget skeleton-chart ${className}`}>
        <Skeleton height="200px" borderRadius="8px" />
      </div>
    );
  }

  if (type === 'stats') {
    return (
      <div className={`skeleton-widget skeleton-stats ${className}`}>
        <div className="skeleton-stat-row">
          <Skeleton width="30%" height="2em" />
          <Skeleton width="20%" height="1.5em" />
        </div>
        <div className="skeleton-stat-row">
          <Skeleton width="40%" height="2em" />
          <Skeleton width="25%" height="1.5em" />
        </div>
        <div className="skeleton-stat-row">
          <Skeleton width="35%" height="2em" />
          <Skeleton width="15%" height="1.5em" />
        </div>
      </div>
    );
  }

  // Default: list type
  return (
    <div className={`skeleton-widget skeleton-list ${className}`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="skeleton-list-item">
          <Skeleton width="60%" height="1em" />
          <Skeleton width="30%" height="0.875em" />
        </div>
      ))}
    </div>
  );
}

export default Skeleton;
