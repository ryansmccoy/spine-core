/**
 * Status tabs with live run counts per status.
 * Replaces simple pill filters with rich, count-aware tabs.
 */

import type { RunStats } from '../api/hooks';

type StatusKey = '' | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

interface StatusTabConfig {
  key: StatusKey;
  label: string;
  color: string;
  activeColor: string;
  countKey?: keyof RunStats;
}

const STATUS_TABS: StatusTabConfig[] = [
  { key: '', label: 'All', color: 'text-gray-600', activeColor: 'bg-spine-600 text-white' },
  { key: 'pending', label: 'Pending', color: 'text-gray-500', activeColor: 'bg-gray-500 text-white', countKey: 'pending' },
  { key: 'running', label: 'Running', color: 'text-blue-600', activeColor: 'bg-blue-600 text-white', countKey: 'running' },
  { key: 'completed', label: 'Completed', color: 'text-green-600', activeColor: 'bg-green-600 text-white', countKey: 'completed' },
  { key: 'failed', label: 'Failed', color: 'text-red-600', activeColor: 'bg-red-600 text-white', countKey: 'failed' },
  { key: 'cancelled', label: 'Cancelled', color: 'text-gray-400', activeColor: 'bg-gray-400 text-white', countKey: 'cancelled' },
];

interface StatusTabsProps {
  /** Currently active status filter */
  value: string;
  /** Called when user selects a tab */
  onChange: (status: string) => void;
  /** Live run stats for count badges */
  stats?: RunStats | null;
}

export default function StatusTabs({ value, onChange, stats }: StatusTabsProps) {
  const totalCount = stats ? stats.total : undefined;

  return (
    <div className="flex gap-1 bg-gray-50 rounded-lg p-1">
      {STATUS_TABS.map((tab) => {
        const isActive = value === tab.key;
        const count = tab.key === ''
          ? totalCount
          : (tab.countKey && stats ? stats[tab.countKey] : undefined);

        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`
              relative flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium
              transition-all duration-150
              ${isActive
                ? `${tab.activeColor} shadow-sm`
                : `bg-transparent ${tab.color} hover:bg-gray-100`}
            `}
          >
            {tab.label}
            {count !== undefined && count > 0 && (
              <span
                className={`
                  inline-flex items-center justify-center min-w-[18px] h-[18px] px-1
                  rounded-full text-[10px] font-semibold leading-none
                  ${isActive
                    ? 'bg-white/25 text-current'
                    : 'bg-gray-200 text-gray-600'}
                `}
              >
                {count > 999 ? '999+' : count}
              </span>
            )}
            {/* Pulse indicator for running tab when active */}
            {tab.key === 'running' && count !== undefined && count > 0 && !isActive && (
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
            )}
          </button>
        );
      })}
    </div>
  );
}
