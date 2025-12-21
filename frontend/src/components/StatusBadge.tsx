import {
  CheckCircle2,
  XCircle,
  Play,
  Ban,
  Clock,
  AlertTriangle,
  RotateCw,
  Inbox,
  Pause,
  CircleDot,
  type LucideIcon,
} from 'lucide-react';

interface StatusConfig {
  icon: LucideIcon;
  bg: string;
  text: string;
  dot: string;
  animate?: boolean;
}

const STATUS_CONFIG: Record<string, StatusConfig> = {
  pending:        { icon: Clock,          bg: 'bg-gray-50',      text: 'text-gray-600',    dot: 'bg-gray-400' },
  queued:         { icon: Inbox,          bg: 'bg-yellow-50',    text: 'text-yellow-700',  dot: 'bg-yellow-500' },
  running:        { icon: Play,           bg: 'bg-blue-50',      text: 'text-blue-700',    dot: 'bg-blue-500', animate: true },
  completed:      { icon: CheckCircle2,   bg: 'bg-emerald-50',   text: 'text-emerald-700', dot: 'bg-emerald-500' },
  failed:         { icon: XCircle,        bg: 'bg-red-50',       text: 'text-red-700',     dot: 'bg-red-500' },
  cancelled:      { icon: Ban,            bg: 'bg-gray-50',      text: 'text-gray-500',    dot: 'bg-gray-400' },
  dead_lettered:  { icon: AlertTriangle,  bg: 'bg-orange-50',    text: 'text-orange-700',  dot: 'bg-orange-500' },
  retrying:       { icon: RotateCw,       bg: 'bg-purple-50',    text: 'text-purple-700',  dot: 'bg-purple-500', animate: true },
  started:        { icon: Play,           bg: 'bg-blue-50',      text: 'text-blue-700',    dot: 'bg-blue-500' },
  idle:           { icon: Pause,          bg: 'bg-gray-50',      text: 'text-gray-500',    dot: 'bg-gray-300' },
  healthy:        { icon: CheckCircle2,   bg: 'bg-emerald-50',   text: 'text-emerald-700', dot: 'bg-emerald-500' },
  degraded:       { icon: AlertTriangle,  bg: 'bg-yellow-50',    text: 'text-yellow-700',  dot: 'bg-yellow-500' },
  unhealthy:      { icon: XCircle,        bg: 'bg-red-50',       text: 'text-red-700',     dot: 'bg-red-500' },
  PASS:           { icon: CheckCircle2,   bg: 'bg-emerald-50',   text: 'text-emerald-700', dot: 'bg-emerald-500' },
  FAIL:           { icon: XCircle,        bg: 'bg-red-50',       text: 'text-red-700',     dot: 'bg-red-500' },
};

const DEFAULT_CONFIG: StatusConfig = {
  icon: CircleDot,
  bg: 'bg-gray-50',
  text: 'text-gray-500',
  dot: 'bg-gray-400',
};

interface StatusBadgeProps {
  status: string;
  /** 'default' shows icon+text pill, 'dot' shows just a colored dot, 'minimal' text only */
  variant?: 'default' | 'dot' | 'minimal';
  /** Compact size for table cells */
  size?: 'sm' | 'md';
}

export default function StatusBadge({ status, variant = 'default', size = 'sm' }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG[status?.toLowerCase()] ?? DEFAULT_CONFIG;
  const Icon = config.icon;
  const displayStatus = status?.replace('_', ' ') ?? 'unknown';

  if (variant === 'dot') {
    return (
      <span className="inline-flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${config.dot} ${config.animate ? 'animate-pulse' : ''}`} />
        <span className={`text-xs font-medium ${config.text}`}>{displayStatus}</span>
      </span>
    );
  }

  if (variant === 'minimal') {
    return (
      <span className={`text-xs font-medium ${config.text}`}>
        {displayStatus}
      </span>
    );
  }

  const sizeClasses = size === 'sm'
    ? 'px-2 py-0.5 text-xs gap-1'
    : 'px-2.5 py-1 text-sm gap-1.5';

  return (
    <span
      className={`inline-flex items-center ${sizeClasses} rounded-md font-medium ${config.bg} ${config.text} border border-current/10`}
    >
      <Icon size={size === 'sm' ? 12 : 14} className={config.animate ? 'animate-spin' : ''} />
      {displayStatus}
    </span>
  );
}
