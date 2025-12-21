import { useState } from 'react';
import type { RunEvent } from '../types/api';

function formatTs(ts: string | null | undefined): string {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return ts; }
}

interface EventTimelineProps {
  events: RunEvent[];
  isLoading?: boolean;
}

/**
 * Vertical event timeline with colored dots, timestamps, and expandable data.
 * Color coding: error=red, success=green, default=spine blue.
 */
export default function EventTimeline({ events, isLoading }: EventTimelineProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (isLoading) {
    return <div className="text-sm text-gray-400 py-4">Loading events…</div>;
  }

  if (!events.length) {
    return <div className="text-sm text-gray-400 py-4">No events recorded</div>;
  }

  return (
    <div className="relative">
      {/* Timeline line */}
      <div className="absolute left-[7px] top-3 bottom-3 w-0.5 bg-gray-200" />
      <div className="space-y-0">
        {events.map((e, i) => {
          const isError =
            e.event_type?.toLowerCase().includes('fail') ||
            e.event_type?.toLowerCase().includes('error');
          const isSuccess =
            e.event_type?.toLowerCase().includes('complet') ||
            e.event_type?.toLowerCase().includes('success');
          const dotColor = isError
            ? 'bg-red-500'
            : isSuccess
              ? 'bg-green-500'
              : 'bg-spine-400';
          const hasData = e.data && Object.keys(e.data).length > 0;
          const isExpanded = expandedId === (e.event_id || String(i));

          return (
            <div key={e.event_id || i} className="flex items-start gap-3 py-2.5 relative">
              <div
                className={`w-3.5 h-3.5 mt-0.5 rounded-full ${dotColor} shrink-0 z-10 ring-2 ring-white`}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-semibold text-gray-800">
                    {e.event_type}
                  </span>
                  <span className="text-[10px] text-gray-400">
                    {formatTs(e.timestamp)}
                  </span>
                  {hasData && (
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : (e.event_id || String(i)))}
                      className="text-[10px] text-spine-500 hover:text-spine-700"
                    >
                      {isExpanded ? '▾ collapse' : '▸ details'}
                    </button>
                  )}
                </div>
                {e.message && (
                  <p className="text-xs text-gray-600">{e.message}</p>
                )}
                {isExpanded && hasData && (
                  <pre className="text-[10px] text-gray-400 mt-1 bg-gray-50 rounded p-1.5 overflow-x-auto">
                    {JSON.stringify(e.data, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
