export function Card({
  title,
  value,
  subtitle,
  color = 'blue',
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  color?: 'blue' | 'green' | 'red' | 'yellow' | 'gray';
}) {
  const ring: Record<string, string> = {
    blue: 'border-l-spine-500',
    green: 'border-l-green-500',
    red: 'border-l-red-500',
    yellow: 'border-l-yellow-500',
    gray: 'border-l-gray-400',
  };
  return (
    <div
      className={`bg-white rounded-lg shadow-sm border border-gray-200 border-l-4 ${ring[color]} p-4`}
    >
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        {title}
      </p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
      {subtitle && (
        <p className="mt-0.5 text-xs text-gray-400">{subtitle}</p>
      )}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-spine-200 border-t-spine-600" />
    </div>
  );
}

export function ErrorBox({ 
  message, 
  detail, 
  onRetry 
}: { 
  message: string; 
  detail?: string;
  onRetry?: () => void;
}) {
  const isDbError = detail?.includes('no such table') || message?.includes('no such table');
  const isNetworkError = detail?.includes('NetworkError') || detail?.includes('Failed to fetch');
  
  let helpText = '';
  if (isDbError) {
    helpText = 'Database not initialized. Try: POST /api/v1/database/init';
  } else if (isNetworkError) {
    helpText = 'Cannot connect to API. Is the server running?';
  }

  return (
    <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-medium">{message}</p>
          {detail && <p className="mt-1 text-xs text-red-600">{detail}</p>}
          {helpText && <p className="mt-2 text-xs text-red-500 italic">{helpText}</p>}
        </div>
        {onRetry && (
          <button 
            onClick={onRetry}
            className="ml-4 px-2 py-1 text-xs bg-red-100 hover:bg-red-200 rounded transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-12 text-gray-400 text-sm">{message}</div>
  );
}

export function Button({
  children,
  onClick,
  variant = 'primary',
  size = 'sm',
  disabled = false,
  type = 'button',
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  size?: 'xs' | 'sm';
  disabled?: boolean;
  type?: 'button' | 'submit';
}) {
  const base = 'inline-flex items-center font-medium rounded transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1';
  const sz = size === 'xs' ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm';
  const variants: Record<string, string> = {
    primary:
      'bg-spine-600 text-white hover:bg-spine-700 focus:ring-spine-500 disabled:bg-spine-300',
    secondary:
      'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 focus:ring-gray-400',
    danger:
      'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 disabled:bg-red-300',
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${sz} ${variants[variant]}`}
    >
      {children}
    </button>
  );
}

/** Reusable modal overlay. */
export function Modal({
  title,
  children,
  onClose,
  maxWidth = 'max-w-lg',
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  maxWidth?: string;
}) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`bg-white rounded-xl shadow-xl w-full ${maxWidth} max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h3 className="text-lg font-bold text-gray-900">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>
        <div className="px-6 py-4">{children}</div>
      </div>
    </div>
  );
}

/** Key-value detail row used in detail modals and pages. */
export function DetailRow({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start py-2 border-b border-gray-50 last:border-0">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide w-32 shrink-0 pt-0.5">{label}</span>
      <span className={`text-sm text-gray-900 ${mono ? 'font-mono text-xs' : ''}`}>{value || '—'}</span>
    </div>
  );
}

/** JSON viewer with collapsible detail. */
export function JsonBlock({ data, label }: { data: unknown; label?: string }) {
  if (!data || (typeof data === 'object' && Object.keys(data as object).length === 0)) return null;
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5 mb-6">
      {label && <h3 className="text-sm font-medium text-gray-700 mb-2">{label}</h3>}
      <pre className="text-xs bg-gray-50 rounded p-3 overflow-x-auto whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
