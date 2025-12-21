import { useState } from 'react';

interface JsonViewerProps {
  data: unknown;
  label?: string;
  defaultExpanded?: boolean;
  maxHeight?: string;
}

/**
 * Collapsible JSON viewer with syntax highlighting.
 * Replaces the static JsonBlock for interactive inspection.
 */
export default function JsonViewer({
  data,
  label,
  defaultExpanded = false,
  maxHeight = 'max-h-64',
}: JsonViewerProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  if (!data || (typeof data === 'object' && Object.keys(data as object).length === 0)) {
    if (!label) return null;
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <h3 className="text-sm font-medium text-gray-700">{label}</h3>
        <p className="text-xs text-gray-400 mt-1">Empty</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm font-medium text-gray-700 w-full text-left"
      >
        <span className="text-xs text-gray-400">{expanded ? '▾' : '▸'}</span>
        {label || 'JSON'}
        <span className="text-xs text-gray-400 font-normal">
          {typeof data === 'object' && data !== null
            ? `${Object.keys(data).length} key${Object.keys(data).length !== 1 ? 's' : ''}`
            : typeof data}
        </span>
      </button>
      {expanded && (
        <pre
          className={`text-xs bg-gray-50 rounded p-3 mt-2 overflow-x-auto whitespace-pre-wrap break-words ${maxHeight} overflow-y-auto`}
        >
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
