/**
 * Empty State Component
 *
 * Shows a friendly message when there's no data to display,
 * with a clear call-to-action.
 */

import { Link } from 'react-router-dom';

interface EmptyStateProps {
  /** Icon or emoji to display */
  icon?: string;
  /** Main heading */
  title: string;
  /** Description text */
  description?: string;
  /** Primary action button */
  action?: {
    label: string;
    href?: string;
    onClick?: () => void;
  };
  /** Secondary action button */
  secondaryAction?: {
    label: string;
    href?: string;
    onClick?: () => void;
  };
  /** Additional CSS class */
  className?: string;
}

export function EmptyState({
  icon = '📭',
  title,
  description,
  action,
  secondaryAction,
  className = '',
}: EmptyStateProps) {
  return (
    <div
      className={`empty-state ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
        textAlign: 'center',
        minHeight: '200px',
      }}
    >
      <span style={{ fontSize: '48px', marginBottom: '16px' }}>{icon}</span>
      <h3
        style={{
          margin: '0 0 8px 0',
          fontSize: '1.25rem',
          fontWeight: 600,
          color: 'var(--text-primary)',
        }}
      >
        {title}
      </h3>
      {description && (
        <p
          style={{
            margin: '0 0 24px 0',
            color: 'var(--text-muted)',
            maxWidth: '400px',
          }}
        >
          {description}
        </p>
      )}
      <div style={{ display: 'flex', gap: '12px' }}>
        {action && (
          action.href ? (
            <Link
              to={action.href}
              style={{
                padding: '10px 20px',
                background: 'var(--accent-blue)',
                color: 'white',
                borderRadius: '6px',
                textDecoration: 'none',
                fontWeight: 500,
              }}
            >
              {action.label}
            </Link>
          ) : (
            <button
              onClick={action.onClick}
              style={{
                padding: '10px 20px',
                background: 'var(--accent-blue)',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              {action.label}
            </button>
          )
        )}
        {secondaryAction && (
          secondaryAction.href ? (
            <Link
              to={secondaryAction.href}
              style={{
                padding: '10px 20px',
                background: 'var(--bg-tertiary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                textDecoration: 'none',
                fontWeight: 500,
              }}
            >
              {secondaryAction.label}
            </Link>
          ) : (
            <button
              onClick={secondaryAction.onClick}
              style={{
                padding: '10px 20px',
                background: 'var(--bg-tertiary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              {secondaryAction.label}
            </button>
          )
        )}
      </div>
    </div>
  );
}

/**
 * Empty state specifically for when database has no data
 */
export function NoDataEmptyState({ dataType = 'data' }: { dataType?: string }) {
  return (
    <EmptyState
      icon="🗄️"
      title={`No ${dataType} yet`}
      description="Run a pipeline to load data from FINRA OTC transparency reports."
      action={{
        label: 'Go to Pipelines',
        href: '/dashboard/pipelines',
      }}
      secondaryAction={{
        label: 'View Documentation',
        href: '/dashboard/settings',
      }}
    />
  );
}

/**
 * Empty state for when a connection error occurred
 */
export function ConnectionErrorEmptyState({
  onRetry,
}: {
  onRetry?: () => void;
}) {
  return (
    <EmptyState
      icon="🔌"
      title="Connection Error"
      description="Unable to connect to the backend API. Make sure the server is running."
      action={
        onRetry
          ? { label: 'Retry', onClick: onRetry }
          : { label: 'Check Settings', href: '/dashboard/settings' }
      }
    />
  );
}

export default EmptyState;
