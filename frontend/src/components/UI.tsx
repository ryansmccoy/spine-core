import { AlertCircle, RefreshCw, Inbox, Loader2 } from 'lucide-react';

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
    green: 'border-l-emerald-500',
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
    <div className="flex items-center justify-center py-16">
      <Loader2 size={24} className="animate-spin text-spine-500" />
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
      <div className="flex items-start gap-3">
        <AlertCircle size={18} className="shrink-0 mt-0.5 text-red-500" />
        <div className="flex-1">
          <p className="font-medium">{message}</p>
          {detail && <p className="mt-1 text-xs text-red-600/80">{detail}</p>}
          {helpText && <p className="mt-2 text-xs text-red-500 italic">{helpText}</p>}
        </div>
        {onRetry && (
          <button 
            onClick={onRetry}
            className="ml-2 p-1.5 rounded-md text-red-500 hover:bg-red-100 transition-colors"
            title="Retry"
          >
            <RefreshCw size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ message, icon }: { message: string; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
      {icon ?? <Inbox size={40} className="mb-3 text-gray-300" />}
      <p className="text-sm">{message}</p>
    </div>
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
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'xs' | 'sm';
  disabled?: boolean;
  type?: 'button' | 'submit';
}) {
  const base = 'inline-flex items-center font-medium rounded-md transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-1';
  const sz = size === 'xs' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm';
  const variants: Record<string, string> = {
    primary:
      'bg-spine-600 text-white hover:bg-spine-700 active:bg-spine-800 focus:ring-spine-500 disabled:bg-spine-300 shadow-sm',
    secondary:
      'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 active:bg-gray-100 focus:ring-gray-400 shadow-sm',
    danger:
      'bg-red-600 text-white hover:bg-red-700 active:bg-red-800 focus:ring-red-500 disabled:bg-red-300 shadow-sm',
    ghost:
      'bg-transparent text-gray-600 hover:bg-gray-100 active:bg-gray-200 focus:ring-gray-400',
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
