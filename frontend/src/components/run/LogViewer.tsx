/**
 * Log viewer component for run execution logs.
 * Wraps @melloware/react-logviewer LazyLog with level filtering
 * and step-name badges.
 */

import { useState, useMemo } from 'react';
import { LazyLog } from '@melloware/react-logviewer';
import type { RunLogEntry } from '../../types/api';

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR'] as const;
type LogLevel = (typeof LOG_LEVELS)[number];

const LEVEL_COLORS: Record<LogLevel, string> = {
  DEBUG: 'bg-gray-100 text-gray-600',
  INFO: 'bg-blue-50 text-blue-700',
  WARN: 'bg-yellow-50 text-yellow-700',
  ERROR: 'bg-red-50 text-red-700',
};

interface LogViewerProps {
  /** Log entries from the API */
  logs: RunLogEntry[];
  /** Fixed height in pixels (default 400) */
  height?: number;
  /** Whether to auto-follow new lines */
  follow?: boolean;
  /** Loading state */
  loading?: boolean;
}

function formatLogLine(entry: RunLogEntry): string {
  const ts = entry.timestamp?.replace('T', ' ').replace('Z', '') ?? '';
  const level = (entry.level ?? 'INFO').padEnd(5);
  const step = entry.step_name ? `[${entry.step_name}]` : '';
  return `${ts} ${level} ${step} ${entry.message}`;
}

export default function LogViewer({
  logs,
  height = 400,
  follow: defaultFollow = true,
  loading = false,
}: LogViewerProps) {
  const [levelFilter, setLevelFilter] = useState<Set<LogLevel>>(new Set(LOG_LEVELS));
  const [stepFilter, setStepFilter] = useState<string>('');
  const [followMode, setFollowMode] = useState(defaultFollow);

  // Extract unique step names
  const stepNames = useMemo(() => {
    const names = new Set<string>();
    for (const l of logs) {
      if (l.step_name) names.add(l.step_name);
    }
    return Array.from(names).sort();
  }, [logs]);

  // Apply filters
  const filteredLogs = useMemo(() => {
    return logs.filter((l) => {
      const level = (l.level ?? 'INFO').toUpperCase() as LogLevel;
      if (!levelFilter.has(level)) return false;
      if (stepFilter && l.step_name !== stepFilter) return false;
      return true;
    });
  }, [logs, levelFilter, stepFilter]);

  // Convert to text for LazyLog
  const logText = useMemo(() => {
    if (filteredLogs.length === 0) return loading ? 'Loading logs...' : 'No log entries';
    return filteredLogs.map(formatLogLine).join('\n');
  }, [filteredLogs, loading]);

  const toggleLevel = (level: LogLevel) => {
    setLevelFilter((prev) => {
      const next = new Set(prev);
      if (next.has(level)) {
        next.delete(level);
      } else {
        next.add(level);
      }
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-gray-200 bg-gray-50 rounded-t-lg flex-wrap">
        {/* Level filter pills */}
        <div className="flex gap-1">
          {LOG_LEVELS.map((level) => (
            <button
              key={level}
              onClick={() => toggleLevel(level)}
              className={`text-[10px] px-2 py-0.5 rounded font-medium transition-all ${
                levelFilter.has(level)
                  ? LEVEL_COLORS[level]
                  : 'bg-gray-50 text-gray-300 line-through'
              }`}
            >
              {level}
            </button>
          ))}
        </div>

        {/* Step filter */}
        {stepNames.length > 1 && (
          <select
            value={stepFilter}
            onChange={(e) => setStepFilter(e.target.value)}
            className="text-xs border rounded px-2 py-0.5 bg-white"
          >
            <option value="">All Steps</option>
            {stepNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        )}

        {/* Follow toggle */}
        <button
          onClick={() => setFollowMode((f) => !f)}
          className={`ml-auto text-[10px] px-2 py-0.5 rounded font-medium transition-colors ${
            followMode
              ? 'bg-blue-50 text-blue-700'
              : 'bg-gray-100 text-gray-500'
          }`}
        >
          {followMode ? '⬇ Following' : '⏸ Paused'}
        </button>

        <span className="text-[10px] text-gray-400">
          {filteredLogs.length} / {logs.length} lines
        </span>
      </div>

      {/* Log content */}
      <div style={{ height }} className="bg-[#1e1e1e] rounded-b-lg overflow-hidden">
        <LazyLog
          text={logText}
          follow={followMode}
          enableSearch
          enableLineNumbers
          caseInsensitive
          wrapLines
          selectableLines
          height={height}
          extraLines={1}
          style={{
            fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
            fontSize: '12px',
          }}
        />
      </div>
    </div>
  );
}
